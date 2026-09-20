"""FastAPI API routes for GRIDPOINT warehouse location optimization platform.
Adheres strictly to Hackathon Honesty Rules and B2B Operations rigor.
"""

import io
import os
import uuid
import hashlib
import logging
from typing import Dict, List, Optional, Any
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status

from core.models import Neighborhood, WarehouseCandidate, CFLPResult
from core.validation import validate_neighborhood_dataframe, validate_presolve_feasibility
from core.metrics import safe_pct_change
from routing.distance import get_matrix, DistanceMatrix
from optimization.cflp import solve_cflp, get_milp_solver
from optimization.assignment import process_assignments
from optimization.cvrp import solve_cvrp_for_warehouse
from simulation.scenario import run_scenario_simulation
from api.schemas import (
    NeighborhoodItem,
    NeighborhoodListRequest,
    UploadResponse,
    OptimizeRequest,
    OptimizeResponse,
    WarehouseSummary,
    AssignmentItem,
    CompareResponse,
    SystemMetricSnapshot,
    TradeoffResponse,
    TradeoffPoint,
    ScenarioRequest,
    ScenarioResponse,
    ExplainResponse,
    DemandDriver,
    NextBestCandidate,
    AgentExtractRequest,
    AgentExtractResponse,
    SyntheticDataRequest,
    AgentExplainRequest,
    AgentExplainResponse,
)
from api.agent import process_agent_dialog, generate_synthetic_demand_dataset, process_agent_explanation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["optimization"])

# In-memory session data store and server-side solve cache
SESSION_STORE: Dict[str, Dict[str, Any]] = {}
SOLVE_CACHE: Dict[str, OptimizeResponse] = {}

# Logistics vehicle emissions factor: 0.21 kg CO2 per km for delivery fleet
EMISSIONS_KG_PER_KM = 0.21


def _compute_solve_cache_key(req: OptimizeRequest, session_id: str, zone_count: int = 0, total_demand: float = 0.0) -> str:
    """Computes deterministic hash for request parameters to prevent redundant CPU solves."""
    raw = (
        f"{session_id}_{zone_count}_{total_demand:.1f}_{req.p}_{req.auto_size}_{req.p_max}_{req.warehouse_capacity}_{req.radius_max_km}_"
        f"{req.cost_per_km}_{req.fixed_cost_per_warehouse}_{req.routing_mode}_"
        f"{req.priority_preset}_{req.include_cvrp}_{req.vehicle_capacity}_{req.vehicle_fixed_cost}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_or_load_default_session(session_id: str = "default") -> Dict[str, Any]:
    """Retrieves session data, loading the preloaded 36 Bengaluru demo dataset if empty."""
    if session_id not in SESSION_STORE:
        # Check demo file paths
        csv_path = "data/demo_neighborhoods.csv" if os.path.exists("data/demo_neighborhoods.csv") else "data/sample_neighborhoods.csv"
        df = pd.read_csv(csv_path)
        is_val, errs, clean_df = validate_neighborhood_dataframe(df)
        if not is_val:
            raise RuntimeError(f"Demo dataset failed validation: {errs}")

        neighborhoods = [
            Neighborhood(
                id=str(row["neighborhood_id"]).strip(),
                name=str(row["name"]).strip(),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                daily_orders=float(row["daily_orders"]),
                capacity=float(row["capacity"]) if "capacity" in row and pd.notna(row["capacity"]) else None,
            )
            for _, row in clean_df.iterrows()
        ]
        SESSION_STORE[session_id] = {
            "neighborhoods": neighborhoods,
            "df": clean_df,
            "last_optimize": None,
            "last_matrix": None,
        }
    return SESSION_STORE[session_id]


# 1. Health & Solver Verification
@router.get("/health")
def health_check():
    """Reports system health and active MILP solver status."""
    try:
        solver = get_milp_solver()
        solver_name = type(solver).__name__
        solver_avail = solver.available()
    except Exception as e:
        solver_name = "Heuristic Fallback Ready"
        solver_avail = True

    return {
        "status": "healthy",
        "solver": solver_name,
        "solver_available": bool(solver_avail),
        "platform": "GRIDPOINT B2B Logistics Optimization",
        "version": "2.0.0",
    }


# 2. Demo Data & Data Ingestion
@router.get("/demo-data", response_model=UploadResponse)
def get_demo_data():
    """Returns the pre-packaged 36-neighborhood Bengaluru dataset for instant zero-setup demo."""
    session = _get_or_load_default_session("default")
    neighborhoods: List[Neighborhood] = session["neighborhoods"]
    total_demand = sum(n.daily_orders for n in neighborhoods)

    preview_items = [
        NeighborhoodItem(
            neighborhood_id=n.id,
            name=n.name,
            latitude=n.latitude,
            longitude=n.longitude,
            daily_orders=n.daily_orders,
            capacity=n.capacity,
        )
        for n in neighborhoods
    ]

    return UploadResponse(
        session_id="default",
        neighborhood_count=len(neighborhoods),
        total_demand=total_demand,
        preview=preview_items,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_neighborhood_csv(file: UploadFile = File(...)):
    """Accepts and strictly validates uploaded CSV dataset."""
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse uploaded CSV file: {str(e)}",
        )

    is_valid, errors, cleaned_df = validate_neighborhood_dataframe(df)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": errors, "row_count": len(df)},
        )

    session_id = str(uuid.uuid4())[:8]
    neighborhoods = [
        Neighborhood(
            id=str(row["neighborhood_id"]).strip(),
            name=str(row["name"]).strip(),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            daily_orders=float(row["daily_orders"]),
            capacity=float(row["capacity"]) if "capacity" in row and pd.notna(row["capacity"]) else None,
        )
        for _, row in cleaned_df.iterrows()
    ]

    SESSION_STORE[session_id] = {
        "neighborhoods": neighborhoods,
        "df": cleaned_df,
        "last_optimize": None,
        "last_matrix": None,
    }
    SOLVE_CACHE.clear()

    total_demand = sum(n.daily_orders for n in neighborhoods)
    preview_items = [
        NeighborhoodItem(
            neighborhood_id=n.id,
            name=n.name,
            latitude=n.latitude,
            longitude=n.longitude,
            daily_orders=n.daily_orders,
            capacity=n.capacity,
        )
        for n in neighborhoods
    ]

    return UploadResponse(
        session_id=session_id,
        neighborhood_count=len(neighborhoods),
        total_demand=total_demand,
        preview=preview_items,
    )


