"""Unit tests for the Conversational Optimization Agent (POST /api/agent/extract).
"""

import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_agent_extract_complete_happy_path():
    payload = {
        "message": "Plan a 3-warehouse network with 4000 orders/day capacity within 25 km radius, cost focus.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "confirm"
    assert data["ready_to_optimize"] is True
    assert data["extracted_params"]["warehouse_count"] == 3
    assert data["extracted_params"]["warehouse_capacity"] == 4000.0
    assert data["extracted_params"]["max_service_radius_km"] == 25.0
    assert data["extracted_params"]["priority_preset"] == "cost"


def test_agent_extract_missing_capacity_clarification():
    payload = {
        "message": "I want to open 4 warehouses with 20 km radius.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "clarify"
    assert data["ready_to_optimize"] is False
    assert "warehouse_capacity" in data["missing_required"]
    assert "capacity" in data["reply"].lower()


def test_agent_extract_drive_time_correction():
    payload = {
        "message": "Plan 3 warehouses with 4000 capacity within 20 minutes drive time.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "clarify"
    assert "geographic" in data["reply"].lower() or "haversine" in data["reply"].lower()


def test_agent_extract_unlimited_radius():
    payload = {
        "message": "Build 2 facilities with 5000 orders/day capacity with no radius limit, speed priority.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "confirm"
    assert data["ready_to_optimize"] is True
    assert data["extracted_params"]["warehouse_count"] == 2
    assert data["extracted_params"]["warehouse_capacity"] == 5000.0
    assert data["extracted_params"]["max_service_radius_km"] is None
    assert data["extracted_params"]["priority_preset"] == "speed"


def test_agent_extract_cvrp_fleet_intent():
    payload = {
        "message": "Plan 3 warehouses with 4500 capacity, unlimited radius, and tactical fleet van routing with 200 orders per van.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "confirm"
    assert data["extracted_params"]["include_cvrp"] is True
    assert data["extracted_params"]["vehicle_capacity"] == 200


def test_agent_extract_out_of_bounds_warehouses():
    payload = {
        "message": "I need 0 warehouses with 4000 capacity.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "error"
    assert "at least 1" in data["reply"].lower()


# ============================================================================
# PHASE 3: AI SYNTHETIC DATA GENERATION TESTS
# ============================================================================

def test_generate_synthetic_demand_dataset_default():
    payload = {
        "zone_count": 50,
        "pattern_hint": "clustered",
        "city_hint": "bengaluru"
    }
    res = client.post("/api/agent/generate-synthetic-data", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["neighborhood_count"] == 50
    assert data["is_synthetic_ai"] is True
    assert data["dataset_type"] == "ai_synthetic"
    assert len(data["preview"]) == 50
    assert data["total_demand"] > 0

    # Ensure non-uniform demand distribution
    demands = [n["daily_orders"] for n in data["preview"]]
    assert len(set(demands)) > 1
    assert max(demands) > min(demands) * 2

    # Ensure realistic coordinates within India / Bengaluru bounds
    for n in data["preview"]:
        assert 12.0 <= n["latitude"] <= 14.0
        assert 77.0 <= n["longitude"] <= 78.5
        assert n["daily_orders"] > 0


def test_generate_synthetic_demand_dataset_clamped_bounds():
    # Test lower bound clamp (min 10)
    res_low = client.post("/api/agent/generate-synthetic-data", json={"zone_count": 5})
    assert res_low.status_code == 200
    assert res_low.json()["neighborhood_count"] == 10

    # Test upper bound clamp (max 150)
    res_high = client.post("/api/agent/generate-synthetic-data", json={"zone_count": 300})
    assert res_high.status_code == 200
    assert res_high.json()["neighborhood_count"] == 150


def test_generate_synthetic_demand_dataset_regions():
    res_mum = client.post("/api/agent/generate-synthetic-data", json={"zone_count": 25, "city_hint": "mumbai"})
    assert res_mum.status_code == 200
    preview_mum = res_mum.json()["preview"]
    assert 18.5 <= preview_mum[0]["latitude"] <= 19.5
    assert 72.5 <= preview_mum[0]["longitude"] <= 73.5

    res_del = client.post("/api/agent/generate-synthetic-data", json={"zone_count": 25, "city_hint": "delhi"})
    assert res_del.status_code == 200
    preview_del = res_del.json()["preview"]
    assert 28.0 <= preview_del[0]["latitude"] <= 29.0
    assert 76.5 <= preview_del[0]["longitude"] <= 77.8


# ============================================================================
# PHASE 4: PER-PAGE EXPLAIN MODE TESTS
# ============================================================================

def test_agent_explain_results_grounded():
    page_context = {
        "view": "viewResults",
        "status": "Optimal",
        "warehouse_count": 3,
        "total_delivery_cost": 4620.50,
        "estimated_monthly_savings": 54200.0,
        "avg_distance_km": 4.1,
        "max_distance_km": 9.2,
        "cost_pct_change": -34.8,
        "co2_pct_change": -34.8,
        "warehouses": [
            {
                "warehouse_id": "W-01",
                "name": "Koramangala Hub",
                "assigned_demand": 3800,
                "capacity": 4000,
                "capacity_utilization_pct": 95.0,
                "neighborhoods_count": 12
            },
            {
                "warehouse_id": "W-02",
                "name": "Indiranagar Hub",
                "assigned_demand": 3200,
                "capacity": 4000,
                "capacity_utilization_pct": 80.0,
                "neighborhoods_count": 14
            }
        ]
    }

    payload = {
        "page": "viewResults",
        "message": "Why is Koramangala Hub at 95% capacity utilization and what are our monthly savings?",
        "page_context": page_context,
        "history": []
    }

    res = client.post("/api/agent/explain", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["grounded"] is True
    assert "95.0%" in data["reply"] or "95%" in data["reply"] or "Koramangala" in data["reply"]
    assert "54,200" in data["reply"] or "54200" in data["reply"]
    assert len(data["suggested_followups"]) > 0


def test_agent_explain_hypothetical_redirection():
    page_context = {
        "view": "viewResults",
        "total_delivery_cost": 4620.50,
        "warehouses": []
    }

    payload = {
        "page": "viewResults",
        "message": "What if demand increases by 50% next week?",
        "page_context": page_context,
        "history": []
    }

    res = client.post("/api/agent/explain", json=payload)
    assert res.status_code == 200
    data = res.json()
    # Must redirect to Scenario Lab rather than fabricating numbers
    assert "scenario" in data["reply"].lower() or "what-if" in data["reply"].lower()


def test_agent_explain_empty_context():
    payload = {
        "page": "viewResults",
        "message": "Explain the current results.",
        "page_context": {},
        "history": []
    }

    res = client.post("/api/agent/explain", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "no computed optimization results" in data["reply"].lower() or "load demo" in data["reply"].lower() or "run network optimization" in data["reply"].lower()
