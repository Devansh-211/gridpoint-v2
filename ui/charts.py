"""Plotly interactive charts for cost breakdown, vehicle utilization, and trade-off sensitivity curves.
"""

from typing import List, Dict, Tuple
import plotly.graph_objects as go
from core.models import ComparisonMetrics, SystemSummary


def create_cost_comparison_chart(comparison: ComparisonMetrics) -> go.Figure:
    """Grouped bar chart comparing cost components between Baseline and Optimized."""
    base_cb = comparison.baseline.cost_breakdown
    opt_cb = comparison.optimized.cost_breakdown

    categories = ["Distance Cost", "Driver Time Cost", "Fixed Fleet Cost", "Total Delivery Cost"]
    base_vals = [base_cb.distance_cost, base_cb.time_cost, base_cb.vehicle_cost, base_cb.total_cost]
    opt_vals = [opt_cb.distance_cost, opt_cb.time_cost, opt_cb.vehicle_cost, opt_cb.total_cost]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=comparison.baseline.mode_label,
            x=categories,
            y=base_vals,
            marker_color="#94A3B8",
            text=[f"${v:,.2f}" for v in base_vals],
            textposition="auto",
        )
    )
    fig.add_trace(
        go.Bar(
            name=comparison.optimized.mode_label,
            x=categories,
            y=opt_vals,
            marker_color="#3B82F6",
            text=[f"${v:,.2f}" for v in opt_vals],
            textposition="auto",
        )
    )

    fig.update_layout(
        title="Delivery Cost Breakdown: Baseline vs Optimized",
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0", family="Plus Jakarta Sans"),
        yaxis=dict(title="Cost ($)", gridcolor="rgba(255,255,255,0.1)"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def create_warehouse_demand_chart(summary: SystemSummary) -> go.Figure:
    """Bar chart illustrating assigned demand vs total capacity per opened warehouse."""
    names = [w.name for w in summary.open_warehouses]
    assigned = [w.total_assigned_demand for w in summary.open_warehouses]
    capacities = [w.capacity for w in summary.open_warehouses]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Assigned Demand",
            x=names,
            y=assigned,
            marker_color="#10B981",
            text=[f"{v:,.0f}" for v in assigned],
            textposition="auto",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Site Capacity",
            x=names,
            y=capacities,
            marker_color="rgba(148, 163, 184, 0.4)",
            text=[f"{v:,.0f}" for v in capacities],
            textposition="auto",
        )
    )

    fig.update_layout(
        title="Warehouse Assigned Demand vs Capacity Limit",
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0", family="Plus Jakarta Sans"),
        yaxis=dict(title="Daily Orders", gridcolor="rgba(255,255,255,0.1)"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def create_vehicle_utilization_chart(summary: SystemSummary) -> go.Figure:
    """Bar chart showing utilization of each active vehicle route across warehouses."""
    route_labels = []
    utilizations = []
    loads = []
    caps = []

    for wid, cvrp_res in summary.cvrp_results.items():
        w_short = wid[:8]
        for r in cvrp_res.routes:
            route_labels.append(f"{w_short} - V#{r.vehicle_index}")
            utilizations.append(r.utilization * 100.0)
            loads.append(r.total_load)
            caps.append(r.capacity)

    colors = ["#10B981" if u >= 80 else "#3B82F6" if u >= 50 else "#F59E0B" for u in utilizations]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=route_labels,
            y=utilizations,
            marker_color=colors,
            text=[f"{u:.1f}% ({loads[i]:.0f}/{caps[i]:.0f})" for i, u in enumerate(utilizations)],
            textposition="auto",
        )
    )

    fig.update_layout(
        title="Vehicle Capacity Load Utilization (%)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0", family="Plus Jakarta Sans"),
        yaxis=dict(title="Load Utilization (%)", range=[0, 110], gridcolor="rgba(255,255,255,0.1)"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def create_tradeoff_curve_chart(
    p_values: List[int],
    delivery_costs: List[float],
    fixed_warehouse_costs: List[float],
    total_system_costs: List[float],
) -> go.Figure:
    """Plots the trade-off curve between number of warehouses p and total delivery/network cost."""
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=p_values,
            y=delivery_costs,
            mode="lines+markers",
            name="Tactical Delivery Cost",
            line=dict(color="#3B82F6", width=3),
            marker=dict(size=8),
        )
    )

    if any(fixed_warehouse_costs):
        fig.add_trace(
            go.Scatter(
                x=p_values,
                y=fixed_warehouse_costs,
                mode="lines+markers",
                name="Fixed Warehouse Lease Cost",
                line=dict(color="#F59E0B", width=2, dash="dash"),
                marker=dict(size=6),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=p_values,
                y=total_system_costs,
                mode="lines+markers",
                name="Combined System Cost",
                line=dict(color="#10B981", width=3),
                marker=dict(size=10, symbol="diamond"),
            )
        )

    fig.update_layout(
        title="Warehouse Count (p) vs Network Delivery Cost Trade-off",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0", family="Plus Jakarta Sans"),
        xaxis=dict(title="Number of Warehouses (p)", dtick=1, gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(title="Cost ($)", gridcolor="rgba(255,255,255,0.1)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig
