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
