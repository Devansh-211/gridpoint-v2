# GRIDPOINT — Intelligent Warehouse Location & Delivery Network Optimizer
### Hack-A-Matics 2026 Prototype — Operations-Research Logistics Decision Support Tool

**GRIDPOINT** is a B2B logistics decision-support tool designed for operations and supply chain managers at quick-commerce and e-commerce enterprises. Rather than relying on intuition or manual guesswork, GRIDPOINT applies mathematical optimization to determine **where warehouses should go, how many to open, which delivery zones each facility should serve, and quantifies the exact cost and distance improvements over a reference baseline**.

---

## 1. Executive Value Proposition

- **Make smarter delivery decisions:** Strategic Capacitated Facility Location Problem (CFLP) solved to mathematical optimality via Mixed-Integer Linear Programming (**PuLP + CBC**) with automated greedy + 2-opt local search fallback.
- **Save more:** Quantifies daily and monthly cost reductions over a rigorous **Single-Warehouse Reference Baseline** (1-median center).
- **Plan for disruption:** Interactive Scenario Lab simulating demand surges (+20% weekend, +50% festival peaks) and facility outage re-routing.
- **Explainable intelligence:** "Why this location?" mathematical intelligence breaking down key demand drivers and the exact score gap of rejected candidate facilities.
- **Tactical fleet execution:** Dedicated Capacitated Vehicle Routing Problem (CVRP) solving multi-stop vehicle tours via **Google OR-Tools Guided Local Search**.
- **Modern B2B Design System:** 10-screen persistent Left-Rail navigation architecture built with custom design tokens, responsive typography, and strict product honesty rules.

---

## 2. Mathematical Formulation & Architecture

### Strategic Optimization: Capacitated Facility Location Problem (CFLP)

Let:
- $I = \{1, \dots, n\}$ be the set of delivery zones (neighborhoods) with daily order demand $d_i \ge 0$.
- $J = \{1, \dots, m\}$ be the set of candidate warehouse facility locations with throughput capacity $C_j > 0$.
- $D_{i,j}$ be the geographic delivery distance (Haversine straight-line distance, $R \approx 6371\text{ km}$) between delivery zone $i$ and candidate warehouse $j$.
- $p \in [1, 5]$ be the exact number of warehouse facilities to open.
- $R_{\max}$ be the maximum permissible service radius in kilometers.

#### Decision Variables:
$$y_j \in \{0, 1\} \quad \forall j \in J \quad (1 \text{ if warehouse } j \text{ is opened, } 0 \text{ otherwise})$$
$$x_{i,j} \in \{0, 1\} \quad \forall i \in I, j \in J \quad (1 \text{ if delivery zone } i \text{ is assigned to warehouse } j, 0 \text{ otherwise})$$

#### Objective Function:
Minimize **Total Demand-Weighted Geographic Delivery Distance**:
$$\min \sum_{i \in I} \sum_{j \in J} d_i \cdot D_{i,j} \cdot x_{i,j}$$

#### Constraints:
1. **Single Assignment:** Each delivery zone is assigned to exactly one distribution warehouse:
   $$\sum_{j \in J} x_{i,j} = 1 \quad \forall i \in I$$
2. **Facility Linkage:** Zones can only be assigned to opened warehouse facilities:
   $$x_{i,j} \le y_j \quad \forall i \in I, j \in J$$
3. **Capacity Limit:** Total demand allocated to warehouse $j$ cannot exceed its throughput capacity:
   $$\sum_{i \in I} d_i \cdot x_{i,j} \le C_j \cdot y_j \quad \forall j \in J$$
4. **Exact Warehouse Count:** Exactly $p$ distribution centers are opened:
   $$\sum_{j \in J} y_j = p$$
5. **Maximum Service Radius:**
   $$x_{i,j} = 0 \quad \forall (i, j) \text{ where } D_{i,j} > R_{\max}$$

---

### Tactical Routing: Capacitated Vehicle Routing Problem (CVRP)

For opened warehouses with assigned delivery zone clusters, GRIDPOINT executes a secondary tactical vehicle tour optimization using Google OR-Tools Guided Local Search with virtual demand splitting to construct legal vehicle tours:
- Vehicle capacity $Q$ (e.g. 250 orders/van).
- Fixed vehicle dispatch penalty $F_{\text{veh}}$ (e.g. $150/van) to discourage fleet proliferation and maximize payload consolidation.

---

## 3. Tech Stack

