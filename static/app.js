/**
 * GRIDPOINT — B2B Logistics Warehouse Location Optimization Client
 * Presentation-Layer Architecture with Single-State Router and Leaflet Engine.
 * Strictly adheres to B2B Operations rigor and Hackathon Honesty Rules.
 */

// Single Client-Side State Object
const appState = {
  sessionId: "default",
  neighborhoods: [],
  configMode: "manual", // "manual" or "auto"
  lastOptimize: null,
  lastCompare: null,
  lastTradeoff: null,
  lastScenario: null,
  explainCache: {},
  currentView: "viewLanding",
  priorityPreset: "cost",
  maps: {
    results: null,
    demand: null,
  },
  layers: {
    results: {
      candidates: L.layerGroup(),
      neighborhoods: L.layerGroup(),
      warehouses: L.layerGroup(),
      assignments: L.layerGroup(),
      radius: L.layerGroup(),
      routes: L.layerGroup(),
    },
    demand: {
      candidates: L.layerGroup(),
      neighborhoods: L.layerGroup(),
    }
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

// View Metadata for Header Breadcrumb & Title
const VIEW_METADATA = {
  viewLanding: { breadcrumb: "Setup", title: "Landing & Entry" },
  viewDashboard: { breadcrumb: "Setup", title: "Dashboard Overview" },
  viewData: { breadcrumb: "Setup", title: "Demand Data Ingestion" },
  viewConfig: { breadcrumb: "Setup", title: "Network Configuration" },
  viewResults: { breadcrumb: "Results & Solvers", title: "Optimization Results" },
  viewScenarios: { breadcrumb: "Results & Solvers", title: "Scenario Lab (What-If)" },
  viewDisruption: { breadcrumb: "Results & Solvers", title: "Disruption & Resilience" },
  viewFleet: { breadcrumb: "Results & Solvers", title: "Tactical Fleet Routing (CVRP)" },
  viewAnalytics: { breadcrumb: "Reference", title: "Analytics & Trade-off Curve" },
  viewMethodology: { breadcrumb: "Reference", title: "Methodology & Honesty Rules" },
};

// ============================================================================
// CONVERSATIONAL LOGISTICS AI AGENT & EXPLAIN SYSTEM (PHASES 2, 3 & 4)
// ============================================================================

const agentState = {
  mode: "setup", // "setup", "explain", "synthetic"
  historySetup: [],
  historyExplain: [],
  knownParams: {
    warehouse_count: 3,
    warehouse_capacity: 4000,
    max_service_radius_km: 25.0,
    cost_per_km: 1.25,
    fixed_cost_per_warehouse: 300.0,
    priority_preset: "cost",
    include_cvrp: false,
    vehicle_capacity: 250,
    vehicle_fixed_cost: 150.0,
  },
  isProcessing: false,
};

const EXPLAIN_PROMPTS_BY_VIEW = {
  viewResults: [
    "Why were these specific warehouse locations selected?",
    "Show facility throughput capacity and utilization breakdown",
    "Explain savings compared to the single-warehouse baseline",
    "How is demand-weighted distance calculated?",
  ],
  viewScenarios: [
    "How does the network respond to a +50% festival demand surge?",
    "What is the simulated cost shift during peak volume?",
    "Are any warehouse throughput capacities exceeded in this scenario?",
  ],
  viewDisruption: [
    "What happens if our primary central warehouse suffers an outage?",
    "How is displaced demand re-routed during facility failure?",
    "What is the emergency reassignment cost impact?",
  ],
  viewFleet: [
    "How are multi-stop CVRP vehicle routes constructed?",
    "Explain vehicle payload utilization across the fleet",
    "What is the total estimated fleet travel distance?",
  ],
  viewAnalytics: [
    "Where is the point of diminishing returns on the trade-off curve?",
    "Why does marginal savings decrease as warehouse count p increases?",
    "Explain the fleet CO2 emissions calculation formula",
  ],
  viewConfig: [
    "How does changing p from 3 to 4 impact delivery cost?",
    "What does maximum service radius constrain in the solver?",
    "What are the default cost and lease assumptions?",
  ],
  viewData: [
    "What validation rules are enforced on uploaded CSV datasets?",
    "How are candidate facility locations identified from delivery zones?",
    "What is the total daily demand volume across active zones?",
  ],
};

function updateSyntheticDatasetBadge(isSynthetic) {
  appState.isSyntheticAi = !!isSynthetic;
  appState.datasetType = isSynthetic ? "ai_synthetic" : "demo";
  const badge = document.getElementById("headerSyntheticBadge");
  if (badge) {
    badge.style.display = isSynthetic ? "inline-flex" : "none";
  }
}

function gatherPageContext(viewId) {
  const ctx = {
    view: viewId,
    session_id: appState.sessionId,
    is_synthetic_ai: appState.isSyntheticAi,
    dataset_type: appState.datasetType,
  };

  if (viewId === "viewResults" && appState.lastOptimize) {
    const opt = appState.lastOptimize;
    ctx.status = opt.status;
    ctx.warehouse_count = opt.warehouse_count || (opt.warehouses ? opt.warehouses.length : 3);
    ctx.total_delivery_cost = opt.total_delivery_cost;
    ctx.estimated_monthly_savings = opt.estimated_monthly_savings;
    ctx.avg_distance_km = opt.avg_delivery_distance_km;
    ctx.max_distance_km = opt.max_delivery_distance_km;
    ctx.unassigned_count = opt.unassigned_neighborhoods ? opt.unassigned_neighborhoods.length : 0;
    ctx.priority_preset = opt.priority_preset || appState.priorityPreset;
    ctx.warehouses = (opt.warehouses || []).map(w => ({
      warehouse_id: w.warehouse_id,
      name: w.name,
      assigned_demand: w.assigned_demand,
      capacity: w.capacity,
      capacity_utilization_pct: w.capacity_utilization_pct,
      neighborhoods_count: w.neighborhoods_count,
    }));
    if (appState.lastCompare) {
      ctx.cost_pct_change = appState.lastCompare.cost_pct_change;
      ctx.co2_pct_change = appState.lastCompare.co2_pct_change;
    }
  } else if (viewId === "viewScenarios" && appState.lastScenario) {
    const sc = appState.lastScenario;
    ctx.demand_multiplier = sc.demand_multiplier;
    ctx.cost_pct_change = sc.cost_pct_change;
    ctx.scenario_warehouses = sc.scenario_warehouses;
    ctx.unserved_demand = sc.unserved_demand;
  } else if (viewId === "viewDisruption" && appState.lastScenario) {
    const sc = appState.lastScenario;
    ctx.failed_warehouse_id = sc.failed_warehouse;
    ctx.cost_pct_change = sc.cost_pct_change;
    ctx.scenario_warehouses = sc.scenario_warehouses;
  } else if (viewId === "viewFleet" && appState.lastOptimize?.cvrp_routes) {
    ctx.routes_count = appState.lastOptimize.cvrp_routes.length;
    ctx.total_fleet_distance_km = appState.lastOptimize.total_cvrp_distance_km;
  } else if (viewId === "viewAnalytics" && appState.lastTradeoff) {
    ctx.tradeoff_points = appState.lastTradeoff.points;
  } else if (viewId === "viewData") {
    ctx.neighborhood_count = appState.neighborhoods ? appState.neighborhoods.length : 0;
    ctx.total_demand = appState.neighborhoods ? appState.neighborhoods.reduce((sum, n) => sum + (n.daily_orders || 0), 0) : 0;
  } else if (viewId === "viewConfig") {
    ctx.warehouse_count = parseInt(document.getElementById("inputConfigP")?.value) || 3;
    ctx.warehouse_capacity = parseInt(document.getElementById("inputConfigCap")?.value) || 4000;
    ctx.max_service_radius_km = parseFloat(document.getElementById("inputConfigRadius")?.value) || 25.0;
    ctx.priority_preset = appState.priorityPreset;
  }

  return ctx;
}

function renderExplainQuickQuestions(viewId) {
  const container = document.getElementById("agentExplainQuickPrompts");
  if (!container) return;
  const questions = EXPLAIN_PROMPTS_BY_VIEW[viewId] || EXPLAIN_PROMPTS_BY_VIEW["viewResults"];
  container.innerHTML = '<div class="gp-quick-prompts-label">Screen Questions:</div>';
  questions.forEach(q => {
    const chip = document.createElement("button");
    chip.className = "gp-quick-chip";
    chip.textContent = `• ${q}`;
    chip.addEventListener("click", () => sendAgentExplainMessage(q));
    container.appendChild(chip);
  });
}

function setAgentMode(mode) {
  agentState.mode = mode;
  const btnSetup = document.getElementById("btnModeSetup");
  const btnExplain = document.getElementById("btnModeExplain");
  const containerSetup = document.getElementById("agentSetupContainer");
  const containerSynthetic = document.getElementById("agentSyntheticContainer");
  const containerExplain = document.getElementById("agentExplainContainer");
  const bannerExplain = document.getElementById("agentExplainBanner");
  const bannerText = document.getElementById("agentExplainBannerText");
  const inputEl = document.getElementById("agentInput");
  const titleEl = document.getElementById("agentDrawerTitle");
  const subEl = document.getElementById("agentDrawerSubtitle");

  if (mode === "setup") {
    btnSetup?.classList.add("active");
    btnExplain?.classList.remove("active");
    if (containerSetup) containerSetup.style.display = "flex";
    if (containerSynthetic) containerSynthetic.style.display = "none";
    if (containerExplain) containerExplain.style.display = "none";
    if (bannerExplain) bannerExplain.style.display = "none";
    if (inputEl) inputEl.placeholder = "Describe network requirements (e.g. 3 sites, 4000 cap)...";
    if (titleEl) titleEl.textContent = "Logistics Assistant";
    if (subEl) subEl.textContent = "Plain-Language Optimization Setup";
  } else if (mode === "synthetic") {
    btnSetup?.classList.add("active");
    btnExplain?.classList.remove("active");
    if (containerSetup) containerSetup.style.display = "none";
    if (containerSynthetic) containerSynthetic.style.display = "flex";
    if (containerExplain) containerExplain.style.display = "none";
    if (bannerExplain) bannerExplain.style.display = "none";
    if (inputEl) inputEl.placeholder = "Describe region or zone preferences...";
    if (titleEl) titleEl.textContent = "Synthetic Data Generator";
    if (subEl) subEl.textContent = "Consent-Gated Non-Uniform AI Data";
  } else if (mode === "explain") {
    btnSetup?.classList.remove("active");
    btnExplain?.classList.add("active");
    if (containerSetup) containerSetup.style.display = "none";
    if (containerSynthetic) containerSynthetic.style.display = "none";
    if (containerExplain) containerExplain.style.display = "flex";
    if (bannerExplain) {
      bannerExplain.style.display = "flex";
      const meta = VIEW_METADATA[appState.currentView] || { title: "Workspace" };
      if (bannerText) bannerText.textContent = `Grounded in active ${meta.title} computed metrics`;
    }
    if (inputEl) inputEl.placeholder = `Ask AI about ${VIEW_METADATA[appState.currentView]?.title || "this screen"}...`;
    if (titleEl) titleEl.textContent = "Logistics AI Explainer";
    if (subEl) subEl.textContent = "Grounded Real-Data Explanations";

    renderExplainQuickQuestions(appState.currentView);
  }
}

function syncUiToAgentParams() {
  const pVal = parseInt(document.getElementById("inputConfigP")?.value) || 3;
  const capVal = parseInt(document.getElementById("inputConfigCap")?.value) || 4000;
  const radVal = parseFloat(document.getElementById("inputConfigRadius")?.value) || 25.0;
  const cvrpVal = document.getElementById("chkIncludeCvrp")?.checked || false;
  const preset = appState.priorityPreset || "cost";
  agentState.knownParams = {
    ...agentState.knownParams,
    warehouse_count: pVal,
    warehouse_capacity: capVal,
    max_service_radius_km: radVal,
    include_cvrp: cvrpVal,
    priority_preset: preset,
  };
}

function applyAgentParamsToUi(params) {
  if (!params) return;
  if (params.warehouse_count !== undefined && params.warehouse_count !== null) {
    const el = document.getElementById("inputConfigP");
    if (el) el.value = params.warehouse_count;
    const valEl = document.getElementById("valConfigP");
    if (valEl) valEl.textContent = `${params.warehouse_count} sites`;
  }
  if (params.warehouse_capacity !== undefined && params.warehouse_capacity !== null) {
    const el = document.getElementById("inputConfigCap");
    if (el) el.value = params.warehouse_capacity;
    const valEl = document.getElementById("valConfigCap");
    if (valEl) valEl.textContent = `${Number(params.warehouse_capacity).toLocaleString()} orders/day`;
  }
  if (params.max_service_radius_km !== undefined && params.max_service_radius_km !== null) {
    const el = document.getElementById("inputConfigRadius");
    if (el) el.value = params.max_service_radius_km;
    const valEl = document.getElementById("valConfigRadius");
    if (valEl) valEl.textContent = `${params.max_service_radius_km} km`;
  }
  if (params.include_cvrp !== undefined && params.include_cvrp !== null) {
    const el1 = document.getElementById("chkIncludeCvrp");
    if (el1) el1.checked = !!params.include_cvrp;
    const el2 = document.getElementById("chkFleetEnableCvrp");
    if (el2) el2.checked = !!params.include_cvrp;
  }
  if (params.priority_preset) {
    appState.priorityPreset = params.priority_preset;
    document.querySelectorAll(".gp-preset-pill").forEach(pill => {
      if (pill.getAttribute("data-preset") === params.priority_preset) {
        pill.classList.add("active");
      } else {
        pill.classList.remove("active");
      }
    });
  }
  updateLiveSummary();
  updateDashboardStats();
  agentState.knownParams = { ...agentState.knownParams, ...params };
}

function toggleAgentDrawer(open, optionalMode = null) {
  const drawer = document.getElementById("agentDrawer");
  const backdrop = document.getElementById("agentDrawerBackdrop");
  if (!drawer || !backdrop) return;

  if (open) {
    if (optionalMode) {
      setAgentMode(optionalMode);
    } else {
      // Auto-default based on page
      if (["viewResults", "viewScenarios", "viewDisruption", "viewFleet", "viewAnalytics"].includes(appState.currentView)) {
        setAgentMode("explain");
      } else {
        setAgentMode("setup");
      }
    }
    syncUiToAgentParams();
    drawer.classList.add("active");
    backdrop.classList.add("active");
    setTimeout(() => document.getElementById("agentInput")?.focus(), 150);
  } else {
    drawer.classList.remove("active");
    backdrop.classList.remove("active");
  }
}

function updateAgentFabVisibility(viewId) {
  const fab = document.getElementById("btnOpenAgentDrawer");
  if (!fab) return;
  // Accessible across all actionable screens
  if (viewId !== "viewLanding" && viewId !== "viewMethodology") {
    fab.classList.add("visible");
  } else {
    fab.classList.remove("visible");
  }
}

function appendAgentMessage(text, role = "agent", targetContainerId = "agentSetupContainer") {
  const body = document.getElementById(targetContainerId);
  if (!body) return;
  const bubble = document.createElement("div");
  bubble.className = `gp-bubble ${role === "user" ? "gp-bubble-user" : "gp-bubble-agent"}`;
  bubble.textContent = text;
  body.appendChild(bubble);
  const chatBody = document.getElementById("agentChatBody");
  if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
}

function showThinkingPulse() {
  const chatBody = document.getElementById("agentChatBody");
  if (!chatBody) return;
  removeThinkingPulse();
  const pulse = document.createElement("div");
  pulse.id = "agentThinkingPulse";
  pulse.className = "gp-thinking-pulse";
  pulse.innerHTML = `
    <div class="gp-thinking-dot"></div>
    <div class="gp-thinking-dot"></div>
    <div class="gp-thinking-dot"></div>
  `;
  chatBody.appendChild(pulse);
  chatBody.scrollTop = chatBody.scrollHeight;
}

function removeThinkingPulse() {
  const p = document.getElementById("agentThinkingPulse");
  if (p) p.remove();
}

function renderSuggestedPrompts(prompts) {
  const body = document.getElementById("agentSetupContainer");
  if (!body || !prompts || prompts.length === 0) return;
  const container = document.createElement("div");
  container.className = "gp-quick-prompts";
  container.innerHTML = '<div class="gp-quick-prompts-label">Suggested Replies:</div>';
  prompts.forEach(p => {
    const chip = document.createElement("button");
    chip.className = "gp-quick-chip";
    chip.textContent = `• ${p}`;
    chip.addEventListener("click", () => sendAgentMessage(p));
    container.appendChild(chip);
  });
  body.appendChild(container);
  const chatBody = document.getElementById("agentChatBody");
  if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
}

function renderConfirmationCard(data) {
  const body = document.getElementById("agentSetupContainer");
  if (!body || !data.confirmation_card) return;
  const cardData = data.confirmation_card;
  const p = cardData.params || {};

  const card = document.createElement("div");
  card.className = "gp-confirm-card";
  
  let notesHtml = "";
  if (cardData.defaults_applied && cardData.defaults_applied.length > 0) {
    notesHtml += `<div class="gp-confirm-notes"><strong>Defaults applied:</strong> ${cardData.defaults_applied.join("; ")}</div>`;
  }
  if (cardData.warnings && cardData.warnings.length > 0) {
    notesHtml += `<div class="gp-confirm-notes" style="border-left-color:var(--gp-warning); margin-top:4px;"><strong>Note:</strong> ${cardData.warnings.join("; ")}</div>`;
  }

  card.innerHTML = `
    <div class="gp-confirm-title">
      <span>Proposed Configuration</span>
      <span class="gp-badge gp-badge-estimate" style="font-size:10px;">[Ready to Solve]</span>
    </div>
    <div class="gp-confirm-grid">
      <div class="gp-confirm-field">
        <span class="gp-confirm-label">Warehouses (p)</span>
        <input type="number" min="1" max="5" class="gp-confirm-val" id="cfgEditP" value="${p.warehouse_count ?? 3}">
      </div>
      <div class="gp-confirm-field">
        <span class="gp-confirm-label">Capacity (orders/day)</span>
        <input type="number" step="500" class="gp-confirm-val" id="cfgEditCap" value="${p.warehouse_capacity ?? 4000}">
      </div>
      <div class="gp-confirm-field">
        <span class="gp-confirm-label">Max Radius (km)</span>
        <input type="number" step="1" class="gp-confirm-val" id="cfgEditRadius" value="${p.max_service_radius_km ?? 25}">
      </div>
      <div class="gp-confirm-field">
        <span class="gp-confirm-label">Priority Preset</span>
        <select class="gp-confirm-val" id="cfgEditPreset" style="font-size:11px; cursor:pointer;">
          <option value="cost" ${p.priority_preset === 'cost' ? 'selected' : ''}>Cost Focus</option>
          <option value="speed" ${p.priority_preset === 'speed' ? 'selected' : ''}>Speed Focus</option>
          <option value="sustainability" ${p.priority_preset === 'sustainability' ? 'selected' : ''}>Sustainability</option>
        </select>
      </div>
    </div>
    ${notesHtml}
    <div class="gp-confirm-actions">
      <button class="gp-btn gp-btn-primary gp-btn-sm" id="btnConfirmRunOpt" style="flex:1;">
        Run Optimization
      </button>
      <button class="gp-btn gp-btn-secondary gp-btn-sm" id="btnConfirmKeepTalking">
        Keep Talking
      </button>
    </div>
  `;

  body.appendChild(card);
  const chatBody = document.getElementById("agentChatBody");
  if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;

  const btnRun = card.querySelector("#btnConfirmRunOpt");
  const btnKeep = card.querySelector("#btnConfirmKeepTalking");

  btnRun.addEventListener("click", async () => {
    btnRun.disabled = true;
    btnRun.textContent = "Applying & Solving...";
    
    const finalParams = {
      ...p,
      warehouse_count: parseInt(card.querySelector("#cfgEditP").value) || p.warehouse_count || 3,
      warehouse_capacity: parseInt(card.querySelector("#cfgEditCap").value) || p.warehouse_capacity || 4000,
      max_service_radius_km: parseFloat(card.querySelector("#cfgEditRadius").value) || p.max_service_radius_km || 25.0,
      priority_preset: card.querySelector("#cfgEditPreset").value || p.priority_preset || "cost",
    };

    applyAgentParamsToUi(finalParams);
    toggleAgentDrawer(false);
    showToast("Optimization triggered from Logistics Agent.");
    await runOptimization();
    switchView("viewResults");
  });

  btnKeep.addEventListener("click", () => {
    document.getElementById("agentInput")?.focus();
  });
}

async function sendAgentMessage(userText) {
  if (!userText || !userText.trim() || agentState.isProcessing) return;
  const text = userText.trim();
  
  const inputEl = document.getElementById("agentInput");
  if (inputEl) inputEl.value = "";

  appendAgentMessage(text, "user", "agentSetupContainer");
  agentState.historySetup.push({ role: "user", content: text });

  showThinkingPulse();
  agentState.isProcessing = true;

  try {
    syncUiToAgentParams();
    const res = await fetch("/api/agent/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: agentState.historySetup.slice(-10),
        known_params: agentState.knownParams,
      }),
    });

    const data = await res.json();
    removeThinkingPulse();
    agentState.isProcessing = false;

    if (!res.ok) {
      appendAgentMessage(`Error processing request: ${data.detail || "Server error"}`, "agent", "agentSetupContainer");
      return;
    }

    agentState.historySetup.push({ role: "assistant", content: data.reply });
    appendAgentMessage(data.reply, "agent", "agentSetupContainer");

    if (data.extracted_params) {
      agentState.knownParams = { ...agentState.knownParams, ...data.extracted_params };
    }

    if (data.status === "confirm" && data.confirmation_card) {
      renderConfirmationCard(data);
    }

    if (data.suggested_prompts && data.suggested_prompts.length > 0) {
      renderSuggestedPrompts(data.suggested_prompts);
    }
  } catch (err) {
    removeThinkingPulse();
    agentState.isProcessing = false;
    appendAgentMessage(`Connection error: ${err.message}`, "agent", "agentSetupContainer");
  }
}

