"""KPI Summary cards, metric comparisons, route manifests, and data tables.
"""

from typing import List, Dict, Optional
import streamlit as st
import pandas as pd
from core.models import ComparisonMetrics, SystemSummary


def render_assumptions_banner(assumptions: Dict[str, any]):
    """Renders clean banner explicitly showing all foundational modeling assumptions."""
    st.markdown(
        f"""
        <div class="assumption-strip">
            <div class="assumption-item">
                <span>Cost / km:</span> <strong>${assumptions.get('cost_per_km', 0.0):.2f}</strong>
            </div>
            <div class="assumption-item">
                <span>Driver Cost / hr:</span> <strong>${assumptions.get('cost_per_hour', 0.0):.2f}</strong>
            </div>
            <div class="assumption-item">
                <span>Fixed Vehicle Cost:</span> <strong>${assumptions.get('fixed_vehicle_cost', 0.0):.2f}</strong>
            </div>
            <div class="assumption-item">
                <span>Vehicle Capacity:</span> <strong>{assumptions.get('vehicle_capacity', 0):,d} orders</strong>
            </div>
            <div class="assumption-item">
                <span>Max Service Radius T_max:</span> <strong>{assumptions.get('service_radius_min', 0.0):.0f} min</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_metrics_grid(comp: ComparisonMetrics):
    """Renders 4x2 responsive grid of KPI cards with baseline vs optimized comparison."""
    # Row 1: Cost, Distance, Time, Vehicles
    c1, c2, c3, c4 = st.columns(4)

    # 1. Total Delivery Cost
    cost_delta = comp.cost_delta
    cost_pct = comp.cost_pct_change
    cost_class = "kpi-delta-good" if cost_delta <= 0 else "kpi-delta-bad"
    cost_arrow = "&darr;" if cost_delta <= 0 else "&uarr;"

    with c1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Simulated Delivery Cost</div>
                <div class="kpi-val-container">
                    <span class="kpi-val">${comp.optimized.cost_breakdown.total_cost:,.2f}</span>
                    <span class="{cost_class}">{cost_arrow} {abs(cost_pct):.1f}%</span>
                </div>
                <div class="kpi-baseline">Baseline: ${comp.baseline.cost_breakdown.total_cost:,.2f} (diff: ${cost_delta:+,.2f})</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2. Total Distance
    dist_delta = comp.distance_delta_km
    dist_pct = comp.distance_pct_change
    dist_class = "kpi-delta-good" if dist_delta <= 0 else "kpi-delta-bad"
    dist_arrow = "&darr;" if dist_delta <= 0 else "&uarr;"

    with c2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Total Delivery Distance</div>
                <div class="kpi-val-container">
                    <span class="kpi-val">{comp.optimized.total_distance_km:,.1f} <span style='font-size: 1rem; color: #94A3B8;'>km</span></span>
                    <span class="{dist_class}">{dist_arrow} {abs(dist_pct):.1f}%</span>
                </div>
                <div class="kpi-baseline">Baseline: {comp.baseline.total_distance_km:,.1f} km (diff: {dist_delta:+,.1f} km)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3. Total Delivery Time
    dur_delta = comp.duration_delta_hours
    dur_pct = comp.duration_pct_change
    dur_class = "kpi-delta-good" if dur_delta <= 0 else "kpi-delta-bad"
    dur_arrow = "&darr;" if dur_delta <= 0 else "&uarr;"

    with c3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Total Route Duration</div>
                <div class="kpi-val-container">
                    <span class="kpi-val">{comp.optimized.total_duration_hours:,.1f} <span style='font-size: 1rem; color: #94A3B8;'>hrs</span></span>
                    <span class="{dur_class}">{dur_arrow} {abs(dur_pct):.1f}%</span>
                </div>
                <div class="kpi-baseline">Baseline: {comp.baseline.total_duration_hours:,.1f} hrs (diff: {dur_delta:+,.1f} hrs)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 4. Vehicles Deployed
    veh_delta = comp.vehicles_delta
    veh_pct = comp.vehicles_pct_change
    veh_class = "kpi-delta-good" if veh_delta <= 0 else "kpi-delta-bad" if veh_delta > 0 else "kpi-delta-neutral"
    veh_arrow = "&darr;" if veh_delta < 0 else "&uarr;" if veh_delta > 0 else "="

    with c4:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Vehicles Deployed</div>
                <div class="kpi-val-container">
                    <span class="kpi-val">{comp.optimized.vehicles_used} <span style='font-size: 1rem; color: #94A3B8;'>vans</span></span>
                    <span class="{veh_class}">{veh_arrow} {abs(veh_pct):.0f}%</span>
                </div>
                <div class="kpi-baseline">Baseline: {comp.baseline.vehicles_used} vans (diff: {veh_delta:+d})</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # Row 2: Warehouses, Utilization, Strategic Travel Time, CFLP Solve Time
    c5, c6, c7, c8 = st.columns(4)

    with c5:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Warehouses Open</div>
                <div class="kpi-val-container">
                    <span class="kpi-val">{comp.optimized.warehouses_open_count} <span style='font-size: 1rem; color: #94A3B8;'>sites</span></span>
                    <span class="kpi-delta-neutral">Ref: {comp.baseline.warehouses_open_count}</span>
                </div>
                <div class="kpi-baseline">Status: {comp.optimized.cflp_result.status}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c6:
        u_opt = comp.optimized.avg_load_utilization * 100.0
        u_base = comp.baseline.avg_load_utilization * 100.0
        u_delta = u_opt - u_base
        u_class = "kpi-delta-good" if u_delta >= 0 else "kpi-delta-neutral"
        with c6:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">Avg Fleet Load Utilization</div>
                    <div class="kpi-val-container">
                        <span class="kpi-val">{u_opt:.1f}%</span>
                        <span class="{u_class}">{u_delta:+0.1f}%</span>
                    </div>
                    <div class="kpi-baseline">Baseline: {u_base:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with c7:
        w_delta = comp.weighted_time_delta
        w_pct = comp.weighted_time_pct_change
        w_class = "kpi-delta-good" if w_delta <= 0 else "kpi-delta-bad"
        w_arrow = "&darr;" if w_delta <= 0 else "&uarr;"
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Weighted Strategic Travel Time</div>
                <div class="kpi-val-container">
                    <span class="kpi-val" style="font-size: 1.4rem;">{comp.optimized.weighted_strategic_travel_time:,.0f} <span style='font-size: 0.8rem; color: #94A3B8;'>ord&middot;min</span></span>
                    <span class="{w_class}">{w_arrow} {abs(w_pct):.1f}%</span>
                </div>
                <div class="kpi-baseline">Baseline: {comp.baseline.weighted_strategic_travel_time:,.0f} ord&middot;min</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c8:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">Solver Runtime</div>
                <div class="kpi-val-container">
                    <span class="kpi-val" style="font-size: 1.4rem;">{comp.optimized.cflp_result.solve_time_seconds:.2f} <span style='font-size: 0.8rem; color: #94A3B8;'>sec</span></span>
                    <span class="badge-pill badge-live" style="font-size: 0.65rem;">CBC MILP</span>
                </div>
                <div class="kpi-baseline">{comp.optimized.cflp_result.solver_message}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_warehouse_summary_table(summary: SystemSummary):
    """Renders a structured dataframe of opened warehouses with assigned demand and utilization."""
    rows = []
    for w in summary.open_warehouses:
        util_pct = (w.total_assigned_demand / w.capacity * 100.0) if w.capacity > 0 else 0.0
        cvrp_w = summary.cvrp_results.get(w.id)
        vehicles = cvrp_w.vehicles_used if cvrp_w else 0
        km = cvrp_w.total_distance_km if cvrp_w else 0.0
        hrs = cvrp_w.total_duration_hours if cvrp_w else 0.0

        rows.append(
            {
                "Warehouse ID": w.id,
                "Warehouse Name": w.name,
                "Assigned Neighborhoods": len(w.assigned_neighborhood_ids),
                "Assigned Demand (orders)": f"{w.total_assigned_demand:,.0f}",
                "Capacity (orders)": f"{w.capacity:,.0f}",
                "Site Capacity Utilization": f"{util_pct:.1f}%",
                "Vehicles Used": vehicles,
                "Route Distance (km)": f"{km:.1f}",
                "Route Duration (hrs)": f"{hrs:.2f}",
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_route_manifest_table(summary: SystemSummary):
    """Renders detailed route-by-route manifest across all warehouses."""
    rows = []
    w_map = {w.id: w for w in summary.open_warehouses}

    for wid, cvrp_res in summary.cvrp_results.items():
        wname = w_map[wid].name if wid in w_map else wid
        for r in cvrp_res.routes:
            rows.append(
                {
                    "Warehouse": f"{wname} ({wid})",
                    "Vehicle #": r.vehicle_index,
                    "Total Stops": len(r.stop_ids),
                    "Stop Sequence": " -> ".join(r.stop_names),
                    "Vehicle Load (orders)": f"{r.total_load:,.0f} / {r.capacity:,.0f}",
                    "Utilization": f"{r.utilization * 100.0:.1f}%",
                    "Route Distance (km)": f"{r.distance_km:.1f}",
                    "Route Time (hrs)": f"{r.duration_hours:.2f}",
                }
            )

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No active vehicle routes generated.")
