"""Operational delivery cost model and baseline comparison metrics.
"""

from typing import Dict, Any
from core.models import CostBreakdown, SystemSummary, ComparisonMetrics


def compute_delivery_cost(
    total_distance_km: float,
    total_duration_hours: float,
    vehicles_used: int,
    cost_per_km: float,
    cost_per_hour: float,
    fixed_vehicle_cost: float,
    vehicle_capacity: int,
    service_radius_min: float,
) -> CostBreakdown:
    """Computes total operational delivery cost and records all foundational assumptions.

    total_cost = (km * cost/km) + (hours * cost/hour) + (vehicles * fixed_cost)
    """
    distance_cost = float(total_distance_km * cost_per_km)
    time_cost = float(total_duration_hours * cost_per_hour)
    vehicle_cost = float(vehicles_used * fixed_vehicle_cost)
    total_cost = distance_cost + time_cost + vehicle_cost

    assumptions = {
        "cost_per_km": cost_per_km,
        "cost_per_hour": cost_per_hour,
        "fixed_vehicle_cost": fixed_vehicle_cost,
        "vehicle_capacity": vehicle_capacity,
        "service_radius_min": service_radius_min,
    }

    return CostBreakdown(
        distance_cost=distance_cost,
        time_cost=time_cost,
        vehicle_cost=vehicle_cost,
        total_cost=total_cost,
        assumptions=assumptions,
    )


def safe_pct_change(new_val: float, base_val: float) -> float:
    """Computes percentage change safely without dividing by zero.

    Returns ((new - base) / base) * 100.0 if base > 0, else 0.0.
    """
    if base_val == 0.0:
        return 0.0
    return ((new_val - base_val) / base_val) * 100.0


def compare_network_summaries(
    baseline: SystemSummary,
    optimized: SystemSummary,
) -> ComparisonMetrics:
    """Computes delta and percentage change between baseline and optimized solutions."""
    cost_base = baseline.cost_breakdown.total_cost
    cost_opt = optimized.cost_breakdown.total_cost
    cost_delta = cost_opt - cost_base
    cost_pct = safe_pct_change(cost_opt, cost_base)

    dist_base = baseline.total_distance_km
    dist_opt = optimized.total_distance_km
    dist_delta = dist_opt - dist_base
    dist_pct = safe_pct_change(dist_opt, dist_base)

    dur_base = baseline.total_duration_hours
    dur_opt = optimized.total_duration_hours
    dur_delta = dur_opt - dur_base
    dur_pct = safe_pct_change(dur_opt, dur_base)

    veh_base = baseline.vehicles_used
    veh_opt = optimized.vehicles_used
    veh_delta = veh_opt - veh_base
    veh_pct = safe_pct_change(float(veh_opt), float(veh_base))

    w_base = baseline.weighted_strategic_travel_time
    w_opt = optimized.weighted_strategic_travel_time
    w_delta = w_opt - w_base
    w_pct = safe_pct_change(w_opt, w_base)

    util_delta = optimized.avg_load_utilization - baseline.avg_load_utilization

    return ComparisonMetrics(
        baseline=baseline,
        optimized=optimized,
        cost_delta=cost_delta,
        cost_pct_change=cost_pct,
        distance_delta_km=dist_delta,
        distance_pct_change=dist_pct,
        duration_delta_hours=dur_delta,
        duration_pct_change=dur_pct,
        vehicles_delta=veh_delta,
        vehicles_pct_change=veh_pct,
        weighted_time_delta=w_delta,
        weighted_time_pct_change=w_pct,
        utilization_delta=util_delta,
    )