async function sendAgentExplainMessage(userText) {
  if (!userText || !userText.trim() || agentState.isProcessing) return;
  const text = userText.trim();

  const inputEl = document.getElementById("agentInput");
  if (inputEl) inputEl.value = "";

  const body = document.getElementById("agentExplainContainer");
  if (!body) return;

  const userBubble = document.createElement("div");
  userBubble.className = "gp-bubble gp-bubble-user";
  userBubble.textContent = text;
  body.appendChild(userBubble);

  agentState.historyExplain.push({ role: "user", content: text });
  showThinkingPulse();
  agentState.isProcessing = true;

  try {
    const pageCtx = gatherPageContext(appState.currentView);
    const res = await fetch("/api/agent/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page: appState.currentView,
        message: text,
        page_context: pageCtx,
        history: agentState.historyExplain.slice(-6),
      }),
    });

    const data = await res.json();
    removeThinkingPulse();
    agentState.isProcessing = false;

    if (!res.ok) {
      const errBubble = document.createElement("div");
      errBubble.className = "gp-bubble gp-bubble-agent";
      errBubble.textContent = `Error: ${data.detail || "Could not generate explanation"}`;
      body.appendChild(errBubble);
      return;
    }

    agentState.historyExplain.push({ role: "assistant", content: data.reply });

    const agentBubble = document.createElement("div");
    agentBubble.className = "gp-bubble gp-bubble-agent";
    agentBubble.style.whiteSpace = "pre-line";
    agentBubble.innerHTML = data.reply
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n\n/g, '<br><br>');
    body.appendChild(agentBubble);

    if (data.suggested_followups && data.suggested_followups.length > 0) {
      const followContainer = document.createElement("div");
      followContainer.className = "gp-quick-prompts";
      followContainer.innerHTML = '<div class="gp-quick-prompts-label">Follow-up Questions:</div>';
      data.suggested_followups.forEach(fq => {
        const chip = document.createElement("button");
        chip.className = "gp-quick-chip";
        chip.textContent = `• ${fq}`;
        chip.addEventListener("click", () => sendAgentExplainMessage(fq));
        followContainer.appendChild(chip);
      });
      body.appendChild(followContainer);
    }

    const chatBody = document.getElementById("agentChatBody");
    if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
  } catch (err) {
    removeThinkingPulse();
    agentState.isProcessing = false;
    const errBubble = document.createElement("div");
    errBubble.className = "gp-bubble gp-bubble-agent";
    errBubble.textContent = `Connection error: ${err.message}`;
    body.appendChild(errBubble);
  }
}

