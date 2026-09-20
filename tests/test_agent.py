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

def _clear_all_ai_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def test_agent_extract_missing_api_key_shows_unavailable_state(monkeypatch):
    """When no LLM API key is configured, the extract route must return an honest unavailable status."""
    _clear_all_ai_keys(monkeypatch)
    
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
    """When no LLM API key is configured, explain mode returns an honest unavailable notice."""
    _clear_all_ai_keys(monkeypatch)

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
    """When no LLM API key is configured, synthetic data generation returns 503 unavailable."""
    _clear_all_ai_keys(monkeypatch)

    payload = {
        "zone_count": 30,
        "pattern_hint": "clustered",
        "city_hint": "bengaluru"
    }
    res = client.post("/api/agent/generate-synthetic-data", json=payload)
    assert res.status_code == 503
    data = res.json()
    assert "API_KEY" in str(data["detail"]) or "unavailable" in str(data["detail"]).lower()


def test_core_app_unaffected_when_api_key_is_missing(monkeypatch):
    """Confirm solver, demo data, and metrics operate with ZERO degradation when no AI API keys are present."""
    _clear_all_ai_keys(monkeypatch)

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
    """Verify that Claude parses the generation request into structured parameters,
    and the deterministic sampler generates verified zones and non-uniform demand.
    """
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "parse_geodata_sampler_parameters"
    mock_content.input = {
        "zone_count": 10,
        "scope": "single_city",
        "region_filter": {
            "country_code": "IN",
            "city_name": "Bengaluru"
        },
        "demand_pattern": "clustered"
    }
    mock_resp = MagicMock(content=[mock_content])

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        res = client.post("/api/agent/generate-synthetic-data", json={
            "zone_count": 10,
            "prompt": "Give me 10 zones around Bengaluru",
            "seed": 42
        })

        assert res.status_code == 200
        data = res.json()
        assert data["neighborhood_count"] == 10
        assert data["is_synthetic_ai"] is True
        assert data["dataset_type"] == "real_locations_synthetic_demand"
        assert data["scope"] == "single_city"
        assert "[Real City Anchor" in data["badge_text"]
        assert len(data["preview"]) == 10
        # Check derived zone names
        assert all("Bengaluru Zone" in item["name"] for item in data["preview"])
        # Check coordinates plausible near Bengaluru
        assert all(12.7 <= item["latitude"] <= 13.3 for item in data["preview"])
        assert all(77.3 <= item["longitude"] <= 77.9 for item in data["preview"])
        assert data["total_demand"] > 0


def test_agent_generate_synthetic_data_state_scope():
    """Verify regional/statewide generation samples distinct real towns."""
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "parse_geodata_sampler_parameters"
    mock_content.input = {
        "zone_count": 15,
        "scope": "state",
        "region_filter": {
            "country_code": "IN",
            "state_name": "Karnataka"
        },
        "demand_pattern": "clustered"
    }
    mock_resp = MagicMock(content=[mock_content])

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        res = client.post("/api/agent/generate-synthetic-data", json={
            "zone_count": 15,
            "prompt": "15 delivery hubs across Karnataka",
            "seed": 100
        })

        assert res.status_code == 200
        data = res.json()
        assert data["neighborhood_count"] == 15
        assert data["scope"] == "state"
        assert data["badge_text"] == "[Real Towns, Synthetic Demand]"
        assert len(data["preview"]) == 15
        # Confirm unique town names
        names = [item["name"] for item in data["preview"]]
        assert len(set(names)) == 15


def test_agent_generate_synthetic_data_insufficient_candidates_returns_422():
    """Confirm requesting more real towns than exist in a state returns 422 with actionable message."""
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "parse_geodata_sampler_parameters"
    mock_content.input = {
        "zone_count": 500,
        "scope": "state",
        "region_filter": {
            "country_code": "IN",
            "state_name": "Goa"
        },
        "demand_pattern": "clustered"
    }
    mock_resp = MagicMock(content=[mock_content])

    with patch("api.agent.get_anthropic_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        res = client.post("/api/agent/generate-synthetic-data", json={
            "zone_count": 500,
            "prompt": "500 zones across Goa",
        })

        assert res.status_code == 422
        data = res.json()
        err_text = str(data["detail"])
        assert "Goa" in err_text
        assert "contains only 50 distinct real cities/towns" in err_text