- **Backend:** Python 3.11+ / 3.14, FastAPI, Uvicorn (`uvicorn app:app --reload`).
- **Optimization:** PuLP + CBC (Coin-or branch and cut), Google OR-Tools (CVRP Guided Local Search).
- **Data & Math:** Pandas, NumPy, Haversine Geospatial Matrix Engine.
- **Frontend:** Semantic HTML5, CSS3 Tokens Design System (`tokens.css`, `style.css`), Vanilla JavaScript (`app.js` Single State Architecture).
- **Geospatial & Charts:** Leaflet.js (interactive maps & cluster rendering), Chart.js (trade-off curves & analytics).

---

## 4. Information Architecture & Navigation

The platform is structured into a persistent **Left-Rail application shell** across 10 distinct, fully-grounded screens:

| Category | Screen | ID | Key Capabilities |
|---|---|---|---|
| **Setup** | **Landing & Entry** | `viewLanding` | Overview of system capabilities, quickstart buttons to load demo data or upload CSV. |
| **Setup** | **Dashboard Overview** | `viewDashboard` | High-level operations workspace summary with session metrics and 4-step workflow cards. |
| **Setup** | **Demand Data Ingestion** | `viewData` | CSV drag-and-drop, validation feedback banner, raw JSON editor, and interactive Demand Map. |
| **Setup** | **Network Configuration** | `viewConfig` | Facility count $p$, capacity, radius $R_{\max}$, priority presets (Cost, Speed, Green), and live plain-language summary line. |
| **Results** | **Optimization Results** | `viewResults` | Centerpiece Leaflet map with layer toggles, 6 executive KPI cards with `[Estimate]` badges & delta chips, baseline comparison benchmark table, facility manifest, "Why here?" decision intelligence, and demand-weighting explainer. |
| **Results** | **Scenario Lab (What-If)** | `viewScenarios` | Demand shock simulation (Normal 1.0x, Weekend +20%, Festival +50%) with before/after comparisons and topology shift detection. |
| **Results** | **Disruption & Resilience** | `viewDisruption` | Single-point-of-failure facility outage simulator with emergency zone reassignment and cost impact analysis. |
| **Results** | **Tactical Fleet Routing** | `viewFleet` | Dedicated Google OR-Tools CVRP routing screen: turn-by-turn vehicle stop sequences, payload utilization bars, and fleet distance manifests. |
| **Reference** | **Analytics & Trade-off** | `viewAnalytics` | Facility count vs. delivery cost trade-off curve ($p=1..5$) with Chart.js, diminishing returns curve, and visible on-screen CO₂ emissions formula footnote ($0.21 \text{ kg CO}_2/\text{km}$). |
| **Reference** | **Methodology & About** | `viewMethodology` | CFLP Integer Program formulation, CVRP formulation, the 8 Product Honesty Rules, tech stack summary, and Hackathon AI Usage Disclosure. |

---

## 5. Project Directory Structure

```
gridpoint/
├── api/
│   ├── routes.py            # FastAPI REST endpoints & optimization handlers
│   └── schemas.py           # Pydantic request/response schemas
├── core/
│   ├── models.py            # Domain data classes (Neighborhood, WarehouseCandidate, CFLPResult)
│   ├── validation.py        # Presolve feasibility checks & CSV schema validation
│   └── metrics.py           # Financial cost formulas & safe percentage deltas
├── data/
│   ├── demo_neighborhoods.csv   # Curated 36 Bengaluru delivery zones (synthetic dataset)
│   └── sample_neighborhoods.csv # Demonstration dataset
├── optimization/
│   ├── cflp.py              # PuLP/CBC MILP formulation with Greedy + 2-Opt Heuristic fallback
│   ├── assignment.py        # Neighborhood cluster assignment & utilization aggregator
│   └── cvrp.py              # Google OR-Tools CVRP solver for multi-stop vehicle tours
├── routing/
│   ├── distance.py          # Haversine distance engine & empirical road proxy
│   ├── matrix.py            # Pairwise distance matrix computation
│   └── osrm.py              # Routing abstraction layer
├── simulation/
│   ├── baseline.py          # 1-median Single-Warehouse Reference Baseline calculation
│   └── scenario.py          # Demand shock (+20%, +50%) & warehouse outage simulator
├── static/
│   ├── tokens.css           # Design tokens (colors, typography, 8px spacing, elevation)
│   ├── style.css            # Component library (buttons, cards, KPIs, tables, skeletons, error banners)
│   ├── index.html           # 10-screen Left-Rail application shell
│   └── app.js               # Reactive client router, Leaflet geospatial engine & Chart.js
├── tests/
│   ├── test_api.py          # REST endpoint integration tests (12 test suites)
│   ├── test_cflp.py         # CFLP solver unit tests
│   ├── test_cvrp.py         # CVRP routing unit tests
│   ├── test_metrics.py      # Financial & delta metrics tests
│   └── test_validation.py   # Presolve validation tests
├── app.py                   # Application entrypoint & CBC solver startup verification
├── config.py                # Configuration constants & defaults
├── requirements.txt         # Python dependencies
└── README.md                # System documentation & Hackathon AI Usage Disclosure
```

