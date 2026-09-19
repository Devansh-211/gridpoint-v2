"""Road network distance and duration matrix manager with caching and offline demo bundling.
"""

import json
import os
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from core.models import Neighborhood
from routing.osrm import OSRMClient


@dataclass
class NetworkMatrix:
    neighborhood_ids: List[str]
    distances_km: Dict[str, Dict[str, float]]
    durations_min: Dict[str, Dict[str, float]]
    durations_hours: Dict[str, Dict[str, float]]
    mode: str  # "DEMO" or "LIVE"
    traffic_multiplier: float = 1.0


def _compute_dataset_hash(neighborhoods: List[Neighborhood]) -> str:
    hasher = hashlib.sha256()
    for n in sorted(neighborhoods, key=lambda x: x.id):
        hasher.update(f"{n.id}:{n.latitude:.5f}:{n.longitude:.5f}".encode("utf-8"))
    return hasher.hexdigest()[:16]


def generate_deterministic_road_matrix(
    neighborhoods: List[Neighborhood],
    detour_factor: float = 1.35,
    avg_speed_kmh: float = 24.0,
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    """Generates a realistic, deterministic road-network distance and duration matrix

    Uses actual geographical coordinates with an empirical urban road detour factor (1.35x)
    and realistic urban commercial vehicle speed (24 km/h) for Bengaluru road conditions.
    """
    n = len(neighborhoods)
    dist_km: Dict[str, Dict[str, float]] = {}
    dur_min: Dict[str, Dict[str, float]] = {}

    for i in range(n):
        id_i = neighborhoods[i].id
        dist_km[id_i] = {}
        dur_min[id_i] = {}

        for j in range(n):
            id_j = neighborhoods[j].id
            if i == j:
                dist_km[id_i][id_j] = 0.0
                dur_min[id_i][id_j] = 0.0
            else:
                lat1, lon1 = neighborhoods[i].latitude, neighborhoods[i].longitude
                lat2, lon2 = neighborhoods[j].latitude, neighborhoods[j].longitude
                straight_m = OSRMClient._haversine_meters(lat1, lon1, lat2, lon2)
                road_km = (straight_m * detour_factor) / 1000.0
                road_min = (road_km / avg_speed_kmh) * 60.0
                dist_km[id_i][id_j] = round(road_km, 3)
                dur_min[id_i][id_j] = round(road_min, 2)

    return dist_km, dur_min


def load_bundled_offline_matrix(
    matrix_filepath: str,
) -> Optional[Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]]:
    """Loads pre-computed deterministic road matrix from JSON if present."""
    if not os.path.exists(matrix_filepath):
        return None

    try:
        with open(matrix_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("distances_km"), data.get("durations_min")
    except Exception:
        return None


def save_offline_matrix(
    matrix_filepath: str,
    distances_km: Dict[str, Dict[str, float]],
    durations_min: Dict[str, Dict[str, float]],
):
    """Saves matrix to JSON file."""
    os.makedirs(os.path.dirname(matrix_filepath), exist_ok=True)
    with open(matrix_filepath, "w", encoding="utf-8") as f:
        json.dump({"distances_km": distances_km, "durations_min": durations_min}, f, indent=2)


def build_network_matrix(
    neighborhoods: List[Neighborhood],
    mode: str = "DEMO",
    osrm_client: Optional[OSRMClient] = None,
    traffic_multiplier: float = 1.0,
    offline_json_path: str = "data/sample_matrix_offline.json",
) -> NetworkMatrix:
    """Builds or fetches distance (km) and duration (min/hours) matrices.

    In DEMO mode, loads deterministic bundled matrix or generates deterministic road matrix.
    In LIVE mode, queries OSRM Table service.
    """
    n_ids = [n.id for n in neighborhoods]
    distances_km: Dict[str, Dict[str, float]] = {}
    durations_min: Dict[str, Dict[str, float]] = {}

    if mode == "DEMO":
        # Check bundled offline matrix first
        bundled = load_bundled_offline_matrix(offline_json_path)
        if bundled is not None and all(nid in bundled[0] for nid in n_ids):
            base_dist, base_dur = bundled
        else:
            base_dist, base_dur = generate_deterministic_road_matrix(neighborhoods)
            # Save for subsequent instant offline reloads
            save_offline_matrix(offline_json_path, base_dist, base_dur)

        distances_km = base_dist
        durations_min = base_dur
        actual_mode = "DEMO"
    else:
        # LIVE OSRM mode
        if osrm_client is None:
            osrm_client = OSRMClient()

        coords = [(n.latitude, n.longitude) for n in neighborhoods]
        try:
            raw_dist_m, raw_dur_s = osrm_client.get_table_matrix(coords)
            for i, id_i in enumerate(n_ids):
                distances_km[id_i] = {}
                durations_min[id_i] = {}
                for j, id_j in enumerate(n_ids):
                    distances_km[id_i][id_j] = round(raw_dist_m[i][j] / 1000.0, 3)
                    durations_min[id_i][id_j] = round(raw_dur_s[i][j] / 60.0, 2)
            actual_mode = "LIVE"
        except Exception as exc:
            # If live fails, fall back to DEMO road matrix with explicit notification
            base_dist, base_dur = generate_deterministic_road_matrix(neighborhoods)
            distances_km = base_dist
            durations_min = base_dur
            actual_mode = "DEMO (Fallback: OSRM Unreachable)"

    # Apply traffic multiplier to durations
    adj_durations_min: Dict[str, Dict[str, float]] = {}
    adj_durations_hours: Dict[str, Dict[str, float]] = {}

    for id_i in n_ids:
        adj_durations_min[id_i] = {}
        adj_durations_hours[id_i] = {}
        for id_j in n_ids:
            adj_min = durations_min[id_i][id_j] * traffic_multiplier
            adj_durations_min[id_i][id_j] = round(adj_min, 2)
            adj_durations_hours[id_i][id_j] = round(adj_min / 60.0, 4)

    return NetworkMatrix(
        neighborhood_ids=n_ids,
        distances_km=distances_km,
        durations_min=adj_durations_min,
        durations_hours=adj_durations_hours,
        mode=actual_mode,
        traffic_multiplier=traffic_multiplier,
    )