// ============================================================================
// 1. TOAST NOTIFICATIONS & INFEASIBILITY MODAL
// ============================================================================

function showToast(message, type = "success") {
  const toast = document.getElementById("alertToast");
  if (!toast) return;
  toast.className = `gp-toast active ${type}`;
  toast.innerHTML = message;
  setTimeout(() => {
    toast.className = "gp-toast";
  }, 4500);
}

function showErrorModal(title, message, diagnostics = []) {
  const modal = document.getElementById("errorModal");
  document.getElementById("errorModalTitle").textContent = title || "Configuration Infeasible";
  
  let bodyHtml = `<p style="margin-bottom:10px;">${message}</p>`;
  if (diagnostics && diagnostics.length > 0) {
    bodyHtml += '<div style="background:var(--gp-danger-bg); border:1px solid var(--gp-danger-border); border-radius:var(--gp-radius-sm); padding:10px; margin-top:8px;">';
    bodyHtml += '<strong style="color:var(--gp-danger); font-size:12px;">Diagnostics & Causes:</strong><ul style="margin-left:18px; margin-top:4px; font-size:12px;">';
    diagnostics.forEach(d => {
      bodyHtml += `<li style="margin-bottom:2px;">${d}</li>`;
    });
    bodyHtml += '</ul></div>';
  }
  bodyHtml += '<div style="margin-top:12px; font-size:12px; color:var(--gp-text-secondary);"><strong>Suggested Action:</strong> Increase the warehouse count (p), raise site throughput capacity, or expand maximum service radius.</div>';

  document.getElementById("errorModalBody").innerHTML = bodyHtml;
  modal.classList.add("active");
}

// ============================================================================
// 2. VIEW ROUTER (switchView)
// ============================================================================

function switchView(viewId) {
  if (!document.getElementById(viewId)) return;
  appState.currentView = viewId;

  // 1. Update Left-Rail Active State
  document.querySelectorAll(".gp-nav-item").forEach(item => {
    if (item.getAttribute("data-view") === viewId) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });

  // 2. Hide all views and show requested view
  document.querySelectorAll(".gp-view").forEach(v => v.classList.remove("active"));
  document.getElementById(viewId).classList.add("active");

  // 3. Update Header Breadcrumb and Title
  const meta = VIEW_METADATA[viewId] || { breadcrumb: "Workspace", title: "GRIDPOINT" };
  document.getElementById("headerBreadcrumb").textContent = meta.breadcrumb;
  document.getElementById("headerScreenTitle").textContent = meta.title;

  // 4. Update Agent FAB Visibility (Visible only on Dashboard and Network Configuration)
  updateAgentFabVisibility(viewId);

  // 5. Invalidate Map Sizes on View Switch (prevents Leaflet tile render glitches)
  setTimeout(() => {
    if (viewId === "viewResults" && appState.maps.results) {
      appState.maps.results.invalidateSize();
    } else if (viewId === "viewData" && appState.maps.demand) {
      appState.maps.demand.invalidateSize();
    } else if (viewId === "viewAnalytics" && appState.lastTradeoff) {
      renderTradeoffChart(appState.lastTradeoff);
    }
  }, 100);
}

// ============================================================================
// 3. MAP INITIALIZATION (Results Map + Demand Input Map)
// ============================================================================

function initMaps() {
  const defaultCenter = [12.9716, 77.5946];
  const tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const tileAttrib = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

  // Results Map
  const resultsContainer = document.getElementById("resultsMap");
  if (resultsContainer) {
    appState.maps.results = L.map("resultsMap", {
      center: defaultCenter,
      zoom: 11,
      zoomControl: true,
    });
    L.tileLayer(tileUrl, { maxZoom: 19, attribution: tileAttrib }).addTo(appState.maps.results);

    appState.layers.results.candidates.addTo(appState.maps.results);
    appState.layers.results.neighborhoods.addTo(appState.maps.results);
    appState.layers.results.radius.addTo(appState.maps.results);
    appState.layers.results.assignments.addTo(appState.maps.results);
    appState.layers.results.routes.addTo(appState.maps.results);
    appState.layers.results.warehouses.addTo(appState.maps.results);
  }

  // Demand Map (Data Input View)
  const demandContainer = document.getElementById("demandMap");
  if (demandContainer) {
    appState.maps.demand = L.map("demandMap", {
      center: defaultCenter,
      zoom: 11,
      zoomControl: true,
    });
    L.tileLayer(tileUrl, { maxZoom: 19, attribution: tileAttrib }).addTo(appState.maps.demand);

    appState.layers.demand.candidates.addTo(appState.maps.demand);
    appState.layers.demand.neighborhoods.addTo(appState.maps.demand);
  }

  // Layer Visibility Toggles on Results Map
  const chkCand = document.getElementById("chkShowCandidates");
  if (chkCand) {
    chkCand.addEventListener("change", (e) => {
      if (e.target.checked) appState.maps.results.addLayer(appState.layers.results.candidates);
      else appState.maps.results.removeLayer(appState.layers.results.candidates);
    });
  }

  const chkAssign = document.getElementById("chkShowAssignments");
  if (chkAssign) {
    chkAssign.addEventListener("change", (e) => {
      if (e.target.checked) appState.maps.results.addLayer(appState.layers.results.assignments);
      else appState.maps.results.removeLayer(appState.layers.results.assignments);
    });
  }

  const chkRad = document.getElementById("chkShowRadius");
  if (chkRad) {
    chkRad.addEventListener("change", (e) => {
      if (e.target.checked) appState.maps.results.addLayer(appState.layers.results.radius);
      else appState.maps.results.removeLayer(appState.layers.results.radius);
    });
  }

  const chkRts = document.getElementById("chkShowRoutes");
  if (chkRts) {
    chkRts.addEventListener("change", (e) => {
      if (e.target.checked) appState.maps.results.addLayer(appState.layers.results.routes);
      else appState.maps.results.removeLayer(appState.layers.results.routes);
    });
  }
}

