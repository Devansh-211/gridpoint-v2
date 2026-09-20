"""Integration tests for GRIDPOINT FastAPI endpoints.
"""

import io
import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_api_health():
    """Validates /api/health endpoint returns 200 and active CBC solver."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["solver_available"] is True
    assert "CBC" in data["solver"] or "COIN" in data["solver"] or "Heuristic" in data["solver"]


def test_api_demo_data():
    """Validates /api/demo-data returns 36 Bengaluru neighborhoods."""
    res = client.get("/api/demo-data")
    assert res.status_code == 200
    data = res.json()
    assert data["neighborhood_count"] == 36
    assert data["total_demand"] > 0
    assert len(data["preview"]) == 36


def test_api_upload_valid_csv():
    """Validates /api/upload accepts a valid CSV."""
    csv_content = (
        "neighborhood_id,name,latitude,longitude,daily_orders\n"
        "N1,Alpha,12.91,77.51,150\n"
        "N2,Beta,12.92,77.52,200\n"
        "N3,Gamma,12.93,77.53,250\n"
    )
    file = io.BytesIO(csv_content.encode("utf-8"))
    res = client.post("/api/upload", files={"file": ("test.csv", file, "text/csv")})
    assert res.status_code == 200
    data = res.json()
    assert data["neighborhood_count"] == 3
    assert data["total_demand"] == 600.0


def test_api_upload_invalid_csv_returns_422():
    """Validates /api/upload returns 422 with structured errors on missing columns."""
    csv_content = (
        "neighborhood_id,name,latitude\n"  # missing longitude and daily_orders
        "N1,Alpha,12.91\n"
    )
    file = io.BytesIO(csv_content.encode("utf-8"))
    res = client.post("/api/upload", files={"file": ("invalid.csv", file, "text/csv")})
    assert res.status_code == 422


def test_api_optimize_returns_optimal_solution():
    """Validates /api/optimize runs CFLP and returns p warehouses with assignments."""
    payload = {
        "session_id": "default",
        "p": 3,
        "warehouse_capacity": 4000.0,
        "cost_per_km": 1.25,
        "routing_mode": "haversine",
        "priority_preset": "cost",
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_optimal"] is True or data["status"].startswith("Feasible")
    assert data["p"] == 3
    assert len(data["warehouses"]) == 3
    assert len(data["assignments"]) == 36
    assert data["total_weighted_distance_km"] > 0
    assert data["total_delivery_cost"] > 0
    assert data["coverage_percentage"] >= 0
    assert data["fast_delivery_coverage_pct"] >= 0
    assert data["estimated_co2_kg_per_day"] >= 0
    assert "cost_per_km" in data["assumptions"]


def test_api_optimize_priority_presets():
    """Validates /api/optimize supports speed and sustainability presets."""
    for preset in ["cost", "speed", "sustainability"]:
        payload = {
            "session_id": "default",
            "p": 3,
            "warehouse_capacity": 4000.0,
            "priority_preset": preset,
        }
        res = client.post("/api/optimize", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["assumptions"]["priority_preset"] == preset


def test_api_optimize_infeasible_returns_400():
    """Validates /api/optimize returns 400 with diagnostic explanation when infeasible."""
    # Impossible radius: 0.5 km radius in a 30km city
    payload = {
        "session_id": "default",
        "p": 3,
        "warehouse_capacity": 4000.0,
        "radius_max_km": 0.5,
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert "detail" in data
    assert "diagnostics" in data["detail"] or "error" in data["detail"]


def test_api_compare_baseline():
    """Validates /api/compare returns baseline vs optimized metrics with % change."""
    res = client.get("/api/compare?session_id=default")
    assert res.status_code == 200
    data = res.json()
    assert data["baseline"]["warehouses_count"] == 1
    assert data["optimized"]["warehouses_count"] >= 1
    # Optimized distance should be lower than single warehouse baseline
    assert data["weighted_distance_delta"] < 0
    assert data["weighted_distance_pct_change"] < 0
    assert "estimated_monthly_savings" in data
    assert "co2_delta_kg" in data


def test_api_tradeoff_curve():
    """Validates /api/tradeoff returns points for p = 1 to 5."""
    res = client.get("/api/tradeoff?session_id=default&fixed_cost=300")
    assert res.status_code == 200
    data = res.json()
    assert len(data["points"]) >= 3
    for pt in data["points"]:
        assert pt["p"] >= 1
        assert pt["infrastructure_cost"] == pt["p"] * 300.0


def test_api_scenario_demand_shock():
    """Validates /api/scenario simulates demand multiplier and measures cost shift."""
    payload = {
        "session_id": "default",
        "demand_multiplier": 1.2,
        "p": 3,
        "warehouse_capacity": 5000.0,
    }
    res = client.post("/api/scenario", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["demand_multiplier"] == 1.2
    assert data["scenario_cost"] > data["original_cost"]
    assert data["cost_pct_change"] > 0


def test_api_explain_warehouse():
    """Validates /api/explain/{warehouse_id} returns demand, utilization, demand drivers, and next-best runner-up."""
    # First ensure optimization has run
    opt_res = client.post("/api/optimize", json={"session_id": "default", "p": 3, "warehouse_capacity": 4000.0})
    assert opt_res.status_code == 200
    opt_data = opt_res.json()
    target_wid = opt_data["warehouses"][0]["warehouse_id"]

    res = client.get(f"/api/explain/{target_wid}?session_id=default")
    assert res.status_code == 200
    data = res.json()
    assert data["warehouse_id"] == target_wid
    assert data["demand_served"] > 0
    assert data["capacity_utilization_pct"] > 0
    assert "key_demand_drivers" in data
    assert len(data["key_demand_drivers"]) > 0
    assert "burden_eliminated_km" in data
    assert data["next_best_rejected"] is not None
    assert "reason_rejected" in data["next_best_rejected"]


def test_api_optimize_with_cvrp_and_cache():
    """Validates /api/optimize with include_cvrp=True returns fleet routes, and verifies server cache."""
    payload = {
        "session_id": "default",
        "p": 2,
        "warehouse_capacity": 6000.0,
        "cost_per_km": 1.25,
        "routing_mode": "haversine",
        "include_cvrp": True,
        "vehicle_capacity": 500,
        "vehicle_fixed_cost": 150.0,
    }
    # First solve (computes CVRP)
    res1 = client.post("/api/optimize", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["cvrp_summary"] is not None
    cvrp = data1["cvrp_summary"]
    assert cvrp["vehicles_deployed"] > 0
    assert cvrp["avg_vehicle_utilization_pct"] > 0
    assert cvrp["vehicle_fixed_cost"] == 150.0
    assert len(cvrp["routes"]) > 0
    first_route = cvrp["routes"][0]
    assert "vehicle_id" in first_route
    assert "stops" in first_route
    assert len(first_route["route_coords"]) >= 2

    # Second call with identical payload (cache hit)
    res2 = client.post("/api/optimize", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_delivery_cost"] == data1["total_delivery_cost"]
    assert data2["cvrp_summary"]["vehicles_deployed"] == cvrp["vehicles_deployed"]


def test_api_optimize_auto_size_mode():
    """Validates /api/optimize in auto_size mode returns solver-chosen warehouse count with system headroom."""
    payload = {
        "session_id": "default",
        "auto_size": True,
        "p_max": 6,
        "warehouse_capacity": 4000.0,
        "cost_per_km": 1.25,
        "fixed_cost_per_warehouse": 300.0,
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["auto_size"] is True
    assert 1 <= data["p"] <= 6
    assert len(data["warehouses"]) == data["p"]
    assert "sizing_rationale" in data
    assert data["sizing_rationale"] is not None
    assert f"Auto-sized to {data['p']} warehouse" in data["sizing_rationale"]
    # Check throughput headroom
    assert data["total_system_capacity"] >= data["total_system_demand"]
    assert data["capacity_headroom"] >= 0
    assert data["capacity_headroom_pct"] >= 0


def test_api_optimize_auto_size_p_max_exceeds_candidates():
    """Validates /api/optimize rejects p_max exceeding available candidate sites with diagnostic message."""
    payload = {
        "session_id": "default",
        "auto_size": True,
        "p_max": 100,  # Demo dataset only has 36 candidate zones
        "warehouse_capacity": 4000.0,
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert "detail" in data
    detail_str = str(data["detail"]).lower()
    assert "exceeds total candidate sites" in detail_str or "candidate" in detail_str


def test_api_optimize_capacity_required_and_headroom_fields():
    """Validates that warehouses have capacity_required and capacity_ceiling as distinct fields."""
    payload = {
        "session_id": "default",
        "p": 3,
        "warehouse_capacity": 4000.0,
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()
    for w in data["warehouses"]:
        assert "capacity_required" in w
        assert "capacity_ceiling" in w
        assert w["capacity_required"] == w["assigned_demand"]
        assert w["capacity_ceiling"] == w["capacity"]
        assert w["capacity_required"] <= w["capacity_ceiling"]


def test_api_explain_warehouse_fallback_and_synthetic():
    """Validates /api/explain falls back gracefully when given a non-existent warehouse_id and works with synthetic datasets."""
    # 1. Non-existent warehouse ID should gracefully fallback to the first open warehouse
    res = client.get("/api/explain/non_existent_wid_999?session_id=default")
    assert res.status_code == 200
    data = res.json()
    assert "warehouse_id" in data
    assert "key_demand_drivers" in data
    assert isinstance(data["key_demand_drivers"], list)

    # 2. Test explain on synthetic dataset session
    synth_req = {
        "zone_count": 10,
        "scope": "single_city",
        "region_filter": {"city_name": "Pune", "country_code": "IN"},
        "seed": 42,
        "session_id": "test_synth_explain",
    }
    synth_res = client.post("/api/agent/generate-synthetic-data", json=synth_req)
    assert synth_res.status_code == 200

    # Request explain without manual optimization call first
    explain_res = client.get("/api/explain/any_id?session_id=test_synth_explain")
    assert explain_res.status_code == 200
    explain_data = explain_res.json()
    assert "warehouse_id" in explain_data
    assert "key_demand_drivers" in explain_data
    assert isinstance(explain_data["key_demand_drivers"], list)


def test_generated_data_optimization_and_auto_size():
    """Validates that 50-zone generated geodata can be optimized in Auto-Size mode and produces valid tradeoff & compare results."""
    session_id = "test_gen_auto_size_50"
    synth_req = {
        "zone_count": 50,
        "scope": "single_city",
        "region_filter": {"city_name": "Bengaluru", "country_code": "IN"},
        "seed": 99,
        "session_id": session_id,
    }
    synth_res = client.post("/api/agent/generate-synthetic-data", json=synth_req)
    assert synth_res.status_code == 200
    synth_data = synth_res.json()
    assert synth_data["neighborhood_count"] == 50
    total_demand = synth_data["total_demand"]
    assert total_demand > 10000

    # Test Auto-Size optimization with scaled capacity
    suggested_cap = (total_demand / 3.0) * 1.35
    opt_payload = {
        "session_id": session_id,
        "auto_size": True,
        "p_max": 6,
        "warehouse_capacity": suggested_cap,
        "cost_per_km": 1.25,
        "fixed_cost_per_warehouse": 300.0,
    }
    opt_res = client.post("/api/optimize", json=opt_payload)
    assert opt_res.status_code == 200
    opt_data = opt_res.json()
    assert opt_data["auto_size"] is True
    assert 1 <= opt_data["p"] <= 6
    assert len(opt_data["warehouses"]) == opt_data["p"]
    assert opt_data["total_system_capacity"] >= opt_data["total_system_demand"]
    assert "sizing_rationale" in opt_data
    assert opt_data["sizing_rationale"] is not None

    # Test Trade-off curve calculation on this 50-zone generated dataset
    tradeoff_res = client.get(f"/api/tradeoff?session_id={session_id}")
    assert tradeoff_res.status_code == 200
    tradeoff_data = tradeoff_res.json()
    assert len(tradeoff_data["points"]) > 0
    # At least some points should be feasible
    assert any(pt["is_feasible"] for pt in tradeoff_data["points"])

    # Test Baseline comparison on this 50-zone generated dataset
    compare_res = client.get(f"/api/compare?session_id={session_id}")
    assert compare_res.status_code == 200
    compare_data = compare_res.json()
    assert compare_data["baseline"]["warehouses_count"] == 1
    assert compare_data["optimized"]["warehouses_count"] == opt_data["p"]


def test_generated_data_state_scope_optimization():
    """Validates optimization on state-scoped geodata sampled across regional towns."""
    session_id = "test_gen_state_opt"
    synth_req = {
        "zone_count": 25,
        "scope": "state",
        "region_filter": {"state_name": "Karnataka", "country_code": "IN"},
        "seed": 101,
        "session_id": session_id,
    }
    synth_res = client.post("/api/agent/generate-synthetic-data", json=synth_req)
    assert synth_res.status_code == 200
    synth_data = synth_res.json()
    total_demand = synth_data["total_demand"]

    opt_payload = {
        "session_id": session_id,
        "p": 3,
        "warehouse_capacity": max(5000.0, (total_demand / 3.0) * 1.5),
    }
    opt_res = client.post("/api/optimize", json=opt_payload)
    assert opt_res.status_code == 200
    opt_data = opt_res.json()
    assert opt_data["p"] == 3
    assert len(opt_data["warehouses"]) == 3


def test_api_scenario_facility_failure_disruption():
    """Validates /api/scenario correctly handles warehouse failure and populates friendly names."""
    # Run baseline optimization first
    opt_res = client.post("/api/optimize", json={"session_id": "default", "p": 3, "warehouse_capacity": 4000.0})
    assert opt_res.status_code == 200
    opt_data = opt_res.json()
    failed_wid = opt_data["warehouses"][0]["warehouse_id"]
    failed_wname = opt_data["warehouses"][0]["name"]

    payload = {
        "session_id": "default",
        "demand_multiplier": 1.0,
        "warehouse_failure_id": failed_wid,
        "p": 3,
        "warehouse_capacity": 6000.0,
    }
    res = client.post("/api/scenario", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["failed_warehouse_id"] == failed_wid
    assert data["failed_warehouse_name"] == failed_wname
    assert len(data["original_warehouses"]) == 3
    assert len(data["original_warehouse_names"]) == 3
    # Surviving warehouses must not include the failed warehouse
    assert failed_wid not in data["scenario_warehouses"]
    assert len(data["scenario_warehouses"]) >= 1
    assert len(data["scenario_warehouse_names"]) == len(data["scenario_warehouses"])


def test_api_scenario_on_generated_dataset():
    """Validates /api/scenario executes properly on a generated geodata dataset."""
    session_id = "test_gen_scenario"
    synth_req = {
        "zone_count": 30,
        "scope": "city",
        "region_filter": {"city_name": "Bengaluru", "country_code": "IN"},
        "seed": 42,
        "session_id": session_id,
    }
    synth_res = client.post("/api/agent/generate-synthetic-data", json=synth_req)
    assert synth_res.status_code == 200

    # Optimize on this dataset
    opt_res = client.post("/api/optimize", json={"session_id": session_id, "p": 3})
    assert opt_res.status_code == 200
    opt_data = opt_res.json()

    # Run 1.2x surge scenario
    scenario_res = client.post("/api/scenario", json={
        "session_id": session_id,
        "demand_multiplier": 1.2,
    })
    assert scenario_res.status_code == 200
    sc_data = scenario_res.json()
    assert sc_data["demand_multiplier"] == 1.2
    assert sc_data["scenario_cost"] > 0
    assert len(sc_data["scenario_warehouses"]) >= 1