@router.post("/neighborhoods", response_model=UploadResponse)
def set_manual_neighborhoods(req: NeighborhoodListRequest):
    """Accepts manual neighborhood JSON array for live editing during judging."""
    data = [item.model_dump() for item in req.neighborhoods]
    df = pd.DataFrame(data)
    is_valid, errors, cleaned_df = validate_neighborhood_dataframe(df)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": errors},
        )

    session_id = str(uuid.uuid4())[:8]
    neighborhoods = [
        Neighborhood(
            id=str(row["neighborhood_id"]).strip(),
            name=str(row["name"]).strip(),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            daily_orders=float(row["daily_orders"]),
            capacity=float(row["capacity"]) if "capacity" in row and pd.notna(row["capacity"]) else None,
        )
        for _, row in cleaned_df.iterrows()
    ]

    SESSION_STORE[session_id] = {
        "neighborhoods": neighborhoods,
        "df": cleaned_df,
        "last_optimize": None,
        "last_matrix": None,
    }
    SOLVE_CACHE.clear()

    total_demand = sum(n.daily_orders for n in neighborhoods)
    return UploadResponse(
        session_id=session_id,
        neighborhood_count=len(neighborhoods),
        total_demand=total_demand,
        preview=req.neighborhoods,
    )


# 3. Strategic Network Optimization (CFLP)
@router.post("/optimize", response_model=OptimizeResponse)
def optimize_network(req: OptimizeRequest):
    """Solves Capacitated Facility Location Problem (CFLP) to determine p optimal warehouse sites."""
    session = _get_or_load_default_session(req.session_id or "default")
    neighborhoods: List[Neighborhood] = session["neighborhoods"]
    total_demand = sum(n.daily_orders for n in neighborhoods)

    # Server-side cache check
    cache_key = _compute_solve_cache_key(req, req.session_id or "default", zone_count=len(neighborhoods), total_demand=total_demand)
    if cache_key in SOLVE_CACHE:
        logger.info("Serving optimization solution from server-side cache (key: %s)", cache_key)
        cached_response = SOLVE_CACHE[cache_key]
        session["last_optimize"] = cached_response
        return cached_response

    # Adjust parameters based on priority preset
    effective_cost_per_km = req.cost_per_km
    effective_radius = req.radius_max_km

    if req.priority_preset == "speed":
        # Proximity priority: tighten effective radius if not set, prioritize proximity
        if effective_radius is None:
            effective_radius = 20.0
    elif req.priority_preset == "sustainability":
        # Green priority: slightly heavier penalty on distance to discourage long hauls
        effective_cost_per_km = req.cost_per_km * 1.15

    # Build candidate warehouses (every neighborhood is a candidate site)
    candidates = [
        WarehouseCandidate(
            id=n.id,
            name=n.name,
            latitude=n.latitude,
            longitude=n.longitude,
            capacity=n.capacity if n.capacity else req.warehouse_capacity,
        )
        for n in neighborhoods
    ]

    # Compute Distance Matrix (Haversine by default, straight-line geographic distance)
    matrix = get_matrix(neighborhoods, mode=req.routing_mode)
    session["last_matrix"] = matrix

    # Determine validation count and auto_size bounds
    p_max_to_use = req.p_max if req.p_max is not None and req.p_max >= 1 else min(10, len(candidates))
    if req.auto_size and req.p_max is not None and req.p_max > len(candidates):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid Parameter Ceiling",
                "diagnostics": [
                    f"Requested maximum warehouse count p_max={req.p_max} exceeds total candidate sites ({len(candidates)}). "
                    f"You cannot consider more warehouses than available candidate locations."
                ],
                "p_max": req.p_max,
                "candidate_count": len(candidates),
            },
        )

    p_to_validate = p_max_to_use if req.auto_size else req.p

    # Pre-solve feasibility checks
    is_feasible, diagnostics = validate_presolve_feasibility(
        neighborhood_ids=[n.id for n in neighborhoods],
        demands={n.id: n.daily_orders for n in neighborhoods},
        candidate_ids=[c.id for c in candidates],
        capacities={c.id: c.capacity for c in candidates},
        p_warehouses=p_to_validate,
        duration_matrix_min=matrix.distances_km,
        t_max_minutes=effective_radius,
        auto_size=req.auto_size,
    )

    if not is_feasible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Optimization Infeasible",
                "diagnostics": diagnostics,
                "p": req.p,
                "p_max": req.p_max,
                "auto_size": req.auto_size,
                "warehouse_capacity": req.warehouse_capacity,
            },
        )

    # Solve CFLP with PuLP + CBC / Heuristic fallback
    cflp_res = solve_cflp(
        neighborhoods=neighborhoods,
        candidates=candidates,
        p_warehouses=req.p,
        duration_matrix_min=matrix.distances_km,
        t_max_minutes=effective_radius,
        auto_size=req.auto_size,
        p_max=req.p_max,
        cost_per_km=effective_cost_per_km,
        fixed_cost_per_warehouse=req.fixed_cost_per_warehouse,
    )

    if not cflp_res.is_optimal and not cflp_res.status.startswith("Feasible") and cflp_res.status != "Optimal":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": f"Solver Status: {cflp_res.status}",
                "message": cflp_res.solver_message,
                "diagnostics": cflp_res.diagnostics,
            },
        )

    # Process assignments
    updated_candidates = process_assignments(candidates, neighborhoods, cflp_res)
    cand_map = {c.id: c for c in updated_candidates}
    n_map = {n.id: n for n in neighborhoods}
    actual_p = len(cflp_res.open_warehouse_ids)

    # Format warehouse summaries
    warehouses_summary: List[WarehouseSummary] = []
    for wid in cflp_res.open_warehouse_ids:
        c = cand_map[wid]
        util_pct = (c.total_assigned_demand / c.capacity * 100.0) if c.capacity > 0 else 0.0
        warehouses_summary.append(
            WarehouseSummary(
                warehouse_id=c.id,
                name=c.name,
                latitude=c.latitude,
                longitude=c.longitude,
                capacity=c.capacity,
                assigned_demand=c.total_assigned_demand,
                capacity_required=c.total_assigned_demand,
                capacity_ceiling=c.capacity,
                capacity_utilization_pct=round(util_pct, 1),
                neighborhoods_count=len(c.assigned_neighborhood_ids),
            )
        )

    # Format assignments & calculate fast delivery proxy (< 5 km)
    assignments_list: List[AssignmentItem] = []
    fast_delivery_demand = 0.0
    covered_demand = 0.0

    for nid, wid in cflp_res.assignments.items():
        n = n_map[nid]
        w = cand_map[wid]
        dist = matrix.distances_km.get(w.id, {}).get(n.id, 0.0)
        assignments_list.append(
            AssignmentItem(
                neighborhood_id=n.id,
                neighborhood_name=n.name,
                latitude=n.latitude,
                longitude=n.longitude,
                warehouse_id=w.id,
                warehouse_name=w.name,
                warehouse_latitude=w.latitude,
                warehouse_longitude=w.longitude,
                distance_km=round(dist, 2),
                daily_orders=n.daily_orders,
            )
        )
        if dist <= 5.0:
            fast_delivery_demand += n.daily_orders
        if effective_radius is None or dist <= effective_radius:
            covered_demand += n.daily_orders

    # Coverage percentages
    cov_pct = round((covered_demand / max(1.0, total_demand)) * 100.0, 1)
    fast_cov_pct = round((fast_delivery_demand / max(1.0, total_demand)) * 100.0, 1)

    # Delivery distance and cost calculation
    total_weighted_dist = cflp_res.weighted_strategic_travel_time
    avg_dist_km = round(total_weighted_dist / max(1.0, total_demand), 2)
    delivery_cost = round(total_weighted_dist * (effective_cost_per_km / 50.0), 2)
    infra_cost = round(actual_p * req.fixed_cost_per_warehouse, 2)
    combined_cost = round(delivery_cost + infra_cost, 2)

    # Throughput & Headroom metrics
    total_system_capacity = sum(w.capacity for w in warehouses_summary)
    capacity_headroom = round(total_system_capacity - total_demand, 1)
    capacity_headroom_pct = round(((total_system_capacity - total_demand) / max(1.0, total_system_capacity)) * 100.0, 1)

    # Plain language sizing rationale
    if req.auto_size:
        sizing_rationale = (
            f"Auto-sized to {actual_p} warehouse(s) (from up to {p_max_to_use} considered). "
            f"The mathematical solver selected {actual_p} facilities to minimize combined daily costs: "
            f"${delivery_cost:,.2f} transit + ${infra_cost:,.2f} infrastructure = ${combined_cost:,.2f}/day total."
        )
    else:
        sizing_rationale = (
            f"Manual exact configuration: exactly {actual_p} warehouse(s) opened per user constraint."
        )

    # Baseline comparison for monthly savings & CO2 calculation
    min_base_weighted_dist = float("inf")
    for cand in neighborhoods:
        w_d = sum(n.daily_orders * matrix.distances_km.get(cand.id, {}).get(n.id, 0.0) for n in neighborhoods)
        if w_d < min_base_weighted_dist:
            min_base_weighted_dist = w_d

    base_deliv_cost = round(min_base_weighted_dist * (effective_cost_per_km / 50.0), 2)
    base_infra_cost = round(1 * req.fixed_cost_per_warehouse, 2)
    base_combined = round(base_deliv_cost + base_infra_cost, 2)
    daily_savings = max(0.0, base_combined - combined_cost)
    monthly_savings = round(daily_savings * 30.0, 2)

    # CO2 emissions estimation (0.21 kg/km per vehicle round-trip estimate)
    opt_co2 = round((total_weighted_dist / max(1.0, total_demand) * len(neighborhoods) * 2.0) * EMISSIONS_KG_PER_KM, 1)
    base_co2 = round((min_base_weighted_dist / max(1.0, total_demand) * len(neighborhoods) * 2.0) * EMISSIONS_KG_PER_KM, 1)
    co2_reduc_pct = safe_pct_change(opt_co2, base_co2)

    assumptions = {
        "cost_per_km": req.cost_per_km,
        "fixed_cost_per_warehouse": req.fixed_cost_per_warehouse,
        "warehouse_capacity": req.warehouse_capacity,
        "radius_max_km": effective_radius,
        "routing_mode": req.routing_mode,
        "priority_preset": req.priority_preset or "cost",
        "p": actual_p,
        "auto_size": req.auto_size,
        "p_max": req.p_max,
        "include_cvrp": req.include_cvrp,
        "vehicle_capacity": req.vehicle_capacity,
        "vehicle_fixed_cost": req.vehicle_fixed_cost,
        "time_window_start": req.time_window_start,
        "time_window_end": req.time_window_end,
    }


    # Optional CVRP routing refinement if requested
    cvrp_summary = None
    if req.include_cvrp:
        tot_cvrp_dist = 0.0
        tot_cvrp_dur = 0.0
        tot_cvrp_veh = 0
        all_routes_data = []
        for wid in cflp_res.open_warehouse_ids:
            c = cand_map[wid]
            assigned_n = [n_map[n_id] for n_id in c.assigned_neighborhood_ids]
            res_w = solve_cvrp_for_warehouse(
                warehouse=c,
                assigned_neighborhoods=assigned_n,
                network_matrix=matrix,
                vehicle_capacity=req.vehicle_capacity,
                time_limit_seconds=2,
            )
            tot_cvrp_dist += res_w.total_distance_km
            tot_cvrp_dur += res_w.total_duration_hours
            tot_cvrp_veh += res_w.vehicles_used

            for r in res_w.routes:
                cumul_dist = 0.0
                cumul_load = 0.0
                stop_items = []
                prev_id = c.id
                for idx, stop_id in enumerate(r.stop_ids):
                    n_stop = n_map[stop_id]
                    step_d = matrix.distances_km.get(prev_id, {}).get(stop_id, 0.0)
                    cumul_dist += step_d
                    dem = r.stop_demands[idx] if idx < len(r.stop_demands) else n_stop.daily_orders
                    cumul_load += dem
                    stop_items.append({
                        "stop_index": idx + 1,
                        "neighborhood_id": stop_id,
                        "neighborhood_name": r.stop_names[idx] if idx < len(r.stop_names) else n_stop.name,
                        "demand": dem,
                        "cumulative_load": round(cumul_load, 1),
                        "cumulative_distance_km": round(cumul_dist, 2),
                    })
                    prev_id = stop_id

                util = round((r.total_load / req.vehicle_capacity * 100.0) if req.vehicle_capacity > 0 else 0.0, 1)
                all_routes_data.append({
                    "vehicle_id": f"V-{c.id}-{r.vehicle_index}",
                    "warehouse_id": c.id,
                    "warehouse_name": c.name,
                    "stops": stop_items,
                    "stop_names": r.stop_names,
                    "total_distance_km": round(r.distance_km, 2),
                    "total_duration_hours": round(r.duration_hours, 2),
                    "total_load": round(r.total_load, 1),
                    "capacity": float(req.vehicle_capacity),
                    "utilization_pct": util,
                    "route_coords": [[pt[0], pt[1]] for pt in r.route_coords],
                })

        avg_veh_util = round(sum(rt["utilization_pct"] for rt in all_routes_data) / max(1, len(all_routes_data)), 1) if all_routes_data else 0.0
        cvrp_summary = {
            "routed_distance_km": round(tot_cvrp_dist, 1),
            "routed_duration_hours": round(tot_cvrp_dur, 1),
            "vehicles_deployed": tot_cvrp_veh,
            "vehicle_capacity": req.vehicle_capacity,
            "vehicle_fixed_cost": req.vehicle_fixed_cost,
            "avg_vehicle_utilization_pct": avg_veh_util,
            "routes": all_routes_data,
        }

    response = OptimizeResponse(
        status="Optimal" if cflp_res.is_optimal else ("Feasible (Heuristic)" if "Heuristic" in cflp_res.status else "Feasible"),
        solver_message=cflp_res.solver_message,
        is_optimal=cflp_res.is_optimal,
        p=actual_p,
        auto_size=req.auto_size,
        total_weighted_distance_km=round(total_weighted_dist, 1),
        average_distance_km=avg_dist_km,
        total_delivery_cost=delivery_cost,
        total_infrastructure_cost=infra_cost,
        combined_total_cost=combined_cost,
        total_system_capacity=round(total_system_capacity, 1),
        total_system_demand=round(total_demand, 1),
        capacity_headroom=capacity_headroom,
        capacity_headroom_pct=capacity_headroom_pct,
        sizing_rationale=sizing_rationale,
        coverage_percentage=cov_pct,
        fast_delivery_coverage_pct=fast_cov_pct,
        unserved_demand=0.0,
        estimated_co2_kg_per_day=opt_co2,
        co2_baseline_kg_per_day=base_co2,
        co2_reduction_pct=round(co2_reduc_pct, 1),
        estimated_monthly_savings=monthly_savings,
        assumptions=assumptions,
        warehouses=warehouses_summary,
        assignments=assignments_list,
        cvrp_summary=cvrp_summary,
    )


    # Store in session and in server cache
    session["last_optimize"] = response
    session["candidates"] = updated_candidates
    session["cflp_result"] = cflp_res
    session["last_req"] = req
    SOLVE_CACHE[cache_key] = response

    return response


