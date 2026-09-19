"""Unit tests for delivery cost calculation and percentage change metrics.
"""

import pytest
from core.metrics import compute_delivery_cost, safe_pct_change, compare_network_summaries
from core.models import SystemSummary, CostBreakdown, CFLPResult, WarehouseCandidate


def test_delivery_cost_formula():
    """Validates cost = km*cost_per_km + hours*cost_per_hour + vehicles*fixed_cost."""
    cb = compute_delivery_cost(
        total_distance_km=100.0,
        total_duration_hours=4.0,
        vehicles_used=3,
        cost_per_km=1.5,
        cost_per_hour=20.0,
        fixed_vehicle_cost=50.0,
        vehicle_capacity=250,
        service_radius_min=45.0,
    )

    # 100 * 1.5 = 150.0
    # 4.0 * 20.0 = 80.0
    # 3 * 50.0 = 150.0
    # Total = 380.0
    assert cb.distance_cost == 150.0
    assert cb.time_cost == 80.0
    assert cb.vehicle_cost == 150.0
    assert cb.total_cost == 380.0
    assert cb.assumptions["cost_per_km"] == 1.5
    assert cb.assumptions["vehicle_capacity"] == 250


def test_safe_pct_change_zero_division():
    """Validates that a zero baseline returns 0.0 without ZeroDivisionError."""
    # Zero baseline
    assert safe_pct_change(100.0, 0.0) == 0.0
    assert safe_pct_change(0.0, 0.0) == 0.0

    # Normal calculation: (150 - 100) / 100 * 100 = 50.0%
    assert safe_pct_change(150.0, 100.0) == 50.0
    # Reduction: (80 - 100) / 100 * 100 = -20.0%
    assert safe_pct_change(80.0, 100.0) == -20.0
