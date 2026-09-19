/**
 * GRIDPOINT — B2B Logistics Warehouse Location Optimization Client
 * Single State Architecture, Leaflet Geospatial Engine, Chart.js Analytics.
 * Strictly adheres to B2B operations rigor and Hackathon Honesty Rules.
 */

// Single Client-Side State Object
const appState = {
  sessionId: "default",
  neighborhoods: [],
  lastOptimize: null,
  lastCompare: null,
  lastTradeoff: null,
  lastScenario: null,
  explainCache: {},
  activeStep: "stepDemand",
  priorityPreset: "cost",
  map: null,
  layers: {
    candidates: L.layerGroup(),
    neighborhoods: L.layerGroup(),
    warehouses: L.layerGroup(),
    assignments: L.layerGroup(),
    radius: L.layerGroup(),
    routes: L.layerGroup(),
  },
  tradeoffChartInstance: null,
};

// Deterministic Cluster Color Palette for Warehouses and Zones
const CLUSTER_COLORS = [
  "#2563EB", // Royal Blue
  "#0D9488", // Teal
  "#D97706", // Amber
  "#7C3AED", // Purple
  "#DB2777", // Rose
  "#0284C7", // Sky
  "#EA580C", // Orange
  "#4F46E5", // Indigo
];

// Helper: Toast Notifications
function showToast(message, type = "success") {
  const toast = document.getElementById("alertToast");
  toast.className = `alert-toast active ${type}`;
  toast.innerHTML = message;
  setTimeout(() => {
    toast.className = "alert-toast";
  }, 4500);
}

// Helper: Show Infeasibility Modal
function showErrorModal(title, message, diagnostics = []) {
  const modal = document.getElementById("errorModal");
  document.getElementById("errorModalTitle").textContent = title || "Optimization Infeasible";
  
  let bodyHtml = `<p style="margin-bottom:10px;">${message}</p>`;
  if (diagnostics && diagnostics.length > 0) {
    bodyHtml += '<div style="background:var(--danger-bg); border:1px solid var(--danger-border); border-radius:var(--radius-sm); padding:10px; margin-top:8px;">';
    bodyHtml += '<strong style="color:var(--danger); font-size:0.78rem;">Diagnostics & Causes:</strong><ul style="margin-left:18px; margin-top:4px; font-size:0.76rem;">';
    diagnostics.forEach(d => {
      bodyHtml += `<li style="margin-bottom:2px;">${d}</li>`;
    });
    bodyHtml += '</ul></div>';
  }
  bodyHtml += '<div style="margin-top:12px; font-size:0.78rem; color:var(--text-muted);"><strong>Suggested Action:</strong> Increase the warehouse count (p), raise site throughput capacity, or expand maximum service radius.</div>';

  document.getElementById("errorModalBody").innerHTML = bodyHtml;
  modal.classList.add("active");
}

// 1. Initialize Map
function initMap() {
  appState.map = L.map("map", {
    center: [12.9716, 77.5946],
    zoom: 11,
    zoomControl: true,
  });

  // OpenStreetMap standard tile layer (Crisp high-contrast light tiles)
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(appState.map);

  appState.layers.candidates.addTo(appState.map);
  appState.layers.neighborhoods.addTo(appState.map);
  appState.layers.radius.addTo(appState.map);
  appState.layers.assignments.addTo(appState.map);
  appState.layers.routes.addTo(appState.map);
  appState.layers.warehouses.addTo(appState.map);

  // Layer Visibility Toggles
  document.getElementById("chkShowCandidates").addEventListener("change", (e) => {
    if (e.target.checked) appState.map.addLayer(appState.layers.candidates);
    else appState.map.removeLayer(appState.layers.candidates);
  });

  document.getElementById("chkShowAssignments").addEventListener("change", (e) => {
    if (e.target.checked) appState.map.addLayer(appState.layers.assignments);
    else appState.map.removeLayer(appState.layers.assignments);
  });

  document.getElementById("chkShowRadius").addEventListener("change", (e) => {
    if (e.target.checked) appState.map.addLayer(appState.layers.radius);
    else appState.map.removeLayer(appState.layers.radius);
  });

  document.getElementById("chkShowRoutes").addEventListener("change", (e) => {
    if (e.target.checked) appState.map.addLayer(appState.layers.routes);
    else appState.map.removeLayer(appState.layers.routes);
  });
}

// 2. Fetch Server Health & Check Solver
async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.solver_available) {
      document.getElementById("solverStatusText").textContent = `Solver: ${data.solver} Active`;
    } else {
      document.getElementById("solverStatusText").textContent = "Solver: Heuristic Active";
    }
  } catch (err) {
    console.error("Health check failed:", err);
  }
}