# 4. Baseline Comparison
@router.get("/compare", response_model=CompareResponse)
def get_baseline_comparison(session_id: str = "default"):
    """Compares the optimized network against the Single-Warehouse Reference Baseline."""
    session = _get_or_load_default_session(session_id)
    neighborhoods: List[Neighborhood] = session["neighborhoods"]
    last_opt: Optional[OptimizeResponse] = session.get("last_optimize")

    if last_opt is None:
        demands = {n.id: n.daily_orders for n in neighborhoods}
        total_demand = sum(demands.values())
        safe_cap = max(4000.0, (total_demand / 3.0) * 1.5)
        last_opt = optimize_network(OptimizeRequest(session_id=session_id, warehouse_capacity=safe_cap))

    matrix: DistanceMatrix = session["last_matrix"]
    demands = {n.id: n.daily_orders for n in neighborhoods}
    total_demand = sum(demands.values())

    # Find the Single-Warehouse Reference Baseline (1-median center)
    best_candidate_id = None
    min_weighted_dist = float("inf")

    for cand in neighborhoods:
        w_dist = sum(demands[n.id] * matrix.distances_km.get(cand.id, {}).get(n.id, 0.0) for n in neighborhoods)
        if w_dist < min_weighted_dist:
            min_weighted_dist = w_dist
            best_candidate_id = cand.id

    cost_per_km = last_opt.assumptions.get("cost_per_km", 1.25)
    fixed_infra = last_opt.assumptions.get("fixed_cost_per_warehouse", 300.0)

    base_deliv_cost = round(min_weighted_dist * (cost_per_km / 50.0), 2)
    base_infra_cost = round(1 * fixed_infra, 2)
    base_combined_cost = round(base_deliv_cost + base_infra_cost, 2)

    base_co2 = round((min_weighted_dist / max(1.0, total_demand) * len(neighborhoods) * 2.0) * EMISSIONS_KG_PER_KM, 1)
    opt_co2 = last_opt.estimated_co2_kg_per_day

    baseline_snapshot = SystemMetricSnapshot(
        label="Single-Warehouse Reference Baseline",
        warehouses_count=1,
        warehouses_open=[best_candidate_id] if best_candidate_id else [],
        total_delivery_cost=base_deliv_cost,
        total_infrastructure_cost=base_infra_cost,
        combined_total_cost=base_combined_cost,
        total_distance_km=round(min_weighted_dist / max(1, total_demand) * 2.0, 1),
        weighted_distance_km=round(min_weighted_dist, 1),
        avg_capacity_utilization_pct=100.0,
        estimated_co2_kg_per_day=base_co2,
    )

    opt_snapshot = SystemMetricSnapshot(
        label=f"Optimized Network ({last_opt.p} Warehouses)",
        warehouses_count=last_opt.p,
        warehouses_open=[w.warehouse_id for w in last_opt.warehouses],
        total_delivery_cost=last_opt.total_delivery_cost,
        total_infrastructure_cost=last_opt.total_infrastructure_cost,
        combined_total_cost=last_opt.combined_total_cost,
        total_distance_km=round(last_opt.total_weighted_distance_km / max(1, total_demand) * 2.0, 1),
        weighted_distance_km=last_opt.total_weighted_distance_km,
        avg_capacity_utilization_pct=round(
            sum(w.capacity_utilization_pct for w in last_opt.warehouses) / max(1, len(last_opt.warehouses)), 1
        ),
        estimated_co2_kg_per_day=opt_co2,
    )

    cost_delta = opt_snapshot.total_delivery_cost - baseline_snapshot.total_delivery_cost
    cost_pct = safe_pct_change(opt_snapshot.total_delivery_cost, baseline_snapshot.total_delivery_cost)

    dist_delta = opt_snapshot.weighted_distance_km - baseline_snapshot.weighted_distance_km
    dist_pct = safe_pct_change(opt_snapshot.weighted_distance_km, baseline_snapshot.weighted_distance_km)

    daily_savings = max(0.0, base_combined_cost - opt_snapshot.combined_total_cost)
    monthly_savings = round(daily_savings * 30.0, 2)

    co2_delta = round(opt_co2 - base_co2, 1)
    co2_pct = safe_pct_change(opt_co2, base_co2)

    return CompareResponse(
        baseline=baseline_snapshot,
        optimized=opt_snapshot,
        cost_delta=round(cost_delta, 2),
        cost_pct_change=round(cost_pct, 1),
        distance_delta_km=round(dist_delta, 1),
        distance_pct_change=round(dist_pct, 1),
        weighted_distance_delta=round(dist_delta, 1),
        weighted_distance_pct_change=round(dist_pct, 1),
        estimated_monthly_savings=monthly_savings,
        co2_delta_kg=co2_delta,
        co2_pct_change=round(co2_pct, 1),
        assumptions=last_opt.assumptions,
    )


