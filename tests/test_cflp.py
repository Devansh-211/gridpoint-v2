"""Unit tests for Capacitated Facility Location Problem (CFLP) strategic optimization.
"""

import pytest
from core.models import Neighborhood, WarehouseCandidate
from optimization.cflp import solve_cflp


def test_cflp_exact_p_warehouses_and_single_assignment():
    """Validates that exactly p warehouses are opened and every neighborhood is assigned once."""
    neighborhoods = [
        Neighborhood(id="N1", name="North", latitude=13.0, longitude=77.5, daily_orders=100),
        Neighborhood(id="N2", name="South", latitude=12.9, longitude=77.5, daily_orders=150),
        Neighborhood(id="N3", name="East", latitude=12.95, longitude=77.6, daily_orders=200),
        Neighborhood(id="N4", name="West", latitude=12.95, longitude=77.4, daily_orders=120),
    ]
    candidates = [
        WarehouseCandidate(id="N1", name="North Site", latitude=13.0, longitude=77.5, capacity=500),
        WarehouseCandidate(id="N2", name="South Site", latitude=12.9, longitude=77.5, capacity=500),
        WarehouseCandidate(id="N3", name="East Site", latitude=12.95, longitude=77.6, capacity=500),
        WarehouseCandidate(id="N4", name="West Site", latitude=12.95, longitude=77.4, capacity=500),
    ]

    # Simple synthetic duration matrix
    durations = {
        c.id: {
            n.id: abs(c.latitude - n.latitude) * 100 + abs(c.longitude - n.longitude) * 100
            for n in neighborhoods
        }
        for c in candidates
    }

    # Solve for p = 2
    result = solve_cflp(
        neighborhoods=neighborhoods,
        candidates=candidates,
        p_warehouses=2,
        duration_matrix_min=durations,
        t_max_minutes=60.0,
    )

    assert result.is_optimal is True
    assert len(result.open_warehouse_ids) == 2
    assert len(result.assignments) == len(neighborhoods)
    # Every neighborhood assigned exactly once
    assert set(result.assignments.keys()) == {n.id for n in neighborhoods}
    # All assignments point to open warehouses
    assert all(wid in result.open_warehouse_ids for wid in result.assignments.values())


def test_cflp_capacity_never_exceeded():
    """Validates that total assigned demand does not exceed warehouse capacity."""
    neighborhoods = [
        Neighborhood(id="N1", name="N1", latitude=13.0, longitude=77.5, daily_orders=300),
        Neighborhood(id="N2", name="N2", latitude=13.0, longitude=77.5, daily_orders=300),
        Neighborhood(id="N3", name="N3", latitude=12.0, longitude=77.5, daily_orders=250),
    ]
    # Each warehouse has capacity 350. N1 and N2 cannot be grouped into one warehouse (300+300 = 600 > 350).
    candidates = [
        WarehouseCandidate(id="N1", name="Site 1", latitude=13.0, longitude=77.5, capacity=350),
        WarehouseCandidate(id="N2", name="Site 2", latitude=13.0, longitude=77.5, capacity=350),
        WarehouseCandidate(id="N3", name="Site 3", latitude=12.0, longitude=77.5, capacity=350),
    ]
    durations = {
        c.id: {n.id: 10.0 if c.id == n.id else 30.0 for n in neighborhoods}
        for c in candidates
    }

    result = solve_cflp(
        neighborhoods=neighborhoods,
        candidates=candidates,
        p_warehouses=3,
        duration_matrix_min=durations,
    )

    assert result.is_optimal is True
    # Calculate load per open warehouse
    loads = {wid: 0.0 for wid in result.open_warehouse_ids}
    for nid, wid in result.assignments.items():
        dem = next(n.daily_orders for n in neighborhoods if n.id == nid)
        loads[wid] += dem

    for wid, total_load in loads.items():
        cap = next(c.capacity for c in candidates if c.id == wid)
        assert total_load <= cap, f"Warehouse {wid} exceeded capacity ({total_load} > {cap})"


def test_cflp_infeasible_detected():
    """Validates that an infeasible scenario returns a structured diagnostic report rather than crashing."""
    neighborhoods = [
        Neighborhood(id="N1", name="N1", latitude=13.0, longitude=77.5, daily_orders=500),
        Neighborhood(id="N2", name="N2", latitude=13.0, longitude=77.5, daily_orders=500),
    ]
    # Total demand = 1000, but warehouse capacity = 400 with p=1
    candidates = [
        WarehouseCandidate(id="N1", name="Site 1", latitude=13.0, longitude=77.5, capacity=400),
    ]
    durations = {"N1": {"N1": 0.0, "N2": 10.0}}

    result = solve_cflp(
        neighborhoods=neighborhoods,
        candidates=candidates,
        p_warehouses=1,
        duration_matrix_min=durations,
    )

    assert result.is_optimal is False
    assert "Infeasible" in result.status
    assert len(result.diagnostics) > 0
