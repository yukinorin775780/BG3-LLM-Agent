/**
 * director-trace.js
 * AI Director route-chain visualization.
 * Exposed on window.BG3DirectorTrace.
 */
(() => {
  "use strict";

  let currentState = "idle";
  let traceTimers = [];
  let idleTimer = null;
  let transitionToken = 0;
  let pendingStartedAt = 0;
  let lastNodes = [];
  const TRACE_STEP_MS = 240;

  const CHAIN = Object.freeze([
    ["player_input", "Player Input", "narrative command"],
    ["dm_router", "DM Router", "intent routing"],
    ["actor_view_filter", "ActorView Filter", "memory isolation"],
    ["actor_runtime", "Actor Runtime / Party Coordinator", "party turn arbitration"],
    ["domain_event", "DomainEvent", "event contracts"],
    ["event_drain", "EventDrain", "state write-back"],
    ["ui_events", "UI Events", "HUD projection"],
  ]);

  const NODE_DISPLAY = Object.freeze(
    CHAIN.reduce((acc, [id, label, subtitle]) => {
      acc[id] = { label, subtitle };
      return acc;
    }, {})
  );

  const ALIASES = Object.freeze({
    input_processing: "player_input",
    input_node: "player_input",
    dm_analysis: "dm_router",
    dm_node: "dm_router",
    mechanics_processing: "domain_event",
    mechanics_node: "domain_event",
    dialogue_processing: "actor_runtime",
    dialogue_node: "actor_runtime",
    generation: "ui_events",
    generation_node: "ui_events",
    actor_view: "actor_view_filter",
    party_coordinator: "actor_runtime",
    party_turn_coordinator: "actor_runtime",
    eventdrain: "event_drain",
    ui_event: "ui_events",
  });

  let els = null;

  function safeObj(value) {
    return value && typeof value === "object" ? value : {};
  }

  function safeArr(value) {
    return Array.isArray(value) ? value : [];
  }

  function normalizeId(value) {
    return String(value || "").trim().toLowerCase();
  }

  function normalizeNodeName(name) {
    const n = normalizeId(name);
    return ALIASES[n] || n;
  }

  function nowMs() {
    return typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
  }

  function cacheEls() {
    if (els && document.body.contains(els.panel)) return;
    els = {
      panel: document.getElementById("director-trace-panel"),
      nodeTimeline: document.getElementById("director-node-timeline"),
      stateIndicator: document.getElementById("director-state-indicator"),
      fallback: document.getElementById("director-fallback-reason"),
    };
  }

  function ensureTimeline() {
    cacheEls();
    if (!els.nodeTimeline) return;
    els.nodeTimeline.innerHTML = "";
    CHAIN.forEach(([id, label, subtitle]) => {
      const item = document.createElement("li");
      item.dataset.node = id;
      item.className = "director-chain-node node-status--idle";
      item.innerHTML =
        '<div class="node-copy"><strong></strong><small></small>' +
        '<span class="node-io node-input"></span><span class="node-io node-output"></span></div>' +
        '<div class="node-meta"><span class="node-status">idle</span><span class="node-timing">--ms</span></div>';
      item.querySelector("strong").textContent = label;
      item.querySelector("small").textContent = subtitle;
      els.nodeTimeline.appendChild(item);
    });
  }

  function ensureFallbackSlot() {
    cacheEls();
    if (!els.panel || els.fallback) return;
    const slot = document.createElement("div");
    slot.id = "director-fallback-reason";
    slot.className = "director-fallback-reason is-hidden";
    const header = els.panel.querySelector(".xray-header");
    if (header) header.appendChild(slot);
    els.fallback = slot;
  }

  function clearTraceAnimation() {
    traceTimers.forEach((id) => window.clearTimeout(id));
    traceTimers = [];
  }

  function clearIdleTimer() {
    if (idleTimer) window.clearTimeout(idleTimer);
    idleTimer = null;
  }

  function updateStateIndicator(text, stateClass) {
    cacheEls();
    if (!els.stateIndicator) return;
    els.stateIndicator.textContent = text;
    els.stateIndicator.className = "director-state-indicator director-state--" + stateClass;
  }

  function statusForNode(activeNodes, activeNode, nodeId) {
    if (!activeNodes.includes(nodeId)) return "skipped";
    if (activeNode === nodeId) return "active";
    if (activeNodes.indexOf(nodeId) < activeNodes.indexOf(activeNode)) return "done";
    return "pending";
  }

  function timingText(ms, estimated) {
    const n = Number(ms);
    if (!Number.isFinite(n) || n < 0) return "--ms";
    return Math.round(n) + "ms" + (estimated ? " client-est." : "");
  }

  function timingClass(ms) {
    const n = Number(ms);
    if (!Number.isFinite(n)) return "";
    if (n <= 120) return "node-timing--fast";
    if (n <= 450) return "node-timing--medium";
    return "node-timing--slow";
  }

  function applyNodeStates(activeNodes, activeNode, details = {}) {
    cacheEls();
    if (!els.nodeTimeline) return;
    els.nodeTimeline.querySelectorAll("li[data-node]").forEach((item) => {
      const node = normalizeNodeName(item.dataset.node);
      const status = statusForNode(activeNodes, activeNode, node);
      const detail = safeObj(details[node]);
      item.classList.toggle("is-active", status === "active");
      item.classList.toggle("is-visited", status === "done");
      item.classList.toggle("is-skipped", status === "skipped");
      item.classList.toggle("is-agent-signal", detail.signal === "agent_signal");
      item.classList.remove("node-status--idle", "node-status--pending", "node-status--active", "node-status--done", "node-status--skipped");
      item.classList.add("node-status--" + status);
      const statusEl = item.querySelector(".node-status");
      const timingEl = item.querySelector(".node-timing");
      const inputEl = item.querySelector(".node-input");
      const outputEl = item.querySelector(".node-output");
      if (statusEl) statusEl.textContent = status;
      if (timingEl) {
        timingEl.textContent = timingText(detail.ms, detail.estimated !== false);
        timingEl.classList.remove("node-timing--fast", "node-timing--medium", "node-timing--slow");
        const klass = timingClass(detail.ms);
        if (klass) timingEl.classList.add(klass);
      }
      if (inputEl) {
        inputEl.textContent = detail.input ? "in: " + detail.input : "";
        inputEl.classList.toggle("is-empty", !detail.input);
      }
      if (outputEl) {
        outputEl.textContent = detail.output ? "out: " + detail.output : "";
        outputEl.classList.toggle("is-empty", !detail.output);
      }
    });
  }

  function scheduleAutoIdle(token, delayMs) {
    clearIdleTimer();
    idleTimer = window.setTimeout(() => {
      if (token !== transitionToken) return;
      setIdle();
    }, Math.max(360, Number(delayMs) || 1500));
  }

  function extractFallbackReason(data) {
    const payload = safeObj(data);
    const gameState = safeObj(payload.game_state || payload.gameState || {});
    const intent = safeObj(gameState.intent_context || payload.intent_context || {});
    return String(payload.fallback_reason || intent.fallback_reason || payload._fallback_reason || "").trim();
  }

  function updateFallback(reason) {
    ensureFallbackSlot();
    if (!els.fallback) return;
    els.fallback.textContent = reason ? "fallback_reason: " + reason : "";
    els.fallback.classList.toggle("is-hidden", !reason);
  }

  function eventTypes(data, providedEvents) {
    const events = safeArr(providedEvents).length
      ? safeArr(providedEvents)
      : safeArr(data && data.ui_events);
    return events.map((event) => normalizeId(safeObj(event).type)).filter(Boolean);
  }

  function textBlob(data, userLine, intent) {
    const payload = safeObj(data);
    return [
      userLine,
      intent,
      safeArr(payload.journal_events).join(" "),
      JSON.stringify(payload.latest_roll || {}),
      JSON.stringify(payload.combat_state || {}),
      JSON.stringify(payload.game_state || {}),
    ].join(" ");
  }

  function summarizeInput(userLine, intent, data) {
    const payload = safeObj(data);
    const gameState = safeObj(payload.game_state || {});
    const target = safeObj(gameState.intent_context).action_target || payload.target || "";
    const raw = String(userLine || intent || "narrative event").trim();
    const clipped = raw.length > 34 ? raw.slice(0, 31) + "..." : raw;
    return target && !clipped.includes(target) ? clipped + " -> " + target : clipped;
  }

  function summarizeDomain(data, events, blob) {
    const parts = [];
    const types = new Set(eventTypes(data, events));
    if (/memory|记忆|actor_runtime_state|memory_notes/i.test(blob) || types.has("memory_added")) parts.push("memory_update x" + Math.max(1, (blob.match(/memory_notes|记忆/g) || []).length));
    if (/item|transfer|获得|搜刮|heavy_iron_key|lab_key|钥匙/i.test(blob) || types.has("item_gained")) parts.push("item_transfer");
    if (types.has("companion_guidance")) parts.push("companion_guidance");
    if (types.has("negotiation_leverage") || /\[交涉筹码\]|diary_evidence|gribbo_elixir_truth/i.test(blob)) parts.push("negotiation_leverage");
    if (types.has("trap_insight") || /\[陷阱感知\]|gas_trap_1.*revealed|poison_trap_revealed/i.test(blob)) parts.push("trap_reveal");
    if (types.has("trap_disarmed") || /\[陷阱解除\]|gas_trap_1.*disabled|poison_trap_disarmed/i.test(blob)) parts.push("trap_disarmed");
    if (types.has("trap_triggered") || /\[毒气陷阱\]|gas_trap_1.*triggered|poisoned|中毒/i.test(blob)) parts.push("trap_triggered");
    const aff = blob.match(/affection[^\d+\-]*([+\-]\s*\d+)/i) || blob.match(/好感度?\s*([+\-]\s*\d+)/);
    if (aff) parts.push("affection " + aff[1].replace(/\s/g, ""));
    if (/combat_active|initiative_order|战斗|hostile|敌对/i.test(blob)) parts.push("combat/hostility");
    if (/demo_cleared|DEMO CLEARED/i.test(blob)) parts.push("completion");
    return parts.join(", ") || "domain patch";
  }

  function summarizeUi(events, blob) {
    const types = new Set(eventTypes({}, events));
    const out = [];
    if (types.has("roll_result") || /latest_roll|检定|掷骰/i.test(blob)) out.push("Dice Card");
    if (types.has("memory_added") || /记忆|memory/i.test(blob)) out.push("Memory Card");
    if (types.has("item_gained") || /获得|已入包|heavy_iron_key|lab_key/i.test(blob)) out.push("Item Toast");
    if (types.has("affection_delta") || /affection|好感/i.test(blob)) out.push("Affection Chip");
    if (types.has("companion_guidance") || /\[队友建议\]/i.test(blob)) out.push("Guidance Card");
    if (types.has("negotiation_leverage") || /\[交涉筹码\]/i.test(blob)) out.push("Leverage Card");
    if (types.has("trap_insight") || /\[陷阱感知\]/i.test(blob)) out.push("Trap Insight Card");
    if (types.has("trap_disarmed") || /\[陷阱解除\]/i.test(blob)) out.push("Trap Disarmed Card");
    if (types.has("trap_triggered") || /\[毒气陷阱\]|poisoned|中毒/i.test(blob)) out.push("Trap Triggered Card");
    if (types.has("demo_cleared") || /demo_cleared|DEMO CLEARED/i.test(blob)) out.push("Demo Banner");
    if (types.has("trap_discovered") || types.has("trap_triggered") || /陷阱|trap/i.test(blob)) out.push("Trap HUD");
    return out.join(", ") || "HUD events";
  }

  function estimateTimings(nodes, timings) {
    const map = safeObj(timings);
    const elapsed = pendingStartedAt ? Math.max(20, nowMs() - pendingStartedAt) : nodes.length * 80;
    const slice = elapsed / Math.max(1, nodes.length);
    const out = {};
    nodes.forEach((node, index) => {
      const real = Number(map[node]);
      out[node] = {
        ms: Number.isFinite(real) ? Math.round(real) : Math.round(slice * (0.72 + index * 0.08)),
        estimated: !Number.isFinite(real),
      };
    });
    return out;
  }

  function buildTraceNodes(data, options = {}) {
    const opts = safeObj(options);
    const payload = safeObj(data);
    const events = safeArr(opts.uiEvents || opts.events);
    const gameState = safeObj(payload.game_state || payload.gameState || {});
    const explicit = normalizeNodeName(payload.last_node || gameState.last_node || gameState.current_node || "");
    if (explicit === "dm_router") return ["player_input", "dm_router"];
    if (explicit === "actor_view_filter") return ["player_input", "dm_router", "actor_view_filter"];
    if (explicit === "actor_runtime") return ["player_input", "dm_router", "actor_view_filter", "actor_runtime"];
    if (explicit === "domain_event") return ["player_input", "dm_router", "actor_view_filter", "actor_runtime", "domain_event"];
    if (explicit === "event_drain") return ["player_input", "dm_router", "actor_view_filter", "actor_runtime", "domain_event", "event_drain"];
    const blob = textBlob(payload, opts.userLine, opts.intent);
    const intentKey = normalizeId(opts.intent || safeObj(gameState.intent_context).fallback_intent || "");
    const isDiaryRead = intentKey === "read" && /necromancer_diary|diary|日记|读日记|阅读日记/i.test(blob);
    const isGribboDiaryNegotiation =
      /(chat|start_dialogue|dialogue_reply)/i.test(intentKey)
      && /gribbo|格里布|格里波|地精|boss/i.test(blob)
      && /diary|日记|药剂|灵药|死灵|实验|解药|钥匙|真相|gribbo_elixir_truth|diary_negotiation/i.test(blob);
    if (isDiaryRead || isGribboDiaryNegotiation) {
      return ["player_input", "dm_router", "actor_view_filter", "actor_runtime", "domain_event", "event_drain", "ui_events"];
    }
    const nodes = ["player_input", "dm_router", "actor_view_filter"];
    const types = eventTypes(payload, events);
    const hasTrapSignal = types.some((type) => ["trap_insight", "trap_disarmed", "trap_triggered"].includes(type))
      || /\[陷阱感知\]|\[陷阱解除\]|\[毒气陷阱\]|gas_trap_1|poison_trap/i.test(blob);
    const needsParty = /gribbo|astarion|dialogue|party|好感|affection|combat|initiative|台词|对话/i.test(blob) || types.includes("trap_insight");
    const needsDomain = /memory|记忆|item|transfer|获得|搜刮|flag|demo_cleared|combat|hostile|affection|状态|status|EventDrain|\[交涉筹码\]/i.test(blob)
      || hasTrapSignal
      || types.some((type) => ["memory_added", "item_gained", "affection_delta", "status_changed", "demo_cleared", "negotiation_leverage"].includes(type));
    if (needsParty || needsDomain) nodes.push("actor_runtime");
    if (needsDomain) nodes.push("domain_event", "event_drain");
    nodes.push("ui_events");
    return Array.from(new Set(nodes));
  }

  function buildTraceDetails(data, options = {}) {
    const opts = safeObj(options);
    const payload = safeObj(data);
    const events = safeArr(opts.uiEvents || opts.events);
    const nodes = safeArr(opts.nodes).map(normalizeNodeName).filter(Boolean);
    const timings = estimateTimings(nodes, opts.timings);
    const blob = textBlob(payload, opts.userLine, opts.intent);
    const domainSummary = summarizeDomain(payload, events, blob);
    const uiSummary = summarizeUi(events, blob);
    const inputSummary = summarizeInput(opts.userLine, opts.intent, payload);
    const details = {
      player_input: { input: inputSummary, output: String(opts.intent || "routed").toUpperCase() || "routed" },
      dm_router: { input: inputSummary, output: /fallback/i.test(blob) ? "fallback selected" : "route selected" },
      actor_view_filter: { input: "world + actor scope", output: /memory|记忆|actor_private/i.test(blob) ? "ActorView private memory" : "visible slice" },
      actor_runtime: { input: "filtered ActorView", output: /gribbo|astarion|party|dialogue|对话|台词/i.test(blob) ? "Party Coordinator" : "actor runtime" },
      domain_event: { input: "runtime decisions", output: domainSummary },
      event_drain: { input: "pending events", output: /EventDrain|event_drain|pending_events|item|memory|affection|flag/i.test(blob) ? domainSummary : "state committed" },
      ui_events: { input: "response/ui_events", output: uiSummary },
    };
    const types = new Set(eventTypes(payload, events));
    if (types.has("companion_guidance") || /\[队友建议\]/i.test(blob)) {
      details.ui_events.signal = "agent_signal";
    }
    if (types.has("negotiation_leverage") || /\[交涉筹码\]/i.test(blob)) {
      details.domain_event.signal = "agent_signal";
      details.event_drain.signal = "agent_signal";
      details.ui_events.signal = "agent_signal";
    }
    if (types.has("trap_insight") || /\[陷阱感知\]/i.test(blob)) {
      details.actor_view_filter.signal = "agent_signal";
      details.actor_runtime.signal = "agent_signal";
      details.domain_event.signal = "agent_signal";
      details.event_drain.signal = "agent_signal";
      details.ui_events.signal = "agent_signal";
    }
    if (types.has("trap_disarmed") || types.has("trap_triggered") || /\[陷阱解除\]|\[毒气陷阱\]/i.test(blob)) {
      details.dm_router.signal = "agent_signal";
      details.domain_event.signal = "agent_signal";
      details.event_drain.signal = "agent_signal";
      details.ui_events.signal = "agent_signal";
    }
    Object.keys(details).forEach((node) => Object.assign(details[node], timings[node] || { ms: null, estimated: true }));
    return details;
  }

  function setIdle() {
    transitionToken += 1;
    clearIdleTimer();
    clearTraceAnimation();
    currentState = "idle";
    updateStateIndicator("Director Idle · Local Exploration", "idle");
    applyNodeStates([], "", {});
    updateFallback("");
  }

  function setPending(context = {}) {
    transitionToken += 1;
    clearIdleTimer();
    clearTraceAnimation();
    currentState = "pending";
    pendingStartedAt = nowMs();
    updateStateIndicator("Director Processing…", "pending");
    const nodes = ["player_input", "dm_router", "actor_view_filter", "actor_runtime", "domain_event", "event_drain", "ui_events"];
    const details = buildTraceDetails({}, { nodes, userLine: safeObj(context).userLine || "", intent: safeObj(context).intent || "" });
    applyNodeStates(nodes, "player_input", details);
  }

  function activateTrace(nodes, options = {}) {
    const opts = safeObj(options);
    const normalized = safeArr(nodes).map(normalizeNodeName).filter(Boolean);
    const traceNodes = normalized.length ? normalized : buildTraceNodes(opts.data || {}, opts);
    const details = opts.details || buildTraceDetails(opts.data || {}, { ...opts, nodes: traceNodes });
    const fallbackReason = opts.fallbackReason || extractFallbackReason(opts.data || {});
    updateFallback(fallbackReason);
    transitionToken += 1;
    const token = transitionToken;
    currentState = "active";
    lastNodes = traceNodes.slice();
    updateStateIndicator("Director Active · Route Chain", "active");
    clearTraceAnimation();

    if (!traceNodes.length || opts.animate === false) {
      applyNodeStates(traceNodes, traceNodes[traceNodes.length - 1] || "", details);
      scheduleAutoIdle(token, opts.autoIdleMs || 2600);
      return;
    }

    traceNodes.forEach((node, index) => {
      traceTimers.push(window.setTimeout(() => {
        if (token !== transitionToken) return;
        applyNodeStates(traceNodes, node, details);
      }, index * (opts.stepMs || TRACE_STEP_MS)));
    });
    traceTimers.push(window.setTimeout(() => {
      if (token !== transitionToken) return;
      applyNodeStates(traceNodes, traceNodes[traceNodes.length - 1] || "", details);
      scheduleAutoIdle(token, opts.autoIdleMs || 3200);
    }, traceNodes.length * (opts.stepMs || TRACE_STEP_MS) + 20));
  }

  function updateTimings(timingMap) {
    const details = buildTraceDetails({}, { nodes: lastNodes, timings: timingMap || {} });
    applyNodeStates(lastNodes, lastNodes[lastNodes.length - 1] || "", details);
  }

  function resetTimings() {
    updateTimings({});
  }

  function getState() {
    return currentState;
  }

  function getLastNodes() {
    return lastNodes.slice();
  }

  function init() {
    cacheEls();
    ensureTimeline();
    ensureFallbackSlot();
    setIdle();
  }

  window.BG3DirectorTrace = Object.freeze({
    NODE_DISPLAY,
    CHAIN,
    normalizeNodeName,
    buildTraceNodes,
    buildTraceDetails,
    setIdle,
    setPending,
    activateTrace,
    updateTimings,
    resetTimings,
    getState,
    getLastNodes,
    init,
  });
})();