// 3. Update Live Plain-Language Summary Box
function updateLiveSummary() {
  const p = parseInt(document.getElementById("inputP").value) || 3;
  const cap = parseFloat(document.getElementById("inputCapacity").value) || 4000;
  const radiusVal = document.getElementById("inputRadius").value;
  const nZones = appState.neighborhoods.length || 36;
  const totalCap = p * cap;

  let radiusText = radiusVal ? ` within <strong>${radiusVal} km</strong> radius` : "";
  const box = document.getElementById("liveSummaryBox");
  if (box) {
    box.innerHTML = `You are planning a <strong>${p}-warehouse</strong> network serving <strong>${nZones} delivery zones</strong> with <strong>${totalCap.toLocaleString()} orders/day</strong> combined capacity${radiusText}.`;
  }
}

// 4. Load Demo Dataset
async function loadDemoData() {
  try {
    const res = await fetch("/api/demo-data");
    const data = await res.json();
    appState.sessionId = data.session_id;
    appState.neighborhoods = data.preview;

    renderNeighborhoodsOnMap(data.preview);
    updateLiveSummary();
    showToast(`Loaded 36 curated Bengaluru delivery zones (${data.total_demand.toLocaleString()} orders/day).`);
    
    // Auto-trigger optimization with default p=3
    await runOptimization();
  } catch (err) {
    showToast(`Failed to load demo data: ${err.message}`, "error");
  }
}

// 5. Render Raw Delivery Zones & Candidate Markers on Map
function renderNeighborhoodsOnMap(neighborhoods) {
  appState.layers.candidates.clearLayers();
  appState.layers.neighborhoods.clearLayers();
  appState.layers.assignments.clearLayers();
  appState.layers.radius.clearLayers();
  appState.layers.routes.clearLayers();
  appState.layers.warehouses.clearLayers();

  if (!neighborhoods || neighborhoods.length === 0) return;

  const lats = neighborhoods.map(n => n.latitude);
  const lons = neighborhoods.map(n => n.longitude);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  appState.map.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [40, 40] });

  const maxDemand = Math.max(...neighborhoods.map(n => n.daily_orders));

  neighborhoods.forEach(n => {
    // Candidate site marker (subtle slate ring)
    const candMarker = L.circleMarker([n.latitude, n.longitude], {
      radius: 4,
      fillColor: "#94A3B8",
      color: "#64748B",
      weight: 1,
      opacity: 0.6,
      fillOpacity: 0.3,
    }).bindTooltip(`Candidate Site: <b>${n.name}</b> (${n.neighborhood_id})<br>Throughput Capacity: 4,000 orders/day`);
    appState.layers.candidates.addLayer(candMarker);

    // Neighborhood demand node (sized by volume)
    const radius = 5 + (n.daily_orders / maxDemand) * 12;
    const nMarker = L.circleMarker([n.latitude, n.longitude], {
      radius: radius,
      fillColor: "#3B82F6",
      color: "#2563EB",
      weight: 1.5,
      opacity: 0.9,
      fillOpacity: 0.7,
    }).bindPopup(`
      <div style="font-family:var(--font-sans); padding:4px;">
        <div style="font-weight:700; font-size:0.9rem; color:var(--text-main);">${n.name}</div>
        <div style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono);">${n.neighborhood_id}</div>
        <hr style="margin:6px 0; border:0; border-top:1px solid var(--border-subtle);">
        <div style="font-size:0.8rem; color:var(--text-secondary);">
          <strong>Daily Orders:</strong> ${n.daily_orders.toLocaleString()} orders/day<br>
          <strong>Coordinates:</strong> ${n.latitude.toFixed(4)}, ${n.longitude.toFixed(4)}
        </div>
      </div>
    `);
    appState.layers.neighborhoods.addLayer(nMarker);
  });

  // Populate failed warehouse dropdown for scenario lab
  const selectFailed = document.getElementById("selectFailedWarehouse");
  if (selectFailed) {
    selectFailed.innerHTML = '<option value="">None (All Operational)</option>';
    neighborhoods.forEach(n => {
      selectFailed.innerHTML += `<option value="${n.neighborhood_id}">${n.name} (${n.neighborhood_id})</option>`;
    });
  }
}

// 6. Run Strategic Network Optimization
async function runOptimization() {
  const btn = document.getElementById("btnOptimize");
  const overlay = document.getElementById("mapLoadingOverlay");
  btn.disabled = true;
  document.getElementById("btnOptimizeText").textContent = "Solving CFLP...";
  overlay.classList.add("active");

  const p = parseInt(document.getElementById("inputP").value);
  const cap = parseFloat(document.getElementById("inputCapacity").value);
  const radius = document.getElementById("inputRadius").value ? parseFloat(document.getElementById("inputRadius").value) : null;
  const costKm = parseFloat(document.getElementById("inputCostKm").value);
  const fixedCost = parseFloat(document.getElementById("inputFixedCost").value);
  const mode = document.getElementById("selectDistanceMode").value;
  const includeCvrp = document.getElementById("chkIncludeCvrp").checked;
  const vehCap = parseInt(document.getElementById("inputVehicleCapacity").value) || 250;
  const vehCost = parseFloat(document.getElementById("inputVehicleFixedCost").value) || 150.0;

  const payload = {
    session_id: appState.sessionId,
    p: p,
    warehouse_capacity: cap,
    radius_max_km: radius,
    cost_per_km: costKm,
    fixed_cost_per_warehouse: fixedCost,
    routing_mode: mode,
    priority_preset: appState.priorityPreset,
    include_cvrp: includeCvrp,
    vehicle_capacity: vehCap,
    vehicle_fixed_cost: vehCost,
  };

  try {
    const res = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) {
      const diag = data.detail?.diagnostics || [];
      showErrorModal("Optimization Infeasible", data.detail?.error || "Constraint violation", diag);
      return;
    }

    appState.lastOptimize = data;
    appState.explainCache = {}; // invalidate cache

    renderOptimizationResults(data);
    await fetchBaselineComparison();
    await fetchTradeoffCurve();

    showToast(`Network Optimized: ${data.p} warehouses assigned to ${data.assignments.length} delivery zones.`);
  } catch (err) {
    showErrorModal("Network Request Failed", err.message);
  } finally {
    btn.disabled = false;
    document.getElementById("btnOptimizeText").textContent = "Run Network Optimization";
    overlay.classList.remove("active");
  }
}