// ============================================================================
// 4. HEALTH CHECK & SOLVER STATUS
// ============================================================================

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const textStatus = document.getElementById("textSolverStatus");
    if (data.solver_available) {
      textStatus.textContent = `Solver: ${data.solver} Active`;
    } else {
      textStatus.textContent = "Solver: Heuristic Active";
    }
  } catch (err) {
    console.error("Health check failed:", err);
  }
}

// ============================================================================
// 5. DATA INGESTION & CANONICAL DATASET LOADER
// ============================================================================

function applyCanonicalDataset(data, options = {}) {
  if (!data || !data.preview || data.preview.length === 0) {
    showErrorModal("Dataset Missing", "No valid delivery zone data was provided.");
    return false;
  }

  appState.sessionId = data.session_id || "default";
  appState.neighborhoods = data.preview;
  appState.datasetLoaded = true;
  appState.isSyntheticAi = !!options.isSynthetic;
  appState.datasetType = options.isSynthetic ? "ai_synthetic" : (options.source || "demo");

  updateSyntheticDatasetBadge(appState.isSyntheticAi);
  renderDataInputTable(data.preview);
  renderDemandMap(data.preview);
  updateDashboardStats();
  updateLiveSummary();

  if (options.toastMessage) {
    showToast(options.toastMessage);
  }
  return true;
}

async function loadDemoData() {
  try {
    const res = await fetch("/api/demo-data");
    const data = await res.json();
    applyCanonicalDataset(data, {
      isSynthetic: false,
      source: "demo",
      toastMessage: `Loaded 36 curated Bengaluru delivery zones (${data.total_demand.toLocaleString()} orders/day).`
    });

    // Auto-trigger default optimization (p=3)
    await runOptimization();
  } catch (err) {
    showToast(`Failed to load demo dataset: ${err.message}`, "error");
  }
}

function renderDataInputTable(neighborhoods) {
  const tbody = document.getElementById("tbodyNeighborhoods");
  if (!tbody) return;

  if (!neighborhoods || neighborhoods.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--gp-text-tertiary); padding:20px;">No zones loaded.</td></tr>';
    return;
  }

  tbody.innerHTML = neighborhoods.map(n => `
    <tr>
      <td><span style="font-family:var(--gp-font-family-mono); font-weight:600; font-size:12px;">${n.neighborhood_id}</span></td>
      <td><strong>${n.name}</strong></td>
      <td>${n.daily_orders.toLocaleString()} ord/day</td>
      <td><span style="font-family:var(--gp-font-family-mono); font-size:11px; color:var(--gp-text-secondary);">${n.latitude.toFixed(4)}, ${n.longitude.toFixed(4)}</span></td>
    </tr>
  `).join("");

  document.getElementById("railSessionMeta").textContent = `Dataset: ${neighborhoods.length} zones loaded`;
}

function renderDemandMap(neighborhoods) {
  if (!appState.maps.demand || !neighborhoods || neighborhoods.length === 0) return;

  appState.layers.demand.candidates.clearLayers();
  appState.layers.demand.neighborhoods.clearLayers();

  const lats = neighborhoods.map(n => n.latitude);
  const lons = neighborhoods.map(n => n.longitude);
  appState.maps.demand.fitBounds([
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)]
  ], { padding: [30, 30] });

  const maxDemand = Math.max(...neighborhoods.map(n => n.daily_orders));

  neighborhoods.forEach(n => {
    // Candidate marker
    const cMarker = L.circleMarker([n.latitude, n.longitude], {
      radius: 4,
      fillColor: "#94A3B8",
      color: "#64748B",
      weight: 1,
      opacity: 0.6,
      fillOpacity: 0.3,
    }).bindTooltip(`Candidate Site: <b>${n.name}</b> (${n.neighborhood_id})`);
    appState.layers.demand.candidates.addLayer(cMarker);

    // Demand node
    const radius = 4 + (n.daily_orders / maxDemand) * 10;
    const nMarker = L.circleMarker([n.latitude, n.longitude], {
      radius: radius,
      fillColor: "#3B82F6",
      color: "#2563EB",
      weight: 1.5,
      opacity: 0.9,
      fillOpacity: 0.7,
    }).bindPopup(`
      <div style="font-family:var(--gp-font-family-sans); padding:4px;">
        <div style="font-weight:700; font-size:14px; color:var(--gp-text-primary);">${n.name}</div>
        <div style="font-size:11px; color:var(--gp-text-tertiary); font-family:var(--gp-font-family-mono);">${n.neighborhood_id}</div>
        <hr style="margin:6px 0; border:0; border-top:1px solid var(--gp-border);">
        <div style="font-size:12px; color:var(--gp-text-secondary);">
          <strong>Daily Demand:</strong> ${n.daily_orders.toLocaleString()} orders/day<br>
          <strong>Coordinates:</strong> ${n.latitude.toFixed(4)}, ${n.longitude.toFixed(4)}
        </div>
      </div>
    `);
    appState.layers.demand.neighborhoods.addLayer(nMarker);
  });
}

// ============================================================================
// 6. NETWORK OPTIMIZATION SOLVER (POST /api/optimize)
// ============================================================================

async function runOptimization() {
  if (!appState.neighborhoods || appState.neighborhoods.length === 0) {
    showErrorModal(
      "No Dataset Loaded",
      "No delivery zone dataset is currently loaded in memory. Please load the Bengaluru demo dataset, upload a CSV file, or generate AI synthetic data before running optimization."
    );
    return;
  }

  const isAuto = appState.configMode === "auto";
  const p = parseInt(document.getElementById("inputConfigP")?.value) || 3;
  const pMax = parseInt(document.getElementById("inputConfigPMax")?.value) || 6;
  const cap = parseFloat(document.getElementById("inputConfigCap").value) || 4000;
  const radius = document.getElementById("inputConfigRadius").value ? parseFloat(document.getElementById("inputConfigRadius").value) : null;
  const costKm = parseFloat(document.getElementById("inputCostKm").value) || 1.25;
  const fixedCost = parseFloat(document.getElementById("inputFixedCost").value) || 300;
  const mode = document.getElementById("selectDistanceMode").value || "haversine";
  const includeCvrp = document.getElementById("chkIncludeCvrp").checked || document.getElementById("chkFleetEnableCvrp").checked;

  // Validate candidate availability
  if (isAuto && pMax > appState.neighborhoods.length) {
    showErrorModal(
      "Invalid Parameter Ceiling",
      `Requested maximum warehouse count p_max=${pMax} exceeds total candidate sites (${appState.neighborhoods.length}).`,
      ["You cannot consider more warehouses than available candidate locations. Reduce p_max ceiling or add more zones."]
    );
    return;
  }

  const payload = {
    session_id: appState.sessionId,
    p: p,
    auto_size: isAuto,
    p_max: isAuto ? pMax : null,
    warehouse_capacity: cap,
    radius_max_km: radius,
    cost_per_km: costKm,
    fixed_cost_per_warehouse: fixedCost,
    routing_mode: mode,
    priority_preset: appState.priorityPreset,
    include_cvrp: includeCvrp,
    vehicle_capacity: 250,
    vehicle_fixed_cost: 150.0,
  };

  try {
    const res = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) {
      showErrorModal("Optimization Infeasible", data.detail?.error || "Constraint violation", data.detail?.diagnostics || []);
      return;
    }

    appState.lastOptimize = data;
    appState.explainCache = {};

    renderResultsScreen(data);
    await fetchBaselineComparison();
    await fetchTradeoffCurve();
    updateDashboardStats();

    showToast(`Network Optimized: ${data.p} warehouses serving ${data.assignments.length} delivery zones.`);
  } catch (err) {
    showErrorModal("Network Request Failed", err.message);
  }
}

// ============================================================================
// 7. RENDER RESULTS SCREEN (KPIs, Map, Explainability, Manifest)
// ============================================================================