# 5. Infrastructure vs Delivery Cost Trade-off Curve (p = 1..5)
@router.get("/tradeoff", response_model=TradeoffResponse)
def get_tradeoff_curve(session_id: str = "default", fixed_cost: float = 300.0, cost_per_km: float = 1.25):
    """Sweeps p = 1 to 5 to generate the infrastructure vs delivery cost trade-off curve."""
    session = _get_or_load_default_session(session_id)
    neighborhoods: List[Neighborhood] = session["neighborhoods"]
    matrix = get_matrix(neighborhoods, mode="haversine")

    total_demand = sum(n.daily_orders for n in neighborhoods)
    fallback_cap = max(4000.0, float(total_demand) * 1.25)
    points: List[TradeoffPoint] = []
    candidates = [
        WarehouseCandidate(
            id=n.id,
            name=n.name,
            latitude=n.latitude,
            longitude=n.longitude,
            capacity=n.capacity if (n.capacity is not None and n.capacity > 0) else fallback_cap,
        )
        for n in neighborhoods
    ]

    for p_val in range(1, min(6, len(neighborhoods) + 1)):
        cflp = solve_cflp(
            neighborhoods=neighborhoods,
            candidates=candidates,
            p_warehouses=p_val,
            duration_matrix_min=matrix.distances_km,
        )
        if cflp.is_optimal or cflp.status in ["Optimal", "Feasible"] or "Heuristic" in cflp.status:
            w_dist = cflp.weighted_strategic_travel_time
            deliv_cost = round(w_dist * (cost_per_km / 50.0), 2)
            infra_cost = round(p_val * fixed_cost, 2)
            combined = round(deliv_cost + infra_cost, 2)
            points.append(
                TradeoffPoint(
                    p=p_val,
                    delivery_cost=deliv_cost,
                    infrastructure_cost=infra_cost,
                    combined_cost=combined,
                    weighted_distance_km=round(w_dist, 1),
                    is_feasible=True,
                    warehouses_open=cflp.open_warehouse_ids,
                )
            )
        else:
            points.append(
                TradeoffPoint(
                    p=p_val,
                    delivery_cost=0.0,
                    infrastructure_cost=round(p_val * fixed_cost, 2),
                    combined_cost=0.0,
                    weighted_distance_km=0.0,
                    is_feasible=False,
                    warehouses_open=[],
                )
            )

    return TradeoffResponse(
        points=points,
        fixed_cost_per_warehouse=fixed_cost,
        cost_per_km=cost_per_km,
    )


