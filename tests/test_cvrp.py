"""Unit tests for Capacitated Vehicle Routing Problem (CVRP) tactical optimization.
"""

import pytest
from core.models import Neighborhood, WarehouseCandidate
from routing.matrix import NetworkMatrix
from optimization.cvrp import solve_cvrp_for_warehouse


def test_cvrp_vehicle_capacity_strictly_respected():
    """Validates that every active delivery route respects the vehicle capacity constraint."""
    warehouse = WarehouseCandidate(id="W1", name="Central Depot", latitude=12.97, longitude=77.59, capacity=5000)
    neighborhoods = [
        Neighborhood(id="N1", name="Stop A", latitude=12.98, longitude=77.60, daily_orders=80),
        Neighborhood(id="N2", name="Stop B", latitude=12.96, longitude=77.58, daily_orders=90),
        Neighborhood(id="N3", name="Stop C", latitude=12.95, longitude=77.61, daily_orders=70),
        Neighborhood(id="N4", name="Stop D", latitude=12.99, longitude=77.57, daily_orders=60),
    ]

    all_ids = ["W1", "N1", "N2", "N3", "N4"]
    dist_map = {i: {j: (0.0 if i == j else 5.0) for j in all_ids} for i in all_ids}
    dur_map = {i: {j: (0.0 if i == j else 15.0) for j in all_ids} for i in all_ids}
    dur_hrs = {i: {j: (0.0 if i == j else 0.25) for j in all_ids} for i in all_ids}

    matrix = NetworkMatrix(
        neighborhood_ids=all_ids,
        distances_km=dist_map,
        durations_min=dur_map,
        durations_hours=dur_hrs,
        mode="DEMO",
    )

    # Vehicle capacity = 150 (Total demand is 300, requires at least 2 vehicles)
    v_cap = 150
    res = solve_cvrp_for_warehouse(
        warehouse=warehouse,
        assigned_neighborhoods=neighborhoods,
        network_matrix=matrix,
        vehicle_capacity=v_cap,
        time_limit_seconds=2,
    )

    assert res.vehicles_used >= 2
    assert len(res.routes) == res.vehicles_used

    # Check each route's payload
    visited_stops = set()
    for r in res.routes:
        assert r.total_load <= v_cap, f"Route exceeded vehicle capacity: {r.total_load} > {v_cap}"
        assert r.utilization <= 1.0
        visited_stops.update(r.stop_ids)

    # All customer stops were visited
    assert visited_stops == {"N1", "N2", "N3", "N4"}


def test_cvrp_demand_splitting_on_large_stop():
    """Validates that a single neighborhood with demand greater than vehicle capacity is split without crashing."""
    warehouse = WarehouseCandidate(id="W1", name="Central Depot", latitude=12.97, longitude=77.59, capacity=5000)
    # Stop has 320 orders, but vehicle capacity is only 200
    neighborhoods = [
        Neighborhood(id="N1", name="Mega Cluster", latitude=12.98, longitude=77.60, daily_orders=320),
    ]

    all_ids = ["W1", "N1"]
    dist_map = {i: {j: (0.0 if i == j else 5.0) for j in all_ids} for i in all_ids}
    dur_map = {i: {j: (0.0 if i == j else 15.0) for j in all_ids} for i in all_ids}
    dur_hrs = {i: {j: (0.0 if i == j else 0.25) for j in all_ids} for i in all_ids}

    matrix = NetworkMatrix(
        neighborhood_ids=all_ids,
        distances_km=dist_map,
        durations_min=dur_map,
        durations_hours=dur_hrs,
        mode="DEMO",
    )

    v_cap = 200
    res = solve_cvrp_for_warehouse(
        warehouse=warehouse,
        assigned_neighborhoods=neighborhoods,
        network_matrix=matrix,
        vehicle_capacity=v_cap,
        time_limit_seconds=2,
    )

    # Must use 2 vehicles to serve 320 orders with 200 capacity
    assert res.vehicles_used == 2
    for r in res.routes:
        assert r.total_load <= v_cap
    assert sum(r.total_load for r in res.routes) == 320
