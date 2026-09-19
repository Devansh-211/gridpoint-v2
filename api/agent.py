"""Conversational Optimization Agent logic for GRIDPOINT.
Parses natural language logistics instructions into structured CFLP/CVRP parameters.
Strictly adheres to Hackathon Honesty Rules and B2B Operations rigor.
"""

import os
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from api.schemas import AgentMessage, ExtractedParams, AgentExtractResponse

logger = logging.getLogger(__name__)

# Number word mapping for plain English inputs
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
}


def _parse_warehouse_count(text: str) -> Optional[int]:
    """Extracts warehouse count p (1 to 5)."""
    # Look for "p = 3", "3-warehouse", "3 warehouses", "open 3 facilities", "3 sites", "3 hubs"
    patterns = [
        r"\bp\s*[:=]\s*(\d+)\b",
        r"\b(\d+)[-\s]*(?:warehouses?|facilities|sites?|hubs?|locations?|distribution centers?)\b",
        r"\b(?:open|plan|place|locate|build)\s*(?:a\s+)?(\d+)\b",
        r"\b(one|two|three|four|five)[-\s]*(?:warehouses?|facilities|sites?|hubs?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            if val in NUMBER_WORDS:
                return NUMBER_WORDS[val]
            try:
                return int(val)
            except ValueError:
                pass
    return None


def _parse_capacity(text: str) -> Optional[float]:
    """Extracts throughput capacity per warehouse in orders/day."""
    # Look for "4000 capacity", "4k orders", "capacity of 4000", "4,000 orders/day", "handles 3500", "with 4000 orders/day capacity"
    patterns = [
        r"\b(?:capacity|throughput)\s*(?:of|is|:)?\s*([\d,]+(?:\.\d+)?)\s*(k|thousand)?\b",
        r"\b([\d,]+(?:\.\d+)?)\s*(k|thousand)?\s*(?:orders?(?:\s*/\s*day)?|daily orders?|throughput)\b",
        r"\b([\d,]+(?:\.\d+)?)\s*(k|thousand)?\s*capacity\b",
        r"\bhandles?\s*([\d,]+(?:\.\d+)?)\s*(k|thousand)?\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            num_str = m.group(1).replace(",", "")
            try:
                val = float(num_str)
                if m.group(2) and m.group(2).lower() in ["k", "thousand"]:
                    val *= 1000.0
                return val
            except ValueError:
                pass
    return None


def _parse_radius(text: str) -> Tuple[Optional[float], bool, bool]:
    """Extracts max service radius in km.
    Returns: (radius_km, is_unlimited, is_drive_time_warning)
    """
    # Detect drive time confusion (e.g. "20 mins", "30 minutes")
    drive_time_match = re.search(r"\b(\d+)\s*(?:mins?|minutes?|hours?|hrs?)\s*(?:drive|travel|delivery)?\s*(?:time|radius)?\b", text, re.IGNORECASE)
    if drive_time_match and not re.search(r"\b\d+\s*(?:km|kilometers?)\b", text, re.IGNORECASE):
        return None, False, True

    # Detect unlimited radius
    if re.search(r"\b(?:no\s+radius|unlimited\s+radius|no\s+limit|any\s+distance|without\s+radius\s+limit)\b", text, re.IGNORECASE):
        return None, True, False

    # Look for "25 km radius", "within 20km", "max radius 30 km", "radius of 15"
    patterns = [
        r"\b(?:radius|distance)\s*(?:of|is|:)?\s*([\d.]+)\s*(?:km|kilometers?)?\b",
        r"\bwithin\s*([\d.]+)\s*(?:km|kilometers?)\b",
        r"\b([\d.]+)\s*(?:km|kilometers?)\s*(?:radius|distance|max|reach)?\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1)), False, False
            except ValueError:
                pass

    return None, False, False


def _parse_priority_preset(text: str) -> Optional[str]:
    """Extracts strategic priority preset."""
    if re.search(r"\b(?:speed|fast|proximity|fastest|quick)\b", text, re.IGNORECASE):
        return "speed"
    if re.search(r"\b(?:green|carbon|co2|sustainability|eco|emissions?)\b", text, re.IGNORECASE):
        return "sustainability"
    if re.search(r"\b(?:cost|cheapest|economical|budget|lowest cost)\b", text, re.IGNORECASE):
        return "cost"
    return None


def _parse_cvrp_intent(text: str) -> Tuple[bool, Optional[int], Optional[float]]:
    """Extracts tactical CVRP routing intent and fleet constraints."""
    include_cvrp = bool(re.search(r"\b(?:cvrp|vehicle|routing|fleet|van|tours?|multi-stop|truck)\b", text, re.IGNORECASE))
    
    veh_cap = None
    patterns_cap = [
        r"\b(?:van|vehicle)\s*(?:capacity|load)?\s*(?:of|is|:)?\s*(\d+)\b",
        r"\b(\d+)\s*(?:orders?|packages?|items?)\s*(?:per|/)\s*(?:van|vehicle)\b",
    ]
    for pat in patterns_cap:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            veh_cap = int(m.group(1))
            break

    veh_cost = None
    cost_match = re.search(r"\b(?:van|vehicle)\s*(?:fixed\s*)?cost\s*(?:of|is|:)?\s*\$?([\d.]+)\b", text, re.IGNORECASE)
    if cost_match:
        veh_cost = float(cost_match.group(1))

    return include_cvrp, veh_cap, veh_cost


def process_agent_dialog(req: AgentExtractRequest) -> AgentExtractResponse:
    """Processes user message and dialogue history to extract structured optimization parameters."""
    msg = req.message.strip()
    history = req.history or []
    known = req.known_params or {}

    # Initialize extracted parameters from known state
    extracted = ExtractedParams(
        warehouse_count=known.get("warehouse_count") or known.get("p"),
        warehouse_capacity=known.get("warehouse_capacity"),
        max_service_radius_km=known.get("max_service_radius_km"),
        cost_per_km=known.get("cost_per_km", 1.25),
        fixed_cost_per_warehouse=known.get("fixed_cost_per_warehouse", 300.0),
        priority_preset=known.get("priority_preset", "cost"),
        include_cvrp=known.get("include_cvrp", False),
        vehicle_capacity=known.get("vehicle_capacity", 250),
        vehicle_fixed_cost=known.get("vehicle_fixed_cost", 150.0),
    )

    # 1. Parse Warehouse Count p
    parsed_p = _parse_warehouse_count(msg)
    if parsed_p is not None:
        if parsed_p < 1:
            return AgentExtractResponse(
                status="error",
                reply="Warehouse count must be at least 1 facility. Please specify between 1 and 5 warehouses.",
                extracted_params=extracted,
                missing_required=["warehouse_count"],
                ready_to_optimize=False,
            )
        elif parsed_p > 5:
            return AgentExtractResponse(
                status="error",
                reply=f"GRIDPOINT supports up to 5 strategic warehouse facilities for optimal delivery territory clustering. Would you like to set p = 5?",
                extracted_params=extracted,
                missing_required=["warehouse_count"],
                ready_to_optimize=False,
            )
        else:
            extracted.warehouse_count = parsed_p

    # 2. Parse Throughput Capacity
    parsed_cap = _parse_capacity(msg)
    if parsed_cap is not None:
        if parsed_cap <= 0:
            return AgentExtractResponse(
                status="error",
                reply="Warehouse throughput capacity must be greater than 0 orders/day. Typical facility capacity ranges from 1,000 to 10,000 orders/day.",
                extracted_params=extracted,
                missing_required=["warehouse_capacity"],
                ready_to_optimize=False,
            )
        extracted.warehouse_capacity = parsed_cap

    # 3. Parse Service Radius (km) & check drive-time confusion
    parsed_radius, is_unlimited, is_drive_time = _parse_radius(msg)
    if is_drive_time:
        return AgentExtractResponse(
            status="clarify",
            reply="GRIDPOINT evaluates geographic delivery distance (Haversine straight-line in km) rather than road drive time. Would a maximum service radius of 20 km work for your network?",
            extracted_params=extracted,
            missing_required=["max_service_radius_km"] if extracted.max_service_radius_km is None else [],
            ready_to_optimize=False,
        )
    elif is_unlimited:
        extracted.max_service_radius_km = None
    elif parsed_radius is not None:
        if parsed_radius <= 0:
            return AgentExtractResponse(
                status="error",
                reply="Service radius must be a positive distance in kilometers. Please specify a valid radius (e.g. 25 km) or specify 'no limit'.",
                extracted_params=extracted,
                missing_required=["max_service_radius_km"],
                ready_to_optimize=False,
            )
        extracted.max_service_radius_km = parsed_radius

    # 4. Parse Priority Preset
    parsed_preset = _parse_priority_preset(msg)
    if parsed_preset:
        extracted.priority_preset = parsed_preset

    # 5. Parse CVRP Intent
    has_cvrp, veh_cap, veh_cost = _parse_cvrp_intent(msg)
    if has_cvrp:
        extracted.include_cvrp = True
    if veh_cap:
        extracted.vehicle_capacity = veh_cap
    if veh_cost:
        extracted.vehicle_fixed_cost = veh_cost

    # 6. Check Ambiguity in units
    if re.search(r"\b(?:holds?|stores?)\s*\d+\s*(?:units?|pallets?|boxes?|tons?)\b", msg, re.IGNORECASE):
        return AgentExtractResponse(
            status="clarify",
            reply="GRIDPOINT measures facility throughput capacity in daily customer order volume (orders/day). Could you specify the capacity in orders per day?",
            extracted_params=extracted,
            missing_required=["warehouse_capacity"],
            ready_to_optimize=False,
        )

    # 7. Evaluate Required Trio: [warehouse_count, warehouse_capacity, max_service_radius_km]
    missing = []
    if extracted.warehouse_count is None:
        missing.append("warehouse_count")
    if extracted.warehouse_capacity is None:
        missing.append("warehouse_capacity")

    # If parameters are still missing, ask exactly one targeted question
    if missing:
        if "warehouse_count" in missing:
            reply = "How many warehouse facilities (1 to 5) would you like to plan across the delivery network?"
        elif "warehouse_capacity" in missing:
            p_text = f"for each of the {extracted.warehouse_count} warehouses" if extracted.warehouse_count else "per warehouse"
            reply = f"What daily order throughput capacity {p_text} should be configured (e.g. 4,000 orders/day)?"
        else:
            reply = "Do you have a maximum service radius constraint per warehouse (e.g. 25 km), or should it be unlimited?"
            
        return AgentExtractResponse(
            status="clarify",
            reply=reply,
            extracted_params=extracted,
            missing_required=missing,
            ready_to_optimize=False,
        )

    # All required parameters resolved! Build confirmation message
    radius_desc = f"{extracted.max_service_radius_km:,.0f} km service radius" if extracted.max_service_radius_km else "unlimited service radius"
    cvrp_desc = " with Google OR-Tools CVRP tactical routing" if extracted.include_cvrp else ""
    preset_desc = f"{extracted.priority_preset.capitalize()} priority" if extracted.priority_preset else "Cost Focus"

    confirmation_reply = (
        f"I have configured a **{extracted.warehouse_count}-warehouse network** with **{extracted.warehouse_capacity:,.0f} orders/day throughput capacity** "
        f"under a **{radius_desc}** ({preset_desc}{cvrp_desc}).\n"
        f"Default delivery assumptions apply ($1.25/km and $300/site/day lease). "
        f"Review the configuration card below and click **Run Optimization** to solve."
    )

    return AgentExtractResponse(
        status="confirm",
        reply=confirmation_reply,
        extracted_params=extracted,
        missing_required=[],
        ready_to_optimize=True,
    )