# 6. Scenario Simulation
@router.post("/scenario", response_model=ScenarioResponse)
def run_scenario(req: ScenarioRequest):
    """Evaluates a demand shock (+20%, +50%) or warehouse outage scenario."""
    session = _get_or_load_default_session(req.session_id or "default")
    neighborhoods: List[Neighborhood] = session["neighborhoods"]
    total_demand = sum(n.daily_orders for n in neighborhoods)

    last_opt: Optional[OptimizeResponse] = session.get("last_optimize")

    p_to_use = req.p if req.p and req.p >= 1 else 3
    if last_opt and last_opt.p and (req.p == 3 or req.p is None):
        p_to_use = last_opt.p

    # Determine safe base capacity if req.warehouse_capacity was left at default on large dataset
    min_needed_cap = (total_demand / max(1, p_to_use)) * 1.35
    base_cap = max(req.warehouse_capacity, min_needed_cap) if req.warehouse_capacity <= 4000.0 and total_demand > 10000.0 else req.warehouse_capacity
    effective_capacity = base_cap * max(1.0, req.demand_multiplier)

    candidates = [
        WarehouseCandidate(
            id=n.id,
            name=n.name,
            latitude=n.latitude,
            longitude=n.longitude,
            capacity=(n.capacity * max(1.0, req.demand_multiplier)) if (n.capacity is not None and n.capacity > 0) else effective_capacity,
        )
        for n in neighborhoods
    ]

    routing_mode = last_opt.assumptions.get("routing_mode", "haversine") if (last_opt and last_opt.assumptions) else "haversine"
    matrix = get_matrix(neighborhoods, mode=routing_mode)

    cost_per_km = last_opt.assumptions.get("cost_per_km", req.cost_per_km) if (last_opt and last_opt.assumptions) else req.cost_per_km
    fixed_cost = last_opt.assumptions.get("fixed_cost_per_warehouse", req.fixed_cost_per_warehouse) if (last_opt and last_opt.assumptions) else req.fixed_cost_per_warehouse

    res = run_scenario_simulation(
        base_neighborhoods=neighborhoods,
        base_candidates=candidates,
        matrix=matrix,
        demand_multiplier=req.demand_multiplier,
        failed_warehouse_id=req.warehouse_failure_id,
        p_warehouses=p_to_use,
        warehouse_capacity=effective_capacity,
        cost_per_km=cost_per_km,
        fixed_cost_per_warehouse=fixed_cost,
    )

    if not res.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Scenario Infeasible",
                "status": res.get("status"),
                "diagnostics": res.get("diagnostics", []),
            },
        )

    return ScenarioResponse(**res)


