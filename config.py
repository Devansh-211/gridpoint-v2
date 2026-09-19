"""GRIDPOINT Configuration & Default Operational Parameters.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class AppConfig:
    # Cost model defaults
    DEFAULT_COST_PER_KM: float = 1.25       # Currency units per km of vehicle travel
    DEFAULT_COST_PER_HOUR: float = 18.00    # Driver/operational cost per hour of travel
    DEFAULT_FIXED_VEHICLE_COST: float = 45.00  # Fixed asset/dispatch cost per vehicle deployed

    # Fleet defaults
    DEFAULT_VEHICLE_CAPACITY: int = 250     # Max daily orders a single delivery vehicle can carry
    VEHICLE_ROUTING_TIME_LIMIT: int = 5     # OR-Tools solve time limit per warehouse (seconds)
    VEHICLE_BUFFER_COUNT: int = 2           # Fleet upper-bound buffer added to ceil(demand / cap)

    # Facility Location Defaults
    DEFAULT_WAREHOUSE_COUNT: int = 3        # Number of warehouses to open (p)
    DEFAULT_WAREHOUSE_CAPACITY: int = 4000  # Default capacity per warehouse site
    DEFAULT_MAX_SERVICE_TIME: float = 45.0  # Max driving time radius T_max in minutes

    # OSRM Service Settings
    DEFAULT_OSRM_URL: str = "https://router.project-osrm.org"
    OSRM_MAX_COORDINATES_PER_CHUNK: int = 80
    OSRM_REQUEST_TIMEOUT_SECONDS: int = 12
    OSRM_MAX_RETRIES: int = 3
    OSRM_BACKOFF_FACTOR: float = 1.5

    # Traffic simulation presets (multipliers applied to road travel time)
    TRAFFIC_PRESETS: Dict[str, float] = None

    def __post_init__(self):
        if self.TRAFFIC_PRESETS is None:
            object.__setattr__(
                self,
                "TRAFFIC_PRESETS",
                {
                    "Standard (1.0x)": 1.0,
                    "Moderate Congestion (1.25x)": 1.25,
                    "Peak Traffic (1.5x)": 1.5,
                },
            )


CONFIG = AppConfig()
