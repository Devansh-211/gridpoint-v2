"""Interactive Folium spatial visualization for GRIDPOINT network, assignments, and routes.
"""

from typing import List, Dict, Optional, Tuple
import folium
from folium import plugins
from core.models import Neighborhood, WarehouseCandidate, VehicleRoute, SystemSummary

CLUSTER_PALETTE = [
    "#3B82F6",  # Blue
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#F97316",  # Orange
    "#14B8A6",  # Teal
]


def render_network_map(
    neighborhoods: List[Neighborhood],
    candidates: List[WarehouseCandidate],
    summary: Optional[SystemSummary] = None,
    show_candidates: bool = True,
    show_assignments: bool = True,
    selected_warehouse_routes: Optional[List[VehicleRoute]] = None,
) -> folium.Map:
    """Builds an interactive Folium map illustrating candidate sites, open warehouses,

    assigned neighborhoods, direct assignment lines, and optional CVRP vehicle routes.
    """
    # Calculate center coordinate
    if neighborhoods:
        center_lat = sum(n.latitude for n in neighborhoods) / len(neighborhoods)
        center_lon = sum(n.longitude for n in neighborhoods) / len(neighborhoods)
    else:
        center_lat, center_lon = 12.9716, 77.5946  # Bengaluru default

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Build color mapping per opened warehouse
    warehouse_colors: Dict[str, str] = {}
    if summary and summary.open_warehouses:
        for idx, w in enumerate(summary.open_warehouses):
            warehouse_colors[w.id] = CLUSTER_PALETTE[idx % len(CLUSTER_PALETTE)]

    # Feature groups for toggleable map layers
    fg_candidates = folium.FeatureGroup(name="Candidate Warehouse Sites", show=show_candidates)
    fg_open = folium.FeatureGroup(name="Opened Warehouses", show=True)
    fg_assignments = folium.FeatureGroup(name="Assignment Lines (Direct, Not Routes)", show=show_assignments)
    fg_neighborhoods = folium.FeatureGroup(name="Neighborhood Demand Nodes", show=True)
    fg_routes = folium.FeatureGroup(name="Optimized Vehicle Routes", show=True)

    cand_map = {c.id: c for c in candidates}
    open_ids = set(summary.open_warehouses_ids if hasattr(summary, "open_warehouses_ids") else [w.id for w in summary.open_warehouses]) if summary else set()

    # 1. Unselected Candidate Sites
    if show_candidates:
        for c in candidates:
            if c.id not in open_ids:
                folium.CircleMarker(
                    location=[c.latitude, c.longitude],
                    radius=4,
                    color="#64748B",
                    fill=True,
                    fill_color="#94A3B8",
                    fill_opacity=0.5,
                    weight=1,
                    tooltip=f"Candidate Site: {c.name} ({c.id})<br>Capacity: {c.capacity:,.0f} orders",
                ).add_to(fg_candidates)

    # 2. Neighborhoods
    max_demand = max([n.daily_orders for n in neighborhoods], default=500.0)
    for n in neighborhoods:
        assigned_wid = summary.assignments.get(n.id) if summary else None
        node_color = warehouse_colors.get(assigned_wid, "#64748B")
        assigned_wname = cand_map[assigned_wid].name if assigned_wid and assigned_wid in cand_map else "Unassigned"

        # Scale radius: min 4px, max 14px
        r = 4 + (n.daily_orders / max_demand) * 10

        popup_html = f"""
        <div style='font-family: sans-serif; font-size: 12px; min-width: 150px;'>
            <strong style='font-size: 13px; color: #0F172A;'>{n.name}</strong><br>
            <b>ID:</b> {n.id}<br>
            <b>Daily Demand:</b> {n.daily_orders:,.0f} orders<br>
            <b>Assigned Warehouse:</b> {assigned_wname}
        </div>
        """

        folium.CircleMarker(
            location=[n.latitude, n.longitude],
            radius=r,
            color=node_color,
            fill=True,
            fill_color=node_color,
            fill_opacity=0.75,
            weight=1.5,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{n.name} — {n.daily_orders:,.0f} orders/day",
        ).add_to(fg_neighborhoods)

    # 3. Direct Assignment Lines
    if summary and show_assignments:
        n_map = {n.id: n for n in neighborhoods}
        for nid, wid in summary.assignments.items():
            if wid in cand_map and nid in n_map:
                w = cand_map[wid]
                n = n_map[nid]
                line_color = warehouse_colors.get(wid, "#3B82F6")

                folium.PolyLine(
                    locations=[[w.latitude, w.longitude], [n.latitude, n.longitude]],
                    color=line_color,
                    weight=1.5,
                    dash_array="4, 6",
                    opacity=0.6,
                    tooltip=f"Direct Assignment: {n.name} &rarr; {w.name} (Direct assignment, not actual route path)",
                ).add_to(fg_assignments)

    # 4. Opened Warehouses
    if summary:
        for w in summary.open_warehouses:
            w_color = warehouse_colors.get(w.id, "#2563EB")
            num_assigned = len(w.assigned_neighborhood_ids)
            util_pct = (w.total_assigned_demand / w.capacity * 100.0) if w.capacity > 0 else 0.0

            w_popup = f"""
            <div style='font-family: sans-serif; font-size: 12px; min-width: 180px;'>
                <span style='background: {w_color}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold;'>WAREHOUSE</span>
                <h4 style='margin: 6px 0 4px 0; color: #0F172A;'>{w.name}</h4>
                <b>Site ID:</b> {w.id}<br>
                <b>Assigned Demand:</b> {w.total_assigned_demand:,.0f} / {w.capacity:,.0f} orders<br>
                <b>Site Utilization:</b> {util_pct:.1f}%<br>
                <b>Assigned Neighborhoods:</b> {num_assigned}
            </div>
            """

            # Folium custom warehouse icon
            folium.Marker(
                location=[w.latitude, w.longitude],
                icon=folium.Icon(color="darkblue", icon="industry", prefix="fa"),
                popup=folium.Popup(w_popup, max_width=300),
                tooltip=f"Warehouse: {w.name} ({w.total_assigned_demand:,.0f} orders assigned)",
            ).add_to(fg_open)

    # 5. Vehicle Routes (Road geometry or waypoint sequence)
    if selected_warehouse_routes:
        route_colors = ["#EF4444", "#8B5CF6", "#10B981", "#F59E0B", "#06B6D4", "#EC4899"]
        for r_idx, r in enumerate(selected_warehouse_routes):
            r_col = route_colors[r_idx % len(route_colors)]
            stops_str = " &rarr; ".join(r.stop_names[:5]) + ("..." if len(r.stop_names) > 5 else "")

            folium.PolyLine(
                locations=r.route_coords,
                color=r_col,
                weight=3.5,
                opacity=0.85,
                tooltip=f"Vehicle #{r.vehicle_index}: {r.total_load:,.0f} orders, {r.distance_km:.1f} km, {r.duration_hours:.2f} hrs<br>Stops: {stops_str}",
            ).add_to(fg_routes)

    # Add layers to map
    fg_candidates.add_to(m)
    fg_assignments.add_to(m)
    fg_neighborhoods.add_to(m)
    fg_open.add_to(m)
    if selected_warehouse_routes:
        fg_routes.add_to(m)

    folium.LayerControl(position="topright").add_to(m)
    return m