# 7. Explainability: "Why here?"
@router.get("/explain/{warehouse_id}", response_model=ExplainResponse)
def explain_warehouse_selection(warehouse_id: str, session_id: str = "default"):
    """Explains why a specific warehouse was chosen, its metrics, and the next-best rejected candidate."""
    session = _get_or_load_default_session(session_id)
    neighborhoods: List[Neighborhood] = session.get("neighborhoods", [])
    if not neighborhoods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No delivery zones loaded in current session. Ingest data first.",
        )

    last_opt: Optional[OptimizeResponse] = session.get("last_optimize")

    if last_opt is None:
        total_demand = sum(n.daily_orders for n in neighborhoods)
        p_val = min(3, len(neighborhoods))
        safe_cap = max(4000.0, (total_demand / max(1, p_val)) * 1.5)
        try:
            last_opt = optimize_network(OptimizeRequest(session_id=session_id, p=p_val, warehouse_capacity=safe_cap))
        except Exception as opt_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Please run network optimization before requesting explainability: {str(opt_err)}",
            )

    if not last_opt or not last_opt.warehouses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No warehouses are currently opened. Run network optimization first.",
        )

    matrix: Optional[DistanceMatrix] = session.get("last_matrix")
    if matrix is None:
        routing_mode = last_opt.assumptions.get("routing_mode", "haversine") if (last_opt and last_opt.assumptions) else "haversine"
        matrix = get_matrix(neighborhoods, mode=routing_mode)
        session["last_matrix"] = matrix

    total_demand = sum(n.daily_orders for n in neighborhoods)
    n_map = {n.id: n for n in neighborhoods}

    # Find the requested warehouse summary with graceful fallback to first open site
    target_w = next((w for w in last_opt.warehouses if w.warehouse_id == warehouse_id), None)
    if not target_w:
        target_w = last_opt.warehouses[0]
        warehouse_id = target_w.warehouse_id

    # Compute assigned neighborhoods and metrics
    assigned_items = [a for a in last_opt.assignments if a.warehouse_id == warehouse_id]
    w_dist_contrib = sum(a.daily_orders * a.distance_km for a in assigned_items)
    avg_dist = (w_dist_contrib / max(1, target_w.assigned_demand)) if target_w.assigned_demand > 0 else 0.0
    cost_contrib = round(w_dist_contrib * (last_opt.assumptions.get("cost_per_km", 1.25) / 50.0), 2)
    demand_pct = round((target_w.assigned_demand / max(1, total_demand)) * 100.0, 1)

    # Calculate Top 3 Key Demand Drivers
    demand_drivers: List[DemandDriver] = []
    sorted_assigned = sorted(assigned_items, key=lambda a: a.daily_orders, reverse=True)
    for a in sorted_assigned[:3]:
        demand_drivers.append(
            DemandDriver(
                neighborhood_id=a.neighborhood_id,
                name=a.neighborhood_name,
                daily_orders=a.daily_orders,
                distance_km=a.distance_km,
                weighted_ord_km=round(a.daily_orders * a.distance_km, 1),
            )
        )

    # Calculate order-km burden eliminated vs single-warehouse baseline
    burden_eliminated = 0.0
    if neighborhoods:
        best_cand_id = min(
            neighborhoods,
            key=lambda c: sum(n.daily_orders * matrix.distances_km.get(c.id, {}).get(n.id, 0.0) for n in neighborhoods)
        ).id
        baseline_dist_for_assigned = sum(
            a.daily_orders * matrix.distances_km.get(best_cand_id, {}).get(a.neighborhood_id, 0.0)
            for a in assigned_items
        )
        burden_eliminated = max(0.0, round(baseline_dist_for_assigned - w_dist_contrib, 1))

    # Compute next-best rejected candidate
    open_ids = {w.warehouse_id for w in last_opt.warehouses}
    rejected_candidates = [n for n in neighborhoods if n.id not in open_ids]

    next_best = None
    if rejected_candidates:
        cand_scores = []
        for c in rejected_candidates:
            score = sum(n.daily_orders * matrix.distances_km.get(c.id, {}).get(n.id, 0.0) for n in neighborhoods)
            cand_scores.append((c, score))

        cand_scores.sort(key=lambda x: x[1])
        best_rejected, best_rejected_score = cand_scores[0]

        target_score = sum(n.daily_orders * matrix.distances_km.get(target_w.warehouse_id, {}).get(n.id, 0.0) for n in neighborhoods)
        gap = round(abs(best_rejected_score - target_score), 1)

        next_best = NextBestCandidate(
            candidate_id=best_rejected.id,
            name=best_rejected.name,
            score_gap_weighted_km=gap,
            reason_rejected=(
                f"Candidate '{best_rejected.name}' ({best_rejected.id}) has {gap:,.0f} ord·km higher aggregate network distance "
                f"and is less central to the primary demand clusters in this sector without risking capacity saturation."
            ),
        )

    return ExplainResponse(
        warehouse_id=target_w.warehouse_id,
        name=target_w.name,
        latitude=target_w.latitude,
        longitude=target_w.longitude,
        demand_served=target_w.assigned_demand,
        demand_pct_of_total=demand_pct,
        capacity=target_w.capacity,
        capacity_utilization_pct=target_w.capacity_utilization_pct,
        neighborhoods_served_count=target_w.neighborhoods_count,
        weighted_distance_contribution=round(w_dist_contrib, 1),
        avg_distance_km=round(avg_dist, 2),
        cost_contribution=cost_contrib,
        burden_eliminated_km=burden_eliminated,
        key_demand_drivers=demand_drivers,
        next_best_rejected=next_best,
    )


