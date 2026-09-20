"""Deterministic Real-Geodata Sampler and Demand Synthesizer for GRIDPOINT.
Replaces AI data fabrication with deterministic sampling over real public geodata
(dr5hn/countries-states-cities-database under ODbL 1.0).
"""

import math
import os
import logging
from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from core.validation import validate_neighborhood_dataframe

logger = logging.getLogger(__name__)

DEFAULT_GEODATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cities_geodata.csv")

# In-memory singleton DataFrame cache
_CITIES_CACHE: Optional[pd.DataFrame] = None


class InsufficientCandidatesError(Exception):
    """Raised when a region cannot supply enough distinct real cities/towns for the requested count."""
    def __init__(self, available: int, requested: int, region: str = "selected region"):
        self.available = available
        self.requested = requested
        self.region = region
        super().__init__(
            f"Requested {requested} delivery zones, but region '{region}' contains only {available} "
            f"distinct real cities/towns in the geodata index. Please lower the zone count (<= {available}) "
            f"or widen the region filter."
        )


def load_cities_geodata(path: Optional[str] = None) -> pd.DataFrame:
    """Loads the cities geodata file once into memory and returns the singleton DataFrame."""
    global _CITIES_CACHE
    if _CITIES_CACHE is not None:
        return _CITIES_CACHE

    target_path = path or DEFAULT_GEODATA_PATH
    if not os.path.exists(target_path):
        raise FileNotFoundError(
            f"Cities geodata CSV not found at '{target_path}'. Please run scripts/download_geodata.py."
        )

    logger.info("Loading cities geodata into memory from %s...", target_path)
    df = pd.read_csv(target_path, dtype={"state_code": str, "country_code": str})
    # Ensure numeric coordinates
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df.dropna(subset=["name", "latitude", "longitude"], inplace=True)
    _CITIES_CACHE = df
    logger.info("Loaded %d real cities into memory cache.", len(df))
    return _CITIES_CACHE


def filter_by_region(cities_df: pd.DataFrame, region_filter: Optional[Dict[str, Any]]) -> pd.DataFrame:
    """Filters the cities dataframe by country_code, state_name, and/or city_name.
    Matches are case-insensitive.
    """
    if cities_df is None or cities_df.empty:
        return pd.DataFrame()

    filtered = cities_df.copy()
    if not region_filter:
        return filtered

    country_code = region_filter.get("country_code")
    if country_code:
        filtered = filtered[filtered["country_code"].str.upper() == country_code.strip().upper()]

    state_name = region_filter.get("state_name")
    if state_name and state_name.strip():
        s_clean = state_name.strip().lower()
        # Allow exact match or substring in state_name
        filtered = filtered[filtered["state_name"].str.lower().str.contains(s_clean, na=False)]

    city_name = region_filter.get("city_name")
    if city_name and city_name.strip():
        c_clean = city_name.strip().lower()
        # Substring / exact match
        city_filtered = filtered[filtered["name"].str.lower().str.contains(c_clean, na=False)]
        if not city_filtered.empty:
            filtered = city_filtered

    return filtered


def jitter_around_anchor(anchor: pd.Series, count: int, rng: np.random.Generator) -> pd.DataFrame:
    """Creates `count` demonstration zones by applying a Gaussian jitter of 2–8 km radius
    around a single real city anchor.
    Zones are clearly labeled f'{anchor_name} Zone {i+1}' as derived demo zones.
    Guarantees unique spatial coordinates.
    """
    anchor_lat = float(anchor["latitude"])
    anchor_lon = float(anchor["longitude"])
    anchor_name = str(anchor["name"]).strip()
    state_name = str(anchor.get("state_name", "Karnataka"))
    country_name = str(anchor.get("country_name", "India"))

    # 1 degree latitude ~= 111.0 km
    # 1 degree longitude ~= 111.0 * cos(lat_radians) km
    lat_deg_per_km = 1.0 / 111.0
    lon_deg_per_km = 1.0 / (111.0 * max(0.2, math.cos(math.radians(anchor_lat))))

    zones = []
    seen_coords = set()

    for i in range(count):
        # Draw distance in km: normal distribution with mean 4.0km, std 1.8km, clipped to [1.5, 9.0] km
        # and random polar angle
        attempts = 0
        while attempts < 50:
            attempts += 1
            dist_km = float(np.clip(rng.normal(loc=4.5, scale=1.8), 1.5, 9.0))
            angle_rad = float(rng.uniform(0, 2 * math.pi))

            d_lat = dist_km * math.sin(angle_rad) * lat_deg_per_km
            d_lon = dist_km * math.cos(angle_rad) * lon_deg_per_km

            z_lat = round(anchor_lat + d_lat, 5)
            z_lon = round(anchor_lon + d_lon, 5)

            if (z_lat, z_lon) not in seen_coords:
                seen_coords.add((z_lat, z_lon))
                break

        zones.append({
            "name": f"{anchor_name} Zone {i + 1}",
            "latitude": z_lat,
            "longitude": z_lon,
            "state_name": state_name,
            "country_name": country_name,
        })

    return pd.DataFrame(zones)


