"""Baseline network simulation: Single-Warehouse Reference Baseline and Historical Baseline.
"""

from typing import List, Dict, Optional, Tuple
import pandas as pd
from core.models import (
    Neighborhood,
    WarehouseCandidate,
    CFLPResult,
    CVRPWarehouseResult,
    CostBreakdown,
    SystemSummary,
)
from routing.matrix import NetworkMatrix
from routing.osrm import OSRMClient
from optimization.cvrp import solve_cvrp_for_warehouse
from core.metrics import compute_delivery_cost


def evaluate_single_warehouse_baseline(
    neighborhoods: List[Neighborhood],
    candidates: List[WarehouseCandidate],
    network_matrix: NetworkMatrix,
    vehicle_capacity: int,
    cost_per_km: float,
    cost_per_hour: float,
    fixed_vehicle_cost: float,
    service_radius_min: float,
    cvrp_time_limit_sec: int = 5,
    osrm_client: Optional[OSRMClient] = None,
) -> SystemSummary:
    """Evaluates the Single-Warehouse Reference Baseline.

    Finds the candidate site that minimizes total order-weighted travel time when serving
    the entire network. Evaluates actual tactical delivery routes using the identical CVRP engine.
    """
    demands = {n.id: float(n.daily_orders) for n in neighborhoods}
    total_demand = sum(demands.values())

    # Find the best single candidate (1-median center)
    best_candidate: Optional[WarehouseCandidate] = None
    min_weighted_time = float("inf")

    for cand in candidates:
        weighted_time = sum(
            demands[nid] * network_matrix.durations_min.get(cand.id, {}).get(nid, 0.0)
            for nid in demands
        )
        if weighted_time < min_weighted_time:
            min_weighted_time = weighted_time
            best_candidate = cand

    if best_candidate is None and candidates:
        best_candidate = candidates[0]
        min_weighted_time = 0.0

    # Configure baseline depot
    baseline_warehouse = WarehouseCandidate(
        id=best_candidate.id,
        name=best_candidate.name,
        latitude=best_candidate.latitude,
        longitude=best_candidate.longitude,
        capacity=max(best_candidate.capacity, total_demand),
        is_open=True,
        assigned_neighborhood_ids=[n.id for n in neighborhoods],
        total_assigned_demand=total_demand,
    )

    # Assignments
    assignments = {n.id: baseline_warehouse.id for n in neighborhoods}

    cflp_result = CFLPResult(
        status="Reference Baseline",
        solver_message="Best single candidate warehouse (1-median reference benchmark)",
        is_optimal=True,
        open_warehouse_ids=[baseline_warehouse.id],
        assignments=assignments,
        weighted_strategic_travel_time=min_weighted_time,
        solve_time_seconds=0.01,
        diagnostics=[],
    )

    # Route entire network through CVRP engine
    cvrp_result = solve_cvrp_for_warehouse(
        warehouse=baseline_warehouse,
        assigned_neighborhoods=neighborhoods,
        network_matrix=network_matrix,
        vehicle_capacity=vehicle_capacity,
        time_limit_seconds=cvrp_time_limit_sec,
        osrm_client=osrm_client,
    )

    cost_breakdown = compute_delivery_cost(
        total_distance_km=cvrp_result.total_distance_km,
        total_duration_hours=cvrp_result.total_duration_hours,
        vehicles_used=cvrp_result.vehicles_used,
        cost_per_km=cost_per_km,
        cost_per_hour=cost_per_hour,
        fixed_vehicle_cost=fixed_vehicle_cost,
        vehicle_capacity=vehicle_capacity,
        service_radius_min=service_radius_min,
    )

    return SystemSummary(
        mode_label="Single-Warehouse Reference Baseline",
        warehouses_open_count=1,
        open_warehouses=[baseline_warehouse],
        assignments=assignments,
        cflp_result=cflp_result,
        cvrp_results={baseline_warehouse.id: cvrp_result},
        total_distance_km=cvrp_result.total_distance_km,
        total_duration_hours=cvrp_result.total_duration_hours,
        vehicles_used=cvrp_result.vehicles_used,
        avg_load_utilization=cvrp_result.avg_load_utilization,
        weighted_strategic_travel_time=min_weighted_time,
        cost_breakdown=cost_breakdown,
    )


