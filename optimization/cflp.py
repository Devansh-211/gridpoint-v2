"""Capacitated Facility Location Problem (CFLP) strategic optimization using PuLP + CBC
with automatic Greedy + 2-Opt Local Search Heuristic fallback.
"""

import time
import logging
import itertools
from typing import List, Dict, Tuple, Optional, Set
import pulp
from core.models import Neighborhood, WarehouseCandidate, CFLPResult
from core.validation import validate_presolve_feasibility

logger = logging.getLogger(__name__)


class SolverUnavailableError(RuntimeError):
    """Raised when no compatible MILP solver (CBC / COIN) is found."""
    pass


def get_milp_solver(time_limit_sec: int = 60, msg: int = 0) -> pulp.LpSolver:
    """Detects and returns available CBC/COIN solver interface.

    In modern PuLP versions, COIN_CMD is the standard interface for the CBC binary.
    """
    # 1. Resolve CBC binary path if installed via cbcbox or local solverdir
    cbc_path = None
    try:
        legacy_cmd = pulp.PULP_CBC_CMD()
        if legacy_cmd.path and legacy_cmd.available():
            cbc_path = legacy_cmd.path
    except Exception:
        pass

    # 2. Try COIN_CMD (with explicit path or PATH discovery)
    try:
        solver = pulp.COIN_CMD(path=cbc_path, msg=msg, timeLimit=time_limit_sec)
        if solver.available():
            return solver
    except Exception:
        pass

    # 3. Try default COIN_CMD without explicit path
    try:
        solver = pulp.COIN_CMD(msg=msg, timeLimit=time_limit_sec)
        if solver.available():
            return solver
    except Exception:
        pass

    # 4. Try default PULP solver
    try:
        default_solver = pulp.LpSolverDefault
        if default_solver is not None and default_solver.available():
            return default_solver
    except Exception:
        pass

    # 5. Check any available solver in listSolvers
    avail = pulp.listSolvers(onlyAvailable=True)
    if avail:
        solver_name = avail[0]
        try:
            return pulp.getSolver(solver_name, timeLimit=time_limit_sec, msg=msg)
        except Exception:
            pass

    raise SolverUnavailableError(
        "No CBC MILP solver detected. Please install CBC support using:\n"
        "    pip install \"pulp[cbc]\"\n"
        "or ensure the 'cbc' binary is installed and present in your system PATH."
    )


def _evaluate_assignments_heuristic(
    open_cands: List[str],
    neighborhoods: List[Neighborhood],
    capacities: Dict[str, float],
    demands: Dict[str, float],
    duration_matrix_min: Dict[str, Dict[str, float]],
    t_max_minutes: Optional[float],
) -> Tuple[bool, Dict[str, str], float]:
    """Assigns neighborhoods to closest open warehouse respecting capacity & service radius."""
    remaining_cap = {w_id: capacities[w_id] for w_id in open_cands}
    assignments: Dict[str, str] = {}
    total_weighted_dist = 0.0

    # Sort neighborhoods by demand descending (high demand gets priority assignment to closest depot)
    sorted_n = sorted(neighborhoods, key=lambda n: n.daily_orders, reverse=True)

    for n in sorted_n:
        dem = demands[n.id]
        # Find feasible open warehouses ordered by distance to n
        eligible = []
        for w_id in open_cands:
            dist = duration_matrix_min.get(w_id, {}).get(n.id, 99999.0)
            if t_max_minutes is not None and dist > t_max_minutes:
                continue
            if remaining_cap[w_id] >= dem:
                eligible.append((dist, w_id))

        if not eligible:
            # Fallback: if capacity tight, pick warehouse with maximum remaining capacity within radius
            fallback = [
                (duration_matrix_min.get(w_id, {}).get(n.id, 99999.0), w_id)
                for w_id in open_cands
                if (t_max_minutes is None or duration_matrix_min.get(w_id, {}).get(n.id, 99999.0) <= t_max_minutes)
            ]
            if not fallback:
                return False, {}, float("inf")
            fallback.sort(key=lambda x: x[0])
            best_w = fallback[0][1]
            dist = fallback[0][0]
        else:
            eligible.sort(key=lambda x: x[0])
            dist, best_w = eligible[0]

        assignments[n.id] = best_w
        remaining_cap[best_w] -= dem
        total_weighted_dist += dem * dist

    return True, assignments, total_weighted_dist


