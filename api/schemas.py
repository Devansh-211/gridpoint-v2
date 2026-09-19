"""Pydantic request and response models for GRIDPOINT REST API.
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# 1. Neighborhood models
class NeighborhoodItem(BaseModel):
    neighborhood_id: str
    name: str
    latitude: float
    longitude: float
    daily_orders: float
    capacity: Optional[float] = None


class NeighborhoodListRequest(BaseModel):
    neighborhoods: List[NeighborhoodItem]


class UploadResponse(BaseModel):
    session_id: str
    neighborhood_count: int
    total_demand: float
    preview: List[NeighborhoodItem]
    is_synthetic_ai: Optional[bool] = False
    dataset_type: Optional[str] = "demo"


# 2. Optimization models
class OptimizeRequest(BaseModel):
    session_id: Optional[str] = "default"
    p: int = Field(default=3, ge=1, le=10, description="Exact number of warehouses to open")
    warehouse_capacity: float = Field(default=4000.0, gt=0, description="Daily throughput capacity per site")
    radius_max_km: Optional[float] = Field(default=None, gt=0, description="Max service radius in kilometers")
    cost_per_km: float = Field(default=1.25, gt=0, description="Cost per kilometer of delivery travel")
    fixed_cost_per_warehouse: float = Field(default=300.0, ge=0, description="Daily facility lease cost per warehouse")
    routing_mode: str = Field(default="haversine", description="'haversine' or 'road_detour'")
    priority_preset: Optional[str] = Field(default="cost", description="'cost', 'speed', or 'sustainability'")
    include_cvrp: bool = Field(default=False, description="Whether to refine straight-line to CVRP vehicle routes")
    vehicle_capacity: int = Field(default=250, gt=0, description="Vehicle order payload capacity")
    vehicle_fixed_cost: float = Field(default=150.0, ge=0, description="Fixed cost penalty per vehicle dispatched")
    time_window_start: Optional[str] = Field(default=None, description="Start of delivery time window HH:MM")
    time_window_end: Optional[str] = Field(default=None, description="End of delivery time window HH:MM")


class WarehouseSummary(BaseModel):
    warehouse_id: str
    name: str
    latitude: float
    longitude: float
    capacity: float
    assigned_demand: float
    capacity_utilization_pct: float
    neighborhoods_count: int


class AssignmentItem(BaseModel):
    neighborhood_id: str
    neighborhood_name: str
    latitude: float
    longitude: float
    warehouse_id: str
    warehouse_name: str
    warehouse_latitude: float
    warehouse_longitude: float
    distance_km: float
    daily_orders: float


class OptimizeResponse(BaseModel):
    status: str
    solver_message: str
    is_optimal: bool
    p: int
    total_weighted_distance_km: float
    average_distance_km: float = 0.0
    total_delivery_cost: float
    total_infrastructure_cost: float
    combined_total_cost: float
    coverage_percentage: float = 100.0
    fast_delivery_coverage_pct: float = 0.0
    unserved_demand: float = 0.0
    estimated_co2_kg_per_day: float = 0.0
    co2_baseline_kg_per_day: float = 0.0
    co2_reduction_pct: float = 0.0
    estimated_monthly_savings: float = 0.0
    assumptions: Dict[str, Any]
    warehouses: List[WarehouseSummary]
    assignments: List[AssignmentItem]
    cvrp_summary: Optional[Dict[str, Any]] = None


# 3. Baseline & Comparison models
class SystemMetricSnapshot(BaseModel):
    label: str
    warehouses_count: int
    warehouses_open: List[str]
    total_delivery_cost: float
    total_infrastructure_cost: float
    combined_total_cost: float
    total_distance_km: float
    weighted_distance_km: float
    avg_capacity_utilization_pct: float
    estimated_co2_kg_per_day: float = 0.0


class CompareResponse(BaseModel):
    baseline: SystemMetricSnapshot
    optimized: SystemMetricSnapshot
    cost_delta: float
    cost_pct_change: float
    distance_delta_km: float
    distance_pct_change: float
    weighted_distance_delta: float
    weighted_distance_pct_change: float
    estimated_monthly_savings: float = 0.0
    co2_delta_kg: float = 0.0
    co2_pct_change: float = 0.0
    assumptions: Dict[str, Any]


# 4. Trade-off Curve models
class TradeoffPoint(BaseModel):
    p: int
    delivery_cost: float
    infrastructure_cost: float
    combined_cost: float
    weighted_distance_km: float
    is_feasible: bool
    warehouses_open: List[str]


class TradeoffResponse(BaseModel):
    points: List[TradeoffPoint]
    fixed_cost_per_warehouse: float
    cost_per_km: float


# 5. Scenario models
class ScenarioRequest(BaseModel):
    session_id: Optional[str] = "default"
    demand_multiplier: float = Field(default=1.2, gt=0, le=5.0)
    warehouse_failure_id: Optional[str] = None
    p: int = Field(default=3, ge=1, le=10)
    warehouse_capacity: float = Field(default=4000.0, gt=0)
    cost_per_km: float = Field(default=1.25, gt=0)
    fixed_cost_per_warehouse: float = Field(default=300.0, ge=0)


class ScenarioResponse(BaseModel):
    scenario_name: str
    demand_multiplier: float
    failed_warehouse_id: Optional[str]
    locations_changed: bool
    original_warehouses: List[str]
    scenario_warehouses: List[str]
    original_cost: float
    scenario_cost: float
    cost_pct_change: float
    original_weighted_distance: float
    scenario_weighted_distance: float
    weighted_distance_pct_change: float
    diagnostics: List[str] = []


# 6. Explainability models ("Why here?")
class DemandDriver(BaseModel):
    neighborhood_id: str
    name: str
    daily_orders: float
    distance_km: float
    weighted_ord_km: float


class NextBestCandidate(BaseModel):
    candidate_id: str
    name: str
    score_gap_weighted_km: float
    reason_rejected: str


class ExplainResponse(BaseModel):
    warehouse_id: str
    name: str
    latitude: float
    longitude: float
    demand_served: float
    demand_pct_of_total: float
    capacity: float
    capacity_utilization_pct: float
    neighborhoods_served_count: int
    weighted_distance_contribution: float
    avg_distance_km: float
    cost_contribution: float
    burden_eliminated_km: float = 0.0
    key_demand_drivers: List[DemandDriver] = []
    next_best_rejected: Optional[NextBestCandidate] = None


# 7. Conversational Agent models
class AgentMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class ExtractedParams(BaseModel):
    warehouse_count: Optional[int] = Field(default=None, description="Number of warehouses p (1-5)")
    warehouse_capacity: Optional[float] = Field(default=None, description="Throughput capacity (orders/day)")
    max_service_radius_km: Optional[float] = Field(default=None, description="Geographic service radius in km")
    cost_per_km: Optional[float] = Field(default=1.25, description="Cost per km in dollars")
    fixed_cost_per_warehouse: Optional[float] = Field(default=300.0, description="Daily facility lease cost")
    priority_preset: Optional[str] = Field(default="cost", description="'cost', 'speed', or 'sustainability'")
    include_cvrp: Optional[bool] = Field(default=False, description="Enable tactical vehicle tour optimization")
    vehicle_capacity: Optional[int] = Field(default=250, description="Payload capacity per vehicle")
    vehicle_fixed_cost: Optional[float] = Field(default=150.0, description="Fixed cost per vehicle")


class AgentExtractRequest(BaseModel):
    message: str
    history: List[AgentMessage] = []
    known_params: Optional[Dict[str, Any]] = None


class AgentExtractResponse(BaseModel):
    status: str = Field(description="'clarify', 'confirm', or 'error'")
    reply: str
    extracted_params: ExtractedParams
    missing_required: List[str] = []
    ready_to_optimize: bool = False
    defaults_applied: Optional[List[str]] = []
    warnings: Optional[List[str]] = []
    suggested_prompts: Optional[List[str]] = []
    confirmation_card: Optional[Dict[str, Any]] = None


# 8. Synthetic Data Generation models (Phase 3)
class SyntheticDataRequest(BaseModel):
    zone_count: Optional[int] = Field(default=50, description="Requested number of delivery zones (10-150)")
    pattern: Optional[str] = Field(default="clustered", description="'clustered', 'multi_hub', or 'corridor'")
    pattern_hint: Optional[str] = Field(default=None)
    region_name: Optional[str] = Field(default="Bengaluru Metro", description="City/region naming flavor")
    city_hint: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default="default")


# 9. Grounded Explain Mode models (Phase 4)
class AgentExplainRequest(BaseModel):
    page: str = Field(description="Active page identifier e.g. 'viewResults', 'viewScenarios', 'viewDisruption', 'viewFleet', 'viewAnalytics'")
    message: str = Field(description="User question about the current screen")
    page_context: Dict[str, Any] = Field(description="Real computed metrics, tables, and parameters currently on this screen")
    history: Optional[List[AgentMessage]] = Field(default=[])


class AgentExplainResponse(BaseModel):
    reply: str
    page: str
    grounded: bool = True
    grounded_facts: List[str] = []
    suggested_followups: List[str] = []