function renderResultsScreen(data) {
  // 1. Update Assumptions Strip
  const costKm = data.assumptions.cost_per_km || 1.25;
  const fixedLease = data.assumptions.fixed_cost_per_warehouse || 300;
  const rMax = data.assumptions.radius_max_km ? `${data.assumptions.radius_max_km} km` : "No Limit";
  const distMode = data.assumptions.routing_mode === "haversine" ? "Geographic Delivery Distance (Haversine)" : "Road Detour (1.35x Proxy)";

  document.getElementById("resultsAssumptionsStrip").innerHTML = `
    <div><strong>Delivery Cost / km:</strong> $${costKm.toFixed(2)} (Estimated)</div>
    <div><strong>Facility Lease:</strong> $${fixedLease.toFixed(0)} / site / day</div>
    <div><strong>Max Service Radius:</strong> ${rMax}</div>
    <div><strong>Distance Metric:</strong> ${distMode}</div>
    <div><strong>Solver Status:</strong> ${data.solver_message}</div>
  `;

  // 1.5 Update Throughput Co-Dependency & Headroom Banner
  const totalCap = data.total_system_capacity || (data.warehouses ? data.warehouses.reduce((s, w) => s + (w.capacity || w.capacity_ceiling || 0), 0) : 0);
  const totalDem = data.total_system_demand || (data.assignments ? data.assignments.reduce((s, a) => s + (a.daily_orders || 0), 0) : 0);
  const headroom = data.capacity_headroom !== undefined ? data.capacity_headroom : (totalCap - totalDem);
  const headroomPct = data.capacity_headroom_pct !== undefined ? data.capacity_headroom_pct : (totalCap > 0 ? ((totalCap - totalDem) / totalCap * 100) : 0);

  const elThroughput = document.getElementById("resTotalThroughput");
  if (elThroughput) elThroughput.textContent = `${totalCap.toLocaleString()} orders/day`;

  const elDemand = document.getElementById("resTotalDemand");
  if (elDemand) elDemand.textContent = `${totalDem.toLocaleString()} orders/day`;

  const elHeadroom = document.getElementById("resCapacityHeadroom");
  if (elHeadroom) {
    elHeadroom.textContent = `${headroom >= 0 ? '+' : ''}${headroom.toLocaleString()} orders/day`;
    elHeadroom.style.color = headroom >= 0 ? "var(--gp-success)" : "var(--gp-danger)";
  }

  const elHeadroomPct = document.getElementById("resHeadroomPct");
  if (elHeadroomPct) {
    elHeadroomPct.textContent = `${headroomPct.toFixed(1)}% buffer`;
    elHeadroomPct.className = `gp-delta-chip ${headroom >= 0 ? 'gp-delta-positive' : 'gp-delta-negative'}`;
  }

  const elModeBadge = document.getElementById("resModeBadge");
  if (elModeBadge) {
    if (data.auto_size) {
      elModeBadge.textContent = `Auto-Sized (${data.p} Sites Optimal)`;
      elModeBadge.className = "gp-badge gp-badge-optimal";
    } else {
      elModeBadge.textContent = `Manual Mode (Exact p = ${data.p})`;
      elModeBadge.className = "gp-badge gp-badge-estimate";
    }
  }

  const boxSizing = document.getElementById("boxSizingRationale");
  const textSizing = document.getElementById("textSizingRationale");
  if (boxSizing && textSizing) {
    if (data.auto_size && data.sizing_rationale) {
      boxSizing.style.display = "flex";
      textSizing.textContent = data.sizing_rationale;
    } else {
      boxSizing.style.display = "none";
    }
  }

  // 2. Executive KPI Cards
  document.getElementById("kpiCost").textContent = `$${data.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("kpiDistance").innerHTML = `${data.total_weighted_distance_km.toLocaleString(undefined, { maximumFractionDigits: 1 })} <span class="gp-kpi-unit">ord·km</span>`;
  document.getElementById("kpiWarehouses").innerHTML = `${data.warehouses.length} <span class="gp-kpi-unit">sites</span>`;
  document.getElementById("kpiWarehousesBadge").textContent = data.auto_size ? `Auto (${data.p} sites)` : `p = ${data.p}`;
  document.getElementById("kpiSolverStatus").textContent = `Status: ${data.status}`;
  document.getElementById("kpiFastDelivery").textContent = `${data.fast_delivery_coverage_pct.toFixed(1)}%`;
  document.getElementById("kpiMonthlySavings").textContent = `$${data.estimated_monthly_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("kpiCO2").innerHTML = `${data.estimated_co2_kg_per_day.toFixed(1)} <span class="gp-kpi-unit">kg</span>`;
  document.getElementById("kpiCO2Badge").textContent = `${data.co2_reduction_pct.toFixed(1)}%`;

  // 3. Clear & Render Map Layers
  appState.layers.results.warehouses.clearLayers();
  appState.layers.results.assignments.clearLayers();
  appState.layers.results.radius.clearLayers();
  appState.layers.results.routes.clearLayers();
  appState.layers.results.candidates.clearLayers();
  appState.layers.results.neighborhoods.clearLayers();

  const wColorMap = {};
  data.warehouses.forEach((w, idx) => {
    wColorMap[w.warehouse_id] = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
  });

  // Fit Bounds
  if (data.assignments && data.assignments.length > 0) {
    const lats = data.assignments.map(a => a.latitude);
    const lons = data.assignments.map(a => a.longitude);
    appState.maps.results.fitBounds([
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)]
    ], { padding: [40, 40] });
  }

  // Render open warehouses
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
      appState.layers.results.radius.addLayer(radiusCircle);
    }

    // Warehouse Marker
    const wIcon = L.divIcon({
      className: "gp-marker-warehouse-container",
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

    const reqCap = (w.capacity_required !== undefined ? w.capacity_required : w.assigned_demand);
    const ceilCap = (w.capacity_ceiling !== undefined ? w.capacity_ceiling : w.capacity);

    const wMarker = L.marker([w.latitude, w.longitude], { icon: wIcon }).bindPopup(`
      <div style="font-family:var(--gp-font-family-sans); padding:4px;">
        <div style="font-size:11px; color:${color}; font-weight:700; text-transform:uppercase;">Selected Facility</div>
        <div style="font-weight:700; font-size:15px; color:var(--gp-text-primary); margin-top:2px;">${w.name}</div>
        <div style="font-size:11px; color:var(--gp-text-tertiary); font-family:var(--gp-font-family-mono);">${w.warehouse_id}</div>
        <hr style="margin:6px 0; border:0; border-top:1px solid var(--gp-border);">
        <div style="font-size:12px; color:var(--gp-text-secondary); line-height:1.5;">
          <strong>Capacity Required:</strong> ${reqCap.toLocaleString()} orders/day<br>
          <strong>Capacity Ceiling:</strong> ${ceilCap.toLocaleString()} orders/day<br>
          <strong>Capacity Utilization:</strong> ${w.capacity_utilization_pct.toFixed(1)}%<br>
          <strong>Zones Served:</strong> ${w.neighborhoods_count} delivery zones
        </div>
      </div>
    `);
    appState.layers.results.warehouses.addLayer(wMarker);
  });

  // Render spider assignment lines & zone nodes
  data.assignments.forEach(a => {
    const color = wColorMap[a.warehouse_id] || "#3B82F6";
    
    // Assignment Line
    const line = L.polyline(
      [[a.latitude, a.longitude], [a.warehouse_latitude, a.warehouse_longitude]],
      {
        color: color,
        weight: 2,
        opacity: 0.65,
        dashArray: "3, 5",
      }
    ).bindTooltip(`<b>${a.neighborhood_name}</b> &rarr; ${a.warehouse_name}<br>Geographic Distance: ${a.distance_km} km<br>Demand: ${a.daily_orders} orders`);
    appState.layers.results.assignments.addLayer(line);

    // Zone Marker
    const zMarker = L.circleMarker([a.latitude, a.longitude], {
      radius: 6,
      fillColor: color,
      color: "#FFFFFF",
      weight: 1.5,
      opacity: 0.9,
      fillOpacity: 0.85,
    }).bindTooltip(`<b>${a.neighborhood_name}</b> (${a.daily_orders} orders/day)<br>Assigned to: ${a.warehouse_name}`);
    appState.layers.results.neighborhoods.addLayer(zMarker);
  });

  // Tactical CVRP Routes
  const routeToggle = document.getElementById("lblShowRoutes");
  if (data.cvrp_summary && data.cvrp_summary.routes && data.cvrp_summary.routes.length > 0) {
    if (routeToggle) routeToggle.style.display = "flex";
    data.cvrp_summary.routes.forEach((r, idx) => {
      const rColor = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
      if (r.route_coords && r.route_coords.length >= 2) {
        const poly = L.polyline(r.route_coords, {
          color: rColor,
          weight: 3.5,
          opacity: 0.85,
        }).bindTooltip(`Vehicle Tour: <b>${r.vehicle_id}</b> (${r.warehouse_name})<br>Distance: ${r.total_distance_km} km<br>Load: ${r.total_load} / ${r.capacity} (${r.utilization_pct}%)`);
        appState.layers.results.routes.addLayer(poly);
      }
    });
    renderFleetRoutesTable(data.cvrp_summary);
  } else {
    if (routeToggle) routeToggle.style.display = "none";
  }

  // 4. Warehouse Facility Manifest Breakdown Table
  renderWarehouseManifestTable(data.warehouses);

  // 5. Explainability Select Dropdown
  const selectExplain = document.getElementById("selectExplainWarehouse");
  if (selectExplain) {
    selectExplain.innerHTML = "";
    data.warehouses.forEach(w => {
      selectExplain.innerHTML += `<option value="${w.warehouse_id}">${w.name} (${w.assigned_demand.toLocaleString()} ord/day)</option>`;
    });
    if (data.warehouses.length > 0) {
      loadExplainability(data.warehouses[0].warehouse_id);
    }
  }

  // 6. Update Failed Facility Select for Disruption view
  const selectFailed = document.getElementById("selectFailedFacility");
  if (selectFailed) {
    selectFailed.innerHTML = '<option value="">None (All Warehouses Operational)</option>';
    data.warehouses.forEach(w => {
      selectFailed.innerHTML += `<option value="${w.warehouse_id}">${w.name} (${w.warehouse_id})</option>`;
    });
  }

  // 7. Dynamic Demand-Weighting Explainer Box
  updateDemandExplainerBox(data.assignments);
}

