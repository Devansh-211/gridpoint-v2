"""Scenario simulation engine for demand shocks and warehouse disruption resilience.
"""

from typing import List, Dict, Optional, Tuple
from core.models import Neighborhood, WarehouseCandidate
from routing.distance import DistanceMatrix, get_matrix
from optimization.cflp import solve_cflp
from optimization.assignment import process_assignments
from core.metrics import safe_pct_change


def run_scenario_simulation(
    base_neighborhoods: List[Neighborhood],
    base_candidates: List[WarehouseCandidate],
    matrix: DistanceMatrix,
    demand_multiplier: float = 1.0,
    failed_warehouse_id: Optional[str] = None,
    p_warehouses: int = 3,
    warehouse_capacity: float = 4000.0,
    cost_per_km: float = 1.25,
    fixed_cost_per_warehouse: float = 300.0,
) -> Dict[str, any]:
    """Simulates a demand surge scenario or a warehouse outage scenario."""
    # 1. Scale demand
    scenario_neighborhoods = [
        Neighborhood(
            id=n.id,
            name=n.name,
            latitude=n.latitude,
            longitude=n.longitude,
            daily_orders=n.daily_orders * demand_multiplier,
            capacity=n.capacity,
        )
        for n in base_neighborhoods
    ]

    # 2. Filter out failed warehouse candidate if specified
    scenario_candidates = [
        WarehouseCandidate(
            id=c.id,
            name=c.name,
            latitude=c.latitude,
            longitude=c.longitude,
            capacity=c.capacity if c.capacity else warehouse_capacity,
        )
        for c in base_candidates
        if failed_warehouse_id is None or c.id != failed_warehouse_id
    ]

    # Ensure requested p <= remaining candidates
    actual_p = min(p_warehouses, len(scenario_candidates))

    # Solve base CFLP
    base_cflp = solve_cflp(
        neighborhoods=base_neighborhoods,
        candidates=base_candidates,
        p_warehouses=p_warehouses,
        duration_matrix_min=matrix.distances_km,  # using distance directly for weighted km
    )

    # Solve scenario CFLP
    scenario_cflp = solve_cflp(
        neighborhoods=scenario_neighborhoods,
        candidates=scenario_candidates,
        p_warehouses=actual_p,
        duration_matrix_min=matrix.distances_km,
    )

    if not scenario_cflp.is_optimal and scenario_cflp.status not in ["Optimal", "Feasible"]:
        return {
            "success": False,
            "status": scenario_cflp.status,
            "solver_message": scenario_cflp.solver_message,
            "diagnostics": scenario_cflp.diagnostics,
            "locations_changed": False,
            "original_warehouses": base_cflp.open_warehouse_ids,
            "scenario_warehouses": [],
            "original_cost": 0.0,
            "scenario_cost": 0.0,
            "cost_pct_change": 0.0,
            "original_weighted_distance": base_cflp.weighted_strategic_travel_time,
            "scenario_weighted_distance": 0.0,
            "weighted_distance_pct_change": 0.0,
        }

    # Compare warehouse selections
    base_open = sorted(base_cflp.open_warehouse_ids)
    scen_open = sorted(scenario_cflp.open_warehouse_ids)
    locations_changed = base_open != scen_open

    # Cost calculation: distance_cost = sum(dist * orders) / avg_load * cost_per_km
    # In straight-line mode: delivery cost approx = weighted_distance * cost_per_km / avg_orders_per_km
    base_w_dist = base_cflp.weighted_strategic_travel_time
    scen_w_dist = scenario_cflp.weighted_strategic_travel_time

    base_deliv_cost = base_w_dist * (cost_per_km / 100.0)
    scen_deliv_cost = scen_w_dist * (cost_per_km / 100.0)

    base_total = base_deliv_cost + (len(base_open) * fixed_cost_per_warehouse)
    scen_total = scen_deliv_cost + (len(scen_open) * fixed_cost_per_warehouse)

    cost_pct = safe_pct_change(scen_total, base_total)
    w_dist_pct = safe_pct_change(scen_w_dist, base_w_dist)

    scenario_label = []
    if demand_multiplier != 1.0:
        scenario_label.append(f"Demand {'+' if demand_multiplier > 1 else ''}{int((demand_multiplier-1)*100)}%")
    if failed_warehouse_id:
        scenario_label.append(f"Warehouse Outage: {failed_warehouse_id}")

    name = " & ".join(scenario_label) if scenario_label else "Baseline Demand"

    return {
        "success": True,
        "scenario_name": name,
        "demand_multiplier": demand_multiplier,
        "failed_warehouse_id": failed_warehouse_id,
        "locations_changed": locations_changed,
        "original_warehouses": base_open,
        "scenario_warehouses": scen_open,
        "original_cost": round(base_total, 2),
        "scenario_cost": round(scen_total, 2),
        "cost_pct_change": round(cost_pct, 1),
        "original_weighted_distance": round(base_w_dist, 1),
        "scenario_weighted_distance": round(scen_w_dist, 1),
        "weighted_distance_pct_change": round(w_dist_pct, 1),
        "diagnostics": [],
    }
