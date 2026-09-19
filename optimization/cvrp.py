"""Tactical delivery routing using Google OR-Tools Capacitated Vehicle Routing Problem (CVRP).
"""

import math
import logging
from typing import List, Dict, Tuple, Optional
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from core.models import Neighborhood, WarehouseCandidate, VehicleRoute, CVRPWarehouseResult
from routing.matrix import NetworkMatrix
from routing.osrm import OSRMClient

logger = logging.getLogger(__name__)


def solve_cvrp_for_warehouse(
    warehouse: WarehouseCandidate,
    assigned_neighborhoods: List[Neighborhood],
    network_matrix: NetworkMatrix,
    vehicle_capacity: int,
    time_limit_seconds: int = 5,
    vehicle_buffer: int = 2,
    fetch_road_geometry: bool = False,
    osrm_client: Optional[OSRMClient] = None,
) -> CVRPWarehouseResult:
    """Solves CVRP for a single opened warehouse and its assigned customer neighborhoods.

    Returns:
        CVRPWarehouseResult with optimized vehicle routes, vehicle counts, and utilization.
    """
    if not assigned_neighborhoods:
        return CVRPWarehouseResult(
            warehouse_id=warehouse.id,
            routes=[],
            total_distance_km=0.0,
            total_duration_hours=0.0,
            vehicles_used=0,
            avg_load_utilization=0.0,
            total_demand_routed=0.0,
        )

    # 1. Virtual demand splitting for orders exceeding vehicle capacity
    node_parent_ids: List[str] = [warehouse.id]  # Index 0 is the depot
    node_names: List[str] = [f"Depot ({warehouse.name})"]
    node_demands: List[float] = [0.0]
    node_coords: List[Tuple[float, float]] = [(warehouse.latitude, warehouse.longitude)]

    for n in assigned_neighborhoods:
        dem = float(n.daily_orders)
        if dem <= vehicle_capacity or vehicle_capacity <= 0:
            node_parent_ids.append(n.id)
            node_names.append(n.name)
            node_demands.append(dem)
            node_coords.append((n.latitude, n.longitude))
        else:
            # Split into chunks of size vehicle_capacity + remainder
            remaining = dem
            chunk_num = 1
            while remaining > 0:
                chunk_demand = min(remaining, float(vehicle_capacity))
                node_parent_ids.append(n.id)
                node_names.append(f"{n.name} (Drop {chunk_num})")
                node_demands.append(chunk_demand)
                node_coords.append((n.latitude, n.longitude))
                remaining -= chunk_demand
                chunk_num += 1

    num_nodes = len(node_parent_ids)
    total_demand = sum(node_demands)

    # 2. Build upper-bound fleet size
    min_vehicles = max(1, math.ceil(total_demand / vehicle_capacity)) if vehicle_capacity > 0 else 1
    buffer = max(vehicle_buffer, int(min_vehicles * 0.20) + 1)
    num_vehicles = min_vehicles + buffer

    # 3. Build submatrix for nodes
    dist_sub = [[0.0] * num_nodes for _ in range(num_nodes)]
    dur_sub = [[0.0] * num_nodes for _ in range(num_nodes)]

    for i in range(num_nodes):
        id_i = node_parent_ids[i]
        for j in range(num_nodes):
            id_j = node_parent_ids[j]
            if i == j:
                dist_sub[i][j] = 0.0
                dur_sub[i][j] = 0.0
            else:
                d = network_matrix.distances_km.get(id_i, {}).get(id_j, 0.0)
                t = network_matrix.durations_hours.get(id_i, {}).get(id_j, 0.0)
                dist_sub[i][j] = d
                dur_sub[i][j] = t

    # 4. OR-Tools Routing Index Manager & Model
    manager = pywrapcp.RoutingIndexManager(num_nodes, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Distance Transit Callback (scaled to integer meters)
    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(dist_sub[from_node][to_node] * 1000)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    routing.SetFixedCostOfAllVehicles(50000)

    # Capacity Dimension
    def demand_callback(from_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        return int(node_demands[from_node])

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        [int(vehicle_capacity)] * num_vehicles,
        True,  # start cumul to zero
        "Capacity",
    )

    # 5. Search Parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(time_limit_seconds)

    # 6. Solve CVRP
    solution = routing.SolveWithParameters(search_parameters)

    # 7. Extract Active Routes
    active_routes: List[VehicleRoute] = []
    total_km = 0.0
    total_hours = 0.0

    if solution:
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route_stops: List[str] = []
            route_names: List[str] = []
            route_demands: List[float] = []
            route_coords: List[Tuple[float, float]] = [node_coords[0]]
            route_dist_km = 0.0
            route_dur_hours = 0.0
            route_load = 0.0

            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                if node_index != 0:
                    route_stops.append(node_parent_ids[node_index])
                    route_names.append(node_names[node_index])
                    route_demands.append(node_demands[node_index])
                    route_coords.append(node_coords[node_index])
                    route_load += node_demands[node_index]

                previous_index = index
                index = solution.Value(routing.NextVar(index))
                next_node = manager.IndexToNode(index)
                route_dist_km += dist_sub[node_index][next_node]
                route_dur_hours += dur_sub[node_index][next_node]

            # Append return to depot
            route_coords.append(node_coords[0])

            if route_stops:
                # Optionally fetch detailed road geometry via OSRM Route service
                road_geometry = route_coords
                if fetch_road_geometry and osrm_client is not None:
                    try:
                        road_geometry = osrm_client.get_route_geometry(route_coords)
                    except Exception:
                        road_geometry = route_coords

                active_routes.append(
                    VehicleRoute(
                        warehouse_id=warehouse.id,
                        vehicle_index=len(active_routes) + 1,
                        stop_ids=route_stops,
                        stop_names=route_names,
                        stop_demands=route_demands,
                        total_load=route_load,
                        capacity=float(vehicle_capacity),
                        distance_km=round(route_dist_km, 2),
                        duration_hours=round(route_dur_hours, 2),
                        route_coords=road_geometry,
                    )
                )
                total_km += route_dist_km
                total_hours += route_dur_hours
    else:
        # Fallback greedy dispatch heuristic if OR-Tools cannot find solution within time limit
        logger.warning(f"OR-Tools found no feasible CVRP solution for warehouse {warehouse.id}. Using nearest neighbor fallback.")
        active_routes, total_km, total_hours = _fallback_greedy_cvrp(
            warehouse, assigned_neighborhoods, dist_sub, dur_sub, node_parent_ids, node_names, node_demands, node_coords, vehicle_capacity
        )

    vehicles_used = len(active_routes)
    avg_utilization = (
        sum(r.utilization for r in active_routes) / vehicles_used if vehicles_used > 0 else 0.0
    )

    return CVRPWarehouseResult(
        warehouse_id=warehouse.id,
        routes=active_routes,
        total_distance_km=round(total_km, 2),
        total_duration_hours=round(total_hours, 2),
        vehicles_used=vehicles_used,
        avg_load_utilization=round(avg_utilization, 4),
        total_demand_routed=total_demand,
    )


def _fallback_greedy_cvrp(
    warehouse: WarehouseCandidate,
    assigned_neighborhoods: List[Neighborhood],
    dist_sub: List[List[float]],
    dur_sub: List[List[float]],
    node_parent_ids: List[str],
    node_names: List[str],
    node_demands: List[float],
    node_coords: List[Tuple[float, float]],
    vehicle_capacity: int,
) -> Tuple[List[VehicleRoute], float, float]:
    """Greedy vehicle dispatch fallback for edge cases."""
    unvisited = list(range(1, len(node_parent_ids)))
    routes: List[VehicleRoute] = []
    total_km = 0.0
    total_hours = 0.0

    while unvisited:
        current_node = 0
        current_load = 0.0
        route_stops = []
        route_names_list = []
        route_demands_list = []
        route_coords = [node_coords[0]]
        route_dist = 0.0
        route_dur = 0.0

        while True:
            # Find nearest feasible unvisited node
            feasible_candidates = [
                n for n in unvisited if (current_load + node_demands[n]) <= vehicle_capacity
            ]
            if not feasible_candidates:
                break

            # Nearest neighbor
            next_node = min(feasible_candidates, key=lambda n: dist_sub[current_node][n])
            unvisited.remove(next_node)
            route_stops.append(node_parent_ids[next_node])
            route_names_list.append(node_names[next_node])
            route_demands_list.append(node_demands[next_node])
            route_coords.append(node_coords[next_node])
            current_load += node_demands[next_node]

            route_dist += dist_sub[current_node][next_node]
            route_dur += dur_sub[current_node][next_node]
            current_node = next_node

        # Return to depot
        route_dist += dist_sub[current_node][0]
        route_dur += dur_sub[current_node][0]
        route_coords.append(node_coords[0])

        routes.append(
            VehicleRoute(
                warehouse_id=warehouse.id,
                vehicle_index=len(routes) + 1,
                stop_ids=route_stops,
                stop_names=route_names_list,
                stop_demands=route_demands_list,
                total_load=current_load,
                capacity=float(vehicle_capacity),
                distance_km=round(route_dist, 2),
                duration_hours=round(route_dur, 2),
                route_coords=route_coords,
            )
        )
        total_km += route_dist
        total_hours += route_dur

    return routes, total_km, total_hours
