"""Enterprise glassmorphic styling and CSS tokens for GRIDPOINT.
"""

CUSTOM_CSS = """
<style>
/* Import modern typography */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

code, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Header styling */
.gridpoint-header {
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #0F172A 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
}

.gridpoint-title {
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, #FFFFFF 30%, #94A3B8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 12px;
}

.gridpoint-subtitle {
    color: #94A3B8;
    font-size: 0.95rem;
    font-weight: 400;
    margin-top: 6px;
    margin-bottom: 0;
}

.badge-pill {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
}

.badge-live {
    background: rgba(16, 185, 129, 0.15);
    color: #10B981;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-demo {
    background: rgba(59, 130, 246, 0.15);
    color: #60A5FA;
    border: 1px solid rgba(59, 130, 246, 0.3);
}

.badge-warning {
    background: rgba(245, 158, 11, 0.15);
    color: #F59E0B;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

/* Metric Cards */
.kpi-card {
    background: #1E293B;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    transition: transform 0.15s ease, border-color 0.15s ease;
}

.kpi-card:hover {
    border-color: rgba(96, 165, 250, 0.4);
    transform: translateY(-2px);
}

.kpi-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #94A3B8;
    margin-bottom: 6px;
}

.kpi-val-container {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
}

.kpi-val {
    font-size: 1.7rem;
    font-weight: 800;
    color: #F8FAFC;
    letter-spacing: -0.02em;
}

.kpi-delta-good {
    color: #10B981;
    font-size: 0.85rem;
    font-weight: 700;
}

.kpi-delta-neutral {
    color: #94A3B8;
    font-size: 0.85rem;
    font-weight: 600;
}

.kpi-delta-bad {
    color: #F87171;
    font-size: 0.85rem;
    font-weight: 700;
}

.kpi-baseline {
    font-size: 0.75rem;
    color: #64748B;
    margin-top: 4px;
}

/* Assumption banner */
.assumption-strip {
    background: rgba(15, 23, 42, 0.7);
    border: 1px dashed rgba(148, 163, 184, 0.25);
    border-radius: 8px;
    padding: 10px 16px;
    margin-bottom: 20px;
    font-size: 0.8rem;
    color: #94A3B8;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;
}

.assumption-item {
    display: flex;
    align-items: center;
    gap: 6px;
}

.assumption-item strong {
    color: #CBD5E1;
}

/* Callout alert */
.alert-box {
    padding: 14px 18px;
    border-radius: 10px;
    margin-bottom: 16px;
    font-size: 0.88rem;
    line-height: 1.4;
}

.alert-error {
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: #FCA5A5;
}

.alert-info {
    background: rgba(59, 130, 246, 0.12);
    border: 1px solid rgba(59, 130, 246, 0.35);
    color: #93C5FD;
}

/* Sidebar button */
div.stButton > button:first-child {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
    color: #FFFFFF;
    font-weight: 700;
    border: none;
    border-radius: 8px;
    padding: 12px 24px;
    font-size: 0.95rem;
    letter-spacing: 0.01em;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    transition: all 0.2s ease;
    width: 100%;
}

div.stButton > button:first-child:hover {
    background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);
    box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
    transform: translateY(-1px);
}
</style>
"""


def get_header_html(mode: str) -> str:
    badge_class = "badge-live" if "LIVE" in mode else "badge-demo"
    return f"""
    <div class="gridpoint-header">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
                <h1 class="gridpoint-title">
                    <span>⚡ GRIDPOINT</span>
                </h1>
                <p class="gridpoint-subtitle">
                    Dual-Tier Strategic (CFLP) & Tactical (CVRP) Warehouse Location Optimization Platform
                </p>
            </div>
            <div>
                <span class="badge-pill {badge_class}">Routing: {mode}</span>
            </div>
        </div>
    </div>
    """
