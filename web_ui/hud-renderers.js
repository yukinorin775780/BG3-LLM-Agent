/**
 * hud-renderers.js — Toast, dice card, affection delta, memory card,
 * item gained toast, LoS overlay, act progress, demo cleared banner.
 * Exposed on window.BG3HudRenderers.
 */
(() => {
  "use strict";

  let toastContainer = null;
  let chipContainer = null;
  let inventoryHintContainer = null;
  let actProgressEl = null;
  let actTitleEl = null;
  let actSummaryEl = null;
  let toastQueue = [];
  const MAX_TOASTS = 4;

  function getToastContainer() {
    if (!toastContainer) toastContainer = document.getElementById("toast-container");
    return toastContainer;
  }

  function getChipContainer() {
    if (chipContainer) return chipContainer;
    chipContainer = document.getElementById("companion-chip-container");
    if (!chipContainer) {
      chipContainer = document.createElement("div");
      chipContainer.id = "companion-chip-container";
      chipContainer.className = "companion-chip-container";
      document.body.appendChild(chipContainer);
    }
    return chipContainer;
  }

  function getInventoryHintContainer() {
    if (inventoryHintContainer) return inventoryHintContainer;
    inventoryHintContainer = document.getElementById("inventory-hint-container");
    if (!inventoryHintContainer) {
      inventoryHintContainer = document.createElement("div");
      inventoryHintContainer.id = "inventory-hint-container";
      inventoryHintContainer.className = "inventory-hint-container";
      document.body.appendChild(inventoryHintContainer);
    }
    return inventoryHintContainer;
  }

  /* ── Toast System ── */
  function showToast(type, content, durationMs) {
    const host = getToastContainer();
    if (!host) return;
    const dur = Number(durationMs) || 3000;
    const el = document.createElement("div");
    el.className = "hud-toast hud-toast--" + (type || "info");
    el.textContent = content;
    el.setAttribute("role", "status");
    host.appendChild(el);
    toastQueue.push(el);
    void el.offsetWidth; // force reflow
    el.classList.add("hud-toast--visible");

    if (toastQueue.length > MAX_TOASTS) {
      const old = toastQueue.shift();
      if (old && old.parentNode) old.parentNode.removeChild(old);
    }

    window.setTimeout(() => {
      el.classList.remove("hud-toast--visible");
      el.classList.add("hud-toast--exit");
      window.setTimeout(() => {
        if (el.parentNode) el.parentNode.removeChild(el);
        const idx = toastQueue.indexOf(el);
        if (idx >= 0) toastQueue.splice(idx, 1);
      }, 320);
    }, dur);
  }

  /* ── Dice Card ── */
  function showDiceCard(rollEvent) {
    const e = rollEvent && typeof rollEvent === "object" ? rollEvent : {};
    const host = document.getElementById("dice-card-container");
    if (!host) return;
    const card = document.createElement("div");
    card.className = "dice-card" + (e.success ? " dice-card--success" : " dice-card--fail");

    const d20 = document.createElement("div");
    d20.className = "dice-card-d20";
    d20.textContent = "🎲 " + (e.roll || "?");

    const info = document.createElement("div");
    info.className = "dice-card-info";
    const actor = document.createElement("span");
    actor.className = "dice-card-actor";
    actor.textContent = e.actor || "player";
    const skill = document.createElement("span");
    skill.className = "dice-card-skill";
    skill.textContent = e.skill || e.text || "检定";
    const dc = document.createElement("span");
    dc.className = "dice-card-dc";
    dc.textContent = e.dc ? "DC " + e.dc : "";
    const result = document.createElement("span");
    result.className = "dice-card-result";
    result.textContent = e.success ? "✓ 成功" : "✗ 失败";

    info.appendChild(actor);
    info.appendChild(skill);
    if (e.dc) info.appendChild(dc);
    info.appendChild(result);
    card.appendChild(d20);
    card.appendChild(info);
    host.appendChild(card);
    void card.offsetWidth;
    card.classList.add("dice-card--visible");

    window.setTimeout(() => {
      card.classList.remove("dice-card--visible");
      card.classList.add("dice-card--exit");
      window.setTimeout(() => { if (card.parentNode) card.parentNode.removeChild(card); }, 400);
    }, 3500);
  }

  /* ── Affection Delta ── */
  function showAffectionDelta(event) {
    const e = event && typeof event === "object" ? event : {};
    const delta = Number(e.delta) || 0;
    if (delta === 0) return;
    const sign = delta > 0 ? "+" : "";
    const actor = String(e.character || "Companion")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    const host = getChipContainer();
    if (!host) return;
    const chip = document.createElement("div");
    chip.className = "companion-chip " + (delta > 0 ? "companion-chip--up" : "companion-chip--down");
    chip.textContent = actor + " " + sign + delta;
    host.appendChild(chip);
    void chip.offsetWidth;
    chip.classList.add("companion-chip--visible");
    window.setTimeout(() => {
      chip.classList.remove("companion-chip--visible");
      chip.classList.add("companion-chip--exit");
      window.setTimeout(() => {
        if (chip.parentNode) chip.parentNode.removeChild(chip);
      }, 220);
    }, 1800);
  }

  /* ── Status Badge ── */
  function showStatusBadge(event) {
    const e = event && typeof event === "object" ? event : {};
    const text = (e.character || "") + " → " + (e.status || "状态变化");
    showToast("info", text, 2500);
  }

  /* ── Memory Card ── */
  function showMemoryCard(event) {
    const e = event && typeof event === "object" ? event : {};
    const host = document.getElementById("dice-card-container");
    if (!host) return;

    const card = document.createElement("div");
    card.className = "memory-card";

    const title = document.createElement("div");
    title.className = "memory-card-title";
    title.textContent = "📜 记忆沉淀";

    const body = document.createElement("div");
    body.className = "memory-card-body";
    body.textContent = e.text || "一段新的记忆被铭记…";

    card.appendChild(title);
    card.appendChild(body);
    host.appendChild(card);
    void card.offsetWidth;
    card.classList.add("memory-card--visible");

    window.setTimeout(() => {
      card.classList.remove("memory-card--visible");
      card.classList.add("memory-card--exit");
      window.setTimeout(() => { if (card.parentNode) card.parentNode.removeChild(card); }, 400);
    }, 3500);
  }

  /* ── Item Gained Toast ── */
  function showItemGainedToast(event) {
    const e = event && typeof event === "object" ? event : {};
    const icon = e.icon || "◻";
    const label = e.label || e.item || "物品";
    const text = icon + " " + label + " — 已入包";
    showToast("item", text, 3000);
    const host = getInventoryHintContainer();
    if (host) {
      const card = document.createElement("div");
      card.className = "inventory-hint";
      card.textContent = "背包 +" + label;
      host.appendChild(card);
      void card.offsetWidth;
      card.classList.add("inventory-hint--visible");
      window.setTimeout(() => {
        card.classList.remove("inventory-hint--visible");
        card.classList.add("inventory-hint--exit");
        window.setTimeout(() => {
          if (card.parentNode) card.parentNode.removeChild(card);
        }, 240);
      }, 1500);
    }
  }

  function showTrapDiscovered(event) {
    const e = event && typeof event === "object" ? event : {};
    showToast("warning", e.text || "你发现了隐藏陷阱。", 2300);
  }

  function showTrapTriggered(event) {
    const e = event && typeof event === "object" ? event : {};
    showToast("warning", e.text || "陷阱被触发，队伍受伤。", 2200);
  }

  /* ── LoS Blocked Indicator ── */
  function showLoSBlockedOverlay(event) {
    showToast("warning", "⚠ 视线被阻挡", 2000);
    /* Phaser-level red overlay delegated to game.js if available */
    if (window.BG3TacticalMap && typeof window.BG3TacticalMap.drawLoSBlockerOverlay === "function") {
      const e = event && typeof event === "object" ? event : {};
      window.BG3TacticalMap.drawLoSBlockerOverlay(e.blockedTiles || []);
    }
  }

  /* ── Act Progress ── */
  function updateActProgress(act, objective) {
    if (!actProgressEl) actProgressEl = document.getElementById("act-progress");
    if (!actTitleEl) actTitleEl = document.getElementById("act-title");
    if (!actSummaryEl) actSummaryEl = document.getElementById("act-summary");
    if (!actProgressEl) return;

    const meta = window.BG3NecromancerMeta;
    const actNum = Number(act) || 1;
    const actObj = meta && meta.ACT_OBJECTIVES[actNum - 1];

    if (actTitleEl) actTitleEl.textContent = "Act " + actNum + (actObj ? " — " + actObj.title : "");
    if (actSummaryEl) actSummaryEl.textContent = objective || (actObj ? actObj.summary : "");
    actProgressEl.classList.remove("act-progress--hidden");
  }

  /* ── Demo Cleared Banner ── */
  function showDemoClearedBanner() {
    const existing = document.getElementById("demo-cleared-banner");
    if (existing) return;

    const banner = document.createElement("div");
    banner.id = "demo-cleared-banner";
    banner.className = "demo-cleared-banner";
    banner.innerHTML =
      '<div class="demo-cleared-content">' +
      '<h1 class="demo-cleared-title">DEMO CLEARED</h1>' +
      '<p class="demo-cleared-subtitle">你成功逃出了死灵法师的废弃实验室</p>' +
      "</div>";
    document.body.appendChild(banner);
    void banner.offsetWidth;
    banner.classList.add("demo-cleared--visible");
  }

  /* ══════════════════════════════════════════════════════
   *  dispatchUIEvents — process array from ui-event-adapter
   * ══════════════════════════════════════════════════════ */
  function dispatchUIEvents(events) {
    if (!Array.isArray(events)) return;
    events.forEach((ev) => {
      if (!ev || !ev.type) return;
      switch (ev.type) {
        case "roll_result": showDiceCard(ev); break;
        case "affection_delta": showAffectionDelta(ev); break;
        case "status_changed": showStatusBadge(ev); break;
        case "memory_added": showMemoryCard(ev); break;
        case "item_gained": showItemGainedToast(ev); break;
        case "line_of_sight_blocked": showLoSBlockedOverlay(ev); break;
        case "act_progress": updateActProgress(ev.act, ev.objective); break;
        case "trap_discovered": showTrapDiscovered(ev); break;
        case "trap_triggered": showTrapTriggered(ev); break;
        case "demo_cleared": showDemoClearedBanner(); break;
        default: break;
      }
    });
  }

  window.BG3HudRenderers = Object.freeze({
    showToast, showDiceCard, showAffectionDelta, showStatusBadge,
    showMemoryCard, showItemGainedToast, showLoSBlockedOverlay,
    updateActProgress, showDemoClearedBanner, showTrapDiscovered,
    showTrapTriggered, dispatchUIEvents,
  });
})();