// 7. Render Optimization Results on UI & Map
function renderOptimizationResults(data) {
  // Update Assumptions Strip
  const costKm = data.assumptions.cost_per_km || 1.25;
  const fixedLease = data.assumptions.fixed_cost_per_warehouse || 300;
  const rMax = data.assumptions.radius_max_km ? `${data.assumptions.radius_max_km} km` : "No Limit";
  const distMode = data.assumptions.routing_mode === "haversine" ? "Geographic Delivery Distance (Haversine)" : "Road Detour (1.35x Proxy)";

  document.getElementById("assumptionsBar").innerHTML = `
    <div><strong>Delivery Cost / km:</strong> $${costKm.toFixed(2)} (Estimated)</div>
    <div><strong>Facility Lease:</strong> $${fixedLease.toFixed(0)} / site / day</div>
    <div><strong>Max Service Radius:</strong> ${rMax}</div>
    <div><strong>Distance Metric:</strong> ${distMode}</div>
    <div><strong>Solver Status:</strong> ${data.solver_message}</div>
  `;

  // Update Executive KPI Cards
  document.getElementById("kpiCost").textContent = `$${data.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("kpiDistance").innerHTML = `${data.total_weighted_distance_km.toLocaleString(undefined, { maximumFractionDigits: 1 })} <span style="font-size:0.85rem; color:var(--text-muted)">ord·km</span>`;
  document.getElementById("kpiWarehouses").innerHTML = `${data.warehouses.length} <span style="font-size:0.85rem; color:var(--text-muted)">sites</span>`;
  document.getElementById("kpiWarehousesBadge").textContent = `p = ${data.p}`;
  document.getElementById("kpiSolverStatus").textContent = `Status: ${data.status}`;
  document.getElementById("kpiFastDelivery").textContent = `${data.fast_delivery_coverage_pct.toFixed(1)}%`;
  document.getElementById("kpiMonthlySavings").textContent = `$${data.estimated_monthly_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("kpiCO2").innerHTML = `${data.estimated_co2_kg_per_day.toFixed(1)} <span style="font-size:0.85rem; color:var(--text-muted)">kg</span>`;
  document.getElementById("kpiCO2Badge").textContent = `${data.co2_reduction_pct.toFixed(1)}%`;

  // Clear previous layers
  appState.layers.warehouses.clearLayers();
  appState.layers.assignments.clearLayers();
  appState.layers.radius.clearLayers();
  appState.layers.routes.clearLayers();

  // Color mapping per warehouse
  const wColorMap = {};
  data.warehouses.forEach((w, idx) => {
    wColorMap[w.warehouse_id] = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
  });

  // Render open warehouses with custom pin icons and service radius rings
  data.warehouses.forEach(w => {
    const color = wColorMap[w.warehouse_id];

    // Service Radius Ring
    if (data.assumptions.radius_max_km) {
      const radiusCircle = L.circle([w.latitude, w.longitude], {
        radius: data.assumptions.radius_max_km * 1000,
        color: color,
        weight: 1,
        dashArray: "4, 6",
        fillColor: color,
        fillOpacity: 0.05,
      });
      appState.layers.radius.addLayer(radiusCircle);
    }

    // Warehouse Marker
    const wIcon = L.divIcon({
      className: "custom-warehouse-pin-container",
      html: `
        <div style="background:${color}; width:32px; height:32px; border:2.5px solid #FFFFFF; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#FFFFFF; box-shadow:0 3px 10px rgba(0,0,0,0.25);">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M12 3l9 4H3l9-4z"></path>
          </svg>
        </div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });

    const wMarker = L.marker([w.latitude, w.longitude], { icon: wIcon }).bindPopup(`
      <div style="font-family:var(--font-sans); padding:4px;">
        <div style="font-size:0.7rem; color:${color}; font-weight:700; text-transform:uppercase;">Selected Facility</div>
        <div style="font-weight:800; font-size:0.95rem; color:var(--text-main); margin-top:2px;">${w.name}</div>
        <div style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono);">${w.warehouse_id}</div>
        <hr style="margin:6px 0; border:0; border-top:1px solid var(--border-subtle);">
        <div style="font-size:0.8rem; color:var(--text-secondary); line-height:1.5;">
          <strong>Throughput Demand:</strong> ${w.assigned_demand.toLocaleString()} orders/day<br>
          <strong>Site Capacity:</strong> ${w.capacity.toLocaleString()} orders/day<br>
          <strong>Capacity Utilization:</strong> ${w.capacity_utilization_pct.toFixed(1)}%<br>
          <strong>Zones Served:</strong> ${w.neighborhoods_count} delivery zones
        </div>
      </div>
    `);
    appState.layers.warehouses.addLayer(wMarker);
  });

  // Render spider assignment lines connecting each zone to its warehouse
  data.assignments.forEach(a => {
    const color = wColorMap[a.warehouse_id] || "#3B82F6";
    const line = L.polyline(
      [[a.latitude, a.longitude], [a.warehouse_latitude, a.warehouse_longitude]],
      {
        color: color,
        weight: 2,
        opacity: 0.65,
        dashArray: "3, 5",
      }
    ).bindTooltip(`<b>${a.neighborhood_name}</b> &rarr; ${a.warehouse_name}<br>Geographic Distance: ${a.distance_km} km<br>Demand: ${a.daily_orders} orders`);
    appState.layers.assignments.addLayer(line);
  });

  // Render CVRP Tactical Routes if available
  const routeToggle = document.getElementById("lblShowRoutes");
  if (data.cvrp_summary && data.cvrp_summary.routes && data.cvrp_summary.routes.length > 0) {
    routeToggle.style.display = "flex";
    data.cvrp_summary.routes.forEach((r, idx) => {
      const rColor = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
      if (r.route_coords && r.route_coords.length >= 2) {
        const poly = L.polyline(r.route_coords, {
          color: rColor,
          weight: 3.5,
          opacity: 0.85,
        }).bindTooltip(`Vehicle Tour: <b>${r.vehicle_id}</b> (${r.warehouse_name})<br>Distance: ${r.total_distance_km} km<br>Load: ${r.total_load} / ${r.capacity} (${r.utilization_pct}%)`);
        appState.layers.routes.addLayer(poly);
      }
    });
    renderRouteManifests(data.cvrp_summary);
  } else {
    routeToggle.style.display = "none";
  }

  // Populate Facility Manifest Table
  renderWarehouseManifestTable(data.warehouses);

  // Populate Explainability Warehouse Select
  const selectExplain = document.getElementById("selectExplainWarehouse");
  if (selectExplain) {
    selectExplain.innerHTML = "";
    data.warehouses.forEach(w => {
      selectExplain.innerHTML += `<option value="${w.warehouse_id}">${w.name} (${w.assigned_demand.toLocaleString()} orders/day)</option>`;
    });
    if (data.warehouses.length > 0) {
      loadExplainability(data.warehouses[0].warehouse_id);
    }
  }

  // Update Dynamic Demand-Weighting Explainer Box with real values
  updateDemandExplainerBox(data.assignments);
}

// 8. Dynamic Demand-Weighting Explainer
function updateDemandExplainerBox(assignments) {
  if (!assignments || assignments.length === 0) return;
  const sorted = [...assignments].sort((a, b) => b.daily_orders - a.daily_orders);
  const high = sorted[0];
  const low = sorted[sorted.length - 1];

  const highOrdKm = Math.round(high.daily_orders * high.distance_km);
  const lowOrdKm = Math.round(low.daily_orders * low.distance_km);

  document.getElementById("expHighName").textContent = `High-Demand Zone: ${high.neighborhood_name}`;
  document.getElementById("expHighMath").textContent = `${high.daily_orders.toLocaleString()} orders/day × ${high.distance_km.toFixed(1)} km = ${highOrdKm.toLocaleString()} order-km`;

  document.getElementById("expLowName").textContent = `Low-Demand Zone: ${low.neighborhood_name}`;
  document.getElementById("expLowMath").textContent = `${low.daily_orders.toLocaleString()} orders/day × ${low.distance_km.toFixed(1)} km = ${lowOrdKm.toLocaleString()} order-km`;
}

// 9. Fetch Baseline Comparison Benchmark
async function fetchBaselineComparison() {
  try {
    const res = await fetch(`/api/compare?session_id=${appState.sessionId}`);
    const data = await res.json();
    appState.lastCompare = data;

    // Update KPI badges with baseline deltas
    document.getElementById("kpiCostBadge").textContent = `${data.cost_pct_change.toFixed(1)}%`;
    document.getElementById("kpiDistanceBadge").textContent = `${data.distance_pct_change.toFixed(1)}%`;
    document.getElementById("kpiCostBaseline").textContent = `Baseline: $${data.baseline.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / day`;
    document.getElementById("kpiDistanceBaseline").textContent = `Baseline: ${data.baseline.weighted_distance_km.toLocaleString(undefined, { maximumFractionDigits: 1 })} ord·km`;

    // Populate Comparison Table
    const tbody = document.getElementById("comparisonTableBody");
    tbody.innerHTML = `
      <tr>
        <td><strong>Simulated Delivery Cost ($/day)</strong></td>
        <td>$${data.baseline.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><strong>$${data.optimized.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></td>
        <td style="color:var(--success); font-weight:700;">-$${Math.abs(data.cost_delta).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><span class="kpi-badge badge-green">${data.cost_pct_change.toFixed(1)}%</span></td>
      </tr>
      <tr>
        <td><strong>Demand-Weighted Delivery Distance (ord·km)</strong></td>
        <td>${data.baseline.weighted_distance_km.toLocaleString()}</td>
        <td><strong>${data.optimized.weighted_distance_km.toLocaleString()}</strong></td>
        <td style="color:var(--success); font-weight:700;">-${Math.abs(data.weighted_distance_delta).toLocaleString()}</td>
        <td><span class="kpi-badge badge-green">${data.weighted_distance_pct_change.toFixed(1)}%</span></td>
      </tr>
      <tr>
        <td><strong>Fixed Facility Lease ($/day)</strong></td>
        <td>$${data.baseline.total_infrastructure_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>$${data.optimized.total_infrastructure_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>+$${(data.optimized.total_infrastructure_cost - data.baseline.total_infrastructure_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><span class="kpi-badge badge-neutral">+${((data.optimized.warehouses_count - 1) * 100).toFixed(0)}%</span></td>
      </tr>
      <tr style="background:var(--bg-surface-secondary);">
        <td><strong>Combined System Cost ($/day)</strong></td>
        <td>$${data.baseline.combined_total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><strong>$${data.optimized.combined_total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></td>
        <td style="color:${data.optimized.combined_total_cost < data.baseline.combined_total_cost ? 'var(--success)' : 'var(--text-main)'}; font-weight:700;">
          ${data.optimized.combined_total_cost < data.baseline.combined_total_cost ? '-' : '+'}$${Math.abs(data.optimized.combined_total_cost - data.baseline.combined_total_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </td>
        <td><span class="kpi-badge ${data.optimized.combined_total_cost < data.baseline.combined_total_cost ? 'badge-green' : 'badge-neutral'}">
          ${(((data.optimized.combined_total_cost - data.baseline.combined_total_cost) / data.baseline.combined_total_cost) * 100).toFixed(1)}%
        </span></td>
      </tr>
      <tr>
        <td><strong>Estimated Daily CO₂ Footprint (kg)</strong></td>
        <td>${data.baseline.estimated_co2_kg_per_day.toFixed(1)} kg</td>
        <td><strong>${data.optimized.estimated_co2_kg_per_day.toFixed(1)} kg</strong></td>
        <td style="color:var(--success); font-weight:700;">-${Math.abs(data.co2_delta_kg).toFixed(1)} kg</td>
        <td><span class="kpi-badge badge-green">${data.co2_pct_change.toFixed(1)}%</span></td>
      </tr>
      <tr>
        <td><strong>Estimated 30-Day Monthly Savings</strong></td>
        <td>$0.00</td>
        <td colspan="3"><strong style="color:var(--success); font-size:0.95rem;">$${data.estimated_monthly_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong> / month</td>
      </tr>
    `;
  } catch (err) {
    console.error("Baseline comparison failed:", err);
  }
}

// 10. Fetch and Render Trade-off Curve (p = 1..5)
async function fetchTradeoffCurve() {
  try {
    const fixedCost = parseFloat(document.getElementById("inputFixedCost").value) || 300;
    const costKm = parseFloat(document.getElementById("inputCostKm").value) || 1.25;
    const res = await fetch(`/api/tradeoff?session_id=${appState.sessionId}&fixed_cost=${fixedCost}&cost_per_km=${costKm}`);
    const data = await res.json();
    appState.lastTradeoff = data;

    renderTradeoffChart(data);
  } catch (err) {
    console.error("Tradeoff curve failed:", err);
  }
}

function renderTradeoffChart(data) {
  const ctx = document.getElementById("tradeoffChart").getContext("2d");
  if (appState.tradeoffChartInstance) {
    appState.tradeoffChartInstance.destroy();
  }

  const labels = data.points.map(pt => `${pt.p} Site${pt.p > 1 ? 's' : ''}`);
  const delivCosts = data.points.map(pt => pt.delivery_cost);
  const infraCosts = data.points.map(pt => pt.infrastructure_cost);
  const combinedCosts = data.points.map(pt => pt.combined_cost);

  appState.tradeoffChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Combined Total Cost ($/day)",
          data: combinedCosts,
          borderColor: "#16A34A",
          backgroundColor: "rgba(22, 163, 74, 0.08)",
          borderWidth: 3,
          pointRadius: 5,
          pointBackgroundColor: "#16A34A",
          tension: 0.25,
          fill: true,
        },
        {
          label: "Delivery Cost ($/day)",
          data: delivCosts,
          borderColor: "#2563EB",
          borderWidth: 2,
          borderDash: [4, 4],
          pointRadius: 4,
          pointBackgroundColor: "#2563EB",
          tension: 0.25,
        },
        {
          label: "Infrastructure Lease ($/day)",
          data: infraCosts,
          borderColor: "#94A3B8",
          borderWidth: 2,
          borderDash: [2, 2],
          pointRadius: 4,
          pointBackgroundColor: "#94A3B8",
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top", labels: { font: { family: "Plus Jakarta Sans", size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(context) {
              return `${context.dataset.label}: $${context.parsed.y.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { callback: val => `$${val}` },
          grid: { color: "rgba(0, 0, 0, 0.05)" },
        },
        x: {
          grid: { display: false },
        }
      }
    }
  });
}

// 11. "Why this location?" Explainability Fetch & Render
async function loadExplainability(warehouseId) {
  const container = document.getElementById("explainContentBox");
  container.innerHTML = '<div style="text-align:center; padding:20px;"><div class="spinner" style="margin:0 auto 10px auto;"></div>Fetching solver intelligence...</div>';

  try {
    let data = appState.explainCache[warehouseId];
    if (!data) {
      const res = await fetch(`/api/explain/${warehouseId}?session_id=${appState.sessionId}`);
      data = await res.json();
      appState.explainCache[warehouseId] = data;
    }

    let driversHtml = '<table class="data-table" style="margin-top:8px;"><thead><tr><th>Top Delivery Zone</th><th>Daily Demand</th><th>Geographic Distance</th><th>Order-km Contribution</th></tr></thead><tbody>';
    data.key_demand_drivers.forEach(d => {
      driversHtml += `
        <tr>
          <td><strong>${d.name}</strong> (${d.neighborhood_id})</td>
          <td>${d.daily_orders.toLocaleString()} orders</td>
          <td>${d.distance_km.toFixed(2)} km</td>
          <td><span style="font-family:var(--font-mono); color:var(--primary);">${d.weighted_ord_km.toLocaleString()} ord·km</span></td>
        </tr>
      `;
    });
    driversHtml += '</tbody></table>';

    let rejectedHtml = '';
    if (data.next_best_rejected) {
      rejectedHtml = `
        <div class="rejected-card">
          <h5>Runner-Up Candidate in this Sector: ${data.next_best_rejected.name} (${data.next_best_rejected.candidate_id})</h5>
          <p>${data.next_best_rejected.reason_rejected}</p>
          <div style="font-size:0.72rem; font-family:var(--font-mono); color:var(--warning); margin-top:4px;">
            Objective Gap: +${data.next_best_rejected.score_gap_weighted_km.toLocaleString()} ord·km higher total travel penalty.
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      <div class="explain-metric-grid">
        <div class="explain-box">
          <div class="label">Assigned Demand Throughput</div>
          <div class="val">${data.demand_served.toLocaleString()} orders/day</div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${data.demand_pct_of_total}% of citywide volume</div>
        </div>
        <div class="explain-box">
          <div class="label">Capacity Utilization</div>
          <div class="val">${data.capacity_utilization_pct.toFixed(1)}%</div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${data.capacity.toLocaleString()} orders max capacity</div>
        </div>
        <div class="explain-box">
          <div class="label">Average Delivery Radius</div>
          <div class="val">${data.avg_distance_km.toFixed(2)} km</div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${data.neighborhoods_served_count} delivery zones served</div>
        </div>
        <div class="explain-box">
          <div class="label">Eliminated Burden vs Baseline</div>
          <div class="val" style="color:var(--success);">-${data.burden_eliminated_km.toLocaleString()} ord·km</div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">Reduction vs single-facility setup</div>
        </div>
      </div>

      <div style="margin-top:16px;">
        <strong style="font-size:0.82rem; color:var(--text-main); text-transform:uppercase; letter-spacing:0.03em;">Key Demand Drivers in Assigned Cluster</strong>
        ${driversHtml}
      </div>

      ${rejectedHtml}
    `;
  } catch (err) {
    container.innerHTML = `<div style="color:var(--danger); font-size:0.82rem;">Failed to fetch explainability: ${err.message}</div>`;
  }
}

// 12. Warehouse Facility Manifest Table
function renderWarehouseManifestTable(warehouses) {
  const tbody = document.getElementById("warehouseTableBody");
  if (!warehouses || warehouses.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:20px;">No active warehouses.</td></tr>';
    return;
  }

  tbody.innerHTML = warehouses.map(w => `
    <tr>
      <td><span style="font-family:var(--font-mono); font-weight:700;">${w.warehouse_id}</span></td>
      <td><strong>${w.name}</strong></td>
      <td>${w.assigned_demand.toLocaleString()} orders/day</td>
      <td>${w.capacity.toLocaleString()} orders/day</td>
      <td>
        <div style="display:flex; align-items:center; gap:8px;">
          <div style="flex:1; height:6px; background:var(--bg-surface-tertiary); border-radius:3px; overflow:hidden;">
            <div style="width:${Math.min(100, w.capacity_utilization_pct)}%; height:100%; background:${w.capacity_utilization_pct > 90 ? 'var(--danger)' : 'var(--primary)'};"></div>
          </div>
          <span style="font-family:var(--font-mono); font-size:0.75rem; font-weight:700;">${w.capacity_utilization_pct.toFixed(1)}%</span>
        </div>
      </td>
      <td>${w.neighborhoods_count} zones</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="inspectWarehouse('${w.warehouse_id}')">Inspect</button>
      </td>
    </tr>
  `).join("");
}

function inspectWarehouse(wId) {
  // Switch to Explainability tab
  document.querySelector('[data-tab="tabExplain"]').click();
  document.getElementById("selectExplainWarehouse").value = wId;
  loadExplainability(wId);
}

// 13. Route Manifests (CVRP)
function renderRouteManifests(cvrp) {
  const tbody = document.getElementById("routeManifestTableBody");
  if (!cvrp || !cvrp.routes || cvrp.routes.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">No active CVRP routes.</td></tr>';
    return;
  }

  tbody.innerHTML = cvrp.routes.map(r => `
    <tr>
      <td><span style="font-family:var(--font-mono); font-weight:700; color:var(--primary);">${r.vehicle_id}</span></td>
      <td><strong>${r.warehouse_name}</strong></td>
      <td style="font-size:0.76rem; max-width:260px;">${r.stop_names.join(" &rarr; ")}</td>
      <td>${r.total_distance_km.toFixed(2)} km</td>
      <td>${r.total_load.toLocaleString()} / ${r.capacity.toLocaleString()} orders</td>
      <td>
        <span class="kpi-badge ${r.utilization_pct > 80 ? 'badge-green' : 'badge-blue'}">${r.utilization_pct.toFixed(1)}%</span>
      </td>
    </tr>
  `).join("");
}

// 14. Scenario Simulation
async function runScenarioSimulation(multiplier, failedWid = null) {
  const box = document.getElementById("scenarioResultBox");
  box.innerHTML = '<div style="text-align:center; padding:10px;"><div class="spinner" style="margin:0 auto 10px auto;"></div>Simulating network resilience...</div>';

  const p = parseInt(document.getElementById("inputP").value) || 3;
  const cap = parseFloat(document.getElementById("inputCapacity").value) || 4000;
  const costKm = parseFloat(document.getElementById("inputCostKm").value) || 1.25;
  const fixedCost = parseFloat(document.getElementById("inputFixedCost").value) || 300;

  const payload = {
    session_id: appState.sessionId,
    demand_multiplier: multiplier,
    warehouse_failure_id: failedWid,
    p: p,
    warehouse_capacity: cap,
    cost_per_km: costKm,
    fixed_cost_per_warehouse: fixedCost,
  };

  try {
    const res = await fetch("/api/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) {
      showErrorModal("Scenario Infeasible", data.detail?.error || "Constraint violation", data.detail?.diagnostics || []);
      box.innerHTML = '<div style="color:var(--danger);">Scenario is infeasible under current capacity limits.</div>';
      return;
    }

    appState.lastScenario = data;

    let warningHtml = "";
    if (data.locations_changed) {
      warningHtml = `<div style="background:var(--warning-bg); border:1px solid var(--warning-border); padding:8px 12px; border-radius:var(--radius-sm); color:var(--warning); font-weight:700; margin-bottom:10px;">
        ⚠️ Facility Locations Shifted: Network topology was reconfigured to maintain service feasibility.
      </div>`;
    }

    box.innerHTML = `
      ${warningHtml}
      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin-bottom:12px;">
        <div class="explain-box">
          <div class="label">Scenario Delivery Cost</div>
          <div class="val">$${data.scenario_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          <div style="font-size:0.72rem; color:${data.cost_pct_change > 0 ? 'var(--danger)' : 'var(--success)'}; font-weight:700; margin-top:2px;">
            ${data.cost_pct_change > 0 ? '+' : ''}${data.cost_pct_change.toFixed(1)}% vs base
          </div>
        </div>
        <div class="explain-box">
          <div class="label">Weighted Delivery Distance</div>
          <div class="val">${data.scenario_weighted_distance.toLocaleString()} ord·km</div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${data.weighted_distance_pct_change.toFixed(1)}% change</div>
        </div>
        <div class="explain-box">
          <div class="label">Active Warehouses</div>
          <div class="val">${data.scenario_warehouses.length} sites</div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${data.scenario_warehouses.join(", ")}</div>
        </div>
      </div>
      <div style="font-size:0.78rem; color:var(--text-secondary); line-height:1.45;">
        ${data.diagnostics.length > 0 ? data.diagnostics.join("<br>") : "All delivery zones remain 100% serviceable within capacity."}
      </div>
    `;
    showToast(`Scenario executed: ${data.scenario_name}`);
  } catch (err) {
    box.innerHTML = `<div style="color:var(--danger);">Scenario execution failed: ${err.message}</div>`;
  }
}

// 15. Setup Event Handlers
function setupEventHandlers() {
  // Step Navigation Ribbon
  document.querySelectorAll(".step-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".step-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const step = tab.getAttribute("data-step");
      appState.activeStep = step;

      // Smooth view switching
      if (step === "stepDemand") {
        document.querySelector('[data-tab="tabComparison"]').click();
      } else if (step === "stepBenchmark") {
        document.querySelector('[data-tab="tabComparison"]').click();
      } else if (step === "stepScenario") {
        document.querySelector('[data-tab="tabScenario"]').click();
      } else if (step === "stepFleet") {
        document.querySelector('[data-tab="tabRouteManifests"]').click();
      }
    });
  });

  // Analytics Tabs Switcher
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const tabId = btn.getAttribute("data-tab");
      const targetContent = document.getElementById(tabId);
      if (targetContent) targetContent.classList.add("active");
    });
  });

  // Slider & Form Input Listeners
  const inputP = document.getElementById("inputP");
  inputP.addEventListener("input", (e) => {
    document.getElementById("valP").textContent = e.target.value;
    updateLiveSummary();
  });

  const inputRadius = document.getElementById("inputRadius");
  inputRadius.addEventListener("input", (e) => {
    document.getElementById("valRadius").textContent = e.target.value ? `${e.target.value} km` : "No Limit";
    updateLiveSummary();
  });

  document.getElementById("inputCapacity").addEventListener("input", updateLiveSummary);

  // Priority Presets
  document.querySelectorAll(".preset-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".preset-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      appState.priorityPreset = pill.getAttribute("data-preset");
    });
  });

  // CVRP Checkbox Toggle
  const chkCvrp = document.getElementById("chkIncludeCvrp");
  chkCvrp.addEventListener("change", (e) => {
    document.getElementById("cvrpSubControls").style.display = e.target.checked ? "block" : "none";
  });

  // Optimize Button
  document.getElementById("btnOptimize").addEventListener("click", runOptimization);

  // Load Demo Button
  document.getElementById("btnLoadDemo").addEventListener("click", loadDemoData);

  // CSV Upload
  document.getElementById("csvFileInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        showErrorModal("CSV Upload Error", "Invalid CSV Format", data.detail?.errors || []);
        return;
      }

      appState.sessionId = data.session_id;
      appState.neighborhoods = data.preview;
      renderNeighborhoodsOnMap(data.preview);
      updateLiveSummary();
      showToast(`Uploaded ${data.neighborhood_count} zones (${data.total_demand.toLocaleString()} orders/day).`);
      await runOptimization();
    } catch (err) {
      showErrorModal("Upload Failed", err.message);
    }
  });

  // Manual JSON Modal
  const modalManual = document.getElementById("manualEntryModal");
  document.getElementById("btnOpenManualEntry").addEventListener("click", () => {
    document.getElementById("manualJsonArea").value = JSON.stringify(appState.neighborhoods, null, 2);
    modalManual.classList.add("active");
  });
  document.getElementById("btnCloseManualModal").addEventListener("click", () => modalManual.classList.remove("active"));
  document.getElementById("btnCancelManual").addEventListener("click", () => modalManual.classList.remove("active"));

  document.getElementById("btnSubmitManual").addEventListener("click", async () => {
    try {
      const parsed = JSON.parse(document.getElementById("manualJsonArea").value);
      const res = await fetch("/api/neighborhoods", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ neighborhoods: parsed }),
      });
      const data = await res.json();
      if (!res.ok) {
        showErrorModal("JSON Error", "Validation failed", data.detail?.errors || []);
        return;
      }
      appState.sessionId = data.session_id;
      appState.neighborhoods = data.preview;
      renderNeighborhoodsOnMap(data.preview);
      modalManual.classList.remove("active");
      showToast(`Applied ${data.neighborhood_count} zones.`);
      await runOptimization();
    } catch (err) {
      alert(`Invalid JSON format: ${err.message}`);
    }
  });

  // Infeasibility Modal Close
  const modalError = document.getElementById("errorModal");
  document.getElementById("btnErrorModalClose").addEventListener("click", () => modalError.classList.remove("active"));
  document.getElementById("btnErrorModalOk").addEventListener("click", () => modalError.classList.remove("active"));

  // Explainability Select
  document.getElementById("selectExplainWarehouse").addEventListener("change", (e) => {
    loadExplainability(e.target.value);
  });

  // Scenario Lab Presets
  document.getElementById("btnPresetNormal").addEventListener("click", () => runScenarioSimulation(1.0));
  document.getElementById("btnPresetWeekend").addEventListener("click", () => runScenarioSimulation(1.2));
  document.getElementById("btnPresetFestival").addEventListener("click", () => runScenarioSimulation(1.5));
  document.getElementById("btnRunScenario").addEventListener("click", () => {
    const failed = document.getElementById("selectFailedWarehouse").value || null;
    runScenarioSimulation(1.0, failed);
  });
}

// Window Onload Initialization
window.addEventListener("DOMContentLoaded", async () => {
  initMap();
  setupEventHandlers();
  await checkHealth();
  await loadDemoData();
});
