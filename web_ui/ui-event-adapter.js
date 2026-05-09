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
  const RE_COMPANION_GUIDANCE = /\[队友建议\]/i;
  const RE_NEGOTIATION_LEVERAGE = /\[交涉筹码\]/i;

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

    const events = safeArr(data.ui_events).map(normalizeDirectUIEvent);
    const gameState = safeObj(data.game_state || data.gameState || data.state);
    const journal = [
      ...safeArr(data.journal_events),
      ...safeArr(gameState.journal_events),
      ...safeArr(data.state && data.state.journal_events),
    ];
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
    inferInventoryDeltas(
      safeObj(prev.player_inventory),
      safeObj(data.player_inventory),
      events
    );
    inferMemoryDeltas(
      safeObj(prev.actor_runtime_state || safeObj(prev.game_state).actor_runtime_state),
      safeObj(data.actor_runtime_state || safeObj(data.game_state).actor_runtime_state),
      events
    );

    /* Demo cleared detection */
    if (data.demo_cleared === true || RE_DEMO_CLEARED.test(journal.join(" "))) {
      events.push({ type: "demo_cleared" });
    }

    inferNegotiationFromFlags(prev, data, events);
    inferNegotiationEffects(prev, data, events);

    return events;
  }

  function normalizeDirectUIEvent(raw) {
    const e = safeObj(raw);
    const type = String(e.type || e.event_type || "").trim().toLowerCase();
    if (type === "item_transfer" || type === "actor_item_transaction_requested") {
      const tx = safeObj(e.transaction || safeObj(e.payload).transaction);
      const item = e.item || e.item_id || tx.item || tx.item_id;
      return {
        type: "item_gained",
        item,
        label: e.label || item,
        icon: e.icon || "◻",
        count: Number(e.count || tx.count) || 1,
      };
    }
    if (type === "memory_update" || type === "memory_added") {
      return {
        type: "memory_added",
        character: e.character || e.actor || e.actor_id || "",
        text: e.text || e.note || e.memory || "",
      };
    }
    if (type === "affection" || type === "affection_delta") {
      return {
        type: "affection_delta",
        character: e.character || e.actor || e.actor_id || "",
        delta: Number(e.delta) || 0,
        newValue: e.newValue ?? e.new_value ?? null,
        reason: e.reason || "",
      };
    }
    if (type === "companion_guidance" || type === "negotiation_leverage") {
      return e;
    }
    return e;
  }

  function inferFromLine(text, events) {
    const guidance = parseCompanionGuidance(text);
    if (guidance) {
      events.push(guidance);
    }

    const leverage = parseNegotiationLeverage(text);
    if (leverage) {
      events.push(leverage);
    }

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

  function titleCaseId(id) {
    return String(id || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function parseActorId(text) {
    const raw = String(text || "");
    if (/astarion|阿斯代伦/i.test(raw)) return "astarion";
    if (/shadowheart|影心/i.test(raw)) return "shadowheart";
    if (/lae[’'`]?zel|laezel|莱埃泽尔/i.test(raw)) return "laezel";
    return "party";
  }

  function parseGuidanceState(text) {
    const raw = String(text || "");
    if (/has_key\s*=\s*true|key[_\s-]*acquired|钥匙在手|已.*钥匙|拿到.*钥匙|有.*钥匙/i.test(raw)) {
      return "key_acquired";
    }
    if (/has_key\s*=\s*false|missing|missing[_\s-]*key|找钥匙|没.*钥匙|缺.*钥匙|书房|撬锁|搜箱|箱子|study|lockpick|chest/i.test(raw)) {
      return "missing_key";
    }
    return "unknown";
  }

  function parseCompanionGuidance(text) {
    const raw = String(text || "");
    if (!RE_COMPANION_GUIDANCE.test(raw)) return null;
    const topicMatch = raw.match(/topic\s*=\s*([a-z0-9_\-]+)/i);
    const topic = topicMatch ? topicMatch[1].toLowerCase() : (/lab[_\s-]*key|实验室.*钥匙|钥匙/i.test(raw) ? "lab_key" : "unknown");
    const advice = raw
      .replace(RE_COMPANION_GUIDANCE, "")
      .replace(/topic\s*=\s*[a-z0-9_\-]+/i, "")
      .replace(/actor\s*=\s*[a-z0-9_'’\-]+/i, "")
      .replace(/\s+/g, " ")
      .trim();
    return {
      type: "companion_guidance",
      actorId: parseActorId(raw),
      topic,
      state: parseGuidanceState(raw),
      advice: advice || raw,
      raw,
    };
  }

  function labelToNegotiationKey(label) {
    const key = String(label || "").trim().toLowerCase();
    if (key === "耐心") return "patience";
    if (key === "恐惧") return "fear";
    if (key === "偏执" || key === "猜疑") return "paranoia";
    return key;
  }

  function parseInlineEffects(text) {
    const raw = String(text || "");
    const effects = {};
    const re = /(patience|fear|paranoia|耐心|恐惧|偏执|猜疑)\s*[:=]?\s*([+\-]\s*\d+)/ig;
    let match;
    while ((match = re.exec(raw))) {
      const key = labelToNegotiationKey(match[1]);
      const value = parseInt(String(match[2] || "0").replace(/\s/g, ""), 10);
      if (["patience", "fear", "paranoia"].includes(key) && value !== 0) effects[key] = value;
    }
    return effects;
  }

  function parseNegotiationLeverage(text) {
    const raw = String(text || "");
    if (!RE_NEGOTIATION_LEVERAGE.test(raw)) return null;
    const match = raw.match(/\[交涉筹码\]\s*([a-z0-9_\-]+)\s*->\s*([a-z0-9_\-]+)/i);
    const evidence = match ? match[1].toLowerCase() : (/diary|日记/i.test(raw) ? "diary_evidence" : "unknown_evidence");
    const pressure = match ? match[2].toLowerCase() : (/elixir|灵药|药剂/i.test(raw) ? "gribbo_elixir_truth" : "unknown_pressure");
    const targetId = /gribbo|格里博/i.test(raw + " " + pressure) ? "gribbo" : "unknown";
    return {
      type: "negotiation_leverage",
      evidence,
      targetId,
      pressure,
      effects: parseInlineEffects(raw),
      raw,
    };
  }

  function actorDynamicValue(record, key) {
    const actor = safeObj(record);
    const states = safeObj(actor.dynamic_states || actor.dynamicStates);
    const raw = states[key] ?? actor[key];
    if (raw && typeof raw === "object") {
      const current = Number(raw.current_value ?? raw.current ?? raw.value);
      return Number.isFinite(current) ? current : null;
    }
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function actorRecordFromState(rawState, actorId) {
    const state = safeObj(rawState);
    const gameState = safeObj(state.game_state || state.gameState || {});
    const pools = [
      state.environment_objects,
      state.environmentObjects,
      state.party_status,
      state.partyStatus,
      state.entities,
      gameState.environment_objects,
      gameState.party_status,
      gameState.entities,
    ];
    for (const pool of pools) {
      const obj = safeObj(pool);
      if (obj[actorId]) return obj[actorId];
    }
    return {};
  }

  function inferNegotiationEffects(previousState, currentState, events) {
    const leverageEvents = events.filter((event) => event && event.type === "negotiation_leverage");
    if (!leverageEvents.length) return;
    leverageEvents.forEach((event) => {
      const target = event.targetId || "gribbo";
      const prevActor = actorRecordFromState(previousState, target);
      const currActor = actorRecordFromState(currentState, target);
      const effects = { ...safeObj(event.effects) };
      ["patience", "fear", "paranoia"].forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(effects, key)) return;
        const before = actorDynamicValue(prevActor, key);
        const after = actorDynamicValue(currActor, key);
        if (before == null || after == null || before === after) return;
        effects[key] = after - before;
      });
      event.effects = effects;
    });
  }

  function flagValue(raw) {
    const record = safeObj(raw);
    if (Object.prototype.hasOwnProperty.call(record, "value")) return record.value;
    return raw;
  }

  function flagsFromState(rawState) {
    const state = safeObj(rawState);
    const gameState = safeObj(state.game_state || state.gameState || state.state);
    return safeObj(state.flags || gameState.flags);
  }

  function hasNegotiationLeverageEvent(events) {
    return events.some((event) => event && event.type === "negotiation_leverage");
  }

  function inferNegotiationFromFlags(previousState, currentState, events) {
    if (hasNegotiationLeverageEvent(events)) return;
    const prevFlags = flagsFromState(previousState);
    const currFlags = flagsFromState(currentState);
    const before = flagValue(prevFlags.necromancer_lab_gribbo_truth_pressure);
    const after = flagValue(currFlags.necromancer_lab_gribbo_truth_pressure);
    if (before === true || after !== true) return;
    events.push({
      type: "negotiation_leverage",
      evidence: "diary_evidence",
      targetId: "gribbo",
      pressure: "gribbo_elixir_truth",
      effects: {},
      raw: "flags.necromancer_lab_gribbo_truth_pressure=true",
    });
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

  function inferInventoryDeltas(prevInventory, currInventory, events) {
    Object.keys(currInventory).forEach((id) => {
      const prevCount = Number(prevInventory[id]) || 0;
      const currCount = Number(currInventory[id]) || 0;
      const delta = currCount - prevCount;
      if (delta <= 0) return;
      const meta =
        window.BG3NecromancerMeta &&
        window.BG3NecromancerMeta.ITEM_META_EXTENSIONS[
          String(id || "").toLowerCase().replace(/\s+/g, "_")
        ];
      events.push({
        type: "item_gained",
        item: id,
        label: meta ? meta.label : id,
        icon: meta ? meta.icon : "◻",
        count: delta,
      });
    });
  }

  function memoryNotesFromActor(actor) {
    const record = safeObj(actor);
    const notes = [];
    safeArr(record.memory_notes).forEach((note) => notes.push(String(note || "")));
    safeArr(record.memories).forEach((item) => {
      if (typeof item === "string") notes.push(item);
      else if (safeObj(item).text) notes.push(String(safeObj(item).text));
      else if (safeObj(item).note) notes.push(String(safeObj(item).note));
    });
    return notes.filter(Boolean);
  }

  function inferMemoryDeltas(prevRuntime, currRuntime, events) {
    Object.keys(currRuntime).forEach((actorId) => {
      const prevNotes = new Set(memoryNotesFromActor(prevRuntime[actorId]));
      memoryNotesFromActor(currRuntime[actorId]).forEach((note) => {
        if (prevNotes.has(note)) return;
        events.push({
          type: "memory_added",
          character: actorId,
          text: note,
        });
      });
    });
  }

  /* ── Public API ── */
  window.BG3UIEventAdapter = Object.freeze({
    extractUIEvents,
  });
})();
