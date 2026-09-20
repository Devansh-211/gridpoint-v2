"""Conversational Optimization Agent logic for GRIDPOINT.
Supports Anthropic Claude and Google Gemini LLMs via official SDKs (anthropic and google-genai).
Strictly adheres to Hackathon Honesty Rules, B2B Operations rigor, and Structured Grounding.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
from api.schemas import AgentExtractRequest, AgentExtractResponse, ExtractedParams, AgentMessage
from core.validation import validate_neighborhood_dataframe

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")



def get_anthropic_client() -> Optional[Any]:
    """Returns an authenticated Anthropic client if ANTHROPIC_API_KEY is configured and SDK is installed."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_") or api_key == "placeholder":
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    except ImportError:
        logger.warning("Anthropic SDK ('anthropic') is not installed in the active Python environment.")
        return None
    except Exception as e:
        logger.error("Failed to initialize Anthropic client: %s", e)
        return None


def get_gemini_client() -> Optional[Any]:
    """Returns an authenticated Google GenAI client if GEMINI_API_KEY is configured and SDK is installed."""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    gemini_key = gemini_key.strip()
    if not gemini_key or gemini_key.startswith("your_") or gemini_key == "placeholder":
        return None
    try:
        from google import genai
        return genai.Client(api_key=gemini_key)
    except ImportError:
        logger.warning("Google GenAI SDK ('google-genai') is not installed in the active Python environment.")
        return None
    except Exception as e:
        logger.error("Failed to initialize Google GenAI client: %s", e)
        return None


def get_llm_provider() -> Tuple[Optional[str], Optional[Any]]:
    """Returns active LLM provider ('anthropic' or 'gemini') and client if configured in environment."""
    client_a = get_anthropic_client()
    if client_a:
        return "anthropic", client_a

    client_g = get_gemini_client()
    if client_g:
        return "gemini", client_g

    return None, None


# ============================================================================
# 1. CONVERSATIONAL PARAMETER EXTRACTION (SETUP MODE)
# ============================================================================

CFLP_EXTRACT_TOOL = {
    "name": "configure_cflp_network",
    "description": "Extract structured optimization parameters and draft the dialogue response for GRIDPOINT CFLP/CVRP.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["clarify", "confirm", "error"],
                "description": "'clarify' if required parameters are missing or ambiguous, 'confirm' if all required parameters are resolved, 'error' if out of bounds or invalid."
            },
            "reply": {
                "type": "string",
                "description": "Professional, concise response directly addressing what the user typed."
            },
            "warehouse_count": {
                "type": ["integer", "null"],
                "description": "Number of warehouse facilities p to open (1 to 5). Null if unspecified."
            },
            "warehouse_capacity": {
                "type": ["number", "null"],
                "description": "Daily order throughput capacity per warehouse in orders/day (must be > 0). Null if unspecified."
            },
            "max_service_radius_km": {
                "type": ["number", "null"],
                "description": "Maximum delivery service radius per warehouse in km (straight-line Haversine). Null if unlimited."
            },
            "cost_per_km": {
                "type": "number",
                "description": "Transit cost per km in dollars (default 1.25)."
            },
            "fixed_cost_per_warehouse": {
                "type": "number",
                "description": "Daily facility fixed lease cost in dollars (default 300.0)."
            },
            "priority_preset": {
                "type": "string",
                "enum": ["cost", "speed", "sustainability"],
                "description": "Optimization priority preset."
            },
            "include_cvrp": {
                "type": "boolean",
                "description": "True if tactical vehicle routing / multi-stop tours / van fleet is requested."
            },
            "vehicle_capacity": {
                "type": "integer",
                "description": "Vehicle payload capacity in orders per vehicle (default 250)."
            },
            "vehicle_fixed_cost": {
                "type": "number",
                "description": "Fixed daily cost per vehicle (default 150.0)."
            },
            "missing_required": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of missing required parameters among ['warehouse_count', 'warehouse_capacity']."
            },
            "ready_to_optimize": {
                "type": "boolean",
                "description": "True only when status is 'confirm' and both warehouse_count and warehouse_capacity are defined."
            },
            "suggested_prompts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-3 short suggested next prompt replies for the user."
            }
        },
        "required": ["status", "reply", "ready_to_optimize", "missing_required"]
    }
}