---

## 6. Quickstart & Installation

### Prerequisites
- Python 3.11+
- Virtual environment tool (`venv`)

### 1. Set Up Environment
```bash
# Clone the repository
git clone https://github.com/Devansh-211/gridpoint.git
cd gridpoint

# Create and activate virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure AI Features (Optional / Recommended)
The core mathematical optimization engines (PuLP/CBC CFLP solver, Google OR-Tools CVRP router, geospatial matrix, baseline comparisons, and CSV upload) have **zero external API dependencies** and run 100% locally.

To enable the **Conversational Logistics Assistant** (natural language parameter extraction), **AI Synthetic Data Generator**, and **Grounded Per-Page Explainer**, configure your Anthropic API key in `.env`:
```bash
# Copy template
cp .env.example .env

# Edit .env and insert your real Anthropic API key
# ANTHROPIC_API_KEY=sk-ant-api03-...
# ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```
*Note: If no `ANTHROPIC_API_KEY` is configured, the core optimizer, maps, and CSV uploads continue to operate with zero degradation; only the AI drawer will display an honest "AI features unavailable — no API key configured" notice.*

### 3. Run Automated Test Suite
```bash
python -m pytest -v
```

### 4. Launch Application
```bash
uvicorn app:app --reload --port 8000
```
Open your browser to: **`http://127.0.0.1:8000/`** (Interactive API Swagger Docs: `http://127.0.0.1:8000/docs`).

---

## 7. End-to-End Demo Script (Under 2 Minutes)

1. **One-Click Demo Ingestion:** Click **"Load Bengaluru Demo"** in the top navigation bar or landing screen. 36 delivery zones instantly load with proportional circle markers.
2. **Configure Facilities:** In **Network Configuration**, set warehouse count $p = 3$, site capacity $= 4,000$ orders/day, and select **"Cost Focus"** priority preset. Observe the live summary update: *"Planning a 3-warehouse network serving 36 delivery zones with 12,000 orders/day capacity."*
3. **Run Optimization:** Click **"Run Network Optimization"**. Within 1–2 seconds, the MILP solver returns the proven optimal 3-facility network.
4. **Inspect Centerpiece Map:** In **Optimization Results**, view selected warehouses (custom building pins), cluster assignment spider lines, and translucent service radius rings.
5. **Review Demand-Weighting Explainer:** Inspect the live dynamic panel showing why high-demand zones (e.g. Koramangala, 420 orders) exert greater mathematical pull than low-demand zones (e.g. Kengeri, 150 orders).
6. **Inspect "Why this location?":** Select a warehouse in the intelligence tab to review its assigned volume, capacity utilization %, top 3 demand drivers, and the **score gap of the runner-up rejected candidate**.
7. **Evaluate Trade-off Curve:** Switch to **Analytics & Trade-off** to review the diminishing returns curve ($p = 1 \dots 5$) balancing delivery distance reduction against fixed facility leases.
8. **Run Disruption Test:** Switch to **Disruption & Resilience** or **Scenario Lab** and click **"Festival Surge (+50%)"** or simulate a warehouse outage to test network resilience and automatic load reassignment.
9. **Tactical CVRP Routes:** Switch to **Tactical Fleet (CVRP)** to review turn-by-turn vehicle tours and vehicle payload utilization.

---

## 8. Transparency, Terminology & Honesty Rules

- **Distance Metric:** All straight-line distances are explicitly labeled **"Geographic delivery distance"** ($R \approx 6371\text{ km}$, Haversine formula) — never implied to be exact road distance.
- **Baseline Benchmark:** Comparisons are explicitly labeled **"Single-Warehouse Reference Baseline vs Optimized Network"** (computed dynamically from the 1-median facility center).
- **Cost & Emissions Estimates:** All financial figures and carbon metrics carry visible **`[Estimate]`** tags and show their calculation assumptions nearby.
- **Fast Delivery Proxy:** Fast delivery coverage is explicitly labeled **"Distance-based service proxy"** (% of demand within 5 km) — never guaranteeing delivery time SLAs.
- **No Fake AI:** The "Why here?" explainability panel is generated strictly from real solver metrics, objective gradients, and candidate score gaps.

---

## 9. Mandatory Hackathon AI Usage Disclosure

*In compliance with Hackathon Rule §17 on AI Transparency and Integrity:*

