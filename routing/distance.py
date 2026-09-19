"""Distance and duration matrix calculation with Haversine default and OSRM road-network support.
"""

import math
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from core.models import Neighborhood
from routing.osrm import OSRMClient


@dataclass
class DistanceMatrix:
    neighborhood_ids: List[str]
    distances_km: Dict[str, Dict[str, float]]
    durations_min: Dict[str, Dict[str, float]]
    durations_hours: Dict[str, Dict[str, float]]
    mode: str  # "haversine", "road_detour", "osrm"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance in kilometers between two points."""
    r = 6371.0  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def get_matrix(
    neighborhoods: List[Neighborhood],
    mode: str = "haversine",
    avg_speed_kmh: float = 25.0,
    detour_factor: float = 1.35,
    osrm_client: Optional[OSRMClient] = None,
) -> DistanceMatrix:
    """Computes distance and duration matrices across all neighborhoods.

    By default, computes exact Haversine straight-line distance with constant average speed.
    This provides zero-network-dependency, instant, deterministic matrix calculation for the demo.
    """
    n_ids = [n.id for n in neighborhoods]
    n = len(neighborhoods)

    distances_km: Dict[str, Dict[str, float]] = {}
    durations_min: Dict[str, Dict[str, float]] = {}
    durations_hours: Dict[str, Dict[str, float]] = {}

    if mode == "osrm" and osrm_client is not None:
        try:
            coords = [(n.latitude, n.longitude) for n in neighborhoods]
            raw_dist_m, raw_dur_s = osrm_client.get_table_matrix(coords)
            for i, id_i in enumerate(n_ids):
                distances_km[id_i] = {}
                durations_min[id_i] = {}
                durations_hours[id_i] = {}
                for j, id_j in enumerate(n_ids):
                    d_km = round(raw_dist_m[i][j] / 1000.0, 3)
                    t_min = round(raw_dur_s[i][j] / 60.0, 2)
                    distances_km[id_i][id_j] = d_km
                    durations_min[id_i][id_j] = t_min
                    durations_hours[id_i][id_j] = round(t_min / 60.0, 4)
            return DistanceMatrix(
                neighborhood_ids=n_ids,
                distances_km=distances_km,
                durations_min=durations_min,
                durations_hours=durations_hours,
                mode="osrm",
            )
        except Exception:
            # Fallback to haversine if OSRM fails
            mode = "haversine_fallback"

    factor = detour_factor if mode == "road_detour" else 1.0
    actual_mode = "road_detour" if mode == "road_detour" else "haversine"

    for i in range(n):
        id_i = neighborhoods[i].id
        distances_km[id_i] = {}
        durations_min[id_i] = {}
        durations_hours[id_i] = {}

        for j in range(n):
            id_j = neighborhoods[j].id
            if i == j:
                distances_km[id_i][id_j] = 0.0
                durations_min[id_i][id_j] = 0.0
                durations_hours[id_i][id_j] = 0.0
            else:
                dist = haversine_km(
                    neighborhoods[i].latitude,
                    neighborhoods[i].longitude,
                    neighborhoods[j].latitude,
                    neighborhoods[j].longitude,
                ) * factor
                dur_min = (dist / avg_speed_kmh) * 60.0

                distances_km[id_i][id_j] = round(dist, 3)
                durations_min[id_i][id_j] = round(dur_min, 2)
                durations_hours[id_i][id_j] = round(dur_min / 60.0, 4)

    return DistanceMatrix(
        neighborhood_ids=n_ids,
        distances_km=distances_km,
        durations_min=durations_min,
        durations_hours=durations_hours,
        mode=actual_mode,
    )
