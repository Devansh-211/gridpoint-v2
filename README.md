# GRIDPOINT — Intelligent Warehouse Location & Delivery Network Optimizer
### Hack-A-Matics 2026 Prototype — Operations-Research Logistics Decision Support Tool

**GRIDPOINT** is a B2B logistics decision-support tool designed for operations and supply chain managers at quick-commerce and e-commerce enterprises. Rather than relying on intuition or manual guesswork, GRIDPOINT applies mathematical optimization to determine **where warehouses should go, how many to open, which delivery zones each facility should serve, and quantifies the exact cost and distance improvements over a reference baseline**.

---

## 1. Executive Value Proposition

- **Make smarter delivery decisions:** Strategic Capacitated Facility Location Problem (CFLP) solved to mathematical optimality via Mixed-Integer Linear Programming (**PuLP + CBC**) with automated greedy + 2-opt local search fallback.
- **Save more:** Quantifies daily and monthly cost reductions over a rigorous **Single-Warehouse Reference Baseline** (1-median center).
- **Plan for disruption:** Interactive Scenario Lab simulating demand surges (+20% weekend, +50% festival peaks) and facility outage re-routing.
- **Explainable intelligence:** "Why this location?" mathematical intelligence breaking down key demand drivers and the exact score gap of rejected candidate facilities.
- **Tactical fleet execution:** Optional Capacitated Vehicle Routing Problem (CVRP) solving multi-stop vehicle tours via **Google OR-Tools Guided Local Search**.

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
- **Frontend:** HTML5, CSS3 (Light Theme Design System), Vanilla JavaScript (Single State Architecture).
- **Geospatial & Charts:** Leaflet.js (interactive maps & cluster rendering), Chart.js (trade-off curves & analytics).

---

## 4. Project Directory Structure

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
│   ├── index.html           # Light-theme dashboard with step navigation ribbon
│   ├── style.css            # Modern B2B logistics design system with soft blue accents
│   └── app.js               # Reactive client state, Leaflet geospatial engine & Chart.js
├── tests/
│   ├── test_api.py          # REST endpoint integration tests (26 test suites)
│   ├── test_cflp.py         # CFLP solver unit tests
│   ├── test_cvrp.py         # CVRP routing unit tests
│   └── test_validation.py   # Presolve validation tests
├── app.py                   # Application entrypoint & CBC solver startup verification
├── config.py                # Configuration constants & defaults
├── requirements.txt         # Python dependencies
└── README.md                # System documentation & Hackathon AI Usage Disclosure
```

---

## 5. Quickstart & Installation

### Prerequisites
- Python 3.11+
- Virtual environment tool (`venv`)

### 1. Set Up Environment
```bash
# Clone the repository
git clone https://github.com/your-repo/gridpoint.git
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

### 2. Run Automated Test Suite
```bash
python -m pytest -v
```

### 3. Launch Application
```bash
uvicorn app:app --reload --port 8000
```
Open your browser to: **`http://127.0.0.1:8000/`** (Interactive API Swagger Docs: `http://127.0.0.1:8000/docs`).

---

## 6. End-to-End Demo Script (Under 2 Minutes)

1. **One-Click Demo Ingestion:** Click **"Load Bengaluru Demo"** in the top navigation bar. 36 delivery zones instantly load with proportional circle markers.
2. **Configure Facilities:** Set warehouse count $p = 3$, site capacity $= 4,000$ orders/day, and select **"Cost Focus"** priority preset. Observe the live summary update: *"Planning a 3-warehouse network serving 36 delivery zones with 12,000 orders/day capacity."*
3. **Run Optimization:** Click **"Run Network Optimization"**. Within 1–2 seconds, the MILP solver returns the proven optimal 3-facility network.
4. **Inspect Centerpiece Map:** View selected warehouses (custom building pins), cluster assignment spider lines, and translucent service radius rings.
5. **Review Demand-Weighting Explainer:** Inspect the live dynamic panel showing why high-demand zones (e.g. Koramangala, 420 orders) exert greater mathematical pull than low-demand zones (e.g. Kengeri, 150 orders).
6. **Inspect "Why this location?":** Select a warehouse in the intelligence tab to review its assigned volume, capacity utilization %, top 3 demand drivers, and the **score gap of the runner-up rejected candidate**.
7. **Evaluate Trade-off Curve:** Switch to the Trade-off tab to review the diminishing returns curve ($p = 1 \dots 5$) balancing delivery distance reduction against fixed facility leases.
8. **Run Disruption Test:** Switch to the Scenario Lab and click **"Festival Surge (+50%)"** or simulate a warehouse outage to test network resilience and automatic load reassignment.
9. **Tactical CVRP Routes:** Enable **"Refine with CVRP (OR-Tools)"** in the sidebar to review turn-by-turn vehicle tours and vehicle payload utilization.

---

## 7. Transparency, Terminology & Honesty Rules

- **Distance Metric:** All straight-line distances are explicitly labeled **"Geographic delivery distance"** ($R \approx 6371\text{ km}$, Haversine formula) — never implied to be exact road distance.
- **Baseline Benchmark:** Comparisons are explicitly labeled **"Single-Warehouse Reference Baseline vs Optimized Network"** (computed dynamically from the 1-median facility center).
- **Cost & Emissions Estimates:** All financial figures and carbon metrics carry visible **`[Estimate]`** tags and show their calculation assumptions nearby.
- **Fast Delivery Proxy:** Fast delivery coverage is explicitly labeled **"Distance-based service proxy"** (% of demand within 5 km) — never guaranteeing delivery time SLAs.
- **No Fake AI:** The "Why here?" explainability panel is generated strictly from real solver metrics, objective gradients, and candidate score gaps.

---

## 8. Mandatory Hackathon AI Usage Disclosure

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