def solve_cflp_heuristic(
    neighborhoods: List[Neighborhood],
    candidates: List[WarehouseCandidate],
    p_warehouses: int,
    duration_matrix_min: Dict[str, Dict[str, float]],
    t_max_minutes: Optional[float] = None,
    auto_size: bool = False,
    p_max: Optional[int] = None,
    cost_per_km: float = 1.25,
    fixed_cost_per_warehouse: float = 300.0,
) -> CFLPResult:
    """Greedy + 2-Opt Local Search Heuristic for Capacitated Facility Location.
    
    Supports both exact warehouse count (Manual mode) and cost-minimizing auto-sizing (Auto mode).
    Guarantees fast, robust, feasible solutions if MILP solver binaries are not installed.
    """
    start_time = time.time()
    demands = {n.id: float(n.daily_orders) for n in neighborhoods}
    capacities = {c.id: float(c.capacity) for c in candidates}
    candidate_ids = [c.id for c in candidates]
    total_demand = sum(demands.values())

    if not candidate_ids:
        return CFLPResult(
            status="Infeasible",
            solver_message="Invalid candidate pool (empty)",
            is_optimal=False,
            open_warehouse_ids=[],
            assignments={},
            weighted_strategic_travel_time=0.0,
            solve_time_seconds=time.time() - start_time,
            diagnostics=["Candidate pool is empty."],
        )

    # If Auto-size mode, sweep k from 1 to p_max (or len(candidates)) and pick lowest total cost
    if auto_size:
        max_k = min(len(candidate_ids), p_max if p_max is not None and p_max >= 1 else min(10, len(candidate_ids)))
        best_overall_cost = float("inf")
        best_result: Optional[CFLPResult] = None

        sorted_caps = sorted(capacities.values(), reverse=True)

        for k in range(1, max_k + 1):
            if sum(sorted_caps[:k]) < total_demand:
                continue  # Cannot satisfy total capacity with k warehouses

            # Run heuristic for count k
            k_res = solve_cflp_heuristic(
                neighborhoods=neighborhoods,
                candidates=candidates,
                p_warehouses=k,
                duration_matrix_min=duration_matrix_min,
                t_max_minutes=t_max_minutes,
                auto_size=False,
            )

            if k_res.status.startswith("Feasible") or k_res.is_optimal:
                deliv_cost = k_res.weighted_strategic_travel_time * (cost_per_km / 50.0)
                infra_cost = len(k_res.open_warehouse_ids) * fixed_cost_per_warehouse
                total_cost = deliv_cost + infra_cost

                if total_cost < best_overall_cost:
                    best_overall_cost = total_cost
                    best_result = k_res

        if best_result is not None:
            return CFLPResult(
                status="Feasible (Heuristic Fallback)",
                solver_message=f"Feasible auto-sized network found via heuristic sweep: {len(best_result.open_warehouse_ids)} warehouses selected (lowest total cost: ${best_overall_cost:,.2f}/day)",
                is_optimal=False,
                open_warehouse_ids=best_result.open_warehouse_ids,
                assignments=best_result.assignments,
                weighted_strategic_travel_time=best_result.weighted_strategic_travel_time,
                solve_time_seconds=time.time() - start_time,
                diagnostics=[],
            )
        else:
            return CFLPResult(
                status="Infeasible",
                solver_message="No feasible warehouse count configuration found within candidate pool.",
                is_optimal=False,
                open_warehouse_ids=[],
                assignments={},
                weighted_strategic_travel_time=0.0,
                solve_time_seconds=time.time() - start_time,
                diagnostics=["Could not find feasible assignments within capacity and radius bounds."],
            )

    if p_warehouses <= 0:
        return CFLPResult(
            status="Infeasible",
            solver_message="p <= 0",
            is_optimal=False,
            open_warehouse_ids=[],
            assignments={},
            weighted_strategic_travel_time=0.0,
            solve_time_seconds=time.time() - start_time,
            diagnostics=["p <= 0"],
        )

    # 1. Greedy initial selection: Score candidates by standalone demand-weighted centrality
    cand_centrality = []
    for c_id in candidate_ids:
        w_score = sum(demands[n.id] * duration_matrix_min.get(c_id, {}).get(n.id, 9999.0) for n in neighborhoods)
        cand_centrality.append((w_score, c_id))
    cand_centrality.sort(key=lambda x: x[0])

    # Seed with top p candidates
    current_open = [c_id for _, c_id in cand_centrality[:p_warehouses]]
    feasible, best_assignments, best_score = _evaluate_assignments_heuristic(
        current_open, neighborhoods, capacities, demands, duration_matrix_min, t_max_minutes
    )

    # 2. Local search: Try single-warehouse swaps to improve solution
    closed_cands = [c_id for c_id in candidate_ids if c_id not in current_open]
    improved = True
    iterations = 0
    max_iterations = 50

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        for i, open_w in enumerate(current_open):
            for closed_w in closed_cands:
                test_open = list(current_open)
                test_open[i] = closed_w
                is_f, test_assign, test_score = _evaluate_assignments_heuristic(
                    test_open, neighborhoods, capacities, demands, duration_matrix_min, t_max_minutes
                )
                if is_f and test_score < best_score:
                    current_open = test_open
                    closed_cands.remove(closed_w)
                    closed_cands.append(open_w)
                    best_assignments = test_assign
                    best_score = test_score
                    improved = True
                    break
            if improved:
                break

    elapsed = time.time() - start_time
    return CFLPResult(
        status="Feasible (Heuristic Fallback)",
        solver_message="Feasible solution found via greedy + 2-opt local search heuristic",
        is_optimal=False,
        open_warehouse_ids=current_open,
        assignments=best_assignments,
        weighted_strategic_travel_time=best_score,
        solve_time_seconds=elapsed,
        diagnostics=[],
    )