def disambiguate_names(names: pd.Series, states: Optional[pd.Series] = None) -> pd.Series:
    """Disambiguates duplicate city names by appending state or integer index if duplicates exist."""
    counts: Dict[str, int] = {}
    result = []
    for i, name in enumerate(names):
        counts[name] = counts.get(name, 0) + 1
        if counts[name] == 1:
            # Check if this name appears multiple times in total
            if (names == name).sum() > 1:
                state_suffix = f" ({states.iloc[i]})" if states is not None and i < len(states) else f" #{counts[name]}"
                result.append(f"{name}{state_suffix}")
            else:
                result.append(name)
        else:
            state_suffix = f" ({states.iloc[i]})" if states is not None and i < len(states) else f" #{counts[name]}"
            result.append(f"{name}{state_suffix}")
    return pd.Series(result, index=names.index)


def sample_zones(cities_df: pd.DataFrame, params: Dict[str, Any], rng: np.random.Generator) -> pd.DataFrame:
    """Deterministic spatial sampler implementing both 'state' and 'single_city' scopes.

    - 'state': Samples N distinct real cities/towns in the region.
      Raises InsufficientCandidatesError if available < N.
    - 'single_city': Anchors to the real city, jittering N demo zones within 2–8 km radius.
    """
    scope = params.get("scope", "single_city")
    zone_count = int(params.get("zone_count", 50))
    region_filter = params.get("region_filter", {}) or {}

    filtered = filter_by_region(cities_df, region_filter)

    if scope == "state":
        n = zone_count
        if len(filtered) < n:
            region_label = region_filter.get("state_name") or region_filter.get("country_code") or "selected region"
            raise InsufficientCandidatesError(available=len(filtered), requested=n, region=region_label)

        # Sample exactly n distinct rows using the seeded generator
        rand_seed = int(rng.integers(0, 2**32 - 1))
        sampled = filtered.sample(n=n, random_state=rand_seed).copy()
        
        # Disambiguate duplicate city names across districts if any
        sampled["name"] = disambiguate_names(sampled["name"], sampled.get("state_name"))
        
        # Check coordinates uniqueness — if two real towns share coordinates, jitter slightly
        sampled_coords = set()
        new_lats = []
        new_lons = []
        for _, row in sampled.iterrows():
            lat, lon = round(float(row["latitude"]), 5), round(float(row["longitude"]), 5)
            while (lat, lon) in sampled_coords:
                lat = round(lat + float(rng.uniform(-0.005, 0.005)), 5)
                lon = round(lon + float(rng.uniform(-0.005, 0.005)), 5)
            sampled_coords.add((lat, lon))
            new_lats.append(lat)
            new_lons.append(lon)
        sampled["latitude"] = new_lats
        sampled["longitude"] = new_lons

        zones = sampled[["name", "latitude", "longitude", "state_name", "country_name"]].copy()
    else:
        # single_city scope: 1 real anchor, jittered into multiple nearby demo zones
        if filtered.empty:
            # Fallback to Bengaluru anchor if filtered empty
            bengaluru_rows = cities_df[cities_df["name"].str.contains("Bengaluru|Bangalore", case=False, na=False)]
            anchor = bengaluru_rows.iloc[0] if not bengaluru_rows.empty else cities_df.iloc[0]
        else:
            anchor = filtered.iloc[0]

        zones = jitter_around_anchor(anchor, count=zone_count, rng=rng)

    return zones.reset_index(drop=True)


def generate_demand(n: int, rng: np.random.Generator) -> np.ndarray:
    """Generates non-uniform, clustered daily order volumes by construction.
    Mirrors real urban logistics distribution:
    - 15% high-demand hubs (1,500 - 2,500 orders/day)
    - 35% medium-demand commercial zones (500 - 1,200 orders/day)
    - 50% low-demand suburban/fringe zones (50 - 400 orders/day)
    """
    tier = rng.choice(["high", "medium", "low"], size=n, p=[0.15, 0.35, 0.50])
    base = {"high": (1500, 2500), "medium": (500, 1200), "low": (50, 400)}
    orders = np.array([rng.integers(*base[t]) for t in tier], dtype=float)
    return orders


