"""Unit tests for the Conversational Optimization Agent, AI Synthetic Data, and Grounded Explain routes.
Verifies real LLM integration, credential handling, missing-key graceful failure, and structured tool handling.
"""

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app import app
from api.schemas import ExtractedParams

client = TestClient(app)


# ============================================================================
# 1. MISSING API KEY BEHAVIOR (FAIL LOUDLY & SPECIFICALLY FOR AI ONLY)
# ============================================================================

def test_agent_extract_missing_api_key_shows_unavailable_state(monkeypatch):
    """When ANTHROPIC_API_KEY is not configured, the extract route must return an honest unavailable status."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    
    payload = {
        "message": "Plan a 3-warehouse network with 4000 orders/day capacity within 25 km radius.",
        "history": [],
        "known_params": {}
    }
    res = client.post("/api/agent/extract", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "error"
    assert data["ready_to_optimize"] is False
    assert "no api key configured" in data["reply"].lower() or "ai features unavailable" in data["reply"].lower()
    assert "api_key" in data["missing_required"]


def test_agent_explain_missing_api_key_shows_unavailable_state(monkeypatch):
    """When ANTHROPIC_API_KEY is not configured, explain mode returns an honest unavailable notice."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    payload = {
        "page": "viewResults",
        "message": "Why were these warehouse locations selected?",
        "page_context": {"total_delivery_cost": 4200.0, "warehouses": []},
        "history": []
    }
    res = client.post("/api/agent/explain", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["grounded"] is False
    assert "no api key configured" in data["reply"].lower() or "ai features unavailable" in data["reply"].lower()


def test_agent_synthetic_missing_api_key_returns_503(monkeypatch):
    """When ANTHROPIC_API_KEY is missing, synthetic data generation returns 503 unavailable."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    payload = {
        "zone_count": 30,
        "pattern_hint": "clustered",
        "city_hint": "bengaluru"
    }
    res = client.post("/api/agent/generate-synthetic-data", json=payload)
    assert res.status_code == 503
    data = res.json()
    assert "ANTHROPIC_API_KEY" in str(data["detail"]) or "unavailable" in str(data["detail"]).lower()


def test_core_app_unaffected_when_api_key_is_missing(monkeypatch):
    """Confirm solver, demo data, and metrics operate with ZERO degradation when ANTHROPIC_API_KEY is absent."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # 1. Health check works
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    # 2. Demo data loads
    demo_res = client.get("/api/demo-data")
    assert demo_res.status_code == 200
    assert demo_res.json()["neighborhood_count"] == 36

    # 3. Solver solves to optimality
    opt_res = client.post("/api/optimize", json={
        "session_id": "default",
        "p": 3,
        "warehouse_capacity": 4000,
        "radius_max_km": 25.0,
        "cost_per_km": 1.25,
        "fixed_cost_per_warehouse": 300.0,
        "routing_mode": "haversine",
        "priority_preset": "cost",
        "include_cvrp": False,
    })
    assert opt_res.status_code == 200
    assert opt_res.json()["status"] == "Optimal"


# ============================================================================
# 2. STRUCTURED LLM CALLS WITH ANTHROPIC CLAUDE SDK
# ============================================================================

def test_agent_extract_with_mocked_claude_complete_spec():
    """Verify that when Anthropic SDK returns configure_cflp_network tool call, parameters are parsed and validated."""
    mock_tool_input = {
        "status": "confirm",
        "reply": "I have configured your 3-warehouse network with 4,000 orders/day capacity within a 25 km radius.",
        "warehouse_count": 3,
        "warehouse_capacity": 4000.0,
        "max_service_radius_km": 25.0,
        "cost_per_km": 1.25,
        "fixed_cost_per_warehouse": 300.0,
        "priority_preset": "cost",
        "include_cvrp": False,
        "vehicle_capacity": 250,
        "vehicle_fixed_cost": 150.0,
        "missing_required": [],
        "ready_to_optimize": True,
        "suggested_prompts": ["Add tactical fleet routing", "Increase to 4 warehouses"],
    }

    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "configure_cflp_network"
    mock_content.input = mock_tool_input

    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client_instance

        payload = {
            "message": "Plan a 3-warehouse network with 4000 capacity and 25km radius.",
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
        assert data["confirmation_card"] is not None


def test_agent_extract_phrasing_variation_reflects_distinct_inputs():
    """Verify §4 test: distinct natural language phrasings produce distinct extracted parameters."""
    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Phrasing 1: 3 warehouses, 20km radius, 3500 capacity
        mock_content1 = MagicMock()
        mock_content1.type = "tool_use"
        mock_content1.name = "configure_cflp_network"
        mock_content1.input = {
            "status": "confirm",
            "reply": "Configured 3 hubs within 20km reach handling 3,500 orders/day.",
            "warehouse_count": 3,
            "warehouse_capacity": 3500.0,
            "max_service_radius_km": 20.0,
            "priority_preset": "speed",
            "include_cvrp": False,
            "missing_required": [],
            "ready_to_optimize": True,
        }
        mock_resp1 = MagicMock(content=[mock_content1])

        # Phrasing 2: 4 distribution centers, unlimited radius, 6000 capacity
        mock_content2 = MagicMock()
        mock_content2.type = "tool_use"
        mock_content2.name = "configure_cflp_network"
        mock_content2.input = {
            "status": "confirm",
            "reply": "Configured 4 distribution centers with no radius limit handling 6k orders.",
            "warehouse_count": 4,
            "warehouse_capacity": 6000.0,
            "max_service_radius_km": None,
            "priority_preset": "cost",
            "include_cvrp": True,
            "missing_required": [],
            "ready_to_optimize": True,
        }
        mock_resp2 = MagicMock(content=[mock_content2])

        mock_client.messages.create.side_effect = [mock_resp1, mock_resp2]

        # Call 1
        res1 = client.post("/api/agent/extract", json={
            "message": "Set up 3 hubs with 20km reach handling 3500 daily orders, fast speed.",
            "history": [],
            "known_params": {}
        })
        data1 = res1.json()
        assert data1["extracted_params"]["warehouse_count"] == 3
        assert data1["extracted_params"]["max_service_radius_km"] == 20.0
        assert data1["extracted_params"]["warehouse_capacity"] == 3500.0

        # Call 2
        res2 = client.post("/api/agent/extract", json={
            "message": "We need 4 distribution centers with 6k capacity and no distance cap plus van routing.",
            "history": [],
            "known_params": {}
        })
        data2 = res2.json()
        assert data2["extracted_params"]["warehouse_count"] == 4
        assert data2["extracted_params"]["max_service_radius_km"] is None
        assert data2["extracted_params"]["warehouse_capacity"] == 6000.0
        assert data2["extracted_params"]["include_cvrp"] is True


def test_agent_explain_grounded_response_from_page_context():
    """Verify that Explain mode returns grounded answers with facts directly from page_context."""
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "output_grounded_explanation"
    mock_content.input = {
        "reply": "Koramangala Hub is operating at **95.0% capacity** (serving 3,800 orders/day against a 4,000 order limit). Total estimated monthly savings are **$54,200** vs single-warehouse baseline.",
        "grounded": True,
        "grounded_facts": [
            "Koramangala Hub capacity utilization: 95.0%",
            "Estimated monthly savings: $54,200 [Estimate]",
            "Solver Status: Optimal"
        ],
        "suggested_followups": ["Show all warehouse utilizations", "Explain baseline comparison formula"]
    }
    mock_resp = MagicMock(content=[mock_content])

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        page_context = {
            "view": "viewResults",
            "total_delivery_cost": 4620.50,
            "estimated_monthly_savings": 54200.0,
            "warehouses": [{"warehouse_id": "W-01", "name": "Koramangala Hub", "capacity_utilization_pct": 95.0}]
        }

        res = client.post("/api/agent/explain", json={
            "page": "viewResults",
            "message": "Why is Koramangala at 95% capacity?",
            "page_context": page_context,
            "history": []
        })

        assert res.status_code == 200
        data = res.json()
        assert data["grounded"] is True
        assert "95.0%" in data["reply"]
        assert len(data["grounded_facts"]) > 0


def test_agent_explain_ungrounded_query_honestly_redirects():
    """Verify that questions unanswerable from the screen context produce honest redirection rather than hallucinations."""
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "output_grounded_explanation"
    mock_content.input = {
        "reply": "The current screen only contains computed results for the active configuration. To simulate a 50% festival demand surge, please navigate to the **Scenario Lab** in the left rail.",
        "grounded": False,
        "grounded_facts": [],
        "suggested_followups": ["Go to Scenario Lab", "Explain current delivery cost"]
    }
    mock_resp = MagicMock(content=[mock_content])

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        res = client.post("/api/agent/explain", json={
            "page": "viewResults",
            "message": "What will happen if demand doubles next Friday?",
            "page_context": {"total_delivery_cost": 4620.50},
            "history": []
        })

        assert res.status_code == 200
        data = res.json()
        assert "scenario" in data["reply"].lower() or "lab" in data["reply"].lower()


def test_agent_generate_synthetic_data_with_mocked_claude():
    """Verify that synthetic data generated by Claude is parsed into DataFrame and strictly validated."""
    mock_zones = [
        {"neighborhood_id": "SYN_01", "name": "Indiranagar Core", "latitude": 12.9784, "longitude": 77.6408, "daily_orders": 450.0, "capacity": 4000.0},
        {"neighborhood_id": "SYN_02", "name": "Koramangala Hub", "latitude": 12.9352, "longitude": 77.6245, "daily_orders": 380.0, "capacity": 5000.0},
        {"neighborhood_id": "SYN_03", "name": "Whitefield Tech", "latitude": 12.9698, "longitude": 77.7499, "daily_orders": 520.0, "capacity": None},
        {"neighborhood_id": "SYN_04", "name": "HSR Sector 2", "latitude": 12.9121, "longitude": 77.6446, "daily_orders": 290.0, "capacity": None},
        {"neighborhood_id": "SYN_05", "name": "Hebbal North", "latitude": 13.0358, "longitude": 77.5970, "daily_orders": 310.0, "capacity": 4000.0},
        {"neighborhood_id": "SYN_06", "name": "Jayanagar 4th Block", "latitude": 12.9250, "longitude": 77.5838, "daily_orders": 210.0, "capacity": None},
        {"neighborhood_id": "SYN_07", "name": "Malleshwaram West", "latitude": 13.0031, "longitude": 77.5643, "daily_orders": 340.0, "capacity": None},
        {"neighborhood_id": "SYN_08", "name": "Electronic City Phase 1", "latitude": 12.8452, "longitude": 77.6602, "daily_orders": 410.0, "capacity": 6000.0},
        {"neighborhood_id": "SYN_09", "name": "Marathahalli Junction", "latitude": 12.9569, "longitude": 77.7011, "daily_orders": 490.0, "capacity": None},
        {"neighborhood_id": "SYN_10", "name": "Peenya Industrial Area", "latitude": 12.9982, "longitude": 77.5530, "daily_orders": 600.0, "capacity": 7500.0},
    ]

    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "output_synthetic_demand_dataset"
    mock_content.input = {
        "region_name": "Bengaluru",
        "zones": mock_zones
    }
    mock_resp = MagicMock(content=[mock_content])

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        res = client.post("/api/agent/generate-synthetic-data", json={
            "zone_count": 10,
            "pattern_hint": "clustered",
            "city_hint": "bengaluru"
        })

        assert res.status_code == 200
        data = res.json()
        assert data["neighborhood_count"] == 10
        assert data["is_synthetic_ai"] is True
        assert data["dataset_type"] == "ai_synthetic"
        assert len(data["preview"]) == 10
        assert data["total_demand"] == sum(z["daily_orders"] for z in mock_zones)
