/**
 * ui-event-adapter.js
 * ───────────────────────────────────────────────────────
 * Unified event consumer: backend response → typed UI events.
 *
 * Fix #5: compat with blocked_by / blockedTiles, and
 * latest_roll.result.raw_roll / is_success / rolls / dc variants.
 *
 * Exposed on window.BG3UIEventAdapter.
 */
(() => {
  "use strict";

  function safeObj(v) {
    return v && typeof v === "object" ? v : {};
  }
  function safeArr(v) {
    return Array.isArray(v) ? v : [];
  }

  /* ── Regex patterns for inference ── */
  const RE_LOS_BLOCKED =
    /NO_LOS|视线.*阻挡|视线.*被.*挡|line.of.sight.*block/i;
  const RE_ROLL_DETAIL =
    /(?:(\w+)\s*)?(?:检定|check|roll).*?(?:DC\s*(\d+)|dc(\d+))?.*?(?:(?:掷出|rolled?|结果)\s*(\d+))?/i;
  const RE_AFFECTION =
    /好感度?\s*([+\-]\s*\d+)|affection\s*([+\-]\s*\d+)/i;
  const RE_ITEM_GAINED =
    /获得\s*[了]?\s*(.+?)(?:\s*[x×]\s*(\d+))?(?:\s*$|\s*[。，,])/i;
  const RE_STATUS_CHANGE =
    /\[状态\]\s*(\S+)\s*[:：]\s*(tense|poisoned|prone|frightened|blessed|中毒|紧张|恐惧|倒地|祝福)/i;
  const RE_MEMORY = /\[记忆\]|\[记忆沉淀\]|memory.*added|记忆沉淀/i;
  const RE_DEMO_CLEARED =
    /demo.*clear|通关|逃出|escape.*complete|任务完成/i;
  const RE_TRAP_DISCOVERED =
    /发现.*陷阱|察觉.*陷阱|trap.*discovered|trap.*revealed/i;
  const RE_TRAP_TRIGGERED =
    /踩中.*陷阱|陷阱.*触发|poison.*damage|毒雾.*喷发|trap.*trigger/i;

  /* ══════════════════════════════════════════════════════
   *  normalizeRollEvent(raw)
   *  Handles multiple backend roll shapes:
   *   - { result, dc, success }                  (current)
   *   - { raw_roll, dc, is_success }             (variant 1)
   *   - { rolls: [n], dc, is_success }           (variant 2)
   *   - { result: { raw_roll, dc, is_success } } (nested)
   * ══════════════════════════════════════════════════════ */
  function normalizeRollEvent(raw) {
    const r = safeObj(raw);

    /* Handle nested result object */
    const inner = r.result && typeof r.result === "object" ? r.result : null;
    const src = inner || r;

    /* Roll value: result > raw_roll > roll > rolls[0] */
    const rollVal =
      Number(inner ? 0 : r.result) ||
      Number(src.raw_roll) ||
      Number(src.roll) ||
      Number(safeArr(src.rolls)[0]) ||
      0;

    /* DC */
    const dc = Number(src.dc) || Number(r.dc) || 0;

    /* Success: is_success > success > (roll >= dc) */
    let success;
    if (typeof src.is_success === "boolean") {
      success = src.is_success;
    } else if (typeof r.success === "boolean") {
      success = r.success;
    } else if (typeof src.success === "boolean") {
      success = src.success;
    } else {
      success = dc > 0 ? rollVal >= dc : true;
    }

    return {
      type: "roll_result",
      actor: r.actor || r.character || src.actor || "player",
      skill: r.skill || r.ability || src.skill || src.ability || "",
      dc,
      roll: rollVal,
      advantage: Boolean(r.advantage || src.advantage),
      success,
      text: r.description || r.text || src.description || src.text || "",
    };
  }

  /* ══════════════════════════════════════════════════════
   *  normalizeLoSEvent(data, text)
   *  Handles blocked_by (backend field) and blockedTiles.
   * ══════════════════════════════════════════════════════ */
  function buildLoSEvent(data, rawText) {
    const d = safeObj(data);
    /* blocked_by: backend may return [{x,y}, …] or "entity_id" */
    let tiles = [];
    if (Array.isArray(d.blocked_by)) {
      tiles = d.blocked_by;
    } else if (Array.isArray(d.blockedTiles)) {
      tiles = d.blockedTiles;
    }
    return {
      type: "line_of_sight_blocked",
      source: d.source || "",
      target: d.target || "",
      blockedTiles: tiles,
      blocked_by: d.blocked_by || null,
      rawText: rawText || "",
    };
  }

  /* ══════════════════════════════════════════════════════
   *  extractUIEvents(backendResponse, previousState?)
   * ══════════════════════════════════════════════════════ */
  function extractUIEvents(backendResponse, previousState) {
    const data = safeObj(backendResponse);

    /* Fast path: backend provides ui_events directly */
    if (Array.isArray(data.ui_events) && data.ui_events.length > 0) {
      return data.ui_events.map((e) => safeObj(e));
    }

    /* Inference path */
    const events = [];
    const journal = safeArr(data.journal_events);
    const prev = safeObj(previousState);

    journal.forEach((line) => {
      const text = String(line || "");
      inferFromLine(text, events);
    });

    /* latest_roll field (multiple shapes supported) */
    if (data.latest_roll) {
      events.push(normalizeRollEvent(data.latest_roll));
    }

    /* Top-level blocked_by field (from mechanics_processing) */
    if (data.blocked_by) {
      events.push(buildLoSEvent(data, ""));
    }

    /* Affection deltas from party_status comparison */
    inferAffectionDeltas(
      safeObj(prev.party_status),
      safeObj(data.party_status),
      events
    );

    /* Demo cleared detection */
    if (data.demo_cleared === true || RE_DEMO_CLEARED.test(journal.join(" "))) {
      events.push({ type: "demo_cleared" });
    }

    return events;
  }

  function inferFromLine(text, events) {
    /* LoS blocked */
    if (RE_LOS_BLOCKED.test(text)) {
      events.push(buildLoSEvent({}, text));
    }

    /* Roll result */
    const rollMatch = text.match(RE_ROLL_DETAIL);
    if (rollMatch && (rollMatch[2] || rollMatch[3] || rollMatch[4])) {
      const dc = Number(rollMatch[2] || rollMatch[3]) || 0;
      const result = Number(rollMatch[4]) || 0;
      events.push({
        type: "roll_result",
        actor: rollMatch[1] || "player",
        skill: "",
        dc,
        roll: result,
        advantage: /优势|advantage/i.test(text),
        success: dc > 0 ? result >= dc : true,
        text,
      });
    }

    /* Affection inline */
    const affMatch = text.match(RE_AFFECTION);
    if (affMatch) {
      const deltaStr = (affMatch[1] || affMatch[2] || "0").replace(/\s/g, "");
      const delta = parseInt(deltaStr, 10);
      if (delta !== 0) {
        events.push({
          type: "affection_delta",
          character: "",
          delta,
          newValue: null,
          reason: text,
        });
      }
    }

    /* Status change */
    const statusMatch = text.match(RE_STATUS_CHANGE);
    if (statusMatch) {
      events.push({
        type: "status_changed",
        character: statusMatch[1] || "",
        status: statusMatch[2] || "",
        added: true,
      });
    }

    /* Memory added */
    if (RE_MEMORY.test(text)) {
      const memText = text
        .replace(/\[记忆[沉淀]*\]\s*/, "")
        .replace(/memory.*?added\s*[:：]?\s*/i, "")
        .trim();
      events.push({
        type: "memory_added",
        character: "",
        text: memText || text,
      });
    }

    if (RE_TRAP_DISCOVERED.test(text)) {
      events.push({
        type: "trap_discovered",
        text,
      });
    }

    if (RE_TRAP_TRIGGERED.test(text)) {
      events.push({
        type: "trap_triggered",
        text,
      });
    }

    /* Item gained */
    const itemMatch = text.match(RE_ITEM_GAINED);
    if (itemMatch) {
      const itemId = (itemMatch[1] || "").trim();
      const count = Number(itemMatch[2]) || 1;
      if (itemId) {
        const meta =
          window.BG3NecromancerMeta &&
          window.BG3NecromancerMeta.ITEM_META_EXTENSIONS[
            itemId.toLowerCase().replace(/\s+/g, "_")
          ];
        events.push({
          type: "item_gained",
          item: itemId,
          label: meta ? meta.label : itemId,
          icon: meta ? meta.icon : "◻",
          count,
        });
      }
    }
  }

  function inferAffectionDeltas(prevParty, currParty, events) {
    Object.keys(currParty).forEach((id) => {
      if (id === "player") return;
      const prev = safeObj(prevParty[id]);
      const curr = safeObj(currParty[id]);
      const prevAff = Number(prev.affection);
      const currAff = Number(curr.affection);
      if (
        Number.isFinite(prevAff) &&
        Number.isFinite(currAff) &&
        prevAff !== currAff
      ) {
        events.push({
          type: "affection_delta",
          character: id,
          delta: currAff - prevAff,
          newValue: currAff,
          reason: "",
        });
      }
    });
  }

  /* ── Public API ── */
  window.BG3UIEventAdapter = Object.freeze({
    extractUIEvents,
  });
})();
