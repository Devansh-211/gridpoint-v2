"""Unit tests for input CSV contract validation and pre-solve feasibility checks.
"""

import pandas as pd
import pytest
from core.validation import validate_neighborhood_dataframe, validate_presolve_feasibility


def test_valid_dataframe_passes():
    df = pd.DataFrame(
        {
            "neighborhood_id": ["N1", "N2", "N3"],
            "name": ["Alpha", "Beta", "Gamma"],
            "latitude": [12.91, 12.92, 12.93],
            "longitude": [77.51, 77.52, 77.53],
            "daily_orders": [100, 200, 150],
        }
    )
    is_valid, errors, cleaned = validate_neighborhood_dataframe(df)
    assert is_valid is True
    assert len(errors) == 0
    assert len(cleaned) == 3


def test_missing_required_column():
    df = pd.DataFrame(
        {
            "neighborhood_id": ["N1", "N2"],
            "name": ["Alpha", "Beta"],
            "latitude": [12.91, 12.92],
            # missing longitude and daily_orders
        }
    )
    is_valid, errors, cleaned = validate_neighborhood_dataframe(df)
    assert is_valid is False
    assert any("Missing required column" in err for err in errors)


def test_duplicate_ids_detected():
    df = pd.DataFrame(
        {
            "neighborhood_id": ["N1", "N1"],  # duplicate
            "name": ["Alpha", "Beta"],
            "latitude": [12.91, 12.92],
            "longitude": [77.51, 77.52],
            "daily_orders": [100, 200],
        }
    )
    is_valid, errors, cleaned = validate_neighborhood_dataframe(df)
    assert is_valid is False
    assert any("Duplicate 'neighborhood_id'" in err for err in errors)


def test_out_of_bounds_coordinates():
    df = pd.DataFrame(
        {
            "neighborhood_id": ["N1", "N2"],
            "name": ["Alpha", "Beta"],
            "latitude": [95.0, 12.92],  # > 90
            "longitude": [77.51, -195.0],  # < -180
            "daily_orders": [100, 200],
        }
    )
    is_valid, errors, cleaned = validate_neighborhood_dataframe(df)
    assert is_valid is False
    assert any("out-of-range" in err for err in errors)


def test_negative_daily_orders():
    df = pd.DataFrame(
        {
            "neighborhood_id": ["N1", "N2"],
            "name": ["Alpha", "Beta"],
            "latitude": [12.91, 12.92],
            "longitude": [77.51, 77.52],
            "daily_orders": [-50, 100],  # negative
        }
    )
    is_valid, errors, cleaned = validate_neighborhood_dataframe(df)
    assert is_valid is False
    assert any("negative" in err.lower() for err in errors)


def test_presolve_feasibility_detects_capacity_shortfall():
    demands = {"N1": 500.0, "N2": 600.0}  # total 1100
    capacities = {"C1": 400.0, "C2": 400.0}  # top 1 is 400
    durations = {"C1": {"N1": 10.0, "N2": 10.0}, "C2": {"N1": 10.0, "N2": 10.0}}

    is_feasible, diagnostics = validate_presolve_feasibility(
        neighborhood_ids=["N1", "N2"],
        demands=demands,
        candidate_ids=["C1", "C2"],
        capacities=capacities,
        p_warehouses=1,
        duration_matrix_min=durations,
        t_max_minutes=60.0,
    )
    assert is_feasible is False
    assert any("Capacity shortfall" in d for d in diagnostics)


def test_presolve_feasibility_detects_tmax_violation():
    demands = {"N1": 100.0, "N2": 100.0}
    capacities = {"C1": 1000.0}
    # N2 is 75 min away, but T_max is 45 min
    durations = {"C1": {"N1": 15.0, "N2": 75.0}}

    is_feasible, diagnostics = validate_presolve_feasibility(
        neighborhood_ids=["N1", "N2"],
        demands=demands,
        candidate_ids=["C1"],
        capacities=capacities,
        p_warehouses=1,
        duration_matrix_min=durations,
        t_max_minutes=45.0,
    )
    assert is_feasible is False
    assert any("Service radius violation" in d for d in diagnostics)
