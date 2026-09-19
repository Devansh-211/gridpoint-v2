"""Assignment mapping and data structuring between strategic CFLP and tactical CVRP.
"""

from typing import List, Dict
from core.models import Neighborhood, WarehouseCandidate, CFLPResult


def process_assignments(
    candidates: List[WarehouseCandidate],
    neighborhoods: List[Neighborhood],
    cflp_result: CFLPResult,
) -> List[WarehouseCandidate]:
    """Populates open status and assigned neighborhoods on WarehouseCandidate objects."""
    n_map = {n.id: n for n in neighborhoods}
    candidate_dict = {c.id: c for c in candidates}

    # Reset all candidates
    for c in candidate_dict.values():
        c.is_open = False
        c.assigned_neighborhood_ids = []
        c.total_assigned_demand = 0.0

    # Mark open warehouses
    for wid in cflp_result.open_warehouse_ids:
        if wid in candidate_dict:
            candidate_dict[wid].is_open = True

    # Assign neighborhoods
    for nid, wid in cflp_result.assignments.items():
        if wid in candidate_dict:
            candidate_dict[wid].assigned_neighborhood_ids.append(nid)
            demand = n_map[nid].daily_orders if nid in n_map else 0.0
            candidate_dict[wid].total_assigned_demand += demand

    return list(candidate_dict.values())
