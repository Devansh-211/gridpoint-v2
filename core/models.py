"""Domain models and data transfer objects for GRIDPOINT.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any


@dataclass
class Neighborhood:
    id: str
    name: str
    latitude: float
    longitude: float
    daily_orders: float
    capacity: Optional[float] = None  # Optional site-specific warehouse capacity override


@dataclass
class WarehouseCandidate:
    id: str
    name: str
    latitude: float
    longitude: float
    capacity: float
    is_open: bool = False
    assigned_neighborhood_ids: List[str] = field(default_factory=list)
    total_assigned_demand: float = 0.0


@dataclass
class VehicleRoute:
    warehouse_id: str
    vehicle_index: int
    stop_ids: List[str]
    stop_names: List[str]
    stop_demands: List[float]
    total_load: float
    capacity: float
    distance_km: float
    duration_hours: float
    route_coords: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def utilization(self) -> float:
        return (self.total_load / self.capacity) if self.capacity > 0 else 0.0


@dataclass
class CFLPResult:
    status: str
    solver_message: str
    is_optimal: bool
    open_warehouse_ids: List[str]
    assignments: Dict[str, str]  # neighborhood_id -> warehouse_id
    weighted_strategic_travel_time: float  # order-weighted travel time (order*minutes)
    solve_time_seconds: float
    diagnostics: List[str] = field(default_factory=list)


@dataclass
class CVRPWarehouseResult:
    warehouse_id: str
    routes: List[VehicleRoute]
    total_distance_km: float
    total_duration_hours: float
    vehicles_used: int
    avg_load_utilization: float
    total_demand_routed: float


@dataclass
class CostBreakdown:
    distance_cost: float
    time_cost: float
    vehicle_cost: float
    total_cost: float
    assumptions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemSummary:
    mode_label: str  # "Single-Warehouse Reference Baseline" or "Optimized Network (p Warehouses)"
    warehouses_open_count: int
    open_warehouses: List[WarehouseCandidate]
    assignments: Dict[str, str]
    cflp_result: CFLPResult
    cvrp_results: Dict[str, CVRPWarehouseResult]
    total_distance_km: float
    total_duration_hours: float
    vehicles_used: int
    avg_load_utilization: float
    weighted_strategic_travel_time: float
    cost_breakdown: CostBreakdown


@dataclass
class ComparisonMetrics:
    baseline: SystemSummary
    optimized: SystemSummary
    cost_delta: float
    cost_pct_change: float
    distance_delta_km: float
    distance_pct_change: float
    duration_delta_hours: float
    duration_pct_change: float
    vehicles_delta: int
    vehicles_pct_change: float
    weighted_time_delta: float
    weighted_time_pct_change: float
    utilization_delta: float
