"""Unit tests for the deterministic real-geodata sampler and demand synthesizer."""

import numpy as np
import pytest
import pandas as pd
from core.geodata import (
    load_cities_geodata,
    filter_by_region,
    jitter_around_anchor,
    sample_zones,
    generate_demand,
    generate_capacity_required,
    generate_geodata_dataset,
    InsufficientCandidatesError,
)
from core.validation import validate_neighborhood_dataframe


@pytest.fixture(scope="module")
def cities_df():
    return load_cities_geodata()


def test_load_cities_geodata(cities_df):
    """Confirm the cities table is loaded with expected schema and non-empty rows."""
    assert isinstance(cities_df, pd.DataFrame)
    assert len(cities_df) > 4000
    expected_cols = [
        "id", "name", "state_id", "state_code", "state_name",
        "country_id", "country_code", "country_name",
        "latitude", "longitude", "wikidataid"
    ]
    for col in expected_cols:
        assert col in cities_df.columns
    # Coordinates must be numeric and not null
    assert not cities_df["latitude"].isna().any()
    assert not cities_df["longitude"].isna().any()


def test_filter_by_region(cities_df):
    """Test filtering by country, state, and city."""
    # State filter
    kt = filter_by_region(cities_df, {"country_code": "IN", "state_name": "Karnataka"})
    assert len(kt) > 200
    assert (kt["state_name"] == "Karnataka").all()

    # City filter
    blr = filter_by_region(cities_df, {"country_code": "IN", "city_name": "Bengaluru"})
    assert not blr.empty
    assert blr["name"].str.contains("Bengaluru", case=False).any()


def test_sample_zones_single_city_jitter(cities_df):
    """Test single_city scope produces jittered zones around the anchor with unique coordinates."""
    rng = np.random.default_rng(42)
    params = {
        "zone_count": 25,
        "scope": "single_city",
        "region_filter": {"country_code": "IN", "city_name": "Bengaluru"}
    }
    zones = sample_zones(cities_df, params, rng)
    assert len(zones) == 25
    assert (zones["name"].str.startswith("Bengaluru Zone")).all()

    # Coordinates must be distinct
    coords = set(zip(zones["latitude"], zones["longitude"]))
    assert len(coords) == 25

    # Coordinates should be within plausible radius (~15 km) of Bengaluru (12.97, 77.59)
    assert (zones["latitude"].between(12.7, 13.3)).all()
    assert (zones["longitude"].between(77.3, 77.9)).all()


def test_sample_zones_state_scope(cities_df):
    """Test state scope samples distinct real towns and disambiguates names."""
    rng = np.random.default_rng(100)
    params = {
        "zone_count": 30,
        "scope": "state",
        "region_filter": {"country_code": "IN", "state_name": "Maharashtra"}
    }
    zones = sample_zones(cities_df, params, rng)
    assert len(zones) == 30
    assert (zones["state_name"] == "Maharashtra").all()
    # All names must be unique
    assert zones["name"].nunique() == 30
    # Coordinates must be unique
    coords = set(zip(zones["latitude"], zones["longitude"]))
    assert len(coords) == 30


def test_sample_zones_insufficient_candidates_raises_error(cities_df):
    """Confirm requesting more real towns than a state has raises InsufficientCandidatesError."""
    rng = np.random.default_rng(7)
    # Goa has ~50 cities in dataset
    params = {
        "zone_count": 200,
        "scope": "state",
        "region_filter": {"country_code": "IN", "state_name": "Goa"}
    }
    with pytest.raises(InsufficientCandidatesError) as exc_info:
        sample_zones(cities_df, params, rng)

    err_msg = str(exc_info.value)
    assert "Requested 200" in err_msg
    assert "Goa" in err_msg
    assert exc_info.value.requested == 200
    assert exc_info.value.available < 200


def test_generate_demand_non_uniform_and_reproducible():
    """Verify generate_demand is non-uniform by construction and reproducible by seed."""
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    orders1 = generate_demand(100, rng1)
    orders2 = generate_demand(100, rng2)

    # Reproducibility with same seed
    assert np.array_equal(orders1, orders2)

    # Non-uniformity checks
    assert len(np.unique(orders1)) > 70
    std_dev = float(np.std(orders1))
    mean_val = float(np.mean(orders1))
    assert std_dev > 300
    assert std_dev / mean_val > 0.5  # High coefficient of variation
    assert np.min(orders1) < 400
    assert np.max(orders1) > 1500


def test_generate_capacity_required():
    """Verify capacity_required varies from orders and is distinct."""
    rng = np.random.default_rng(99)
    orders = generate_demand(50, rng)
    caps = generate_capacity_required(orders, rng)
    assert not np.array_equal(orders, caps)
    # Ratios should be in [0.8, 1.3] range
    ratios = caps / orders
    assert (ratios >= 0.75).all() and (ratios <= 1.35).all()


def test_generate_geodata_dataset_passes_core_validation(cities_df):
    """Verify end-to-end generated dataset passes strict validate_neighborhood_dataframe contract."""
    params = {
        "zone_count": 40,
        "scope": "single_city",
        "region_filter": {"country_code": "IN", "city_name": "Bengaluru"}
    }
    is_valid, errors, df, meta = generate_geodata_dataset(params, seed=123, cities_df=cities_df)
    assert is_valid is True
    assert errors == []
    assert df is not None
    assert len(df) == 40
    assert meta["seed"] == 123
    assert meta["scope"] == "single_city"
    assert "[Real City Anchor" in meta["badge_text"]

    # Validate directly through core data contract
    contract_valid, contract_errors, clean_df = validate_neighborhood_dataframe(df)
    assert contract_valid is True
    assert len(contract_errors) == 0