### Team's Independent Engineering & Creative Contribution:
- **Problem Formulation & Strategy:** Formulation of the Capacitated Facility Location Problem (CFLP) and coupling with tactical CVRP vehicle routing for quick-commerce operations.
- **Mathematical Modeling:** Formulation of decision variables ($y_j, x_{i,j}$), objective functions, capacity constraints, service radius limits, and demand-weighting terms ($\sum d_i D_{i,j} x_{i,j}$).
- **Optimization Architecture:** Designing the PuLP/CBC solver interface, presolve feasibility validation rules, and the greedy + 2-opt local search heuristic fallback.
- **Explainability & Metrics Design:** Defining the "Why here?" candidate score gap algorithm, demand-driver breakdown, and Single-Warehouse Reference Baseline comparison methodology.
- **Scenario Engineering:** Designing the demand shock multipliers (+20%, +50%) and facility outage resilience tests.
- **Integration & Validation:** Authoring 26 automated integration test suites and verifying end-to-end execution.

### AI Coding Assistant Utilization:
- **Code Generation & Boilerplate Acceleration:** Drafting FastAPI endpoint scaffolding, Pydantic data schemas, and Leaflet layer management bindings.
- **Frontend Refinement:** Assisting in the translation of design system tokens (light theme with soft blue accents, CSS variables, responsive typography) and Chart.js options.
- **Test Generation Support:** Accelerating test fixture construction for edge cases (duplicate IDs, out-of-bounds coordinates, presolve infeasibility).

---

## 10. Credits & Open Source Acknowledgements

GRIDPOINT is built upon open data, open-source mathematical solvers, and community-driven geospatial tools. We gratefully acknowledge the following projects and resources:

### Open Data & Geographic Sources
- **[OpenStreetMap (OSM)](https://www.openstreetmap.org/)**: Geographic coordinate reference data and locality centroids for Bengaluru metropolitan wards and urban hubs (licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/)).
- **[CARTO Base Maps (Positron & Dark Matter)](https://carto.com/basemaps/)**: Open-access map tile services used for rendering the interactive Leaflet centerpiece map and cluster assignment spider lines (Map tiles © CARTO, Data © OpenStreetMap contributors).
- **[Bruhat Bengaluru Mahanagara Palike (BBMP) Open Data & Census of India](https://bbmp.gov.in/)**: Urban ward boundaries, commercial density patterns, and population distributions that informed the realistic demand volumes and clustering parameters in `demo_neighborhoods.csv`.
- **[Project-OSRM (Open Source Routing Machine)](http://project-osrm.org/)**: Road network routing abstractions and distance matrix protocols informing the geospatial matrix routing layer.

### Open-Source Solvers & Computational Libraries
- **[COIN-OR CBC (Coin-or branch and cut)](https://github.com/coin-or/Cbc)**: High-performance open-source Mixed Integer Linear Programming (MILP) solver used to compute optimal facility locations for the Capacitated Facility Location Problem (CFLP).
- **[PuLP](https://github.com/coin-or/pulp)**: Python linear programming modeler (BSD License) used to formulate the CFLP objective and constraints.
- **[Google OR-Tools](https://developers.google.com/optimization)**: Combinatorial optimization library (Apache 2.0 License) used for multi-stop vehicle tour optimization in the Capacitated Vehicle Routing Problem (CVRP).
- **[Pandas](https://pandas.pydata.org/) & [NumPy](https://numpy.org/)**: Open-source data manipulation, validation, and vectorized geospatial distance matrix computing (BSD License).

### Frontend Geospatial & UI Libraries
- **[Leaflet.js](https://leafletjs.com/)**: Leading open-source JavaScript library for mobile-friendly interactive maps (BSD 2-Clause License).
- **[Chart.js](https://www.chartjs.org/)**: Simple yet flexible JavaScript charting library for designers and developers (MIT License).
- **[Lucide Icons](https://lucide.dev/)**: Clean, consistent icon set for user interface actions and status indicators (ISC License).
- **[Google Fonts (Inter & JetBrains Mono)](https://fonts.google.com/)**: High-legibility typography designed for user interfaces and data-dense operational displays (SIL Open Font License).

### Backend & Testing Frameworks
- **[FastAPI](https://fastapi.tiangolo.com/) & [Starlette](https://www.starlette.io/)**: Modern, fast web framework for building APIs with Python (MIT License).
- **[Uvicorn](https://www.uvicorn.org/)**: Lightning-fast ASGI server implementation (BSD-3-Clause License).
- **[Pydantic](https://docs.pydantic.dev/)**: Data validation and settings management using Python type annotations (MIT License).
- **[Pytest](https://pytest.org/) & [HTTPX](https://www.python-httpx.org/)**: Robust testing frameworks for Python (MIT & BSD Licenses).