// ============================================================================
// 8. BASELINE COMPARISON & BENCHMARK TABLE
// ============================================================================

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
    const tbody = document.getElementById("tbodyBenchmark");
    if (!tbody) return;

    tbody.innerHTML = `
      <tr>
        <td><strong>Simulated Delivery Cost ($/day)</strong></td>
        <td>$${data.baseline.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><strong>$${data.optimized.total_delivery_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></td>
        <td style="color:var(--gp-success); font-weight:700;">-$${Math.abs(data.cost_delta).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><span class="gp-delta-chip gp-delta-positive">${data.cost_pct_change.toFixed(1)}%</span></td>
      </tr>
      <tr>
        <td><strong>Demand-Weighted Delivery Distance (ord·km)</strong></td>
        <td>${data.baseline.weighted_distance_km.toLocaleString()}</td>
        <td><strong>${data.optimized.weighted_distance_km.toLocaleString()}</strong></td>
        <td style="color:var(--gp-success); font-weight:700;">-${Math.abs(data.weighted_distance_delta).toLocaleString()}</td>
        <td><span class="gp-delta-chip gp-delta-positive">${data.weighted_distance_pct_change.toFixed(1)}%</span></td>
      </tr>
      <tr>
        <td><strong>Fixed Facility Lease ($/day)</strong></td>
        <td>$${data.baseline.total_infrastructure_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>$${data.optimized.total_infrastructure_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>+$${(data.optimized.total_infrastructure_cost - data.baseline.total_infrastructure_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><span class="gp-delta-chip gp-delta-neutral">+${((data.optimized.warehouses_count - 1) * 100).toFixed(0)}%</span></td>
      </tr>
      <tr style="background:var(--gp-surface-sunken);">
        <td><strong>Combined System Cost ($/day)</strong></td>
        <td>$${data.baseline.combined_total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td><strong>$${data.optimized.combined_total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></td>
        <td style="color:${data.optimized.combined_total_cost < data.baseline.combined_total_cost ? 'var(--gp-success)' : 'var(--gp-text-primary)'}; font-weight:700;">
          ${data.optimized.combined_total_cost < data.baseline.combined_total_cost ? '-' : '+'}$${Math.abs(data.optimized.combined_total_cost - data.baseline.combined_total_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </td>
        <td><span class="gp-delta-chip ${data.optimized.combined_total_cost < data.baseline.combined_total_cost ? 'gp-delta-positive' : 'gp-delta-neutral'}">
          ${(((data.optimized.combined_total_cost - data.baseline.combined_total_cost) / data.baseline.combined_total_cost) * 100).toFixed(1)}%
        </span></td>
      </tr>
      <tr>
        <td><strong>Estimated Daily CO₂ Footprint (kg)</strong></td>
        <td>${data.baseline.estimated_co2_kg_per_day.toFixed(1)} kg</td>
        <td><strong>${data.optimized.estimated_co2_kg_per_day.toFixed(1)} kg</strong></td>
        <td style="color:var(--gp-success); font-weight:700;">-${Math.abs(data.co2_delta_kg).toFixed(1)} kg</td>
        <td><span class="gp-delta-chip gp-delta-positive">${data.co2_pct_change.toFixed(1)}%</span></td>
      </tr>
      <tr>
        <td><strong>Estimated 30-Day Monthly Savings</strong></td>
        <td>$0.00</td>
        <td colspan="3"><strong style="color:var(--gp-success); font-size:15px;">$${data.estimated_monthly_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong> / month</td>
      </tr>
    `;
  } catch (err) {
    console.error("Baseline comparison failed:", err);
  }
}

// ============================================================================
// 9. TRADE-OFF CURVE (p = 1..5) & CHART.JS
// ============================================================================

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
  const canvas = document.getElementById("tradeoffChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
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
          borderColor: "#1E8E5A",
          backgroundColor: "rgba(30, 142, 90, 0.08)",
          borderWidth: 3,
          pointRadius: 5,
          pointBackgroundColor: "#1E8E5A",
          tension: 0.25,
          fill: true,
        },
        {
          label: "Delivery Cost ($/day)",
          data: delivCosts,
          borderColor: "#3B76ED",
          borderWidth: 2,
          borderDash: [4, 4],
          pointRadius: 4,
          pointBackgroundColor: "#3B76ED",
          tension: 0.25,
        },
        {
          label: "Infrastructure Lease ($/day)",
          data: infraCosts,
          borderColor: "#8A94A0",
          borderWidth: 2,
          borderDash: [2, 2],
          pointRadius: 4,
          pointBackgroundColor: "#8A94A0",
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top", labels: { font: { family: "Plus Jakarta Sans", size: 12 } } },
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

// ============================================================================
// 10. EXPLAINABILITY INTELLIGENCE ("Why this location?")
// ============================================================================

async function loadExplainability(warehouseId) {
  const container = document.getElementById("boxExplainContent");
  if (!container) return;

  container.innerHTML = '<div style="text-align:center; padding:20px; color:var(--gp-text-tertiary);">Computing solver intelligence...</div>';

  try {
    let data = appState.explainCache[warehouseId];
    if (!data) {
      const res = await fetch(`/api/explain/${warehouseId}?session_id=${appState.sessionId}`);
      data = await res.json();
      appState.explainCache[warehouseId] = data;
    }

    let driversHtml = '<table class="gp-table" style="margin-top:8px;"><thead><tr><th>Top Delivery Zone</th><th>Daily Demand</th><th>Geographic Distance</th><th>Order-km Contribution</th></tr></thead><tbody>';
    data.key_demand_drivers.forEach(d => {
      driversHtml += `
        <tr>
          <td><strong>${d.name}</strong> (${d.neighborhood_id})</td>
          <td>${d.daily_orders.toLocaleString()} orders</td>
          <td>${d.distance_km.toFixed(2)} km</td>
          <td><span style="font-family:var(--gp-font-family-mono); color:var(--gp-primary-600);">${d.weighted_ord_km.toLocaleString()} ord·km</span></td>
        </tr>
      `;
    });
    driversHtml += '</tbody></table>';

    let rejectedHtml = '';
    if (data.next_best_rejected) {
      rejectedHtml = `
        <div style="background:var(--gp-surface-sunken); border:1px solid var(--gp-border); border-radius:var(--gp-radius-sm); padding:var(--gp-space-3); margin-top:var(--gp-space-3);">
          <div style="font-weight:700; font-size:13px; color:var(--gp-text-primary);">Runner-Up Candidate in this Sector: ${data.next_best_rejected.name} (${data.next_best_rejected.candidate_id})</div>
          <p style="font-size:12px; color:var(--gp-text-secondary); margin-top:2px;">${data.next_best_rejected.reason_rejected}</p>
          <div style="font-size:11px; font-family:var(--gp-font-family-mono); color:var(--gp-warning); margin-top:4px;">
            Objective Gap: +${data.next_best_rejected.score_gap_weighted_km.toLocaleString()} ord·km higher total travel penalty.
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:var(--gp-space-3); margin-bottom:var(--gp-space-4);">
        <div style="background:var(--gp-surface-sunken); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Assigned Demand</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-text-primary); margin-top:2px;">${data.demand_served.toLocaleString()} ord/day</div>
          <div style="font-size:11px; color:var(--gp-text-tertiary);">${data.demand_pct_of_total}% of citywide volume</div>
        </div>

        <div style="background:var(--gp-surface-sunken); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Capacity Utilization</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-text-primary); margin-top:2px;">${data.capacity_utilization_pct.toFixed(1)}%</div>
          <div style="font-size:11px; color:var(--gp-text-tertiary);">${data.capacity.toLocaleString()} max capacity</div>
        </div>

        <div style="background:var(--gp-surface-sunken); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Average Delivery Radius</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-text-primary); margin-top:2px;">${data.avg_distance_km.toFixed(2)} km</div>
          <div style="font-size:11px; color:var(--gp-text-tertiary);">${data.neighborhoods_served_count} delivery zones served</div>
        </div>

        <div style="background:var(--gp-surface-sunken); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Eliminated Burden</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-success); margin-top:2px;">-${data.burden_eliminated_km.toLocaleString()} ord·km</div>
          <div style="font-size:11px; color:var(--gp-text-tertiary);">vs single-facility centroid</div>
        </div>
      </div>

      <div style="margin-top:var(--gp-space-3);">
        <strong style="font-size:13px; color:var(--gp-text-primary); text-transform:uppercase; letter-spacing:0.03em;">Key Demand Drivers in Assigned Cluster</strong>
        ${driversHtml}
      </div>

      ${rejectedHtml}
    `;
  } catch (err) {
    container.innerHTML = `<div style="color:var(--gp-danger); font-size:13px;">Failed to fetch explainability: ${err.message}</div>`;
  }
}

// ============================================================================
// 11. WAREHOUSE MANIFEST TABLE
// ============================================================================

function renderWarehouseManifestTable(warehouses) {
  const tbody = document.getElementById("tbodyWarehouseManifest");
  if (!tbody) return;

  if (!warehouses || warehouses.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--gp-text-tertiary); padding:20px;">No open facilities.</td></tr>';
    return;
  }

  tbody.innerHTML = warehouses.map(w => {
    const reqCap = (w.capacity_required !== undefined ? w.capacity_required : w.assigned_demand);
    const ceilCap = (w.capacity_ceiling !== undefined ? w.capacity_ceiling : w.capacity);
    return `
    <tr>
      <td><span style="font-family:var(--gp-font-family-mono); font-weight:700;">${w.warehouse_id}</span></td>
      <td><strong>${w.name}</strong></td>
      <td><span style="font-family:var(--gp-font-family-mono); font-weight:700;">${reqCap.toLocaleString()}</span> <span style="font-size:11px; color:var(--gp-text-tertiary);">ord/day</span></td>
      <td><span style="font-family:var(--gp-font-family-mono);">${ceilCap.toLocaleString()}</span> <span style="font-size:11px; color:var(--gp-text-tertiary);">ord/day</span></td>
      <td>
        <div style="display:flex; align-items:center; gap:8px;">
          <div style="flex:1; height:6px; background:var(--gp-surface-sunken); border-radius:3px; overflow:hidden; min-width:60px;">
            <div style="width:${Math.min(100, w.capacity_utilization_pct)}%; height:100%; background:${w.capacity_utilization_pct > 90 ? 'var(--gp-danger)' : 'var(--gp-primary-500)'};"></div>
          </div>
          <span class="gp-delta-chip ${w.capacity_utilization_pct > 90 ? 'gp-delta-warning' : 'gp-delta-positive'}">${w.capacity_utilization_pct.toFixed(1)}%</span>
        </div>
      </td>
      <td>${w.neighborhoods_count} zones</td>
      <td>
        <button class="gp-btn gp-btn-secondary gp-btn-sm" onclick="inspectWarehouseFacility('${w.warehouse_id}')">Inspect</button>
      </td>
    </tr>
  `;
  }).join("");
}

function inspectWarehouseFacility(wId) {
  // Switch to Explainability subtab
  document.querySelector('[data-subtab="subtabExplain"]').click();
  document.getElementById("selectExplainWarehouse").value = wId;
  loadExplainability(wId);
}

// ============================================================================
// 12. DEMAND-WEIGHTING EXPLAINER BOX
// ============================================================================

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

// ============================================================================
// 13. SCENARIO LAB & DISRUPTION SIMULATION (POST /api/scenario)
// ============================================================================

async function runScenarioSimulation(multiplier, failedWid = null, targetContainerId = "boxScenarioResults") {
  const box = document.getElementById(targetContainerId);
  if (!box) return;

  box.innerHTML = '<div style="text-align:center; padding:16px; color:var(--gp-text-tertiary);">Simulating network stress test...</div>';

  const p = parseInt(document.getElementById("inputConfigP").value) || 3;
  const cap = parseFloat(document.getElementById("inputConfigCap").value) || 4000;
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
      box.innerHTML = '<div style="color:var(--gp-danger); font-size:13px;">Scenario is infeasible under current capacity parameters.</div>';
      return;
    }

    appState.lastScenario = data;

    let warningHtml = "";
    if (data.locations_changed) {
      warningHtml = `<div style="background:var(--gp-warning-bg); border:1px solid var(--gp-warning-border); padding:8px 12px; border-radius:var(--gp-radius-sm); color:var(--gp-warning); font-weight:700; margin-bottom:10px; font-size:13px;">
        ⚠️ Facility Topology Shifted: Warehouse locations were dynamically reconfigured to maintain service feasibility.
      </div>`;
    }

    box.innerHTML = `
      ${warningHtml}
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:var(--gp-space-3); margin-bottom:var(--gp-space-3);">
        <div style="background:var(--gp-surface); border:1px solid var(--gp-border); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Scenario Delivery Cost</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-text-primary); margin-top:2px;">$${data.scenario_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          <div style="font-size:11px; color:${data.cost_pct_change > 0 ? 'var(--gp-danger)' : 'var(--gp-success)'}; font-weight:700; margin-top:2px;">
            ${data.cost_pct_change > 0 ? '+' : ''}${data.cost_pct_change.toFixed(1)}% vs baseline
          </div>
        </div>

        <div style="background:var(--gp-surface); border:1px solid var(--gp-border); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Weighted Distance</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-text-primary); margin-top:2px;">${data.scenario_weighted_distance.toLocaleString()} ord·km</div>
          <div style="font-size:11px; color:var(--gp-text-tertiary);">${data.weighted_distance_pct_change.toFixed(1)}% change</div>
        </div>

        <div style="background:var(--gp-surface); border:1px solid var(--gp-border); padding:var(--gp-space-3); border-radius:var(--gp-radius-sm);">
          <div style="font-size:11px; color:var(--gp-text-tertiary); text-transform:uppercase; font-weight:600;">Active Warehouses</div>
          <div style="font-size:18px; font-weight:700; color:var(--gp-text-primary); margin-top:2px;">${data.scenario_warehouses.length} sites</div>
          <div style="font-size:11px; color:var(--gp-text-tertiary);">${data.scenario_warehouses.join(", ")}</div>
        </div>
      </div>

      <div style="font-size:12px; color:var(--gp-text-secondary); line-height:1.5;">
        ${data.diagnostics.length > 0 ? data.diagnostics.join("<br>") : "All 36 delivery zones remain 100% serviceable within capacity."}
      </div>
    `;

    showToast(`Simulation complete: ${data.scenario_name}`);
  } catch (err) {
    box.innerHTML = `<div style="color:var(--gp-danger); font-size:13px;">Scenario execution failed: ${err.message}</div>`;
  }
}