def evaluate_custom_baseline(
    baseline_df: pd.DataFrame,
    neighborhoods: List[Neighborhood],
    network_matrix: NetworkMatrix,
    vehicle_capacity: int,
    cost_per_km: float,
    cost_per_hour: float,
    fixed_vehicle_cost: float,
    service_radius_min: float,
    cvrp_time_limit_sec: int = 5,
    osrm_client: Optional[OSRMClient] = None,
) -> SystemSummary:
    """Evaluates user-supplied historical baseline warehouse locations."""
    # Build warehouse objects from custom CSV
    warehouses: List[WarehouseCandidate] = []
    for _, row in baseline_df.iterrows():
        wid = str(row.get("warehouse_id", row.get("id", f"W_{len(warehouses)+1}"))).strip()
        wname = str(row.get("name", wid)).strip()
        wlat = float(row["latitude"])
        wlon = float(row["longitude"])
        wcap = float(row.get("capacity", 999999))
        warehouses.append(
            WarehouseCandidate(
                id=wid,
                name=wname,
                latitude=wlat,
                longitude=wlon,
                capacity=wcap,
                is_open=True,
            )
        )

    # Assign each neighborhood to closest warehouse by duration
    n_map = {n.id: n for n in neighborhoods}
    assignments: Dict[str, str] = {}
    total_weighted_time = 0.0

    for n in neighborhoods:
        # Closest warehouse
        best_w = warehouses[0]
        min_dur = float("inf")
        for w in warehouses:
            dur = network_matrix.durations_min.get(w.id, {}).get(n.id)
            if dur is None:
                # Estimate distance
                lat1, lon1 = w.latitude, w.longitude
                lat2, lon2 = n.latitude, n.longitude
                dur = (OSRMClient._haversine_meters(lat1, lon1, lat2, lon2) * 1.35 / 1000.0 / 24.0) * 60.0

            if dur < min_dur:
                min_dur = dur
                best_w = w

        assignments[n.id] = best_w.id
        best_w.assigned_neighborhood_ids.append(n.id)
        best_w.total_assigned_demand += n.daily_orders
        total_weighted_time += n.daily_orders * min_dur

    cflp_result = CFLPResult(
        status="Historical Baseline",
        solver_message="Historical multi-warehouse setup",
        is_optimal=True,
        open_warehouse_ids=[w.id for w in warehouses if w.assigned_neighborhood_ids],
        assignments=assignments,
        weighted_strategic_travel_time=total_weighted_time,
        solve_time_seconds=0.01,
        diagnostics=[],
    )

    # Run CVRP per warehouse
    cvrp_results: Dict[str, CVRPWarehouseResult] = {}
    tot_km = 0.0
    tot_hrs = 0.0
    tot_veh = 0
    util_sums = 0.0

    for w in warehouses:
        if not w.assigned_neighborhood_ids:
            continue
        assigned_n = [n_map[nid] for nid in w.assigned_neighborhood_ids]
        res = solve_cvrp_for_warehouse(
            warehouse=w,
            assigned_neighborhoods=assigned_n,
            network_matrix=network_matrix,
            vehicle_capacity=vehicle_capacity,
            time_limit_seconds=cvrp_time_limit_sec,
            osrm_client=osrm_client,
        )
        cvrp_results[w.id] = res
        tot_km += res.total_distance_km
        tot_hrs += res.total_duration_hours
        tot_veh += res.vehicles_used
        util_sums += res.avg_load_utilization * res.vehicles_used

    avg_util = (util_sums / tot_veh) if tot_veh > 0 else 0.0

    cost_breakdown = compute_delivery_cost(
        total_distance_km=tot_km,
        total_duration_hours=tot_hrs,
        vehicles_used=tot_veh,
        cost_per_km=cost_per_km,
        cost_per_hour=cost_per_hour,
        fixed_vehicle_cost=fixed_vehicle_cost,
        vehicle_capacity=vehicle_capacity,
        service_radius_min=service_radius_min,
    )

    return SystemSummary(
        mode_label="Historical Baseline (Uploaded)",
        warehouses_open_count=len([w for w in warehouses if w.assigned_neighborhood_ids]),
        open_warehouses=[w for w in warehouses if w.assigned_neighborhood_ids],
        assignments=assignments,
        cflp_result=cflp_result,
        cvrp_results=cvrp_results,
        total_distance_km=round(tot_km, 2),
        total_duration_hours=round(tot_hrs, 2),
        vehicles_used=tot_veh,
        avg_load_utilization=round(avg_util, 4),
        weighted_strategic_travel_time=round(total_weighted_time, 2),
        cost_breakdown=cost_breakdown,
    )