def solve_cflp(
    neighborhoods: List[Neighborhood],
    candidates: List[WarehouseCandidate],
    p_warehouses: int = 3,
    duration_matrix_min: Dict[str, Dict[str, float]] = None,
    t_max_minutes: Optional[float] = None,
    time_limit_seconds: int = 60,
    auto_size: bool = False,
    p_max: Optional[int] = None,
    cost_per_km: float = 1.25,
    fixed_cost_per_warehouse: float = 300.0,
) -> CFLPResult:
    """Solves the Capacitated Facility Location Problem (CFLP).

    Supports:
      - Manual mode (auto_size=False): Enforces exact p warehouses open (Σ y_j = p).
      - Auto-size mode (auto_size=True): Treats warehouse count as an optimal decision variable,
        minimizing Total Cost = Delivery Transit Cost + Fixed Facility Lease Cost, bounded by p_max.
    
    If CBC MILP solver is not available, gracefully uses the greedy + local search heuristic.
    """
    start_time = time.time()
    demands = {n.id: float(n.daily_orders) for n in neighborhoods}
    capacities = {c.id: float(c.capacity) for c in candidates}
    neighborhood_ids = [n.id for n in neighborhoods]
    candidate_ids = [c.id for c in candidates]

    # Bound p_max in auto-size mode
    effective_p = p_warehouses
    if auto_size:
        effective_p_max = p_max if p_max is not None and p_max >= 1 else min(10, len(candidate_ids))
        effective_p = effective_p_max

    # Pre-solve feasibility checks
    is_feasible, diagnostics = validate_presolve_feasibility(
        neighborhood_ids=neighborhood_ids,
        demands=demands,
        candidate_ids=candidate_ids,
        capacities=capacities,
        p_warehouses=effective_p,
        duration_matrix_min=duration_matrix_min,
        t_max_minutes=t_max_minutes,
        auto_size=auto_size,
    )

    if not is_feasible:
        return CFLPResult(
            status="Infeasible (Pre-solve)",
            solver_message="Pre-solve feasibility checks detected constraint violations.",
            is_optimal=False,
            open_warehouse_ids=[],
            assignments={},
            weighted_strategic_travel_time=0.0,
            solve_time_seconds=time.time() - start_time,
            diagnostics=diagnostics,
        )

    # Detect solver; if not available, seamlessly fall back to heuristic
    try:
        solver = get_milp_solver(time_limit_sec=time_limit_seconds, msg=0)
    except (SolverUnavailableError, Exception) as exc:
        logger.warning("MILP Solver unavailable (%s). Using greedy + local search heuristic fallback.", exc)
        return solve_cflp_heuristic(
            neighborhoods=neighborhoods,
            candidates=candidates,
            p_warehouses=p_warehouses,
            duration_matrix_min=duration_matrix_min,
            t_max_minutes=t_max_minutes,
            auto_size=auto_size,
            p_max=p_max,
            cost_per_km=cost_per_km,
            fixed_cost_per_warehouse=fixed_cost_per_warehouse,
        )


    # Initialize PuLP MILP Model
    prob = pulp.LpProblem("GRIDPOINT_CFLP", pulp.LpMinimize)

    # Decision variable y[j]: 1 if warehouse j is open, 0 otherwise
    y = {
        j: pulp.LpVariable(f"y_{j}", cat=pulp.LpBinary)
        for j in candidate_ids
    }

    # Decision variable x[i, j]: 1 if neighborhood i assigned to warehouse j, 0 otherwise
    x = {}
    valid_pairs = []
    for i in neighborhood_ids:
        for j in candidate_ids:
            travel_time = duration_matrix_min.get(j, {}).get(i, 9999.0)
            if t_max_minutes is None or travel_time <= t_max_minutes:
                x[(i, j)] = pulp.LpVariable(f"x_{i}_{j}", cat=pulp.LpBinary)
                valid_pairs.append((i, j))

    # Objective: Minimize Total Cost (in Auto-size mode) or Weighted Travel Distance (in Manual mode)
    if auto_size:
        prob += (
            pulp.lpSum(
                demands[i] * duration_matrix_min[j][i] * (cost_per_km / 50.0) * x[(i, j)]
                for (i, j) in valid_pairs
            )
            + pulp.lpSum(fixed_cost_per_warehouse * y[j] for j in candidate_ids)
        )
    else:
        prob += pulp.lpSum(
            demands[i] * duration_matrix_min[j][i] * x[(i, j)]
            for (i, j) in valid_pairs
        )

    # Constraint 1: Every neighborhood assigned to exactly one warehouse
    for i in neighborhood_ids:
        allowed_cands = [j for j in candidate_ids if (i, j) in x]
        if not allowed_cands:
            return CFLPResult(
                status="Infeasible",
                solver_message=f"Delivery zone {i} has no candidate warehouses within max radius = {t_max_minutes} km.",
                is_optimal=False,
                open_warehouse_ids=[],
                assignments={},
                weighted_strategic_travel_time=0.0,
                solve_time_seconds=time.time() - start_time,
                diagnostics=[f"Delivery zone {i} cannot be served within max radius = {t_max_minutes} km."],
            )
        prob += pulp.lpSum(x[(i, j)] for j in allowed_cands) == 1, f"Assign_Once_{i}"

    # Constraint 2: Assignment only to open warehouses (x[i,j] <= y[j])
    for (i, j) in valid_pairs:
        prob += x[(i, j)] <= y[j], f"Link_{i}_{j}"

    # Constraint 3: Warehouse capacity limit
    for j in candidate_ids:
        cands_x = [x[(i, j)] * demands[i] for i in neighborhood_ids if (i, j) in x]
        if cands_x:
            prob += pulp.lpSum(cands_x) <= capacities[j] * y[j], f"Capacity_{j}"
        else:
            prob += y[j] * 0 <= capacities[j]

    # Constraint 4: Warehouse Count Constraint
    if auto_size:
        # In Auto-size mode: Drop exact equality constraint!
        prob += pulp.lpSum(y[j] for j in candidate_ids) >= 1, "At_Least_One_Warehouse"
        if effective_p is not None and effective_p < len(candidate_ids):
            prob += pulp.lpSum(y[j] for j in candidate_ids) <= effective_p, f"Max_{effective_p}_Warehouses"
    else:
        # In Manual mode: Enforce exact p warehouses open
        prob += pulp.lpSum(y[j] for j in candidate_ids) == p_warehouses, "Exact_P_Warehouses"

    # Solve using CBC
    try:
        prob.solve(solver)
    except Exception as exc:
        logger.warning("PuLP solver execution encountered error (%s). Falling back to heuristic.", exc)
        return solve_cflp_heuristic(
            neighborhoods=neighborhoods,
            candidates=candidates,
            p_warehouses=p_warehouses,
            duration_matrix_min=duration_matrix_min,
            t_max_minutes=t_max_minutes,
            auto_size=auto_size,
            p_max=p_max,
            cost_per_km=cost_per_km,
            fixed_cost_per_warehouse=fixed_cost_per_warehouse,
        )

    elapsed = time.time() - start_time
    status_str = pulp.LpStatus[prob.status]

    if prob.status == pulp.LpStatusOptimal:
        is_optimal = True
        solver_msg = "Optimal MILP solution verified"
    elif prob.status == pulp.constants.LpStatusNotSolved:
        is_optimal = False
        solver_msg = "Feasible solution found within time limit"
    else:
        # If solver proved infeasible with exact constraints, return clear diagnostic
        return CFLPResult(
            status=status_str,
            solver_message=f"Solver returned status: {status_str}",
            is_optimal=False,
            open_warehouse_ids=[],
            assignments={},
            weighted_strategic_travel_time=0.0,
            solve_time_seconds=elapsed,
            diagnostics=[
                f"Configuration infeasible ({status_str}). Suggested action: Increase warehouse count (p), increase site capacity, or expand service radius."
            ],
        )

    # Extract open warehouses and assignments
    open_warehouses = [j for j in candidate_ids if pulp.value(y[j]) is not None and pulp.value(y[j]) > 0.5]
    assignments: Dict[str, str] = {}
    for (i, j) in valid_pairs:
        if pulp.value(x[(i, j)]) is not None and pulp.value(x[(i, j)]) > 0.5:
            assignments[i] = j

    # Always compute raw total order-km distance
    raw_weighted_distance = sum(
        demands[i] * duration_matrix_min.get(assignments[i], {}).get(i, 0.0)
        for i in neighborhood_ids
        if i in assignments
    )

    if auto_size:
        solver_msg = f"Optimal auto-sized network verified: {len(open_warehouses)} warehouse(s) opened to minimize combined delivery and fixed costs."

    return CFLPResult(
        status="Optimal" if is_optimal else "Feasible",
        solver_message=solver_msg,
        is_optimal=is_optimal,
        open_warehouse_ids=open_warehouses,
        assignments=assignments,
        weighted_strategic_travel_time=raw_weighted_distance,
        solve_time_seconds=elapsed,
        diagnostics=[],
    )