// ============================================================================
// 14. CVRP FLEET ROUTES TABLE
// ============================================================================

function renderFleetRoutesTable(cvrp) {
  const tbody = document.getElementById("tbodyFleetRoutes");
  if (!tbody) return;

  if (!cvrp || !cvrp.routes || cvrp.routes.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--gp-text-tertiary);">No active CVRP routes.</td></tr>';
    return;
  }

  tbody.innerHTML = cvrp.routes.map(r => `
    <tr>
      <td><span style="font-family:var(--gp-font-family-mono); font-weight:700; color:var(--gp-primary-600);">${r.vehicle_id}</span></td>
      <td><strong>${r.warehouse_name}</strong></td>
      <td style="font-size:12px; max-width:280px;">${r.stop_names.join(" &rarr; ")}</td>
      <td>${r.total_distance_km.toFixed(2)} km</td>
      <td>${r.total_load.toLocaleString()} / ${r.capacity.toLocaleString()} orders</td>
      <td>
        <span class="gp-delta-chip ${r.utilization_pct > 80 ? 'gp-delta-positive' : 'gp-delta-neutral'}">${r.utilization_pct.toFixed(1)}%</span>
      </td>
    </tr>
  `).join("");
}

// ============================================================================
// 15. DASHBOARD STATS & LIVE SUMMARY UPDATE
// ============================================================================