# 8. Conversational Optimization Agent
@router.post("/agent/extract", response_model=AgentExtractResponse)
def extract_agent_parameters(req: AgentExtractRequest):
    """Extracts, clarifies, and validates structured CFLP/CVRP parameters from natural language instructions."""
    try:
        return process_agent_dialog(req)
    except Exception as e:
        logger.error("Error in conversational agent extraction: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Agent parameter extraction failed: {str(e)}",
        )


@router.post("/agent/generate-synthetic-data", response_model=UploadResponse)
def generate_synthetic_data(req: SyntheticDataRequest):
    """Generates realistic delivery zones using deterministic sampling over real public geodata
    (dr5hn/countries-states-cities-database under ODbL 1.0) with synthetic non-uniform demand.
    If a free-text prompt is provided, LLM extracts generation parameters.
    """
    try:
        zone_cnt = req.zone_count if req.zone_count is not None else 50
        pat = req.pattern_hint or req.pattern or "clustered"
        reg = req.city_hint or req.region_name or "Bengaluru"
        is_valid, errors, clean_df, meta = generate_synthetic_demand_dataset(
            zone_count=zone_cnt,
            pattern=pat,
            region_name=reg,
            prompt=req.prompt,
            scope=req.scope,
            region_filter=req.region_filter,
            seed=req.seed,
        )
        if not is_valid or clean_df is None:
            err_msg = errors[0] if errors else "Synthetic data generation failed"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE if any("API_KEY" in e or "unavailable" in e.lower() for e in errors) else status.HTTP_422_UNPROCESSABLE_ENTITY
            raise HTTPException(
                status_code=status_code,
                detail={"error": err_msg, "errors": errors},
            )

        session_id = req.session_id if req.session_id and req.session_id != "default" else str(uuid.uuid4())[:8]
        neighborhoods = [
            Neighborhood(
                id=str(row["neighborhood_id"]).strip(),
                name=str(row["name"]).strip(),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                daily_orders=float(row["daily_orders"]),
                capacity=float(row["capacity"]) if "capacity" in row and pd.notna(row["capacity"]) else None,
            )
            for _, row in clean_df.iterrows()
        ]

        badge_text = meta.get("badge_text", "[Real Locations, Synthetic Demand]")
        scope_val = meta.get("scope", req.scope or "single_city")
        seed_val = meta.get("seed", req.seed)
        source_label = meta.get("source_label", "Real Geodata & Synthetic Demand")

        SESSION_STORE[session_id] = {
            "neighborhoods": neighborhoods,
            "df": clean_df,
            "last_optimize": None,
            "last_matrix": None,
            "is_synthetic_ai": True,
            "dataset_type": "real_locations_synthetic_demand",
            "badge_text": badge_text,
            "scope": scope_val,
            "seed": seed_val,
            "source_label": source_label,
        }
        SOLVE_CACHE.clear()

        total_demand = sum(n.daily_orders for n in neighborhoods)
        preview_items = [
            NeighborhoodItem(
                neighborhood_id=n.id,
                name=n.name,
                latitude=n.latitude,
                longitude=n.longitude,
                daily_orders=n.daily_orders,
                capacity=n.capacity,
            )
            for n in neighborhoods
        ]

        return UploadResponse(
            session_id=session_id,
            neighborhood_count=len(neighborhoods),
            total_demand=round(total_demand, 1),
            preview=preview_items,
            is_synthetic_ai=True,
            dataset_type="real_locations_synthetic_demand",
            badge_text=badge_text,
            scope=scope_val,
            seed=seed_val,
            data_source=meta.get("data_source", "dr5hn/countries-states-cities-database (ODbL 1.0)"),
            source_label=source_label,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating synthetic dataset: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synthetic data generation failed: {str(e)}",
        )


@router.post("/agent/explain", response_model=AgentExplainResponse)
def explain_page_context(req: AgentExplainRequest):
    """Answers user queries grounded strictly in the real computed data of the current screen."""
    try:
        result = process_agent_explanation(
            page=req.page,
            message=req.message,
            page_context=req.page_context,
            history=req.history,
        )
        return AgentExplainResponse(**result)
    except Exception as e:
        logger.error("Error in agent page explain: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Explanation generation failed: {str(e)}",
        )