def process_agent_dialog(req: AgentExtractRequest) -> AgentExtractResponse:
    """Processes user message and dialogue history using Anthropic Claude or Google Gemini."""
    provider, client = get_llm_provider()
    if not provider or not client:
        return AgentExtractResponse(
            status="error",
            reply="AI features unavailable — no API key configured. Please add ANTHROPIC_API_KEY or GEMINI_API_KEY to your .env file to enable the conversational optimization assistant.",
            extracted_params=ExtractedParams(),
            missing_required=["api_key"],
            ready_to_optimize=False,
            defaults_applied=[],
            warnings=["No ANTHROPIC_API_KEY or GEMINI_API_KEY found in environment or .env file."],
            suggested_prompts=[],
        )

    system_prompt = (
        "You are the Conversational Logistics Optimization Assistant for GRIDPOINT, an enterprise B2B decision-support tool. "
        "Your task is to parse plain-language instructions from operations managers into structured parameters for "
        "Capacitated Facility Location Problem (CFLP) and Capacitated Vehicle Routing Problem (CVRP).\n\n"
        "Parameters & Rules:\n"
        "1. warehouse_count (p): Integer between 1 and 5 (maximum 5 facilities supported). If user asks for >5 or <1, flag as status='error'.\n"
        "2. warehouse_capacity: Float in orders/day (throughput per warehouse, must be > 0, typical 1,000 to 10,000). If <=0, flag as error. If user uses pallet/unit storage terms, clarify that GRIDPOINT measures throughput in orders/day.\n"
        "3. max_service_radius_km: Float distance in km (straight-line Haversine). If user specifies drive time (e.g. '20 minutes'), clarify that GRIDPOINT measures geographic km distance. If unlimited or no limit, set to null.\n"
        "4. cost_per_km: Float ($/km, default 1.25).\n"
        "5. fixed_cost_per_warehouse: Float ($/day lease, default 300.0).\n"
        "6. priority_preset: 'cost', 'speed', or 'sustainability'.\n"
        "7. include_cvrp: Boolean (true if user mentions vehicle routing, fleet, vans, tours, multi-stop).\n"
        "8. vehicle_capacity: Integer (orders/vehicle, default 250).\n"
        "9. vehicle_fixed_cost: Float ($/vehicle, default 150.0).\n\n"
        "Workflow:\n"
        "- If required parameters ('warehouse_count' and 'warehouse_capacity') are not yet specified, set status='clarify', ready_to_optimize=false, and ask exactly one concise question.\n"
        "- When all required parameters are resolved, set status='confirm', ready_to_optimize=true, and summarize the configuration."
    )

    tool_input = None

    if provider == "anthropic":
        messages = []
        if req.history:
            for m in req.history[-8:]:
                messages.append({"role": m.role if m.role in ["user", "assistant"] else "user", "content": m.content})
        user_prompt = f"Known parameters so far: {json.dumps(req.known_params or {})}\nUser instruction: {req.message}"
        messages.append({"role": "user", "content": user_prompt})

        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
                tools=[CFLP_EXTRACT_TOOL],
                tool_choice={"type": "tool", "name": "configure_cflp_network"}
            )
            for content in response.content:
                if content.type == "tool_use" and content.name == "configure_cflp_network":
                    tool_input = content.input
                    break
        except Exception as e:
            logger.error("Anthropic API call failed in agent extract: %s", e)
            return AgentExtractResponse(
                status="error",
                reply=f"AI features temporarily unavailable: {str(e)}. Please check your API key configuration.",
                extracted_params=ExtractedParams(),
                missing_required=["api_key"],
                ready_to_optimize=False,
                defaults_applied=[],
                warnings=[str(e)],
                suggested_prompts=[],
            )

    elif provider == "gemini":
        try:
            from google.genai import types
            prompt = (
                f"{system_prompt}\n\n"
                f"Known parameters: {json.dumps(req.known_params or {})}\n"
                f"History: {[m.model_dump() for m in req.history[-6:]]}\n"
                f"User message: {req.message}\n\n"
                "Return a structured JSON object with keys: "
                "status ('clarify'|'confirm'|'error'), reply (string), warehouse_count (int|null), warehouse_capacity (float|null), "
                "max_service_radius_km (float|null), cost_per_km (float), fixed_cost_per_warehouse (float), priority_preset ('cost'|'speed'|'sustainability'), "
                "include_cvrp (bool), vehicle_capacity (int), vehicle_fixed_cost (float), missing_required (list of strings), ready_to_optimize (bool), suggested_prompts (list of strings)."
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            tool_input = json.loads(response.text)
        except Exception as e:
            logger.error("Google Gemini API call failed in agent extract: %s", e)
            return AgentExtractResponse(
                status="error",
                reply=f"AI features temporarily unavailable: {str(e)}. Please check your API key configuration.",
                extracted_params=ExtractedParams(),
                missing_required=["api_key"],
                ready_to_optimize=False,
                defaults_applied=[],
                warnings=[str(e)],
                suggested_prompts=[],
            )

    if not tool_input:
        return AgentExtractResponse(
            status="error",
            reply="Model did not return structured parameters. Please try rephrasing your request.",
            extracted_params=ExtractedParams(),
            missing_required=[],
            ready_to_optimize=False,
            defaults_applied=[],
            warnings=[],
            suggested_prompts=[],
        )


    extracted = ExtractedParams(
        warehouse_count=tool_input.get("warehouse_count"),
        warehouse_capacity=tool_input.get("warehouse_capacity"),
        max_service_radius_km=tool_input.get("max_service_radius_km"),
        cost_per_km=tool_input.get("cost_per_km", 1.25),
        fixed_cost_per_warehouse=tool_input.get("fixed_cost_per_warehouse", 300.0),
        priority_preset=tool_input.get("priority_preset", "cost"),
        include_cvrp=tool_input.get("include_cvrp", False),
        vehicle_capacity=tool_input.get("vehicle_capacity", 250),
        vehicle_fixed_cost=tool_input.get("vehicle_fixed_cost", 150.0),
    )

    status_val = tool_input.get("status", "clarify")
    ready_to_optimize = bool(tool_input.get("ready_to_optimize", False))
    missing_required = tool_input.get("missing_required", [])
    reply = tool_input.get("reply", "")
    suggested_prompts = tool_input.get("suggested_prompts", [])

    # Server-side verification of bounds
    if extracted.warehouse_count is not None:
        if extracted.warehouse_count < 1 or extracted.warehouse_count > 5:
            status_val = "error"
            ready_to_optimize = False
            if "warehouse_count" not in missing_required:
                missing_required.append("warehouse_count")

    if extracted.warehouse_capacity is not None and extracted.warehouse_capacity <= 0:
        status_val = "error"
        ready_to_optimize = False
        if "warehouse_capacity" not in missing_required:
            missing_required.append("warehouse_capacity")

    confirmation_card = None
    if status_val == "confirm" and ready_to_optimize:
        confirmation_card = {
            "params": {
                "warehouse_count": extracted.warehouse_count,
                "warehouse_capacity": extracted.warehouse_capacity,
                "max_service_radius_km": extracted.max_service_radius_km,
                "cost_per_km": extracted.cost_per_km,
                "fixed_cost_per_warehouse": extracted.fixed_cost_per_warehouse,
                "priority_preset": extracted.priority_preset,
                "include_cvrp": extracted.include_cvrp,
            },
            "defaults_applied": ["Cost per km: $1.25", "Facility lease: $300/day"],
            "warnings": ["Distances represent straight-line Haversine geographic arcs."] if not extracted.include_cvrp else ["Tactical CVRP vehicle routes will be generated with OR-Tools."]
        }

    return AgentExtractResponse(
        status=status_val,
        reply=reply,
        extracted_params=extracted,
        missing_required=missing_required,
        ready_to_optimize=ready_to_optimize,
        defaults_applied=["Cost per km: $1.25", "Facility lease: $300/day"] if ready_to_optimize else [],
        warnings=["Distances represent straight-line Haversine geographic arcs."] if ready_to_optimize else [],
        suggested_prompts=suggested_prompts,
        confirmation_card=confirmation_card,
    )


# ============================================================================
# 2. AI SYNTHETIC DATA GENERATION (PHASE 3)
# ============================================================================

# ============================================================================
# 2. REAL-GEODATA SAMPLER & LLM REQUEST PARSER (REPLACING AI FABRICATION)
# ============================================================================

PARSE_GEODATA_REQUEST_TOOL = {
    "name": "parse_geodata_sampler_parameters",
    "description": "Parse the user's natural language request into structured generation parameters for the deterministic geodata sampler.",
    "input_schema": {
        "type": "object",
        "properties": {
            "zone_count": {
                "type": "integer",
                "description": "Number of delivery zones to generate (10 to 150, default 50)."
            },
            "scope": {
                "type": "string",
                "enum": ["state", "single_city"],
                "description": "'state' if multi-city or statewide regional distribution; 'single_city' if zones/neighborhoods anchored to a single city."
            },
            "region_filter": {
                "type": "object",
                "properties": {
                    "country_code": {
                        "type": "string",
                        "description": "ISO 2-letter country code (default 'IN')."
                    },
                    "state_name": {
                        "type": ["string", "null"],
                        "description": "State name (e.g. 'Karnataka', 'Maharashtra'). Required if scope is 'state'."
                    },
                    "city_name": {
                        "type": ["string", "null"],
                        "description": "Anchor city name (e.g. 'Bengaluru', 'Mumbai', 'Delhi'). Required if scope is 'single_city'."
                    }
                },
                "required": ["country_code"]
            },
            "demand_pattern": {
                "type": "string",
                "enum": ["clustered"],
                "description": "Demand distribution pattern — must always be 'clustered'."
            }
        },
        "required": ["zone_count", "scope", "region_filter", "demand_pattern"]
    }
}


def parse_geodata_request_with_llm(prompt: str) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Uses LLM (Claude or Gemini) strictly to parse user's free-text request into generation parameters.
    No coordinates, names, or numeric values are produced by the LLM.
    """
    provider, client = get_llm_provider()
    if not provider or not client:
        return False, ["AI features unavailable — no ANTHROPIC_API_KEY or GEMINI_API_KEY configured in .env."], {}

    system_prompt = (
        "You are the Request Parameter Parser for GRIDPOINT's Real-Geodata Sampler.\n"
        "Your ONLY role is to parse the user's plain-language request into a structured configuration object.\n\n"
        "Rules:\n"
        "1. scope: Choose 'state' if the user asks for a regional, multi-city, or statewide distribution "
        "(e.g. 'across Karnataka', 'cities in Maharashtra'). Choose 'single_city' if the user asks for "
        "neighborhoods or delivery zones within/around a single metropolitan area (e.g. 'around Bengaluru', 'in Mumbai').\n"
        "2. region_filter:\n"
        "   - country_code: Default to 'IN' unless another country is explicitly specified.\n"
        "   - state_name: State name when scope is 'state' (e.g. 'Karnataka', 'Tamil Nadu', 'Maharashtra').\n"
        "   - city_name: City name when scope is 'single_city' (e.g. 'Bengaluru', 'Mumbai', 'Delhi NCR').\n"
        "3. zone_count: Integer between 10 and 150 (default 50).\n"
        "4. demand_pattern: Always set to 'clustered' — uniform demand is never allowed under any circumstances.\n"
        "Do NOT generate or invent coordinates, names, or demand values. Only output the parameter object."
    )

    tool_input = None

    if provider == "anthropic":
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                tools=[PARSE_GEODATA_REQUEST_TOOL],
                tool_choice={"type": "tool", "name": "parse_geodata_sampler_parameters"}
            )
            for content in response.content:
                if content.type == "tool_use" and content.name == "parse_geodata_sampler_parameters":
                    tool_input = content.input
                    break
        except Exception as e:
            logger.error("Anthropic API call failed in parse_geodata_request: %s", e)
            return False, [f"Anthropic API call failed: {str(e)}"], {}

    elif provider == "gemini":
        try:
            from google.genai import types
            g_prompt = (
                f"{system_prompt}\n\n"
                f"User Request: {prompt}\n\n"
                "Return a JSON object with keys: "
                "zone_count (int), scope ('state'|'single_city'), "
                "region_filter (object with country_code, state_name, city_name), "
                "demand_pattern ('clustered')."
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=g_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            tool_input = json.loads(response.text)
        except Exception as e:
            logger.error("Google Gemini API call failed in parse_geodata_request: %s", e)
            return False, [f"Google Gemini API call failed: {str(e)}"], {}

    if not tool_input:
        return False, ["Model failed to parse structured generation parameters from request."], {}

    # Validate and normalize
    zone_cnt = max(10, min(int(tool_input.get("zone_count", 50)), 150))
    scope_val = "state" if tool_input.get("scope") == "state" else "single_city"
    rf = tool_input.get("region_filter", {}) or {}
    country = rf.get("country_code", "IN") or "IN"

    normalized = {
        "zone_count": zone_cnt,
        "scope": scope_val,
        "region_filter": {
            "country_code": country,
            "state_name": rf.get("state_name"),
            "city_name": rf.get("city_name"),
        },
        "demand_pattern": "clustered",
    }
    return True, [], normalized


def generate_synthetic_demand_dataset(
    zone_count: int = 50,
    pattern: str = "clustered",
    region_name: str = "Bengaluru",
    prompt: Optional[str] = None,
    scope: Optional[str] = None,
    region_filter: Optional[Dict[str, Any]] = None,
    seed: Optional[int] = None,
) -> Tuple[bool, List[str], Optional[Any], Dict[str, Any]]:
    """Generates realistic delivery zones using deterministic sampling over real public geodata
    (dr5hn/countries-states-cities-database under ODbL 1.0).
    The LLM is invoked strictly to parse plain-language instructions into structured parameters.
    Coordinates, zone names, and non-uniform demand values are generated deterministically by numpy/pandas.
    """
    from core.geodata import generate_geodata_dataset, InsufficientCandidatesError

    # Determine whether AI parameter parsing is needed
    if prompt:
        ok, errors, parsed_params = parse_geodata_request_with_llm(prompt)
        if not ok:
            return False, errors, None, {}
    elif scope is None and region_filter is None:
        # User came through AI generation flow without pre-structured parameters:
        # AI parses the instruction into parameters.
        ai_prompt = f"Generate {zone_count} delivery zones for {region_name} with {pattern} demand pattern."
        ok, errors, parsed_params = parse_geodata_request_with_llm(ai_prompt)
        if not ok:
            return False, errors, None, {}
    else:
        # Pre-structured parameters provided directly
        parsed_params = {
            "zone_count": max(10, min(int(zone_count), 150)),
            "scope": scope or "single_city",
            "region_filter": region_filter or {"country_code": "IN", "city_name": region_name},
            "demand_pattern": "clustered",
        }

    try:
        is_valid, errors, clean_df, metadata = generate_geodata_dataset(
            params=parsed_params,
            seed=seed,
        )
        return is_valid, errors, clean_df, metadata
    except InsufficientCandidatesError as e:
        return False, [str(e)], None, {"error": str(e)}
    except Exception as e:
        logger.error("Error in deterministic geodata sampler: %s", e)
        return False, [f"Deterministic geodata sampler failed: {str(e)}"], None, {}


# ============================================================================
# 3. GROUNDED PER-PAGE "ASK AI TO EXPLAIN" MODE (PHASE 4)
# ============================================================================

EXPLAIN_TOOL = {
    "name": "output_grounded_explanation",
    "description": "Output an explanation strictly grounded in the computed screen context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "Markdown formatted explanation grounded strictly in page_context. If unanswerable from the context, state so honestly."
            },
            "grounded": {
                "type": "boolean",
                "description": "True if answered from page_context data, False if question cannot be answered from current screen context."
            },
            "grounded_facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key verified facts extracted directly from page_context used to support the answer."
            },
            "suggested_followups": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-3 relevant follow-up questions for the active screen."
            }
        },
        "required": ["reply", "grounded", "grounded_facts", "suggested_followups"]
    }
}


def process_agent_explanation(
    page: str,
    message: str,
    page_context: Dict[str, Any],
    history: Optional[List[AgentMessage]] = None,
) -> Dict[str, Any]:
    """Generates grounded explanations strictly based on real computed page context using Claude or Gemini."""
    provider, client = get_llm_provider()
    if not provider or not client:
        return {
            "reply": "AI features unavailable — no API key configured. Please add ANTHROPIC_API_KEY or GEMINI_API_KEY to your .env file to enable grounded AI explanations.",
            "page": page,
            "grounded": False,
            "grounded_facts": [],
            "suggested_followups": [],
        }

    if not page_context:
        return {
            "reply": (
                "There are currently no computed optimization results on this screen. "
                "Please load the demo dataset or upload a delivery zone CSV, configure constraints, "
                "and click **Run Network Optimization** to generate grounded metrics to explain."
            ),
            "page": page,
            "grounded": False,
            "grounded_facts": [],
            "suggested_followups": ["Load Bengaluru Demo", "Upload CSV Dataset", "Configure Network Parameters"]
        }

    system_prompt = (
        "You are the Explainability AI for GRIDPOINT, an enterprise B2B logistics decision-support platform.\n"
        "You are in read-only EXPLAIN mode. Your role is to interpret and explain the active screen's computed results.\n\n"
        "CRITICAL GROUNDING RULES:\n"
        "1. You must answer ONLY from the provided `page_context` object. Never invent, extrapolate, or hallucinate metrics, costs, savings, or numbers not present in `page_context`.\n"
        "2. If the user's question cannot be answered using the provided `page_context`, or asks about uncomputed hypothetical what-ifs (e.g. surges, outages, custom parameter changes), YOU MUST HONESTLY STATE that the current screen's computed data does not answer that question, and direct the user to the appropriate screen (e.g. Scenario Lab for demand surges/shock tests, Disruption & Resilience for facility outage simulations, Analytics & Trade-off for the p=1..5 curve, or Network Configuration).\n"
        "3. Label financial and emissions figures with [Estimate] where appropriate."
    )

    tool_input = None

    if provider == "anthropic":
        messages = []
        if history:
            for m in history[-6:]:
                messages.append({"role": m.role if m.role in ["user", "assistant"] else "user", "content": m.content})
        user_prompt = f"Active Screen: {page}\nComputed Screen Context (JSON):\n{json.dumps(page_context, indent=2)}\n\nUser Question: {message}"
        messages.append({"role": "user", "content": user_prompt})

        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
                tools=[EXPLAIN_TOOL],
                tool_choice={"type": "tool", "name": "output_grounded_explanation"}
            )
            for content in response.content:
                if content.type == "tool_use" and content.name == "output_grounded_explanation":
                    tool_input = content.input
                    break
        except Exception as e:
            logger.error("Anthropic API call failed in agent explain: %s", e)
            return {
                "reply": f"AI features temporarily unavailable: {str(e)}. Please check your API key configuration.",
                "page": page,
                "grounded": False,
                "grounded_facts": [],
                "suggested_followups": [],
            }

    elif provider == "gemini":
        try:
            from google.genai import types
            prompt = (
                f"{system_prompt}\n\n"
                f"Screen: {page}\n"
                f"Page Context: {json.dumps(page_context)}\n"
                f"Question: {message}\n\n"
                "Return a JSON object with keys: "
                "reply (markdown string), grounded (boolean), grounded_facts (list of strings), suggested_followups (list of strings)."
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            tool_input = json.loads(response.text)
        except Exception as e:
            logger.error("Google Gemini API call failed in agent explain: %s", e)
            return {
                "reply": f"AI features temporarily unavailable: {str(e)}. Please check your API key configuration.",
                "page": page,
                "grounded": False,
                "grounded_facts": [],
                "suggested_followups": [],
            }

    if not tool_input:
        return {
            "reply": "AI explanation unavailable. Please try rephrasing your question.",
            "page": page,
            "grounded": False,
            "grounded_facts": [],
            "suggested_followups": [],
        }


    return {
        "reply": tool_input.get("reply", ""),
        "page": page,
        "grounded": bool(tool_input.get("grounded", True)),
        "grounded_facts": tool_input.get("grounded_facts", []),
        "suggested_followups": tool_input.get("suggested_followups", []),
    }
