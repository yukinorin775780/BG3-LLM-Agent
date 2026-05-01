/**
 * director-trace.js
 * ───────────────────────────────────────────────────────
 * Director Trace Panel — replaces the old X-Ray Logic Tracer.
 *
 * States:
 *   idle     → WASD local movement. Shows "Director Idle · Local Exploration"
 *   pending  → narrative request sent. Shows "Director Processing…"
 *   active   → response received. Plays animated node chain highlight.
 *
 * Only activates on narrative triggers (interaction, dialogue, trigger zone).
 * WASD movement calls setIdle() → panel stays silent.
 *
 * Exposed on window.BG3DirectorTrace.
 */
(() => {
  "use strict";

  /* ── state ── */
  let currentState = "idle"; // idle | pending | active
  let traceTimers = [];
  let idleTimer = null;
  let animatingUntil = 0;
  let nodeTimings = {};
  let transitionToken = 0;
  const TRACE_STEP_MS = 240;

  /* ── demo-audience-friendly labels ── */
  const NODE_DISPLAY = Object.freeze({
    input_processing: {
      label: "Input",
      subtitle: "玩家叙事触发",
    },
    dm_analysis: {
      label: "AI Director",
      subtitle: "意图识别 · 剧情路由",
    },
    mechanics_processing: {
      label: "Mechanics",
      subtitle: "检定 · 物理 · LoS · 物品",
    },
    dialogue_processing: {
      label: "Actor Runtime",
      subtitle: "队友/NPC 发言与事件",
    },
    event_drain: {
      label: "EventDrain",
      subtitle: "好感 · 记忆 · 物品 · 状态写回",
    },
    generation: {
      label: "Narration",
      subtitle: "最终叙事输出",
    },
  });

  /* ── DOM cache ── */
  let els = null;

  function cacheEls() {
    if (els) return;
    els = {
      panel: document.getElementById("director-trace-panel"),
      nodeTimeline: document.getElementById("director-node-timeline"),
      stateIndicator: document.getElementById("director-state-indicator"),
      patienceBar: document.getElementById("patience-bar"),
      patienceValue: document.getElementById("patience-value"),
      patienceLabel: document.getElementById("patience-label"),
      fearBar: document.getElementById("fear-bar"),
      fearValue: document.getElementById("fear-value"),
      fearLabel: document.getElementById("fear-label"),
      jsonInspector: document.getElementById("json-inspector"),
    };
  }

  /* ── node name normalization ── */
  function normalizeNodeName(name) {
    const n = String(name || "")
      .trim()
      .toLowerCase();
    const aliases = {
      input_node: "input_processing",
      dm_node: "dm_analysis",
      mechanics_node: "mechanics_processing",
      dialogue_node: "dialogue_processing",
      generation_node: "generation",
    };
    return aliases[n] || n;
  }

  /* ── DOM manipulation ── */
  function applyNodeClasses(visited, active) {
    cacheEls();
    if (!els.nodeTimeline) return;
    els.nodeTimeline.querySelectorAll("li[data-node]").forEach((item) => {
      const node = normalizeNodeName(item.dataset.node);
      item.classList.toggle("is-active", node === active);
      item.classList.toggle("is-visited", visited.includes(node));
    });
  }

  function clearAllNodeStates() {
    cacheEls();
    if (!els.nodeTimeline) return;
    els.nodeTimeline.querySelectorAll("li[data-node]").forEach((item) => {
      item.classList.remove("is-active", "is-visited");
    });
  }

  function updateStateIndicator(text, stateClass) {
    cacheEls();
    if (!els.stateIndicator) return;
    els.stateIndicator.textContent = text;
    els.stateIndicator.className =
      "director-state-indicator director-state--" + stateClass;
  }

  function clearTraceAnimation() {
    traceTimers.forEach((id) => window.clearTimeout(id));
    traceTimers = [];
    animatingUntil = 0;
  }

  function clearIdleTimer() {
    if (idleTimer) {
      window.clearTimeout(idleTimer);
      idleTimer = null;
    }
  }

  function scheduleAutoIdle(token, delayMs) {
    clearIdleTimer();
    idleTimer = window.setTimeout(() => {
      if (token !== transitionToken) return;
      setIdle();
    }, Math.max(360, Number(delayMs) || 900));
  }

  /* ══════════════════════════════════════════════════════
   *  Public API
   * ══════════════════════════════════════════════════════ */

  /** Called after every local WASD move. Keeps panel silent. */
  function setIdle() {
    transitionToken += 1;
    if (currentState === "idle") return;
    clearIdleTimer();
    currentState = "idle";
    clearTraceAnimation();
    clearAllNodeStates();
    updateStateIndicator("Director Idle · Local Exploration", "idle");
  }

  /** Called when a narrative request is about to be sent. */
  function setPending() {
    transitionToken += 1;
    currentState = "pending";
    clearIdleTimer();
    clearTraceAnimation();
    clearAllNodeStates();
    updateStateIndicator("Director Processing…", "pending");
  }

  /** Called when the backend response arrives. Plays animated trace. */
  function activateTrace(nodes, options) {
    const opts = options && typeof options === "object" ? options : {};
    const normalized = (Array.isArray(nodes) ? nodes : [])
      .map(normalizeNodeName)
      .filter(Boolean);

    transitionToken += 1;
    const token = transitionToken;
    currentState = "active";
    updateStateIndicator("Director Active", "active");

    if (!normalized.length) {
      applyNodeClasses([], "");
      scheduleAutoIdle(token, 900);
      return;
    }

    const animate = opts.animate !== false;
    clearTraceAnimation();

    if (!animate || normalized.length === 1) {
      applyNodeClasses(normalized, normalized[normalized.length - 1] || "");
      scheduleAutoIdle(token, 1100);
      return;
    }

    const stepMs = opts.stepMs || TRACE_STEP_MS;
    animatingUntil = Date.now() + normalized.length * stepMs + 180;

    normalized.forEach((node, index) => {
      const timerId = window.setTimeout(() => {
        applyNodeClasses(normalized.slice(0, index + 1), node);
      }, index * stepMs);
      traceTimers.push(timerId);
    });

    const finalTimer = window.setTimeout(() => {
      if (token !== transitionToken) return;
      applyNodeClasses(normalized, normalized[normalized.length - 1] || "");
      traceTimers = [];
      animatingUntil = 0;
      scheduleAutoIdle(token, 820);
    }, normalized.length * stepMs + 20);
    traceTimers.push(finalTimer);
  }

  /** Update node timing badges */
  function updateTimings(timingMap) {
    cacheEls();
    if (!els.nodeTimeline) return;
    const timings =
      timingMap && typeof timingMap === "object" ? timingMap : {};
    nodeTimings = { ...nodeTimings, ...timings };

    els.nodeTimeline.querySelectorAll("li[data-node]").forEach((item) => {
      const node = normalizeNodeName(item.dataset.node);
      const badge = item.querySelector(".node-timing");
      if (!badge) return;
      const ms = Number(nodeTimings[node]);
      badge.textContent =
        Number.isFinite(ms) && ms >= 0 ? ms + "ms" : "--ms";
      badge.classList.remove(
        "node-timing--fast",
        "node-timing--medium",
        "node-timing--slow"
      );
      if (Number.isFinite(ms)) {
        if (ms <= 120) badge.classList.add("node-timing--fast");
        else if (ms <= 450) badge.classList.add("node-timing--medium");
        else badge.classList.add("node-timing--slow");
      }
    });
  }

  /** Reset timings for new request */
  function resetTimings() {
    nodeTimings = {};
    updateTimings({});
  }

  /** Get current state */
  function getState() {
    return currentState;
  }

  /* ── init: set idle on load ── */
  function init() {
    cacheEls();
    currentState = "idle";
    clearAllNodeStates();
    updateStateIndicator("Director Idle · Local Exploration", "idle");
  }

  window.BG3DirectorTrace = Object.freeze({
    NODE_DISPLAY,
    normalizeNodeName,
    setIdle,
    setPending,
    activateTrace,
    updateTimings,
    resetTimings,
    getState,
    init,
  });
})();
