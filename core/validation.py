"""Input data contract validation and pre-solve feasibility diagnostics.
"""

from typing import Tuple, List, Dict, Any, Optional
import pandas as pd
import numpy as np


REQUIRED_COLUMNS = ["neighborhood_id", "name", "latitude", "longitude", "daily_orders"]


def validate_neighborhood_dataframe(df: pd.DataFrame) -> Tuple[bool, List[str], Optional[pd.DataFrame]]:
    """Strictly validates uploaded or loaded neighborhood CSV data.

    Returns:
        (is_valid, list_of_human_readable_errors, sanitized_dataframe)
    """
    errors: List[str] = []

    if df is None or not isinstance(df, pd.DataFrame):
        return False, ["Input is not a valid tabular DataFrame."], None

    if df.empty:
        return False, ["The dataset is completely empty. Please provide at least 2 neighborhoods."], None

    # 1. Required columns check
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        return (
            False,
            [f"Missing required column(s): {', '.join(missing_cols)}. Expected columns: {', '.join(REQUIRED_COLUMNS)}."],
            None,
        )

    # Work on a copy
    cleaned = df.copy()

    # 2. Check row count >= 2
    if len(cleaned) < 2:
        errors.append(f"At least 2 neighborhoods are required for network optimization, but found only {len(cleaned)} row(s).")

    # 3. Check nulls in required columns
    for col in REQUIRED_COLUMNS:
        null_indices = cleaned[cleaned[col].isna()].index.tolist()
        if null_indices:
            row_numbers = [idx + 2 for idx in null_indices]  # 1-based + header
            errors.append(f"Column '{col}' has null/empty values at CSV row(s): {row_numbers[:10]}{'...' if len(row_numbers) > 10 else ''}.")

    # 4. Check unique IDs
    cleaned["neighborhood_id"] = cleaned["neighborhood_id"].astype(str).str.strip()
    dup_ids = cleaned[cleaned["neighborhood_id"].duplicated(keep=False)]
    if not dup_ids.empty:
        dup_summary = dup_ids.groupby("neighborhood_id").size().to_dict()
        errors.append(f"Duplicate 'neighborhood_id' detected: {dup_summary}. Each neighborhood must have a unique identifier.")

    # 5. Check names
    cleaned["name"] = cleaned["name"].astype(str).str.strip()
    empty_names = cleaned[cleaned["name"] == ""].index.tolist()
    if empty_names:
        row_numbers = [idx + 2 for idx in empty_names]
        errors.append(f"Column 'name' has blank values at CSV row(s): {row_numbers[:10]}.")

    # 6. Check coordinates (lat in [-90, 90], lon in [-180, 180])
    for col, min_val, max_val in [("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)]:
        try:
            cleaned[col] = pd.to_numeric(cleaned[col])
        except Exception:
            errors.append(f"Column '{col}' must contain valid numeric float coordinates.")
            continue

        out_of_bounds = cleaned[(cleaned[col] < min_val) | (cleaned[col] > max_val)].index.tolist()
        if out_of_bounds:
            row_numbers = [idx + 2 for idx in out_of_bounds]
            errors.append(f"Column '{col}' contains out-of-range coordinates (valid range [{min_val}, {max_val}]) at CSV row(s): {row_numbers[:10]}.")

    # Check duplicate coordinates
    if "latitude" in cleaned and "longitude" in cleaned and pd.api.types.is_numeric_dtype(cleaned["latitude"]) and pd.api.types.is_numeric_dtype(cleaned["longitude"]):
        dup_coords = cleaned[cleaned.duplicated(subset=["latitude", "longitude"], keep=False)]
        if not dup_coords.empty:
            dup_pairs = dup_coords.groupby(["latitude", "longitude"])["name"].apply(list).to_dict()
            sample_dup = list(dup_pairs.items())[:3]
            errors.append(f"Duplicate coordinates found across neighborhoods: {sample_dup}. Each neighborhood must have distinct spatial coordinates.")

    # 7. Check daily_orders (numeric, non-negative)
    try:
        cleaned["daily_orders"] = pd.to_numeric(cleaned["daily_orders"])
        neg_orders = cleaned[cleaned["daily_orders"] < 0].index.tolist()
        if neg_orders:
            row_numbers = [idx + 2 for idx in neg_orders]
            errors.append(f"Column 'daily_orders' cannot have negative values. Found negative values at CSV row(s): {row_numbers[:10]}.")
        zero_total = cleaned["daily_orders"].sum()
        if zero_total == 0:
            errors.append("Total daily orders across all neighborhoods is 0. Network demand must be positive.")
    except Exception:
        errors.append("Column 'daily_orders' must contain valid non-negative numeric numbers.")

    # Optional candidate capacity column check
    if "capacity" in cleaned.columns:
        try:
            cleaned["capacity"] = pd.to_numeric(cleaned["capacity"])
            neg_caps = cleaned[cleaned["capacity"] <= 0].index.tolist()
            if neg_caps:
                row_numbers = [idx + 2 for idx in neg_caps]
                errors.append(f"Column 'capacity' must be strictly positive. Found non-positive values at CSV row(s): {row_numbers[:10]}.")
        except Exception:
            errors.append("Optional column 'capacity' must be numeric.")

    if errors:
        return False, errors, None

    return True, [], cleaned


def validate_presolve_feasibility(
    neighborhood_ids: List[str],
    demands: Dict[str, float],
    candidate_ids: List[str],
    capacities: Dict[str, float],
    p_warehouses: int,
    duration_matrix_min: Dict[str, Dict[str, float]],
    t_max_minutes: Optional[float] = None,
    auto_size: bool = False,
) -> Tuple[bool, List[str]]:
    """Performs strategic feasibility checks prior to invoking the MILP solver.

    Checks:
    1. p <= number of candidate sites
    2. Sum of capacities of top p candidate sites >= total demand
    3. Every neighborhood has at least one candidate site reachable within T_max
    """
    diagnostics: List[str] = []
    total_demand = sum(demands.values())
    n_candidates = len(candidate_ids)

    # 1. Check p bounds
    if p_warehouses < 1:
        count_label = "Maximum warehouse count p_max" if auto_size else "Warehouse count p"
        diagnostics.append(f"{count_label} must be at least 1 (requested {p_warehouses}).")
    elif p_warehouses > n_candidates:
        count_label = "maximum warehouse count p_max" if auto_size else "warehouse count p"
        diagnostics.append(
            f"Requested {count_label}={p_warehouses} exceeds total candidate sites ({n_candidates}). "
            f"You cannot consider or open more warehouses than available candidate locations."
        )

    # 2. Check total capacity
    sorted_caps = sorted([capacities[cid] for cid in candidate_ids], reverse=True)
    max_possible_capacity = sum(sorted_caps[:p_warehouses]) if p_warehouses <= n_candidates else sum(sorted_caps)

    if max_possible_capacity < total_demand:
        if auto_size:
            diagnostics.append(
                f"Capacity shortfall: Total network demand is {total_demand:,.0f} orders, but even opening the maximum "
                f"allowed {p_warehouses} warehouse(s) provides only {max_possible_capacity:,.0f} orders capacity "
                f"(shortfall of {total_demand - max_possible_capacity:,.0f} orders). "
                f"Increase p_max ceiling or increase per-warehouse capacity."
            )
        else:
            diagnostics.append(
                f"Capacity shortfall: Total network demand is {total_demand:,.0f} orders, but the maximum possible capacity "
                f"from opening {p_warehouses} warehouse(s) is only {max_possible_capacity:,.0f} orders "
                f"(shortfall of {total_demand - max_possible_capacity:,.0f} orders). "
                f"Increase warehouse count p or increase warehouse capacity."
            )


    # 3. Check reachability within T_max
    if t_max_minutes is not None and t_max_minutes > 0:
        unreachable_neighborhoods = []
        for nid in neighborhood_ids:
            # Find any candidate within t_max
            reachable = False
            for cid in candidate_ids:
                travel_time = duration_matrix_min.get(cid, {}).get(nid, float("inf"))
                if travel_time <= t_max_minutes:
                    reachable = True
                    break
            if not reachable:
                # Find min travel time to any candidate for diagnostics
                times = [duration_matrix_min.get(cid, {}).get(nid, float("inf")) for cid in candidate_ids]
                min_time = min(times) if times else float("inf")
                unreachable_neighborhoods.append((nid, min_time))

        if unreachable_neighborhoods:
            details = [f"{nid} (nearest candidate is {m_t:.1f} min away)" for nid, m_t in unreachable_neighborhoods[:6]]
            diagnostics.append(
                f"Service radius violation: {len(unreachable_neighborhoods)} neighborhood(s) cannot be reached "
                f"by ANY candidate warehouse within the maximum service limit T_max = {t_max_minutes:.0f} minutes. "
                f"Isolated neighborhoods: {', '.join(details)}. "
                f"To resolve, increase T_max or ensure candidate sites are closer to these neighborhoods."
            )

    return len(diagnostics) == 0, diagnostics