function updateDashboardStats() {
  const zonesCount = appState.neighborhoods.length || 36;
  const totalDem = appState.neighborhoods.reduce((acc, n) => acc + (n.daily_orders || 0), 0) || 10240;
  const p = parseInt(document.getElementById("inputConfigP").value) || 3;

  document.getElementById("dashKpiZones").textContent = zonesCount;
  document.getElementById("dashKpiDemand").textContent = totalDem.toLocaleString();
  document.getElementById("dashKpiP").textContent = p;

  if (appState.lastCompare) {
    document.getElementById("dashKpiSavings").textContent = `$${appState.lastCompare.estimated_monthly_savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}

function updateLiveSummary() {
  const isAuto = appState.configMode === "auto";
  const cap = parseFloat(document.getElementById("inputConfigCap").value) || 4000;
  const radiusVal = document.getElementById("inputConfigRadius").value;
  const nZones = appState.neighborhoods.length || 36;
  let radiusText = radiusVal ? ` within <strong>${radiusVal} km</strong> radius` : "";
  const box = document.getElementById("configLiveSummaryText");
  if (!box) return;

  if (isAuto) {
    const pMax = parseInt(document.getElementById("inputConfigPMax")?.value) || 6;
    if (appState.lastOptimize && appState.lastOptimize.auto_size) {
      box.innerHTML = `The lowest-cost network uses <strong>${appState.lastOptimize.p} warehouses</strong> (from up to ${pMax} considered) serving <strong>${nZones} delivery zones</strong>.`;
    } else {
      box.innerHTML = `Choosing the lowest-cost network of up to <strong>${pMax} warehouses</strong> to minimize total cost (delivery transit + facility leases)${radiusText}.`;
    }
  } else {
    const p = parseInt(document.getElementById("inputConfigP")?.value) || 3;
    const totalCap = p * cap;
    box.innerHTML = `You are planning a <strong>${p}-warehouse</strong> network serving <strong>${nZones} delivery zones</strong> with <strong>${totalCap.toLocaleString()} orders/day</strong> combined capacity${radiusText}.`;
  }
}

// ============================================================================
// 16. EVENT LISTENERS & SETUP
// ============================================================================

function setupEventListeners() {
  // 1. Navigation items (Left Rail)
  document.querySelectorAll(".gp-nav-item").forEach(item => {
    item.addEventListener("click", () => {
      const viewId = item.getAttribute("data-view");
      if (viewId) switchView(viewId);
    });
  });

  // 2. Brand Box Logo click -> Dashboard
  document.getElementById("brandHomeBtn").addEventListener("click", () => switchView("viewDashboard"));

  // 3. Landing Page CTAs
  document.getElementById("btnLandingLoadDemo").addEventListener("click", async () => {
    await loadDemoData();
    switchView("viewResults");
  });
  document.getElementById("btnLandingGoData").addEventListener("click", () => switchView("viewData"));

  // 4. Dashboard Quick Action Cards & Buttons
  document.querySelectorAll("[data-jump]").forEach(el => {
    el.addEventListener("click", () => {
      const target = el.getAttribute("data-jump");
      if (target) switchView(target);
    });
  });
  document.getElementById("btnDashQuickData").addEventListener("click", () => switchView("viewData"));
  document.getElementById("btnDashQuickOptimize").addEventListener("click", async () => {
    await runOptimization();
    switchView("viewResults");
  });

  // 5. Header Bar Global Actions
  document.getElementById("btnGlobalLoadDemo").addEventListener("click", async () => {
    await loadDemoData();
    switchView("viewResults");
  });
  document.getElementById("btnGlobalOptimize").addEventListener("click", async () => {
    await runOptimization();
    switchView("viewResults");
  });

  // 6. Data Input View Actions
  document.getElementById("btnDataLoadDemo").addEventListener("click", loadDemoData);

  // CSV File Upload
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

      applyCanonicalDataset(data, {
        isSynthetic: false,
        source: "csv",
        toastMessage: `Uploaded ${data.neighborhood_count} zones (${data.total_demand.toLocaleString()} orders/day).`
      });
      await runOptimization();
    } catch (err) {
      showErrorModal("Upload Failed", err.message);
    }
  });

  // Manual JSON Modal
  const modalManual = document.getElementById("manualEntryModal");
  document.getElementById("btnDataRawJson").addEventListener("click", () => {
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
      applyCanonicalDataset(data, {
        isSynthetic: false,
        source: "manual",
        toastMessage: `Applied ${data.neighborhood_count} zones.`
      });
      modalManual.classList.remove("active");
      await runOptimization();
    } catch (err) {
      alert(`Invalid JSON format: ${err.message}`);
    }
  });

  // 6.5 AI Synthetic Data Generator (Phase 3)
  const btnDataAIGen = document.getElementById("btnDataAIGenerate");
  if (btnDataAIGen) {
    btnDataAIGen.addEventListener("click", () => {
      toggleAgentDrawer(true, "synthetic");
    });
  }

  const inputSynthZones = document.getElementById("inputSynthZones");
  if (inputSynthZones) {
    inputSynthZones.addEventListener("input", (e) => {
      const valEl = document.getElementById("valSynthZones");
      if (valEl) valEl.textContent = `${e.target.value} zones`;
    });
  }

  const btnCancelSynth = document.getElementById("btnCancelSynthetic");
  if (btnCancelSynth) {
    btnCancelSynth.addEventListener("click", () => {
      setAgentMode("setup");
    });
  }

  const btnConfirmSynth = document.getElementById("btnConfirmGenerateSynthetic");
  if (btnConfirmSynth) {
    btnConfirmSynth.addEventListener("click", async () => {
      const zoneCount = parseInt(document.getElementById("inputSynthZones")?.value) || 50;
      const pattern = document.getElementById("selectSynthPattern")?.value || "clustered";
      const region = document.getElementById("selectSynthRegion")?.value || "bengaluru";

      btnConfirmSynth.disabled = true;
      btnConfirmSynth.textContent = "Generating & Validating...";

      try {
        const res = await fetch("/api/agent/generate-synthetic-data", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            zone_count: zoneCount,
            pattern_hint: pattern,
            city_hint: region,
            session_id: appState.sessionId,
          }),
        });

        const data = await res.json();
        btnConfirmSynth.disabled = false;
        btnConfirmSynth.textContent = "Generate Synthetic Data";

        if (!res.ok) {
          showErrorModal("Synthetic Generation Error", data.detail?.error || "Generation failed", data.detail?.errors || []);
          return;
        }

        applyCanonicalDataset(data, {
          isSynthetic: true,
          source: "ai_synthetic",
          toastMessage: `Generated & validated ${data.neighborhood_count} synthetic zones (${data.total_demand.toLocaleString()} orders/day) labeled [AI-Generated Synthetic Dataset].`
        });

        toggleAgentDrawer(false);
        await runOptimization();
        switchView("viewResults");
      } catch (err) {
        btnConfirmSynth.disabled = false;
        btnConfirmSynth.textContent = "Generate Synthetic Data";
        showErrorModal("Generation Failed", err.message);
      }
    });
  }

  // 7. Configuration View Controls & Mode Switcher
  const btnModeMan = document.getElementById("btnConfigModeManual");
  const btnModeAut = document.getElementById("btnConfigModeAuto");
  const boxManualP = document.getElementById("containerManualP");
  const boxAutoPMax = document.getElementById("containerAutoPMax");

  if (btnModeMan && btnModeAut) {
    btnModeMan.addEventListener("click", () => {
      appState.configMode = "manual";
      btnModeMan.classList.add("active");
      btnModeAut.classList.remove("active");
      if (boxManualP) boxManualP.style.display = "flex";
      if (boxAutoPMax) boxAutoPMax.style.display = "none";
      updateLiveSummary();
    });

    btnModeAut.addEventListener("click", () => {
      appState.configMode = "auto";
      btnModeAut.classList.add("active");
      btnModeMan.classList.remove("active");
      if (boxManualP) boxManualP.style.display = "none";
      if (boxAutoPMax) {
        boxAutoPMax.style.display = "flex";
        const sliderPMax = document.getElementById("inputConfigPMax");
        if (sliderPMax && appState.neighborhoods.length > 0) {
          sliderPMax.max = Math.max(1, appState.neighborhoods.length);
        }
      }
      updateLiveSummary();
    });
  }

  const inputP = document.getElementById("inputConfigP");
  if (inputP) {
    inputP.addEventListener("input", (e) => {
      document.getElementById("valConfigP").textContent = `${e.target.value} sites`;
      updateLiveSummary();
      updateDashboardStats();
      agentState.knownParams.warehouse_count = parseInt(e.target.value) || 3;
    });
  }

  const inputPMax = document.getElementById("inputConfigPMax");
  if (inputPMax) {
    inputPMax.addEventListener("input", (e) => {
      document.getElementById("valConfigPMax").textContent = `${e.target.value} sites`;
      updateLiveSummary();
    });
  }

  const inputCap = document.getElementById("inputConfigCap");
  inputCap.addEventListener("input", (e) => {
    document.getElementById("valConfigCap").textContent = `${Number(e.target.value).toLocaleString()} orders/day`;
    updateLiveSummary();
    agentState.knownParams.warehouse_capacity = parseInt(e.target.value) || 4000;
  });

  const inputRad = document.getElementById("inputConfigRadius");
  inputRad.addEventListener("input", (e) => {
    document.getElementById("valConfigRadius").textContent = e.target.value ? `${e.target.value} km` : "No Limit";
    updateLiveSummary();
    agentState.knownParams.max_service_radius_km = parseFloat(e.target.value) || 25.0;
  });

  // Priority Presets
  document.querySelectorAll(".gp-preset-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".gp-preset-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      appState.priorityPreset = pill.getAttribute("data-preset");
      agentState.knownParams.priority_preset = appState.priorityPreset;
    });
  });

  document.getElementById("btnConfigRunOptimization").addEventListener("click", async () => {
    await runOptimization();
    switchView("viewResults");
  });

  // 7.5 Conversational Logistics Agent & Explain Mode (Phases 2, 3 & 4)
  const btnOpenAgent = document.getElementById("btnOpenAgentDrawer");
  if (btnOpenAgent) {
    btnOpenAgent.addEventListener("click", () => toggleAgentDrawer(true));
  }

  const btnCloseAgent = document.getElementById("btnCloseAgentDrawer");
  if (btnCloseAgent) {
    btnCloseAgent.addEventListener("click", () => toggleAgentDrawer(false));
  }

  const backdropAgent = document.getElementById("agentDrawerBackdrop");
  if (backdropAgent) {
    backdropAgent.addEventListener("click", () => toggleAgentDrawer(false));
  }

  // Drawer Mode Switcher Buttons
  const btnModeSetup = document.getElementById("btnModeSetup");
  if (btnModeSetup) {
    btnModeSetup.addEventListener("click", () => setAgentMode("setup"));
  }

  const btnModeExplain = document.getElementById("btnModeExplain");
  if (btnModeExplain) {
    btnModeExplain.addEventListener("click", () => setAgentMode("explain"));
  }

  // Header & In-Screen Explain Buttons
  const btnHeaderExplain = document.getElementById("btnHeaderExplain");
  if (btnHeaderExplain) {
    btnHeaderExplain.addEventListener("click", () => {
      toggleAgentDrawer(true, "explain");
    });
  }

  document.querySelectorAll(".gp-btn-explain-screen").forEach(btn => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-explain-view");
      if (view && view !== appState.currentView) {
        switchView(view);
      }
      toggleAgentDrawer(true, "explain");
    });
  });

  const btnSendAgent = document.getElementById("btnAgentSend");
  const inputAgent = document.getElementById("agentInput");

  if (btnSendAgent && inputAgent) {
    const handleSend = () => {
      const val = inputAgent.value;
      if (!val || !val.trim()) return;
      if (agentState.mode === "explain") {
        sendAgentExplainMessage(val);
      } else {
        sendAgentMessage(val);
      }
    };

    btnSendAgent.addEventListener("click", handleSend);

    inputAgent.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
  }

  // Quick Chips in Initial Agent Setup State
  document.querySelectorAll("#agentQuickPrompts .gp-quick-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const promptText = chip.getAttribute("data-prompt");
      if (promptText) sendAgentMessage(promptText);
    });
  });

  // Quick Chips in Initial Agent Explain State
  document.querySelectorAll("#agentExplainQuickPrompts [data-explain-q]").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-explain-q");
      if (q) sendAgentExplainMessage(q);
    });
  });

  // 8. Results View Subtabs
  document.querySelectorAll(".gp-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".gp-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".gp-tab-pane").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const tabId = btn.getAttribute("data-subtab");
      const targetPane = document.getElementById(tabId);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Explainability Warehouse Select Dropdown
  document.getElementById("selectExplainWarehouse").addEventListener("change", (e) => {
    loadExplainability(e.target.value);
  });

  // 9. Scenario Lab Presets
  document.getElementById("cardScenarioNormal").addEventListener("click", (e) => {
    document.querySelectorAll(".gp-scenario-card").forEach(c => c.classList.remove("active"));
    document.getElementById("cardScenarioNormal").classList.add("active");
    runScenarioSimulation(1.0, null, "boxScenarioResults");
  });
  document.getElementById("cardScenarioWeekend").addEventListener("click", (e) => {
    document.querySelectorAll(".gp-scenario-card").forEach(c => c.classList.remove("active"));
    document.getElementById("cardScenarioWeekend").classList.add("active");
    runScenarioSimulation(1.2, null, "boxScenarioResults");
  });
  document.getElementById("cardScenarioFestival").addEventListener("click", (e) => {
    document.querySelectorAll(".gp-scenario-card").forEach(c => c.classList.remove("active"));
    document.getElementById("cardScenarioFestival").classList.add("active");
    runScenarioSimulation(1.5, null, "boxScenarioResults");
  });

  // 10. Disruption View Simulation
  document.getElementById("btnSimulateOutage").addEventListener("click", () => {
    const failedWid = document.getElementById("selectFailedFacility").value || null;
    runScenarioSimulation(1.0, failedWid, "boxDisruptionResults");
  });

  // 11. Tactical Fleet CVRP Solve Button
  document.getElementById("btnFleetRecompute").addEventListener("click", async () => {
    document.getElementById("chkIncludeCvrp").checked = true;
    document.getElementById("chkFleetEnableCvrp").checked = true;
    await runOptimization();
    switchView("viewFleet");
  });

  // Infeasibility Modal Close
  const modalError = document.getElementById("errorModal");
  document.getElementById("btnErrorModalClose").addEventListener("click", () => modalError.classList.remove("active"));
  document.getElementById("btnErrorModalOk").addEventListener("click", () => modalError.classList.remove("active"));
}

// ============================================================================
// 17. ONLOAD INITIALIZATION
// ============================================================================

window.addEventListener("DOMContentLoaded", async () => {
  initMaps();
  setupEventListeners();
  await checkHealth();
  await loadDemoData();
});
