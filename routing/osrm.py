"""OSRM API integration client (Table service and Route service) with chunking, retry, and backoff.
"""

import time
import logging
from typing import List, Tuple, Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class OSRMClient:
    """Client for querying OSRM (Open Source Routing Machine) Table and Route services."""

    def __init__(
        self,
        base_url: str = "https://router.project-osrm.org",
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "GRIDPOINT-SupplyChainOptimizer/1.0"})

    def _execute_request_with_retry(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes HTTP GET with exponential backoff on errors and rate limits."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "Ok":
                        return data
                    else:
                        raise ValueError(f"OSRM returned error code: {data.get('code')}, message: {data.get('message')}")
                elif response.status_code == 429:
                    sleep_time = (self.backoff_factor ** attempt) * 2.0
                    logger.warning(f"OSRM 429 rate limit hit. Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    response.raise_for_status()
            except (requests.RequestException, ValueError) as exc:
                last_exception = exc
                sleep_time = self.backoff_factor ** attempt
                logger.warning(f"OSRM request failed (attempt {attempt+1}/{self.max_retries}): {exc}. Sleeping {sleep_time:.1f}s...")
                time.sleep(sleep_time)

        raise RuntimeError(f"OSRM query failed after {self.max_retries} attempts: {last_exception}")

    def get_table_matrix(
        self,
        coords: List[Tuple[float, float]],  # list of (lat, lon)
    ) -> Tuple[List[List[float]], List[List[float]]]:
        """Fetches all-to-all driving distance (meters) and duration (seconds) matrix.

        OSRM coordinate format: {longitude},{latitude}
        Returns:
            (distance_matrix_meters, duration_matrix_seconds)
        """
        n = len(coords)
        if n < 2:
            return [[0.0]], [[0.0]]

        # Format coordinates as "lon,lat"
        coord_strings = [f"{lon:.6f},{lat:.6f}" for lat, lon in coords]

        # Check if single request is within limit (<= 80 coordinates)
        if n <= 80:
            coords_path = ";".join(coord_strings)
            url = f"{self.base_url}/table/v1/driving/{coords_path}"
            params = {"annotations": "duration,distance"}
            data = self._execute_request_with_retry(url, params)

            distances = data.get("distances", [])
            durations = data.get("durations", [])
            return self._sanitize_matrix(distances, durations, coords)
        else:
            # Chunk into blocks: sources and destinations
            chunk_size = 50
            full_distances = [[0.0] * n for _ in range(n)]
            full_durations = [[0.0] * n for _ in range(n)]

            for i in range(0, n, chunk_size):
                i_end = min(i + chunk_size, n)
                for j in range(0, n, chunk_size):
                    j_end = min(j + chunk_size, n)

                    # Query sub-block
                    sub_coords = coord_strings[i:i_end] + coord_strings[j:j_end]
                    sources_indices = list(range(0, i_end - i))
                    dest_indices = list(range(i_end - i, len(sub_coords)))

                    coords_path = ";".join(sub_coords)
                    url = f"{self.base_url}/table/v1/driving/{coords_path}"
                    params = {
                        "annotations": "duration,distance",
                        "sources": ";".join(str(s) for s in sources_indices),
                        "destinations": ";".join(str(d) for d in dest_indices),
                    }
                    data = self._execute_request_with_retry(url, params)
                    sub_dist = data.get("distances", [])
                    sub_dur = data.get("durations", [])

                    for r_idx, r in enumerate(range(i, i_end)):
                        for c_idx, c in enumerate(range(j, j_end)):
                            full_distances[r][c] = sub_dist[r_idx][c_idx] if sub_dist else 0.0
                            full_durations[r][c] = sub_dur[r_idx][c_idx] if sub_dur else 0.0

            return self._sanitize_matrix(full_distances, full_durations, coords)

    def _sanitize_matrix(
        self,
        distances: List[List[Optional[float]]],
        durations: List[List[Optional[float]]],
        coords: List[Tuple[float, float]],
    ) -> Tuple[List[List[float]], List[List[float]]]:
        """Replaces null/unreachable values with high penalty / estimated road equivalents."""
        n = len(coords)
        sanitized_dist: List[List[float]] = []
        sanitized_dur: List[List[float]] = []

        for i in range(n):
            dist_row: List[float] = []
            dur_row: List[float] = []
            for j in range(n):
                if i == j:
                    dist_row.append(0.0)
                    dur_row.append(0.0)
                    continue

                d_val = distances[i][j] if (i < len(distances) and j < len(distances[i])) else None
                t_val = durations[i][j] if (i < len(durations) and j < len(durations[i])) else None

                if d_val is None or d_val <= 0 or t_val is None or t_val <= 0:
                    # Unreachable road pair: approximate via conservative road-detour factor (1.5x)
                    lat1, lon1 = coords[i]
                    lat2, lon2 = coords[j]
                    approx_m = self._haversine_meters(lat1, lon1, lat2, lon2) * 1.5
                    approx_s = (approx_m / 1000.0) / 25.0 * 3600.0  # assume 25 km/h urban speed
                    dist_row.append(approx_m)
                    dur_row.append(approx_s)
                else:
                    dist_row.append(float(d_val))
                    dur_row.append(float(t_val))

            sanitized_dist.append(dist_row)
            sanitized_dur.append(dur_row)

        return sanitized_dist, sanitized_dur

    def get_route_geometry(
        self,
        ordered_coords: List[Tuple[float, float]],  # [(lat, lon), ...]
    ) -> List[Tuple[float, float]]:
        """Fetches detailed road geometry (polyline coordinates) for a sequence of stops.

        Returns list of (lat, lon) road waypoints.
        """
        if len(ordered_coords) < 2:
            return ordered_coords

        coord_strings = [f"{lon:.6f},{lat:.6f}" for lat, lon in ordered_coords]
        coords_path = ";".join(coord_strings)
        url = f"{self.base_url}/route/v1/driving/{coords_path}"
        params = {"overview": "full", "geometries": "geojson"}

        try:
            data = self._execute_request_with_retry(url, params)
            routes = data.get("routes", [])
            if routes and "geometry" in routes[0]:
                raw_coords = routes[0]["geometry"].get("coordinates", [])
                # GeoJSON coordinates are [lon, lat] -> convert to (lat, lon)
                return [(float(lat), float(lon)) for lon, lat in raw_coords]
        except Exception as exc:
            logger.warning(f"Could not fetch route geometry from OSRM: {exc}. Using straight-line points.")

        return ordered_coords

    @staticmethod
    def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        import math
        r = 6371000.0  # Earth radius meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
        return float(2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))