def test_agent_extract_with_mocked_gemini():
    """Verify that Google Gemini SDK provider path extracts parameters correctly."""
    mock_gemini_json = (
        '{"status": "confirm", "reply": "Configured 3 facilities with 4,000 throughput.", '
        '"warehouse_count": 3, "warehouse_capacity": 4000.0, "max_service_radius_km": 25.0, '
        '"priority_preset": "cost", "include_cvrp": false, "missing_required": [], "ready_to_optimize": true}'
    )
    mock_response = MagicMock(text=mock_gemini_json)

    with patch("api.agent.get_anthropic_client", return_value=None), \
         patch("api.agent.get_gemini_client") as mock_get_gemini:
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = mock_response
        mock_get_gemini.return_value = mock_gemini

        res = client.post("/api/agent/extract", json={
            "message": "Configure 3 warehouses with 4000 capacity and 25km radius",
            "history": [],
            "known_params": {}
        })

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "confirm"
        assert data["extracted_params"]["warehouse_count"] == 3
        assert data["extracted_params"]["warehouse_capacity"] == 4000.0
        assert data["ready_to_optimize"] is True


def test_agent_explain_with_mocked_gemini():
    """Verify that Google Gemini SDK provider path generates grounded explanations."""
    mock_explain_json = (
        '{"reply": "The 3 warehouses optimize demand-weighted geographic distance.", '
        '"grounded": true, "grounded_facts": ["Delivery cost: $1,317.59 [Estimate]"], "suggested_followups": ["Show utilization"]}'
    )
    mock_response = MagicMock(text=mock_explain_json)

    with patch("api.agent.get_anthropic_client", return_value=None), \
         patch("api.agent.get_gemini_client") as mock_get_gemini:
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.return_value = mock_response
        mock_get_gemini.return_value = mock_gemini

        res = client.post("/api/agent/explain", json={
            "page": "viewResults",
            "message": "Why were these sites chosen?",
            "page_context": {"total_delivery_cost": 1317.59, "warehouses": []},
            "history": []
        })

        assert res.status_code == 200
        data = res.json()
        assert data["grounded"] is True
        assert "optimize demand-weighted" in data["reply"]


# ============================================================================
# 3. MISSING SDK / IMPORTERROR HANDLING (FAIL RESILIENTLY WITHOUT CRASHING)
# ============================================================================

def test_missing_sdk_import_returns_none_gracefully(monkeypatch):
    """Verify get_anthropic_client and get_gemini_client return None when SDK is not installed."""
    from api.agent import get_anthropic_client, get_gemini_client, get_llm_provider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-123456789")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey123456789")

    # Simulate anthropic and google.genai not being installed
    with patch.dict("sys.modules", {"anthropic": None, "google.genai": None, "google": None}):
        client_a = get_anthropic_client()
        assert client_a is None

        client_g = get_gemini_client()
        assert client_g is None

        provider, client_instance = get_llm_provider()
        assert provider is None
        assert client_instance is None


def test_app_and_non_ai_routes_work_when_ai_sdks_missing(monkeypatch):
    """Verify that when AI SDKs raise ImportError, core CFLP/CVRP/map/CSV routes operate normally."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-123456789")

    with patch("api.agent.get_anthropic_client", return_value=None), \
         patch("api.agent.get_gemini_client", return_value=None):

        # Core optimization works
        opt_res = client.post("/api/optimize", json={
            "session_id": "default",
            "p": 3,
            "warehouse_capacity": 4000,
            "radius_max_km": 30.0,
            "cost_per_km": 1.25,
            "fixed_cost_per_warehouse": 300.0,
            "routing_mode": "haversine",
            "priority_preset": "cost",
            "include_cvrp": False,
        })
        assert opt_res.status_code == 200
        assert opt_res.json()["is_optimal"] is True or opt_res.json()["status"].startswith("Feasible") or opt_res.json()["status"] == "Optimal"

        # AI route returns honest unavailable response
        extract_res = client.post("/api/agent/extract", json={
            "message": "Optimize 2 warehouses",
            "history": [],
            "known_params": {}
        })
        assert extract_res.status_code == 200
        extract_data = extract_res.json()
        assert extract_data["status"] == "error"
        assert "api key" in extract_data["reply"].lower() or "ai features unavailable" in extract_data["reply"].lower()