def generate_capacity_required(daily_orders: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Generates distinct throughput capacity requirements for delivery zones.
    Deliberately distinct from daily_orders (0.8x - 1.3x variation).
    """
    per_order_capacity = rng.uniform(0.8, 1.3, size=len(daily_orders))
    return np.round(daily_orders * per_order_capacity).astype(float)


def generate_candidate_capacities(n: int, rng: np.random.Generator, total_demand: Optional[float] = None) -> list:
    """Assigns warehouse throughput capacity ceiling to ~30-40% of zones so they can act
    as candidate warehouse locations in CFLP optimization. Other zones have None capacity.

    If total_demand is provided, scales capacities realistically so that opening 2-6 facilities
    can comfortably cover the demand without artificial capacity shortfalls.
    """
    capacities = []
    # 35% candidate sites
    is_candidate = rng.choice([True, False], size=n, p=[0.35, 0.65])
    # Ensure at least 4 candidates exist even if n is small
    if sum(is_candidate) < 4:
        for idx in rng.choice(n, size=min(4, n), replace=False):
            is_candidate[idx] = True

    if total_demand is not None and total_demand > 0:
        base_cap = max(5000.0, (total_demand / 3.0) * 1.35)
        for cand in is_candidate:
            if cand:
                mult = float(rng.uniform(0.85, 1.35))
                cap_val = round((base_cap * mult) / 500.0) * 500.0
                capacities.append(float(cap_val))
            else:
                capacities.append(None)
    else:
        cap_options = [4000.0, 5000.0, 6000.0, 8000.0, 10000.0]
        for cand in is_candidate:
            if cand:
                capacities.append(float(rng.choice(cap_options)))
            else:
                capacities.append(None)
    return capacities


def generate_geodata_dataset(
    params: Dict[str, Any],
    seed: Optional[int] = None,
    cities_df: Optional[pd.DataFrame] = None,
) -> Tuple[bool, list, Optional[pd.DataFrame], Dict[str, Any]]:
    """Complete end-to-end deterministic generation pipeline.
    
    Returns:
        (is_valid, errors, cleaned_dataframe, metadata)
    """
    if cities_df is None:
        cities_df = load_cities_geodata()

    actual_seed = seed if seed is not None else int(np.random.randint(0, 2**31 - 1))
    rng = np.random.default_rng(actual_seed)

    scope = params.get("scope", "single_city")
    zone_count = int(params.get("zone_count", 50))
    region_filter = params.get("region_filter", {}) or {}

    # 1. Sample zones (raises InsufficientCandidatesError if state scope candidate count is insufficient)
    sampled_zones = sample_zones(cities_df, params, rng)

    n = len(sampled_zones)
    sampled_zones["neighborhood_id"] = [f"ZN_{i+1:03d}" for i in range(n)]

    # 2. Generate non-uniform demand and capacity
    daily_orders = generate_demand(n, rng)
    sampled_zones["daily_orders"] = daily_orders
    total_demand = float(np.sum(daily_orders))
    sampled_zones["capacity"] = generate_candidate_capacities(n, rng, total_demand=total_demand)

    # 3. Validate output against data contract
    is_valid, errors, clean_df = validate_neighborhood_dataframe(sampled_zones)
    if not is_valid:
        return False, errors, None, {"seed": actual_seed}

    # 4. Construct metadata
    if scope == "state":
        state_label = region_filter.get("state_name") or "Regional"
        badge_text = "[Real Towns, Synthetic Demand]"
        source_label = f"Real Towns ({state_label}), Synthetic Demand"
    else:
        city_label = region_filter.get("city_name") or "Bengaluru"
        badge_text = "[Real City Anchor, Jittered Zones & Synthetic Demand]"
        source_label = f"Real City Anchor ({city_label}), Jittered Zones & Synthetic Demand"

    metadata = {
        "seed": actual_seed,
        "scope": scope,
        "badge_text": badge_text,
        "source_label": source_label,
        "zone_count": n,
        "region_filter": region_filter,
        "data_source": "dr5hn/countries-states-cities-database (ODbL 1.0)",
    }

    return True, [], clean_df, metadata
