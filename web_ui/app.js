(() => {
  const API_URL = "/api/chat";
  const STATE_URL = "/api/state";
  const SESSION_ID =
    new URLSearchParams(window.location.search).get("session_id") ||
    "necromancer_lab_demo";
  const IDLE_MS = 30000;
  const DIALOGUE_POLL_MS = 1800;
  const BACKEND_REQUEST_TIMEOUT_MS = 5000;
  const SILENT_FALLBACK_TEXT = "📖 [环境] 一阵阴冷的穿堂风吹过，你暂时失去了对周围环境的感知。";
  const QA_PARAMS = new URLSearchParams(window.location.search);
  const IS_QA_MODE = Array.from(QA_PARAMS.keys()).some((key) => key.startsWith("qa_"));
  const QA_NO_IDLE = QA_PARAMS.get("qa_no_idle") === "1" || window.__BG3_QA_NO_IDLE__ === true;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  /* Merge necromancer-meta extensions if loaded */
  const _necroMeta = window.BG3NecromancerMeta || {};
  const MAP_ID = (_necroMeta.MAP_ID) || "necromancer_lab";

  const SPEAKER_META = Object.assign({
    player: { name: "玩家", color: "#6eb5ff", sigil: "⌘" },
    shadowheart: { name: "影心", color: "#9b84c6", sigil: "✦" },
    astarion: { name: "阿斯代伦", color: "#c97a75", sigil: "🜂" },
    laezel: { name: "莱埃泽尔", color: "#70b99d", sigil: "⚔" },
    dm: { name: "地下城主", color: "#d0ab67", sigil: "☍" },
    npc: { name: "同行者", color: "#b29f7e", sigil: "◈" },
  }, _necroMeta.SPEAKER_META_EXTENSIONS || {});

  const ITEM_META = Object.assign({
    gold: { label: "金币", icon: "🪙" },
    gold_coin: { label: "金币", icon: "🪙" },
    scimitar: { label: "弯刀", icon: "🗡" },
    rusty_dagger: { label: "生锈匕首", icon: "🗡" },
    leather_armor: { label: "皮甲", icon: "▣" },
    shield: { label: "盾牌", icon: "◖" },
    shortbow: { label: "短弓", icon: "🏹" },
    longbow: { label: "长弓", icon: "🏹" },
    chain_mail: { label: "锁子甲", icon: "▣" },
    burnt_map: { label: "烧焦地图", icon: "🗺" },
    healing_potion: { label: "治疗药水", icon: "🧪" },
    mysterious_artifact: { label: "神秘遗物", icon: "🜄" },
    rusty_key: { label: "锈钥匙", icon: "🗝" },
  }, _necroMeta.ITEM_META_EXTENSIONS || {});

  const EQUIPMENT_SLOT_LABELS = {
    weapon: "主手",
    main_hand: "主手",
    ranged: "远程",
    offhand: "副手",
    armor: "护甲",
    shield: "盾牌",
    helmet: "头盔",
    boots: "靴子",
    accessory: "饰品",
  };

  const LOCATION_LABELS = Object.assign({
    camp_center: "营地中央",
    camp_fire: "篝火",
    iron_chest: "铁箱",
  }, _necroMeta.LOCATION_LABEL_EXTENSIONS || {});

  const state = {
    partyStatus: {},
    environmentObjects: {},
    playerInventory: {},
    combatState: {},
    mapData: {},
    activeLogFilters: new Set(["dialogue", "system", "narration"]),
    tacticalOverlayOpen: false,
    partyViewOpen: false,
    activePartyViewTab: "inventory",
    hasSyncedInitialState: false,
    turnCount: 0,
    idleTimer: null,
    dialoguePollTimer: null,
    isLoading: false,
    currentLootTargetId: "",
    seenLootTargets: new Set(),
    currentInteractable: "",
    currentIntent: "",
    readTarget: "",
    activeDialogueTarget: "",
    dialogueText: "",
    xrayTraceTimers: [],
    xrayTraceAnimatingUntil: 0,
    xrayNodeTimings: {},
    qaTraceStepMs: Math.max(120, Number(QA_PARAMS.get("qa_trace_step_ms")) || 240),
    speechRecognition: null,
    speechRecognitionSupported: Boolean(SpeechRecognition),
    isPttRecording: false,
  };

  const INTERACTION_SOURCES = new Set([
    "interaction",
    "ui_click",
    "ui_interaction",
    "keyboard_interaction",
  ]);
  const ACT3_SIDE_MARKERS = [
    "阿斯代伦说得对",
    "顺着阿斯代伦",
    "我同意阿斯代伦",
    "一起嘲笑",
    "和阿斯代伦一起嘲笑",
    "side_with_astarion",
    "side with astarion",
    "sided with astarion",
    "mock gribbo",
  ];
  const ACT3_REBUKE_MARKERS = [
    "阿斯代伦，闭嘴",
    "阿斯代伦闭嘴",
    "训斥阿斯代伦",
    "别拱火",
    "别再嘲笑",
    "rebuke_astarion",
    "rebuke astarion",
    "shut up astarion",
  ];
  const DOOR_ATTACK_MARKERS = ["攻击门", "砸门", "打门", "破门", "attack door", "smash door"];
  const DOOR_INTERACT_MARKERS = [
    "打开门",
    "开门",
    "使用钥匙打开门",
    "用 heavy_iron_key 打开门",
    "检查 heavy_oak_door_1",
    "open heavy_oak_door_1",
    "check heavy_oak_door_1",
  ];

  function readQaNumber(name, fallback) {
    const value = Number(QA_PARAMS.get(name));
    return Number.isFinite(value) ? value : fallback;
  }

  function readQaActions() {
    const traceCommand = String(QA_PARAMS.get("qa_trace") || "").trim();
    const traceIntent = String(QA_PARAMS.get("qa_intent") || "").trim();
    const xrayMode = String(QA_PARAMS.get("qa_xray") || "").trim().toLowerCase();
    const previewTrace = QA_PARAMS.get("qa_preview_trace") === "1";
    const traceDelay = Math.max(0, readQaNumber("qa_trace_delay_ms", 900));
    const xrayDelay = Math.max(0, readQaNumber("qa_xray_delay_ms", 400));
    const shouldToggleXray =
      xrayMode === "toggle"
      || xrayMode === "collapse"
      || xrayMode === "expand";

    return {
      traceCommand,
      traceIntent,
      xrayMode,
      previewTrace,
      traceDelay,
      xrayDelay,
      shouldToggleXray,
    };
  }

  function extractEventLines(data) {
    const lines = [];
    safeArray(data && data.journal_events).forEach((entry) => {
      lines.push(String(entry || ""));
    });
    safeArray(data && data.logs).forEach((entry) => {
      if (typeof entry === "string") {
        lines.push(entry);
        return;
      }
      const record = safeObject(entry);
      if (record.text != null) {
        lines.push(String(record.text));
      }
    });
    return lines;
  }

  function safeArrayOrObjectValues(value) {
    if (Array.isArray(value)) return value;
    if (value && typeof value === "object") return Object.values(value);
    return [];
  }

  const els = {
    currentLocation: document.getElementById("current-location"),
    networkState: document.getElementById("network-state"),
    turnCounter: document.getElementById("turn-counter"),
    tacticalOverlay: document.getElementById("tactical-pause-overlay"),
    tacticalToggleBtn: document.getElementById("tactical-toggle-btn"),
    restControls: document.getElementById("rest-controls"),
    shortRestBtn: document.getElementById("short-rest-btn"),
    longRestBtn: document.getElementById("long-rest-btn"),
    dialogueOverlay: document.getElementById("dialogue-overlay"),
    dialogueNpcName: document.getElementById("dialogue-npc-name"),
    dialogueText: document.getElementById("dialogue-text"),
    dialogueInput: document.getElementById("dialogue-input"),
    pttMicBtn: document.getElementById("ptt-mic-btn"),
    dialogueSendBtn: document.getElementById("dialogue-send-btn"),
    dialogueAttackBtn: document.getElementById("dialogue-attack-btn"),
    mainLayout: document.getElementById("main-layout"),
    xrayToggleBtn: document.getElementById("xray-toggle-btn"),
    nodeTimeline: document.getElementById("director-node-timeline") || document.getElementById("node-timeline"),
    patienceBar: document.getElementById("patience-bar"),
    patienceLabel: document.getElementById("patience-label"),
    patienceValue: document.getElementById("patience-value"),
    fearBar: document.getElementById("fear-bar"),
    fearLabel: document.getElementById("fear-label"),
    fearValue: document.getElementById("fear-value"),
    jsonInspector: document.getElementById("json-inspector"),
    partyViewModal: document.getElementById("party-view-modal"),
    closePartyViewBtn: document.getElementById("close-party-view-btn"),
    partyViewTabs: document.getElementById("party-view-tabs"),
    partyViewContent: document.getElementById("party-view-content"),
    initiativeTracker: document.getElementById("initiative-tracker"),
    initiativeList: document.getElementById("initiative-list"),
    mapContainer: document.getElementById("map-container"),
    worldLog: document.getElementById("world-log"),
    partyRoster: document.getElementById("party-roster"),
    partyCount: document.getElementById("party-count"),
    environmentList: document.getElementById("environment-list"),
    environmentCount: document.getElementById("environment-count"),
    userInput: document.getElementById("user-input"),
    sendBtn: document.getElementById("send-btn"),
    shortcutButtons: Array.from(document.querySelectorAll(".shortcut-btn")),
    logFilterBar: document.getElementById("log-filter-bar"),
    logFilterButtons: Array.from(document.querySelectorAll(".log-filter-btn")),
    lootModal: document.getElementById("loot-modal"),
    lootTitle: document.getElementById("loot-title"),
    lootItems: document.getElementById("loot-items"),
    lootAllBtn: document.getElementById("loot-all-btn"),
    closeLootBtn: document.getElementById("close-loot-btn"),
    /* New layout elements */
    dockInput: document.getElementById("dock-input"),
    dockSendBtn: document.getElementById("dock-send-btn"),
    actProgress: document.getElementById("act-progress"),
    actTitle: document.getElementById("act-title"),
    actSummary: document.getElementById("act-summary"),
  };

  function setNetworkState(text, mode) {
    els.networkState.textContent = text;
    els.networkState.dataset.state = mode;
  }

  function setTacticalOverlay(open) {
    state.tacticalOverlayOpen = Boolean(open);
    if (els.tacticalOverlay) {
      els.tacticalOverlay.classList.toggle("is-hidden", !state.tacticalOverlayOpen);
      els.tacticalOverlay.classList.toggle("active", state.tacticalOverlayOpen);
      els.tacticalOverlay.setAttribute("aria-hidden", String(!state.tacticalOverlayOpen));
    }
    if (els.tacticalToggleBtn) {
      els.tacticalToggleBtn.setAttribute("aria-expanded", String(state.tacticalOverlayOpen));
    }
  }

  function toggleTacticalOverlay() {
    setTacticalOverlay(!state.tacticalOverlayOpen);
  }

  function setPartyView(open) {
    state.partyViewOpen = Boolean(open);
    if (!els.partyViewModal) return;
    els.partyViewModal.classList.toggle("is-hidden", !state.partyViewOpen);
    els.partyViewModal.classList.toggle("active", state.partyViewOpen);
    els.partyViewModal.setAttribute("aria-hidden", String(!state.partyViewOpen));
    if (state.partyViewOpen) {
      renderPartyView();
    }
  }

  function togglePartyView() {
    setPartyView(!state.partyViewOpen);
  }

  function isEditableTarget(target) {
    if (!target || !(target instanceof Element)) return false;
    const tag = target.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
  }

  function safeObject(value) {
    return value && typeof value === "object" ? value : {};
  }

  function safeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function padTurn(num) {
    return String(num).padStart(2, "0");
  }

  function nowStamp() {
    const now = new Date();
    return now.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  function normalizeId(id) {
    return String(id || "").trim().toLowerCase();
  }

  function prettifyId(id) {
    return String(id || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (ch) => ch.toUpperCase());
  }

  function getSpeakerMeta(id) {
    return SPEAKER_META[normalizeId(id)] || SPEAKER_META.npc;
  }

  function getDisplayName(id) {
    return getSpeakerMeta(id).name || prettifyId(id);
  }

  function getEntityDisplayName(id) {
    const key = normalizeId(id);
    const party = safeObject(state.partyStatus);
    const env = safeObject(state.environmentObjects);
    const record = safeObject(party[key] || env[key]);
    return String(record.name || getDisplayName(key) || prettifyId(key));
  }

  function getInitials(id) {
    const clean = normalizeId(id).replace(/[^a-z0-9]/g, "");
    if (!clean) return "??";
    return clean.slice(0, 2).toUpperCase();
  }

  function getCombatantLabel(id) {
    const key = normalizeId(id);
    const party = safeObject(state.partyStatus);
    const env = safeObject(state.environmentObjects);
    const data = safeObject(party[key] || env[key]);
    return data.name || getDisplayName(key) || prettifyId(key);
  }

  function getCombatantSigil(id) {
    const key = normalizeId(id);
    const env = safeObject(state.environmentObjects);
    const party = safeObject(state.partyStatus);
    if (key === "player") return "P";
    if (safeObject(env[key]).faction === "hostile") return "!";
    return getInitials(key || safeObject(party[key]).name);
  }

  function formatLocation(raw) {
    const key = normalizeId(raw);
    return LOCATION_LABELS[key] || raw || "未知地标";
  }

  function itemMeta(itemId) {
    const key = normalizeId(itemId);
    return ITEM_META[key] || { label: prettifyId(itemId), icon: "◻" };
  }

  function equipmentSlotLabel(slot) {
    const key = normalizeId(slot);
    return EQUIPMENT_SLOT_LABELS[key] || prettifyId(slot);
  }

  function equipmentSlotIcon(slot) {
    const key = normalizeId(slot);
    if (key === "main_hand" || key === "weapon") return "⚔";
    if (key === "ranged") return "🏹";
    if (key === "armor") return "▣";
    if (key === "shield" || key === "offhand") return "◖";
    return "◆";
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function objectEntries(obj) {
    return Object.entries(safeObject(obj)).filter(([, value]) => value && typeof value === "object");
  }

  function inventoryEntries(inv) {
    return Object.entries(safeObject(inv)).filter(([, count]) => Number(count) > 0);
  }

  function playerViewData() {
    const party = safeObject(state.partyStatus);
    return {
      ...safeObject(party.player),
      hp: safeObject(party.player).hp ?? 20,
      max_hp: safeObject(party.player).max_hp ?? safeObject(party.player).hp ?? 20,
      affection: safeObject(party.player).affection ?? 100,
      position: safeObject(party.player).position || "camp_center",
      inventory: state.playerInventory,
    };
  }

  function partyViewEntries() {
    const party = safeObject(state.partyStatus);
    const entries = [["player", playerViewData()]];
    objectEntries(party)
      .filter(([id, data]) => {
        const key = normalizeId(id);
        const status = normalizeId(safeObject(data).status || "alive");
        return key !== "player" && status !== "dead";
      })
      .sort(([leftId], [rightId]) => leftId.localeCompare(rightId))
      .forEach(([id, data]) => entries.push([id, safeObject(data)]));
    return entries.slice(0, 4);
  }

  function canLootTarget(target) {
    const data = safeObject(target);
    const status = normalizeId(data.status);
    return inventoryEntries(data.inventory).length > 0 && (status === "open" || status === "opened" || status === "dead");
  }

  function mapInteractableToStructuredAction(interactable) {
    const target = safeObject(interactable);
    const targetId = normalizeId(target.id || "");
    const targetType = normalizeId(target.type || target.entity_type || "");
    if (!targetId) return null;

    if (targetId === "necromancer_diary" || targetType === "readable") {
      return {
        text: "阅读 " + targetId,
        intent: "READ",
        target: "necromancer_diary",
        source: "interaction",
      };
    }
    if (targetId === "gribbo" || targetType === "npc" || targetType === "character") {
      return {
        text: "",
        intent: "CHAT",
        target: "gribbo",
        source: "interaction",
      };
    }
    if (targetId === "heavy_oak_door_1" || targetType === "door") {
      return {
        text: "",
        intent: "INTERACT",
        target: "heavy_oak_door_1",
        source: "interaction",
      };
    }
    if (
      targetType === "loot"
      || targetType === "chest"
      || targetType === "corpse"
      || targetType === "container"
    ) {
      return {
        text: "",
        intent: "ui_action_loot",
        character: "player",
        target: targetId,
        source: "interaction",
      };
    }
    return {
      text: "检查 " + (target.label || target.name || targetId),
      intent: "INTERACT",
      target: targetId,
      source: "interaction",
    };
  }

  function isAct3ChoiceText(text) {
    const raw = String(text || "").trim();
    if (!raw) return false;
    const normalized = raw.toLowerCase();
    return ACT3_SIDE_MARKERS.some((marker) => raw.includes(marker) || normalized.includes(marker))
      || ACT3_REBUKE_MARKERS.some((marker) => raw.includes(marker) || normalized.includes(marker));
  }

  function isDoorAttackText(text) {
    const raw = String(text || "").trim();
    if (!raw) return false;
    const normalized = raw.toLowerCase();
    return DOOR_ATTACK_MARKERS.some((marker) => raw.includes(marker) || normalized.includes(marker));
  }

  function shouldRouteDoorInteractText(text) {
    const raw = String(text || "").trim();
    if (!raw) return false;
    const normalized = raw.toLowerCase();
    const hasDoorHint = raw.includes("门")
      || normalized.includes("door")
      || normalized.includes("heavy_oak_door_1");
    if (!hasDoorHint) return false;
    if (isDoorAttackText(raw)) return false;
    if (DOOR_INTERACT_MARKERS.some((marker) => raw.includes(marker) || normalized.includes(marker))) {
      return true;
    }
    if (normalized.includes("heavy_oak_door_1")) {
      return /(打开|开门|使用|检查|open|interact|check)/i.test(raw);
    }
    return false;
  }

  function clearTransientInteractionContext(options = {}) {
    const opts = options && typeof options === "object" ? options : {};
    state.currentInteractable = "";
    state.currentIntent = "";
    state.readTarget = "";
    if (opts.keepDialogueTarget !== true) {
      state.activeDialogueTarget = "";
    }
  }

  function rememberTransientInteractionContext(intent, target, source) {
    const normalizedIntent = String(intent || "").trim().toUpperCase();
    const normalizedTarget = normalizeId(target);
    const normalizedSource = String(source || "").trim().toLowerCase();
    if (INTERACTION_SOURCES.has(normalizedSource)) {
      state.currentInteractable = normalizedTarget;
      state.currentIntent = normalizedIntent;
    }
    if (normalizedIntent === "READ") {
      state.readTarget = normalizedTarget;
    }
  }

  function resolveChatRouting(text, intent, options = {}) {
    const opts = options && typeof options === "object" ? options : {};
    const userLine = String(text || "").trim();
    const explicitIntent = String(intent || "").trim();
    const explicitTarget = String(opts.target || "").trim();
    const explicitSource = String(opts.source || "").trim();

    let resolvedIntent = explicitIntent;
    let resolvedTarget = explicitTarget;
    let resolvedSource = explicitSource;
    const activeMapId = String(MAP_ID || "").trim().toLowerCase();

    if (
      activeMapId === "necromancer_lab"
      && !resolvedIntent
      && shouldRouteDoorInteractText(userLine)
    ) {
      resolvedIntent = "INTERACT";
      resolvedTarget = "heavy_oak_door_1";
      resolvedSource = resolvedSource || "text_input";
    }

    if (!resolvedIntent) {
      const activeDialogueTarget = normalizeId(state.activeDialogueTarget);
      if (activeDialogueTarget === "gribbo") {
        resolvedIntent = "CHAT";
        resolvedTarget = resolvedTarget || "gribbo";
        resolvedSource = resolvedSource || "dialogue_input";
      } else if (isAct3ChoiceText(userLine)) {
        resolvedIntent = "CHAT";
        resolvedTarget = resolvedTarget || "gribbo";
        resolvedSource = resolvedSource || "text_input";
      } else {
        resolvedIntent = "chat";
        resolvedSource = resolvedSource || "text_input";
      }
    }

    if (String(resolvedIntent).trim().toUpperCase() === "READ") {
      resolvedSource = resolvedSource || "interaction";
      if (!String(resolvedTarget || "").trim()) {
        resolvedTarget = state.readTarget || "necromancer_diary";
      }
    }

    return {
      userLine,
      intentValue: String(resolvedIntent || "").trim(),
      target: String(resolvedTarget || "").trim(),
      source: String(resolvedSource || "").trim(),
    };
  }

  function buildChatPayload(text, intent, character, options = {}) {
    const routed = resolveChatRouting(text, intent, options);
    const characterId = character ? normalizeId(character) : "";
    const payload = {
      user_input: routed.userLine,
      intent: routed.intentValue,
      target: routed.target,
      source: routed.source,
      session_id: SESSION_ID,
      map_id: MAP_ID,
    };
    if (characterId) {
      payload.character = characterId;
    }
    return { payload, routed };
  }

  function hpPercent(hp, maxHp) {
    if (!Number.isFinite(hp) || !Number.isFinite(maxHp) || maxHp <= 0) return 0;
    return clamp((hp / maxHp) * 100, 0, 100);
  }

  function affectionPercent(affection) {
    if (!Number.isFinite(affection)) return 50;
    return clamp(((affection + 100) / 200) * 100, 0, 100);
  }

  function affectionLabel(affection) {
    if (!Number.isFinite(affection)) return "未知";
    if (affection >= 60) return "忠诚";
    if (affection >= 20) return "友善";
    if (affection > -20) return "中立";
    if (affection > -60) return "警惕";
    return "敌意";
  }

  function describeLogKind(line) {
    const text = String(line || "");
    if (/(d20|dc\s*\d+|掷骰|检定|优势|劣势|critical|暴击|大失败|大成功)/i.test(text)) {
      return "roll";
    }
    return "system";
  }

  function createEmptyState(text) {
    const block = document.createElement("div");
    block.className = "empty-state";
    block.textContent = text;
    return block;
  }

  function appendLogEntry(kind, label, text, options = {}) {
    const logType = options.logType || "system";
    const entry = document.createElement("article");
    entry.className = "log-entry log-entry--" + kind + " type-" + logType;
    entry.dataset.logType = logType;

    const meta = document.createElement("div");
    meta.className = "log-meta";

    const badge = document.createElement("div");
    badge.className = "log-badge";

    const sigil = document.createElement("span");
    sigil.className = "log-sigil";
    sigil.textContent = options.sigil || "◈";

    const badgeLabel = document.createElement("span");
    badgeLabel.className = "log-label";
    badgeLabel.textContent = label;
    if (options.color) {
      badgeLabel.style.color = options.color;
    }

    badge.appendChild(sigil);
    badge.appendChild(badgeLabel);

    const stamp = document.createElement("span");
    stamp.textContent = "T" + padTurn(state.turnCount) + " · " + nowStamp();

    meta.appendChild(badge);
    meta.appendChild(stamp);

    const body = document.createElement("div");
    body.className = "log-body";
    body.textContent = text;

    entry.appendChild(meta);
    entry.appendChild(body);
    els.worldLog.appendChild(entry);
    applyLogFilters();
    els.worldLog.scrollTop = els.worldLog.scrollHeight;
  }

  function setFilterButtonState(button, active) {
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }

  function applyLogFilters() {
    const entries = els.worldLog.querySelectorAll(".log-entry");
    entries.forEach((entry) => {
      const type = entry.dataset.logType || "system";
      const visible = state.activeLogFilters.has(type);
      entry.classList.toggle("is-hidden", !visible);
    });
  }

  function handleLogFilterClick(event) {
    const button = event.target.closest(".log-filter-btn");
    if (!button) return;

    const filter = button.dataset.filter;
    if (!filter) return;

    const isActive = state.activeLogFilters.has(filter);
    if (isActive && state.activeLogFilters.size === 1) {
      return;
    }

    if (isActive) {
      state.activeLogFilters.delete(filter);
    } else {
      state.activeLogFilters.add(filter);
    }

    els.logFilterButtons.forEach((candidate) => {
      setFilterButtonState(
        candidate,
        state.activeLogFilters.has(candidate.dataset.filter || "")
      );
    });
    applyLogFilters();
  }

  function renderChrome(currentLocation) {
    els.currentLocation.textContent = currentLocation || "未知区域";
    els.turnCounter.textContent = padTurn(state.turnCount);
  }

  function createItemAction(label, action, itemId, ownerId) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "item-action";
    if (action === "equip") button.classList.add("btn-equip");
    if (action === "unequip") button.classList.add("btn-unequip");
    button.dataset.partyAction = action;
    button.dataset.itemId = itemId;
    button.dataset.ownerId = ownerId;
    button.textContent = label;
    return button;
  }

  function createEquipmentPanel(ownerId, equipment) {
    const panel = document.createElement("div");
    panel.className = "equipped-container equipment-panel";

    const label = document.createElement("p");
    label.className = "gear-section-label";
    label.textContent = "已装备 Equipped";
    panel.appendChild(label);

    const gear = safeObject(equipment);
    const slots = [
      { key: "main_hand", empty: "拳头 (未装备主手)" },
      { key: "ranged", empty: "未装备远程武器" },
      { key: "armor", empty: "未装备护甲" },
    ];

    slots.forEach(({ key, empty }) => {
      const rawItemId = gear[key];
      const normalizedItemId = normalizeId(rawItemId);
      const meta = itemMeta(normalizedItemId);
      const item = document.createElement("div");
      item.className = "equipped-item";

      const text = document.createElement("span");
      if (!normalizedItemId) {
        item.classList.add("equipped-item--empty");
        text.className = "empty-slot";
        text.textContent = equipmentSlotIcon(key) + " " + empty;
        item.appendChild(text);
        panel.appendChild(item);
        return;
      }

      text.textContent = equipmentSlotIcon(key) + " " + meta.label + " (" + equipmentSlotLabel(key) + ")";

      const actions = document.createElement("div");
      actions.className = "item-actions";
      actions.appendChild(createItemAction("卸下", "unequip", normalizedItemId, ownerId));

      item.appendChild(text);
      item.appendChild(actions);
      panel.appendChild(item);
    });

    return panel;
  }

  function createInventoryPanel(ownerId, inventory) {
    const panel = document.createElement("div");
    panel.className = "party-pack inventory-list";

    const label = document.createElement("p");
    label.className = "gear-section-label";
    label.textContent = "你的背包 Inventory";
    panel.appendChild(label);

    const invItems = inventoryEntries(inventory).slice(0, 6);
    if (invItems.length === 0) {
      panel.appendChild(makeItemTag("空背包", "⟡"));
      return panel;
    }

    invItems.forEach(([itemId, count]) => {
      const normalizedItemId = normalizeId(itemId);
      const metaItem = itemMeta(normalizedItemId);
      const row = document.createElement("div");
      row.className = "inventory-item-row";

      const itemTag = makeItemTag(metaItem.label + " x" + count, metaItem.icon);
      const actions = document.createElement("div");
      actions.className = "item-actions";
      actions.appendChild(createItemAction("检查", "inspect", normalizedItemId, ownerId));
      actions.appendChild(createItemAction("装备", "equip", normalizedItemId, ownerId));

      row.appendChild(itemTag);
      row.appendChild(actions);
      panel.appendChild(row);
    });

    return panel;
  }

  function createPartyViewEquipment(ownerId, equipment) {
    const wrap = document.createElement("div");
    wrap.className = "party-view-equipment";

    const title = document.createElement("h4");
    title.textContent = "装备槽位";
    wrap.appendChild(title);

    const gear = safeObject(equipment);
    ["main_hand", "offhand", "ranged", "armor"].forEach((slot) => {
      const itemId = normalizeId(gear[slot]);
      const row = document.createElement("div");
      row.className = "party-view-slot" + (itemId ? "" : " party-view-slot--empty");

      const label = document.createElement("span");
      label.textContent = equipmentSlotIcon(slot) + " " + equipmentSlotLabel(slot);

      const value = document.createElement("strong");
      value.textContent = itemId ? itemMeta(itemId).label : "空";

      row.appendChild(label);
      row.appendChild(value);
      if (itemId) {
        row.appendChild(createItemAction("卸下", "unequip", itemId, ownerId));
      }
      wrap.appendChild(row);
    });

    return wrap;
  }

  function createPartyViewInventory(ownerId, inventory) {
    const wrap = document.createElement("div");
    wrap.className = "party-view-inventory";

    const title = document.createElement("h4");
    title.textContent = "背包格";
    wrap.appendChild(title);

    const grid = document.createElement("div");
    grid.className = "party-view-inventory-grid";

    const items = inventoryEntries(inventory);
    const slotCount = Math.max(12, Math.ceil(items.length / 4) * 4);
    for (let index = 0; index < slotCount; index += 1) {
      const slot = document.createElement("div");
      slot.className = "party-view-inventory-slot";

      const entry = items[index];
      if (!entry) {
        slot.classList.add("party-view-inventory-slot--empty");
        grid.appendChild(slot);
        continue;
      }

      const [itemId, count] = entry;
      const normalizedItemId = normalizeId(itemId);
      const meta = itemMeta(normalizedItemId);
      slot.dataset.partyAction = "use";
      slot.dataset.itemId = normalizedItemId;
      slot.dataset.ownerId = ownerId;
      const icon = document.createElement("span");
      icon.className = "party-view-item-icon";
      icon.textContent = meta.icon;

      const name = document.createElement("strong");
      name.textContent = meta.label;

      const qty = document.createElement("small");
      qty.textContent = "x" + count;

      const actions = document.createElement("div");
      actions.className = "party-view-item-actions";
      actions.appendChild(createItemAction("使用", "use", normalizedItemId, ownerId));
      actions.appendChild(createItemAction("装备", "equip", normalizedItemId, ownerId));

      slot.appendChild(icon);
      slot.appendChild(name);
      slot.appendChild(qty);
      slot.appendChild(actions);
      grid.appendChild(slot);
    }

    wrap.appendChild(grid);
    return wrap;
  }

  function createPartyViewColumn(id, rawData) {
    const data = safeObject(rawData);
    const card = document.createElement("article");
    card.className = "party-view-character";

    const meta = getSpeakerMeta(id);
    const head = document.createElement("div");
    head.className = "party-view-character-head";

    const portrait = document.createElement("div");
    portrait.className = "party-view-portrait";
    portrait.textContent = getInitials(id);
    portrait.style.background = "radial-gradient(circle at 30% 30%, " + meta.color + ", #101319 72%)";

    const text = document.createElement("div");
    const name = document.createElement("h3");
    name.textContent = getDisplayName(id);
    name.style.color = meta.color;
    const role = document.createElement("p");
    role.textContent = "HP " + (data.hp ?? "—") + " / " + (data.max_hp ?? data.hp ?? "—") + " · " + formatLocation(data.position || "camp_center");

    text.appendChild(name);
    text.appendChild(role);
    head.appendChild(portrait);
    head.appendChild(text);

    card.appendChild(head);
    card.appendChild(createPartyViewEquipment(normalizeId(id), data.equipment));
    card.appendChild(createPartyViewInventory(normalizeId(id), data.inventory));
    return card;
  }

  function renderPartyViewTabs() {
    if (!els.partyViewTabs) return;
    els.partyViewTabs.querySelectorAll(".party-view-tab").forEach((button) => {
      const active = normalizeId(button.dataset.partyTab) === state.activePartyViewTab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function renderPartyView() {
    if (!els.partyViewContent) return;
    renderPartyViewTabs();
    els.partyViewContent.innerHTML = "";

    if (state.activePartyViewTab !== "inventory") {
      const wip = document.createElement("div");
      wip.className = "party-view-wip";
      wip.textContent = "建设中 WIP";
      els.partyViewContent.appendChild(wip);
      return;
    }

    const grid = document.createElement("div");
    grid.className = "party-view-grid";
    partyViewEntries().forEach(([id, data]) => {
      grid.appendChild(createPartyViewColumn(id, data));
    });
    els.partyViewContent.appendChild(grid);
  }

  function createTurnResourceIcon(label, value, type) {
    const available = Number(value) > 0;
    const icon = document.createElement("span");
    icon.className = "turn-resource-icon turn-resource-icon--" + type + (available ? " is-available" : " is-spent");
    icon.title = label + ": " + (available ? "可用" : "已消耗");
    icon.setAttribute("aria-label", icon.title);
    icon.textContent = type === "bonus" ? "▲" : "●";
    return icon;
  }

  function createTurnResourcesPanel(id, data) {
    const entity = safeObject(data);
    if (normalizeId(entity.faction) === "hostile") return null;

    const resources = safeObject(safeObject(state.combatState.turn_resources)[normalizeId(id)]);
    const hasResources = Object.prototype.hasOwnProperty.call(resources, "action")
      || Object.prototype.hasOwnProperty.call(resources, "bonus_action")
      || Object.prototype.hasOwnProperty.call(resources, "movement");
    if (!hasResources) return null;

    const panel = document.createElement("div");
    panel.className = "turn-resources";

    const label = document.createElement("span");
    label.className = "turn-resources-label";
    label.textContent = "本回合";

    const icons = document.createElement("div");
    icons.className = "turn-resource-icons";
    icons.appendChild(createTurnResourceIcon("主动作", resources.action, "action"));
    icons.appendChild(createTurnResourceIcon("附赠动作", resources.bonus_action, "bonus"));

    const movement = Number(resources.movement);
    const move = document.createElement("div");
    move.className = "turn-resource-move";

    const moveText = document.createElement("span");
    moveText.textContent = "🥾 " + (Number.isFinite(movement) ? movement : 0) + "ft";

    const moveTrack = document.createElement("span");
    moveTrack.className = "turn-resource-move-track";

    const moveFill = document.createElement("span");
    moveFill.className = "turn-resource-move-fill";
    moveFill.style.width = clamp(Number.isFinite(movement) ? movement : 0, 0, 30) / 30 * 100 + "%";

    moveTrack.appendChild(moveFill);
    move.appendChild(moveText);
    move.appendChild(moveTrack);

    panel.appendChild(label);
    panel.appendChild(icons);
    panel.appendChild(move);
    return panel;
  }

  function turnResourcesFor(id) {
    return safeObject(safeObject(state.combatState.turn_resources)[normalizeId(id)]);
  }

  function hasTurnResourcesFor(id) {
    const resources = turnResourcesFor(id);
    return Object.prototype.hasOwnProperty.call(resources, "action")
      || Object.prototype.hasOwnProperty.call(resources, "bonus_action")
      || Object.prototype.hasOwnProperty.call(resources, "movement");
  }

  function isHostileCombatant(id) {
    const key = normalizeId(id);
    const entity = safeObject(safeObject(state.partyStatus)[key] || safeObject(state.environmentObjects)[key]);
    return normalizeId(entity.faction) === "hostile";
  }

  function createInitiativeResourceDots(id) {
    const resources = turnResourcesFor(id);
    const wrap = document.createElement("span");
    wrap.className = "initiative-resources";

    const action = document.createElement("span");
    action.className = "initiative-resource-dot initiative-resource-dot--action" + (Number(resources.action) > 0 ? " is-available" : " is-spent");
    action.title = "主动作: " + (Number(resources.action) > 0 ? "可用" : "已耗尽");

    const bonus = document.createElement("span");
    bonus.className = "initiative-resource-triangle initiative-resource-triangle--bonus" + (Number(resources.bonus_action) > 0 ? " is-available" : " is-spent");
    bonus.title = "附赠动作: " + (Number(resources.bonus_action) > 0 ? "可用" : "已耗尽");

    wrap.appendChild(action);
    wrap.appendChild(bonus);
    return wrap;
  }

  function renderTacticalGrid(partyStatus, environmentObjects, mapData) {
    if (window.BG3TacticalMap && typeof window.BG3TacticalMap.update === "function") {
      window.BG3TacticalMap.update(partyStatus, environmentObjects, mapData);
    }
  }

  function getTacticalEntities() {
    const records = [];
    const addRecord = (id, data, source) => {
      const entity = safeObject(data);
      const x = Number(entity.x);
      const y = Number(entity.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      records.push({
        id: normalizeId(id),
        data: entity,
        source,
        name: entity.name || getDisplayName(id),
        x,
        y,
      });
    };

    Object.entries(safeObject(state.partyStatus)).forEach(([id, data]) => addRecord(id, data, "party"));
    Object.entries(safeObject(state.environmentObjects)).forEach(([id, data]) => addRecord(id, data, "environment"));
    return records;
  }

  function entityAliases(record) {
    const id = normalizeId(record.id);
    const aliases = [
      id,
      safeObject(record.data).id,
      record.name,
      safeObject(record.data).name,
      prettifyId(id),
      getDisplayName(id),
    ];
    if (id === "player") {
      aliases.push("玩家", "你", "我");
    }
    return Array.from(new Set(aliases.map((alias) => String(alias || "").trim()).filter(Boolean)));
  }

  function entityMentionIndex(text, record) {
    const haystack = String(text || "").toLowerCase();
    return entityAliases(record).reduce((best, alias) => {
      const index = haystack.indexOf(alias.toLowerCase());
      return index >= 0 ? Math.min(best, index) : best;
    }, Number.POSITIVE_INFINITY);
  }

  function mentionedEntities(text, records) {
    return records
      .map((record) => ({ record, index: entityMentionIndex(text, record) }))
      .filter((item) => Number.isFinite(item.index))
      .sort((a, b) => a.index - b.index);
  }

  function activeCombatantRecord(records) {
    const combat = safeObject(state.combatState);
    const order = safeArray(combat.initiative_order).map(normalizeId);
    const index = Number(combat.current_turn_index);
    const id = order[Number.isFinite(index) ? index : 0];
    return records.find((record) => record.id === id) || null;
  }

  function isHostileRecord(record) {
    return normalizeId(safeObject(record && record.data).faction) === "hostile";
  }

  function fallbackSourceRecord(records, blockedId) {
    const active = activeCombatantRecord(records);
    if (active && active.id !== blockedId) return active;
    return records.find((record) => record.id === "player" && record.id !== blockedId)
      || records.find((record) => !isHostileRecord(record) && record.id !== blockedId)
      || null;
  }

  function fallbackTargetRecord(source, records) {
    const sourceHostile = isHostileRecord(source);
    return records.find((record) => record.id !== source.id && isHostileRecord(record) !== sourceHostile)
      || records.find((record) => record.id !== source.id)
      || null;
  }

  function inferVisualEntities(text, mode) {
    const records = getTacticalEntities();
    if (!records.length) return { source: null, target: null };

    const mentions = mentionedEntities(text, records);
    if ((mode === "spell" || mode === "knockback") && mentions.length === 1) {
      const target = mentions[0].record;
      const source = fallbackSourceRecord(records, target.id);
      return { source, target };
    }

    let source = mentions[0] ? mentions[0].record : fallbackSourceRecord(records, "");
    let target = mentions.find((item) => !source || item.record.id !== source.id)?.record || null;

    if (!source && target) {
      source = fallbackSourceRecord(records, target.id);
    }
    if (source && (!target || target.id === source.id)) {
      target = fallbackTargetRecord(source, records);
    }

    return { source, target };
  }

  function parseGridPointFromText(text) {
    const value = String(text || "");
    const patterns = [
      /(?:坐标|位置|落点|推到|推至|击退到|撞到)[^\d-]*\(?\s*(-?\d+)\s*[,，]\s*(-?\d+)\s*\)?/i,
      /\(\s*(-?\d+)\s*[,，]\s*(-?\d+)\s*\)/,
    ];

    for (const pattern of patterns) {
      const match = value.match(pattern);
      if (!match) continue;
      const x = Number(match[1]);
      const y = Number(match[2]);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        return { x, y };
      }
    }
    return null;
  }

  function inferKnockbackTarget(text) {
    const records = getTacticalEntities();
    if (!records.length) return null;

    const value = String(text || "");
    const mentions = mentionedEntities(value, records);
    if (mentions.length === 0) return null;
    if (mentions.length === 1) return mentions[0].record;

    const passiveTarget = mentions.find(({ index }) => {
      const windowText = value.slice(index, index + 48);
      return /被|遭|受到|挨|推开|击退|推入|推到|推至/.test(windowText);
    });
    if (passiveTarget) return passiveTarget.record;

    const verbIndex = value.search(/推击|力量对抗|强制位移|击退|推开|推入|推到|推至/);
    if (verbIndex >= 0) {
      const afterVerb = mentions.find(({ index }) => index > verbIndex);
      if (afterVerb) return afterVerb.record;
    }

    const { target } = inferVisualEntities(value, "knockback");
    return target || mentions[1].record || mentions[0].record;
  }

  function hasTerrainDamageCue(text) {
    return /火焰伤害|篝火|营火|火堆|campfire|fire/i.test(String(text || ""));
  }

  function inferSingleVisualEntity(text) {
    const records = getTacticalEntities();
    if (!records.length) return null;

    const mentions = mentionedEntities(text, records);
    if (mentions.length > 0) {
      return mentions[0].record;
    }
    return activeCombatantRecord(records) || records.find((record) => record.id === "player") || records[0];
  }

  function parseDamageAmount(text) {
    const value = String(text || "");
    const match = value.match(/(?:受到|扣除|损失|造成)?\s*(\d+)\s*点(?:中毒|毒素|毒性|伤害)?/);
    return match ? Number(match[1]) : null;
  }

  function resolveSpeechSpeaker(rawSpeaker, text) {
    const speaker = normalizeId(rawSpeaker);
    if (speaker) {
      const direct = getTacticalEntities().find((record) => {
        return record.id === speaker || entityAliases(record).some((alias) => normalizeId(alias) === speaker);
      });
      if (direct) return direct.id;
    }

    const mentioned = mentionedEntities(text || "", getTacticalEntities());
    return mentioned[0] ? mentioned[0].record.id : "";
  }

  function parseBarkString(line) {
    const value = String(line || "").trim();
    const tagged = value.match(/\[台词\]\s*([^:：]+)?[:：]\s*(.+)$/);
    if (tagged) {
      return { speaker: tagged[1] || "", text: tagged[2] || "" };
    }

    const plain = value.match(/^([^:：]{1,32})[:：]\s*(.+)$/);
    if (plain) {
      return { speaker: plain[1] || "", text: plain[2] || "" };
    }

    return { speaker: "", text: value.replace(/\[台词\]\s*/, "") };
  }

  function extractSpeechBarks(data) {
    const barks = [];
    const pushBark = (speaker, text) => {
      const content = String(text || "").trim();
      if (!content) return;
      const speakerId = resolveSpeechSpeaker(speaker, content);
      if (!speakerId) return;
      barks.push({ speaker: speakerId, text: content });
    };

    safeArrayOrObjectValues(data && data.recent_barks).forEach((entry) => {
      if (typeof entry === "string") {
        const parsed = parseBarkString(entry);
        pushBark(parsed.speaker, parsed.text);
        return;
      }
      const record = safeObject(entry);
      pushBark(
        record.speaker || record.entity_id || record.actor || record.character || record.id,
        record.text || record.line || record.content || record.message,
      );
    });

    safeArray(data && data.responses).forEach((response) => {
      const record = safeObject(response);
      const speaker = normalizeId(record.speaker || "");
      if (!speaker || speaker === "dm" || speaker === "npc") return;
      pushBark(speaker, record.text);
    });

    extractEventLines(data).forEach((line) => {
      if (!/\[台词\]/.test(line)) return;
      const parsed = parseBarkString(line);
      pushBark(parsed.speaker, parsed.text);
    });

    const dedupe = new Set();
    return barks.filter((bark) => {
      const key = bark.speaker + "::" + bark.text;
      if (dedupe.has(key)) return false;
      dedupe.add(key);
      return true;
    });
  }

  function triggerSpeechBubbles(data) {
    if (!window.BG3TacticalMap || typeof window.BG3TacticalMap.playSpeechBubble !== "function") return;
    extractSpeechBarks(data).slice(0, 4).forEach((bark, index) => {
      window.setTimeout(() => {
        window.BG3TacticalMap.playSpeechBubble(bark.speaker, bark.text);
      }, 120 + index * 180);
    });
  }

  function triggerMapTransitionEffects(data) {
    if (!window.BG3TacticalMap || typeof window.BG3TacticalMap.playMapTransition !== "function") return;
    const hasMapCue = extractEventLines(data).some((line) => {
      return /\[地图探索\]|地图探索|地图切换|进入新地图|加载地图|场景切换/.test(String(line || ""));
    });
    if (!hasMapCue) return;
    window.setTimeout(() => {
      window.BG3TacticalMap.playMapTransition();
    }, 40);
  }

  function triggerRestVisualEffects(data, fallbackIntent) {
    if (!window.BG3TacticalMap) return;
    const responseText = safeArray(data && data.responses)
      .map((response) => String(safeObject(response).text || ""))
      .join("\n");
    const events = [extractEventLines(data).join("\n"), responseText].join("\n");
    const intent = normalizeId(fallbackIntent);
    const shortRest = /短休|short\s*rest|short_rest/i.test(events) || intent === "short_rest";
    const longRest = /长休|long\s*rest|long_rest|一夜过去|the next day/i.test(events) || intent === "long_rest";

    if (longRest && typeof window.BG3TacticalMap.playLongRest === "function") {
      window.setTimeout(() => window.BG3TacticalMap.playLongRest(), 80);
      return;
    }

    if (shortRest && typeof window.BG3TacticalMap.playShortRest === "function") {
      window.setTimeout(() => window.BG3TacticalMap.playShortRest(), 80);
    }
  }

  function extractActiveDialogueTarget(data) {
    const payload = safeObject(data);
    const gameState = safeObject(payload.game_state || payload.gameState);
    const combat = safeObject(payload.combat_state);
    return normalizeId(
      payload.active_dialogue_target
      || gameState.active_dialogue_target
      || combat.active_dialogue_target
      || "",
    );
  }

  function dialogueTargetAliases(targetId) {
    const target = normalizeId(targetId);
    const name = normalizeId(getEntityDisplayName(target));
    return new Set([target, name].filter(Boolean));
  }

  function parseDialogueJournalLine(line) {
    const text = String(line || "").trim();
    const match = text.match(/\[([^\]]+)\]\s*[:：]\s*[“"]?([\s\S]*?)[”"]?\s*$/);
    if (!match) return null;
    return {
      speaker: normalizeId(match[1]),
      text: String(match[2] || "").trim(),
    };
  }

  function extractDialogueTextForTarget(data, targetId) {
    const aliases = dialogueTargetAliases(targetId);
    const responses = safeArray(data && data.responses).slice().reverse();
    for (const response of responses) {
      const record = safeObject(response);
      const speaker = normalizeId(record.speaker);
      const text = String(record.text || "").trim();
      if (text && aliases.has(speaker)) {
        return text;
      }
    }

    const events = extractEventLines(data).slice().reverse();
    for (const line of events) {
      const parsed = parseDialogueJournalLine(line);
      if (parsed && parsed.text && aliases.has(parsed.speaker)) {
        return parsed.text;
      }
    }

    return "";
  }

  function updateDialogueOverlay(data) {
    if (!els.dialogueOverlay) return;
    const target = extractActiveDialogueTarget(data);
    state.activeDialogueTarget = target;
    window.BG3DialogueActive = Boolean(target);

    if (!target) {
      state.dialogueText = "";
      els.dialogueOverlay.classList.add("hidden");
      els.dialogueOverlay.setAttribute("aria-hidden", "true");
      return;
    }

    const wasHidden = els.dialogueOverlay.classList.contains("hidden");
    const npcName = getEntityDisplayName(target);
    const dialogueText = extractDialogueTextForTarget(data, target) || state.dialogueText || "……";
    state.dialogueText = dialogueText;

    els.dialogueNpcName.textContent = npcName;
    els.dialogueText.textContent = dialogueText;
    els.dialogueOverlay.classList.remove("hidden");
    els.dialogueOverlay.setAttribute("aria-hidden", "false");

    if (wasHidden && els.dialogueInput) {
      window.requestAnimationFrame(() => {
        els.dialogueInput.focus();
      });
    }
  }

  function triggerCombatVisualEffects(data, userLine) {
    if (!window.BG3TacticalMap) return;

    const dedupe = new Set();
    const events = extractEventLines(data).filter((line) => {
      const key = String(line || "").trim();
      if (!key || dedupe.has(key)) return false;
      dedupe.add(key);
      return true;
    });
    let playedSpellEffect = false;
    const responseHasTerrainDamage = events.some(hasTerrainDamageCue);

    events.forEach((line) => {
      const combinedText = [line, userLine].filter(Boolean).join(" ");
      if (/失败|找不到|未指定|无需再次|动作资源不足/.test(line)) return;

      if (/\[状态结算\]|状态结算/.test(line) && /中毒|poison/i.test(line)) {
        const target = inferSingleVisualEntity(combinedText);
        const damage = parseDamageAmount(line);
        if (target && typeof window.BG3TacticalMap.playStatusDamage === "function") {
          window.setTimeout(() => {
            window.BG3TacticalMap.playStatusDamage(target.id, damage ? "-" + damage : "中毒");
          }, 80);
        }
      }

      if (/获得优势|advantage/i.test(line)) {
        const actor = inferSingleVisualEntity(combinedText);
        if (actor && typeof window.BG3TacticalMap.playAdvantage === "function") {
          window.setTimeout(() => {
            window.BG3TacticalMap.playAdvantage(actor.id);
          }, 80);
        }
      }

      if (/推击|力量对抗|强制位移|击退|推开|推入|推到|推至/.test(line)) {
        const target = inferKnockbackTarget(combinedText);
        const destination = parseGridPointFromText(combinedText) || target;
        if (target && destination && typeof window.BG3TacticalMap.playKnockback === "function") {
          window.setTimeout(() => {
            window.BG3TacticalMap.playKnockback(
              target.id,
              { x: destination.x, y: destination.y },
              {
                terrainDamage: responseHasTerrainDamage || hasTerrainDamageCue(line),
                label: "火焰伤害",
              },
            );
          }, 80);
        }
        return;
      }

      if (!playedSpellEffect && /施放了|施展|吟唱|雷鸣波|圣火术|范围轰炸|aoe/i.test(line)) {
        const { source, target } = inferVisualEntities(combinedText, "spell");
        const center = target || source;
        if (center && typeof window.BG3TacticalMap.playAoE === "function") {
          window.setTimeout(() => {
            window.BG3TacticalMap.playAoE({ x: center.x, y: center.y });
          }, 80);
          playedSpellEffect = true;
        }
        return;
      }

      if (/发起攻击/.test(line)) {
        const { source, target } = inferVisualEntities(combinedText, "attack");
        if (source && target && typeof window.BG3TacticalMap.playProjectile === "function") {
          const color = isHostileRecord(source) ? 0xff4a4a : 0x00ffff;
          window.setTimeout(() => {
            window.BG3TacticalMap.playProjectile(
              { x: source.x, y: source.y },
              { x: target.x, y: target.y },
              color,
            );
          }, 80);
        }
      }
    });
  }

  function isCombatStateActive(combatState) {
    const combat = safeObject(combatState);
    const phase = normalizeId(combat.combat_phase || combat.phase || "");
    const isOutOfCombatPhase = ["out_of_combat", "outofcombat", "exploration", "free_roam", "victory"].includes(phase);
    return combat.combat_active === true && !isOutOfCombatPhase;
  }

  function updateRestControls(combatState) {
    if (!els.restControls) return;
    const isExploration = !isCombatStateActive(combatState);
    els.restControls.classList.toggle("is-hidden", !isExploration);
    els.restControls.setAttribute("aria-hidden", String(!isExploration));
  }

  function normalizeNodeName(nodeName) {
    const node = normalizeId(nodeName);
    const aliases = {
      input_node: "input_processing",
      dm_node: "dm_analysis",
      mechanics_node: "mechanics_processing",
      dialogue_node: "dialogue_processing",
      generation_node: "generation",
    };
    return aliases[node] || node;
  }

  function normalizeTimingMs(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num < 0) return null;
    return Math.round(num);
  }

  function extractTimingMsFromEntry(entry) {
    if (entry == null) return null;
    if (typeof entry === "number" || typeof entry === "string") {
      return normalizeTimingMs(entry);
    }
    if (typeof entry !== "object") return null;
    const record = safeObject(entry);
    return normalizeTimingMs(
      record.timing_ms
      ?? record.duration_ms
      ?? record.elapsed_ms
      ?? record.latency_ms
      ?? record.ms
      ?? record.time_ms
      ?? record.timeMs
      ?? record.duration
      ?? record.elapsed
      ?? null
    );
  }

  function mergeTimingRecord(target, source) {
    const src = safeObject(source);
    Object.entries(src).forEach(([rawNode, rawTiming]) => {
      const node = normalizeNodeName(rawNode);
      if (!node) return;
      const ms = extractTimingMsFromEntry(rawTiming);
      if (ms == null) return;
      target[node] = ms;
    });
  }

  function extractTimingPairsFromArray(target, list) {
    safeArray(list).forEach((rawItem) => {
      const item = safeObject(rawItem);
      const node = normalizeNodeName(item.node || item.node_name || item.name || item.id || "");
      if (!node) return;
      const ms = extractTimingMsFromEntry(item);
      if (ms == null) return;
      target[node] = ms;
    });
  }

  function resolveNodeTimings(payload, gameState) {
    const timings = {};
    const p = safeObject(payload);
    const g = safeObject(gameState);
    const streamState = safeObject(p.state);

    const objectCandidates = [
      p.node_timing_map,
      p.node_timings,
      p.node_timing,
      p.timings,
      p.timing,
      p.node_metrics,
      p.trace_timings,
      p.xray_timing,
      streamState.node_timing_map,
      streamState.node_timings,
      streamState.node_timing,
      streamState.timings,
      streamState.timing,
      streamState.node_metrics,
      streamState.trace_timings,
      streamState.xray_timing,
      g.node_timing_map,
      g.node_timings,
      g.node_timing,
      g.timings,
      g.timing,
      g.node_metrics,
      g.trace_timings,
      g.xray_timing,
    ];
    objectCandidates.forEach((candidate) => mergeTimingRecord(timings, candidate));

    const arrayCandidates = [
      p.node_results,
      p.node_timings_list,
      p.trace_results,
      p.trace_events,
      g.node_results,
      g.node_timings_list,
      g.trace_results,
      g.trace_events,
    ];
    arrayCandidates.forEach((candidate) => extractTimingPairsFromArray(timings, candidate));

    const directNode = normalizeNodeName(p.node_name || streamState.node_name || "");
    const directMs = extractTimingMsFromEntry(
      p.timing_ms
      ?? p.duration_ms
      ?? p.elapsed_ms
      ?? streamState.timing_ms
      ?? streamState.duration_ms
      ?? streamState.elapsed_ms
      ?? null
    );
    if (directNode && directMs != null) {
      timings[directNode] = directMs;
    }

    return timings;
  }

  function timingClassForMs(ms) {
    if (ms == null) return "";
    if (ms <= 120) return "node-timing--fast";
    if (ms <= 450) return "node-timing--medium";
    return "node-timing--slow";
  }

  function updateXrayNodeTimings(timingMap) {
    if (!els.nodeTimeline) return;
    const timings = safeObject(timingMap);
    els.nodeTimeline.querySelectorAll("li[data-node]").forEach((item) => {
      const node = normalizeNodeName(item.dataset.node);
      const badge = item.querySelector(".node-timing");
      if (!badge) return;
      const ms = normalizeTimingMs(timings[node]);
      badge.textContent = ms == null ? "--ms" : ms + "ms";
      badge.classList.remove("node-timing--fast", "node-timing--medium", "node-timing--slow");
      const klass = timingClassForMs(ms);
      if (klass) badge.classList.add(klass);
    });
  }

  function inferNodeTrace(data, userLine, intent) {
    const payload = safeObject(data);
    const gameState = safeObject(payload.game_state);
    const explicit = normalizeNodeName(payload.last_node || gameState.last_node || gameState.current_node);
    if (explicit) {
      const trace = ["input_processing", "dm_analysis"];
      if (explicit === "mechanics_processing") trace.push("mechanics_processing");
      if (explicit === "dialogue_processing") trace.push("dialogue_processing");
      if (explicit === "generation") {
        const combined = [userLine, intent, extractEventLines(data).join(" "), JSON.stringify(gameState.intent_context || {})].join(" ");
        if (/检定|掷骰|潜行|攻击|推击|法术|装备|卸下|搜刮|开锁|解除陷阱|短休|长休|移动|交互/.test(combined)) {
          trace.push("mechanics_processing");
        }
        if (/对话|交涉|台词|说|回复|dialogue/i.test(combined)) {
          trace.push("dialogue_processing");
        }
        trace.push("generation");
      } else {
        trace.push(explicit);
      }
      return Array.from(new Set(trace));
    }

    const text = [userLine, intent, extractEventLines(data).join(" ")].join(" ");
    const trace = ["input_processing", "dm_analysis"];
    if (/检定|掷骰|潜行|攻击|推击|法术|装备|卸下|搜刮|开锁|解除陷阱|短休|长休|移动|交互/.test(text)) {
      trace.push("mechanics_processing");
    }
    if (/对话|交涉|台词|说|回复|dialogue/i.test(text)) {
      trace.push("dialogue_processing");
    }
    trace.push("generation");
    return Array.from(new Set(trace));
  }

  function clearXrayNodeTraceAnimation() {
    state.xrayTraceTimers.forEach((timerId) => window.clearTimeout(timerId));
    state.xrayTraceTimers = [];
    state.xrayTraceAnimatingUntil = 0;
  }

  function applyXrayNodeClasses(visited, active) {
    if (!els.nodeTimeline) return;
    els.nodeTimeline.querySelectorAll("li[data-node]").forEach((item) => {
      const node = normalizeNodeName(item.dataset.node);
      item.classList.toggle("is-active", node === active);
      item.classList.toggle("is-visited", visited.includes(node));
    });
  }

  function setXrayNodeTrace(nodes, options = {}) {
    const normalized = safeArray(nodes).map(normalizeNodeName).filter(Boolean);
    if (!normalized.length) {
      clearXrayNodeTraceAnimation();
      applyXrayNodeClasses([], "");
      return;
    }

    const animate = options.animate === true;
    const now = Date.now();
    if (!animate && state.xrayTraceAnimatingUntil > now) {
      return;
    }

    clearXrayNodeTraceAnimation();
    if (!animate || normalized.length === 1) {
      applyXrayNodeClasses(normalized, normalized[normalized.length - 1] || "");
      return;
    }

    const stepMs = state.qaTraceStepMs;
    state.xrayTraceAnimatingUntil = now + normalized.length * stepMs + 180;
    normalized.forEach((node, index) => {
      const timerId = window.setTimeout(() => {
        applyXrayNodeClasses(normalized.slice(0, index + 1), node);
      }, index * stepMs);
      state.xrayTraceTimers.push(timerId);
    });
    const finalTimer = window.setTimeout(() => {
      applyXrayNodeClasses(normalized, normalized[normalized.length - 1] || "");
      state.xrayTraceTimers = [];
      state.xrayTraceAnimatingUntil = 0;
    }, normalized.length * stepMs + 20);
    state.xrayTraceTimers.push(finalTimer);
  }

  function normalizePercent(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return null;
    const percent = num <= 1 ? num * 100 : num;
    return Math.max(0, Math.min(100, percent));
  }

  function readDynamicState(dynamicStates, key) {
    const states = safeObject(dynamicStates);
    const value = states[key] ?? states[key.toLowerCase()] ?? states[key.toUpperCase()];
    if (value && typeof value === "object") {
      const record = safeObject(value);
      const direct = record.value ?? record.current ?? record.percent ?? record.current_value;
      const max = record.max ?? record.max_value ?? record.maximum ?? record.cap;
      const currentNum = Number(direct);
      const maxNum = Number(max);
      if (Number.isFinite(currentNum) && Number.isFinite(maxNum) && maxNum > 0) {
        return currentNum / maxNum;
      }
      return direct;
    }
    return value;
  }

  function updateXrayMeter(bar, label, title, value) {
    const percent = normalizePercent(value);
    if (bar) bar.style.width = percent == null ? "0%" : percent.toFixed(0) + "%";
    if (label) label.textContent = percent == null ? "--" : percent.toFixed(0) + "%";
    if (title) title.textContent = title.textContent || "";
  }

  function stateLabelFromEntry(key, value, fallback) {
    const record = safeObject(value);
    return String(record.name || fallback || prettifyId(key));
  }

  function resolveWatcherTarget(payload, gameState) {
    const entities = safeObject(gameState.entities || payload.entities);
    const activeDialogueTarget = normalizeId(
      payload.active_dialogue_target
      || gameState.active_dialogue_target
      || safeObject(gameState.intent_context).action_target
      || "",
    );

    const candidates = [];
    const pushCandidate = (id) => {
      const key = normalizeId(id);
      if (!key || candidates.includes(key) || !entities[key]) return;
      candidates.push(key);
    };

    pushCandidate(activeDialogueTarget);
    Object.keys(entities).forEach((id) => {
      if (/gribbo/.test(normalizeId(id)) || /gribbo/.test(normalizeId(safeObject(entities[id]).name))) {
        pushCandidate(id);
      }
    });
    Object.keys(entities).forEach((id) => {
      const dynamicStates = safeObject(safeObject(entities[id]).dynamic_states || safeObject(entities[id]).dynamicStates);
      if (readDynamicState(dynamicStates, "patience") != null || readDynamicState(dynamicStates, "fear") != null) {
        pushCandidate(id);
      }
    });
    Object.keys(entities).forEach((id) => {
      const dynamicStates = safeObject(safeObject(entities[id]).dynamic_states || safeObject(entities[id]).dynamicStates);
      if (Object.keys(dynamicStates).length) pushCandidate(id);
    });

    const targetId = candidates[0] || "";
    return {
      targetId,
      entity: safeObject(entities[targetId]),
      dynamicStates: safeObject(
        safeObject(entities[targetId]).dynamic_states || safeObject(entities[targetId]).dynamicStates
      ),
    };
  }

  function resolveWatcherEntries(dynamicStates) {
    const states = safeObject(dynamicStates);
    const patienceValue = readDynamicState(states, "patience");
    const fearValue = readDynamicState(states, "fear");

    if (patienceValue != null || fearValue != null) {
      return {
        primary: {
          label: stateLabelFromEntry("patience", states.patience, "耐心 Patience"),
          value: patienceValue,
        },
        secondary: {
          label: stateLabelFromEntry("fear", states.fear, "恐惧 Fear"),
          value: fearValue,
        },
      };
    }

    const fallbackEntries = Object.entries(states)
      .map(([key, value]) => ({
        key,
        label: stateLabelFromEntry(key, value, prettifyId(key)),
        value: readDynamicState(states, key),
      }))
      .filter((entry) => entry.value != null);

    return {
      primary: fallbackEntries[0] || { label: "耐心 Patience", value: null },
      secondary: fallbackEntries[1] || { label: "恐惧 Fear", value: null },
    };
  }

  function updateXrayPanel(data, options = {}) {
    if (!els.jsonInspector) return;
    const payload = safeObject(data);
    const gameState = safeObject(payload.game_state || payload.gameState || payload);
    const watcher = resolveWatcherTarget(payload, gameState);
    const watcherEntries = resolveWatcherEntries(watcher.dynamicStates);

    if (els.patienceLabel) els.patienceLabel.textContent = watcherEntries.primary.label;
    if (els.fearLabel) els.fearLabel.textContent = watcherEntries.secondary.label;
    updateXrayMeter(els.patienceBar, els.patienceValue, els.patienceLabel, watcherEntries.primary.value);
    updateXrayMeter(els.fearBar, els.fearValue, els.fearLabel, watcherEntries.secondary.value);

    const trace = options.trace || inferNodeTrace(payload, options.userLine || "", options.intent || "");
    setXrayNodeTrace(trace, { animate: options.animateTrace === true });
    const currentTimings = resolveNodeTimings(payload, gameState);
    if (Object.keys(currentTimings).length) {
      state.xrayNodeTimings = {
        ...state.xrayNodeTimings,
        ...currentTimings,
      };
    }
    updateXrayNodeTimings(state.xrayNodeTimings);

    const inspectorPayload = gameState === payload
      ? payload
      : {
          last_node: payload.last_node || gameState.last_node || gameState.current_node || null,
          node_trace: trace,
          node_timings_ms: state.xrayNodeTimings,
          watcher_target: watcher.targetId || null,
          intent_context: gameState.intent_context || payload.intent_context || null,
          active_dialogue_target: payload.active_dialogue_target || gameState.active_dialogue_target || null,
          entities: gameState.entities || null,
          combat_state: payload.combat_state || gameState.combat_state || null,
          journal_events: payload.journal_events || gameState.journal_events || [],
        };
    els.jsonInspector.textContent = JSON.stringify(inspectorPayload, null, 2);
  }

  function renderInitiativeTracker(combatState, wasCombatActive) {
    const combat = safeObject(combatState);
    const isCombatActive = isCombatStateActive(combat);
    const order = safeArray(combat.initiative_order).map(normalizeId).filter(Boolean);
    const currentIndex = Number(combat.current_turn_index);
    const activeIndex = Number.isFinite(currentIndex) ? currentIndex : -1;

    if (!els.initiativeTracker || !els.initiativeList) return;

    els.initiativeTracker.classList.toggle("is-hidden", !isCombatActive);
    els.initiativeTracker.classList.toggle("is-active", isCombatActive);
    els.initiativeTracker.setAttribute("aria-hidden", String(!isCombatActive));
    els.initiativeList.innerHTML = "";

    if (!isCombatActive) {
      if (wasCombatActive) {
        appendLogEntry("system", "战斗结束", "战斗态势解除，先攻顺位条已收起。", {
          color: "#73c6c3",
          sigil: "◇",
          logType: "system",
        });
        if (window.BG3TacticalMap && typeof window.BG3TacticalMap.playVictoryBanner === "function") {
          window.BG3TacticalMap.playVictoryBanner();
        }
      }
      return;
    }

    if (!wasCombatActive) {
      appendLogEntry("combat", "战斗开始", "⚔ 战斗开始！先攻顺位已锁定。", {
        color: "#ff8a7a",
        sigil: "⚔",
        logType: "system",
      });
    }

    if (order.length === 0) {
      const empty = document.createElement("span");
      empty.className = "initiative-empty";
      empty.textContent = "等待先攻数据...";
      els.initiativeList.appendChild(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    const activeCombatantId = order[activeIndex] || "";
    const shouldShowResources = hasTurnResourcesFor(activeCombatantId) && !isHostileCombatant(activeCombatantId);

    order.forEach((id, index) => {
      const chip = document.createElement("div");
      chip.className = "initiative-chip";
      chip.classList.toggle("active-turn", index === activeIndex);
      chip.dataset.combatantId = id;

      const avatarStack = document.createElement("span");
      avatarStack.className = "initiative-avatar-stack";

      const avatar = document.createElement("span");
      avatar.className = "initiative-avatar";
      avatar.textContent = getCombatantSigil(id);
      avatarStack.appendChild(avatar);

      if (shouldShowResources && hasTurnResourcesFor(id) && !isHostileCombatant(id)) {
        avatarStack.appendChild(createInitiativeResourceDots(id));
      }

      const label = document.createElement("span");
      label.className = "initiative-name";
      label.textContent = getCombatantLabel(id);

      chip.appendChild(avatarStack);
      chip.appendChild(label);
      fragment.appendChild(chip);
    });

    els.initiativeList.appendChild(fragment);
  }

  function createPartyCard(id, rawData) {
    const data = safeObject(rawData);
    const isPlayer = normalizeId(id) === "player";
    const card = document.createElement("article");
    card.className = "party-card";

    const meta = getSpeakerMeta(id);
    const avatar = document.createElement("div");
    avatar.className = "avatar-medallion";
    avatar.textContent = getInitials(id);
    avatar.style.background = "radial-gradient(circle at 30% 30%, " + meta.color + ", #101319 72%)";

    const content = document.createElement("div");

    const head = document.createElement("div");
    head.className = "party-card-head";

    const headText = document.createElement("div");
    const name = document.createElement("h3");
    name.textContent = getDisplayName(id);
    name.style.color = meta.color;
    const role = document.createElement("p");
    role.className = "party-role";
    role.textContent = "位置 · " + formatLocation(data.position || "camp_center");

    headText.appendChild(name);
    headText.appendChild(role);

    head.appendChild(headText);
    if (!isPlayer) {
      const affinity = document.createElement("span");
      affinity.className = "status-pill";
      affinity.textContent = affectionLabel(Number(data.affection));
      head.appendChild(affinity);
    }

    const bars = document.createElement("div");
    bars.className = "party-bars";

    const rawHp = Number(data.hp);
    const maxHp = Number(data.max_hp || 20);
    const hp = Number.isFinite(rawHp) ? Math.min(rawHp, maxHp) : rawHp;
    const aff = Number(data.affection);

    bars.appendChild(createMeter("HP", Number.isFinite(hp) ? hp + " / " + maxHp : "—", hpPercent(hp, maxHp), false));
    if (!isPlayer) {
      bars.appendChild(
        createMeter(
          "好感度",
          Number.isFinite(aff) ? String(aff) : "—",
          affectionPercent(aff),
          true
        )
      );
    }

    content.appendChild(head);
    content.appendChild(bars);
    const resourcesPanel = createTurnResourcesPanel(normalizeId(id), data);
    if (resourcesPanel) {
      content.appendChild(resourcesPanel);
    }
    content.appendChild(createEquipmentPanel(normalizeId(id), data.equipment));

    card.appendChild(avatar);
    card.appendChild(content);
    return card;
  }

  function renderPartyRoster() {
    const party = safeObject(state.partyStatus);
    const companionEntries = objectEntries(party)
      .filter(([id]) => normalizeId(id) !== "player")
      .sort(([leftId], [rightId]) => leftId.localeCompare(rightId));

    els.partyCount.textContent = companionEntries.length + 1 + " 名单位";
    els.partyRoster.innerHTML = "";

    const fragment = document.createDocumentFragment();
    fragment.appendChild(createPartyCard("player", playerViewData()));

    if (companionEntries.length === 0) {
      els.partyRoster.appendChild(fragment);
      return;
    }

    companionEntries.forEach(([id, data]) => {
      fragment.appendChild(createPartyCard(id, data));
    });

    els.partyRoster.appendChild(fragment);
  }

  function createMeter(label, value, percent, isAffection) {
    const wrap = document.createElement("div");
    wrap.className = "meter";

    const head = document.createElement("div");
    head.className = "meter-head";

    const left = document.createElement("span");
    left.textContent = label;
    const right = document.createElement("span");
    right.textContent = value;
    head.appendChild(left);
    head.appendChild(right);

    const track = document.createElement("div");
    track.className = "meter-track";
    const fill = document.createElement("div");
    if (isAffection) {
      track.classList.add("meter-track--bipolar");
      fill.className = "meter-cursor";
      fill.style.left = percent + "%";
    } else {
      fill.className = "meter-fill";
      fill.style.width = percent + "%";
    }
    track.appendChild(fill);

    wrap.appendChild(head);
    wrap.appendChild(track);
    return wrap;
  }

  function makeItemTag(text, icon) {
    const tag = document.createElement("span");
    tag.className = "item-tag";
    tag.textContent = icon + " " + text;
    return tag;
  }

  function renderEnvironmentObjects() {
    const host = els.environmentList;
    const entries = Object.entries(safeObject(state.environmentObjects)).filter(
      ([, value]) => value && typeof value === "object" && !Array.isArray(value)
    ).sort(([leftId], [rightId]) => leftId.localeCompare(rightId));

    els.environmentCount.textContent = entries.length + " 个对象";
    host.innerHTML = "";

    if (entries.length === 0) {
      host.appendChild(createEmptyState("当前房间没有可感知的环境对象。"));
      return;
    }

    const fragment = document.createDocumentFragment();

    entries.forEach(([id, rawData]) => {
      const data = safeObject(rawData);
      const card = document.createElement("article");
      card.className = "environment-card env-object";

      const head = document.createElement("div");
      head.className = "environment-card-head";

      const left = document.createElement("div");
      const title = document.createElement("h4");
      title.textContent = data.name || prettifyId(id);
      const keyLine = document.createElement("p");
      keyLine.className = "environment-desc";
      keyLine.textContent = "ID · " + id;
      left.appendChild(title);
      left.appendChild(keyLine);

      const status = document.createElement("span");
      status.className = "status-pill";
      status.textContent = String(data.status || "unknown");

      head.appendChild(left);
      head.appendChild(status);

      const desc = document.createElement("p");
      desc.className = "environment-desc";
      desc.textContent = data.description || "没有可用描述。";

      const lootWrap = document.createElement("div");
      lootWrap.className = "environment-loot";
      const lootEntries = Object.entries(safeObject(data.inventory)).filter(([, count]) => Number(count) > 0);
      if (lootEntries.length === 0) {
        lootWrap.appendChild(makeItemTag("无可拾取物", "·"));
      } else {
        lootEntries.forEach(([itemId, count]) => {
          const metaItem = itemMeta(itemId);
          lootWrap.appendChild(makeItemTag(metaItem.icon + " " + itemId + " x " + count, "·"));
        });
      }

      const actions = document.createElement("div");
      actions.className = "environment-actions";

      const inspectBtn = document.createElement("button");
      inspectBtn.type = "button";
      inspectBtn.className = "object-action";
      inspectBtn.dataset.command = "检查" + (data.name || prettifyId(id));
      inspectBtn.dataset.targetId = id;
      inspectBtn.dataset.targetType = String(data.type || data.entity_type || "");
      inspectBtn.dataset.targetLabel = String(data.name || prettifyId(id));
      inspectBtn.dataset.targetName = String(data.name || prettifyId(id));
      inspectBtn.textContent = "检查";
      actions.appendChild(inspectBtn);

      if (canLootTarget(data)) {
        const lootBtn = document.createElement("button");
        lootBtn.type = "button";
        lootBtn.className = "object-action";
        lootBtn.dataset.loot = "true";
        lootBtn.dataset.targetId = id;
        lootBtn.textContent = "搜刮";
        actions.appendChild(lootBtn);
      }

      card.appendChild(head);
      card.appendChild(desc);
      card.appendChild(lootWrap);
      card.appendChild(actions);
      fragment.appendChild(card);
    });

    host.appendChild(fragment);
  }

  function renderLootItems(environmentObjects, targetId) {
    const env = safeObject(environmentObjects);
    const normalizedTargetId = normalizeId(targetId);
    const target = safeObject(env[normalizedTargetId]);
    const targetName = target.name || prettifyId(normalizedTargetId);
    const items = inventoryEntries(target.inventory);
    els.lootItems.innerHTML = "";
    els.lootTitle.textContent = "搜刮: " + targetName;

    if (items.length === 0) {
      els.lootItems.appendChild(createEmptyState(targetName + " 已经被搬空。"));
      return;
    }

    items.forEach(([itemId, count]) => {
      const meta = itemMeta(itemId);
      const card = document.createElement("div");
      card.className = "loot-item";

      const icon = document.createElement("div");
      icon.className = "inventory-slot-icon";
      icon.textContent = meta.icon;

      const name = document.createElement("h4");
      name.textContent = meta.label;

      const amount = document.createElement("p");
      amount.textContent = "ID " + itemId + " · x" + count;

      card.appendChild(icon);
      card.appendChild(name);
      card.appendChild(amount);
      els.lootItems.appendChild(card);
    });
  }

  function showLootModal() {
    setTacticalOverlay(true);
    els.lootModal.classList.remove("hidden");
    els.lootModal.setAttribute("aria-hidden", "false");
  }

  function hideLootModal() {
    els.lootModal.classList.add("hidden");
    els.lootModal.setAttribute("aria-hidden", "true");
  }

  function openLootModalForTarget(targetId) {
    const normalizedTargetId = normalizeId(targetId);
    if (!normalizedTargetId) return;
    state.currentLootTargetId = normalizedTargetId;
    renderLootItems(state.environmentObjects, normalizedTargetId);
    showLootModal();
  }

  function maybeShowLootModal(environmentObjects) {
    const env = safeObject(environmentObjects);
    const eligibleTarget = Object.entries(env).find(([id, rawData]) => {
      return !state.seenLootTargets.has(normalizeId(id)) && canLootTarget(rawData);
    });
    if (!eligibleTarget) return;
    openLootModalForTarget(eligibleTarget[0]);
  }

  function updateWorldLog(data, userLine) {
    if (userLine) {
      const playerMeta = getSpeakerMeta("player");
      appendLogEntry("player", "你", userLine, {
        color: playerMeta.color,
        sigil: playerMeta.sigil,
        logType: "dialogue",
      });
    }

    (data.responses || []).forEach((response) => {
      const speaker = normalizeId(response.speaker || "npc");
      const meta = getSpeakerMeta(speaker);
      appendLogEntry("npc", getDisplayName(speaker) + " · " + speaker, response.text || "", {
        color: meta.color,
        sigil: meta.sigil,
        logType: "dialogue",
      });
    });

    (data.journal_events || []).forEach((line) => {
      const kind = describeLogKind(line);
      appendLogEntry(kind, kind === "roll" ? "命运检定" : "系统裁定", line, {
        color: kind === "roll" ? "#73c6c3" : "#d0ab67",
        sigil: kind === "roll" ? "🎲" : "◎",
        logType: kind === "roll" ? "narration" : "system",
      });
    });
  }

  function setLoading(loading) {
    state.isLoading = loading;
    if (loading) {
      stopSpeechRecognition();
    }
    els.userInput.disabled = loading;
    els.sendBtn.disabled = loading;
    els.sendBtn.textContent = loading ? "命运演算中…" : "执行指令";
    if (els.shortRestBtn) els.shortRestBtn.disabled = loading;
    if (els.longRestBtn) els.longRestBtn.disabled = loading;
    if (els.dialogueInput) els.dialogueInput.disabled = loading;
    if (els.pttMicBtn) els.pttMicBtn.disabled = loading || !state.speechRecognitionSupported;
    if (els.dialogueSendBtn) els.dialogueSendBtn.disabled = loading;
    if (els.dialogueAttackBtn) els.dialogueAttackBtn.disabled = loading;
    els.shortcutButtons.forEach((button) => {
      button.disabled = loading;
    });
    Array.from(document.querySelectorAll(".object-action")).forEach((button) => {
      button.disabled = loading;
    });
    Array.from(document.querySelectorAll(".item-action")).forEach((button) => {
      button.disabled = loading;
    });
    els.lootAllBtn.disabled = loading;
    if (loading) {
      setNetworkState("命运演算中", "loading");
    }
  }

  async function fetchWithTimeout(url, options = {}, timeoutMs = BACKEND_REQUEST_TIMEOUT_MS) {
    const controller = new AbortController();
    const timerId = window.setTimeout(() => controller.abort(), Math.max(0, Number(timeoutMs) || 0));
    try {
      const requestOptions = { ...(options || {}), signal: controller.signal };
      return await fetch(url, requestOptions);
    } finally {
      window.clearTimeout(timerId);
    }
  }

  function buildSilentFallbackPayload(userLine, intentValue) {
    const location = String((els.currentLocation && els.currentLocation.textContent) || "未知区域").trim() || "未知区域";
    const fallbackTrace = ["input_processing", "dm_analysis", "generation"];
    const fallbackTimings = {
      input_processing: 0,
      dm_analysis: BACKEND_REQUEST_TIMEOUT_MS,
      generation: 0,
    };
    return {
      responses: [],
      journal_events: [SILENT_FALLBACK_TEXT],
      current_location: location,
      party_status: state.partyStatus,
      environment_objects: state.environmentObjects,
      player_inventory: state.playerInventory,
      combat_state: state.combatState,
      last_node: "generation",
      node_trace: fallbackTrace,
      node_timing_map: fallbackTimings,
      game_state: {
        last_node: "generation",
        intent_context: {
          action_actor: "player",
          action_target: "",
          fallback_intent: normalizeId(intentValue || "fallback"),
          fallback_reason: "network_timeout_or_unavailable",
        },
        entities: state.partyStatus,
        combat_state: state.combatState,
      },
      _local_fallback: true,
      _fallback_trace: fallbackTrace,
      _fallback_user_line: userLine || "",
      _fallback_intent: intentValue || "",
    };
  }

  function applySilentNetworkFallback(userLine, intentValue, options = {}) {
    const data = buildSilentFallbackPayload(userLine, intentValue);
    const trace = safeArray(data._fallback_trace);
    const opts = options && typeof options === "object" ? options : {};
    if (opts.incrementTurn !== false) {
      state.turnCount += 1;
      if (els.turnCounter) els.turnCounter.textContent = padTurn(state.turnCount);
    }
    updateXrayPanel(data, {
      userLine: data._fallback_user_line,
      intent: data._fallback_intent,
      trace,
      animateTrace: true,
    });
    if (!opts.skipLogUpdate) {
      updateWorldLog(data, userLine || null);
    }
    setNetworkState("链路在线", "ok");
    return data;
  }

  function resetIdleTimer() {
    if (IS_QA_MODE || QA_NO_IDLE) return;
    window.clearTimeout(state.idleTimer);
    state.idleTimer = window.setTimeout(() => {
      sendMessage("", "trigger_idle_banter");
    }, IDLE_MS);
  }

  async function sendStructuredAction(action = {}) {
    const descriptor = action && typeof action === "object" ? action : {};
    const options = descriptor.options && typeof descriptor.options === "object" ? descriptor.options : {};
    const opts = options && typeof options === "object" ? options : {};
    const text = descriptor.text;
    const intent = descriptor.intent;
    const character = descriptor.character;
    const built = buildChatPayload(text, intent, character, opts);
    const payload = built.payload;
    const routed = built.routed;
    const userLine = routed.userLine;
    const intentValue = routed.intentValue;

    if (!userLine && !intentValue) {
      return;
    }

    setLoading(true);
    state.xrayNodeTimings = {};
    updateXrayNodeTimings(state.xrayNodeTimings);

    /* Activate Director Trace only for narrative requests */
    const _isNarrative = isNarrativeRequest(intentValue, userLine, routed.source);
    if (_isNarrative && window.BG3DirectorTrace && typeof window.BG3DirectorTrace.setPending === "function") {
      window.BG3DirectorTrace.setPending();
    }
    rememberTransientInteractionContext(intentValue, routed.target, routed.source);
    const shouldClearReadContext = normalizeId(intentValue) === "read";

    try {
      const response = await fetchWithTimeout(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }, BACKEND_REQUEST_TIMEOUT_MS);

      if (!response.ok) {
        return applySilentNetworkFallback(userLine, intentValue, opts);
      }

      const data = await response.json();
      if (opts.incrementTurn !== false) {
        state.turnCount += 1;
      }
      const wasCombatActive = isCombatStateActive(state.combatState);
      const prevPartySnapshot = { ...state.partyStatus };
      state.partyStatus = safeObject(data.party_status);
      state.environmentObjects = safeObject(data.environment_objects);
      state.playerInventory = safeObject(data.player_inventory);
      state.combatState = safeObject(data.combat_state);
      const responseMapData = safeObject(data.map_data);
      state.mapData = Object.keys(responseMapData).length
        ? responseMapData
        : safeObject(state.combatState.map_data);
      updateDialogueOverlay(data);

      if (data.current_location) {
        renderChrome(data.current_location);
      } else {
        renderChrome(els.currentLocation.textContent);
      }

      renderPartyRoster();
      renderEnvironmentObjects();
      if (state.partyViewOpen) {
        renderPartyView();
      }
      renderTacticalGrid(state.partyStatus, state.environmentObjects, state.mapData);
      renderInitiativeTracker(state.combatState, wasCombatActive);
      updateRestControls(state.combatState);
      const trace = inferNodeTrace(data, userLine, intentValue);
      updateXrayPanel(data, {
        userLine,
        intent: intentValue,
        trace,
        animateTrace: true,
      });

      /* Director Trace lifecycle: activateTrace on narrative response */
      if (_isNarrative && window.BG3DirectorTrace && typeof window.BG3DirectorTrace.activateTrace === "function") {
        window.BG3DirectorTrace.activateTrace(trace, { animate: true });
      }

      /* Dispatch HUD UI events from response (#1) */
      if (intentValue.toLowerCase() !== "init_sync") {
        dispatchUIEventsFromResponse(data, { party_status: prevPartySnapshot });
      }

      if (!opts.skipLogUpdate) {
        updateWorldLog(data, userLine || null);
        triggerMapTransitionEffects(data);
        triggerRestVisualEffects(data, intentValue);
        triggerCombatVisualEffects(data, userLine || "");
        triggerSpeechBubbles(data);
      }
      maybeShowLootModal(data.environment_objects);
      setNetworkState("链路在线", "ok");
      return data;
    } catch (error) {
      /* Director Trace: reset to idle on error */
      if (_isNarrative && window.BG3DirectorTrace && typeof window.BG3DirectorTrace.setIdle === "function") {
        window.BG3DirectorTrace.setIdle();
      }
      if (error && error.name === "AbortError") {
        return applySilentNetworkFallback(userLine, intentValue, opts);
      }
      return applySilentNetworkFallback(userLine, intentValue, opts);
    } finally {
      if (shouldClearReadContext) {
        clearTransientInteractionContext({ keepDialogueTarget: true });
      }
      setLoading(false);
      resetIdleTimer();
    }
  }

  async function sendMessage(text, intent, character, options = {}) {
    return sendStructuredAction({
      text,
      intent,
      character,
      options,
    });
  }

  function submitInput() {
    const text = els.userInput.value.trim();
    if (!text) return;
    els.userInput.value = "";
    clearTransientInteractionContext({ keepDialogueTarget: true });
    sendMessage(text, null, null, { source: "text_input" });
  }

  function queueCommand(command) {
    if (state.isLoading) return;
    els.userInput.value = command;
    els.userInput.focus();
    window.requestAnimationFrame(submitInput);
  }

  function handleShortcutClick(event) {
    const button = event.target.closest(".shortcut-btn");
    if (!button) return;
    queueCommand(button.dataset.command || "");
  }

  function handleRestClick(event) {
    const button = event.target.closest(".rest-btn");
    if (!button || state.isLoading || isCombatStateActive(state.combatState)) return;

    const restType = normalizeId(button.dataset.restType);
    if (restType === "short") {
      sendMessage("", "SHORT_REST");
      return;
    }
    if (restType === "long") {
      sendMessage("", "LONG_REST");
    }
  }

  function submitDialogueInput() {
    if (state.isLoading || !state.activeDialogueTarget) return;
    const text = String(els.dialogueInput.value || "").trim();
    if (!text) return;
    els.dialogueInput.value = "";
    sendMessage(text, null, null, {
      source: "dialogue_input",
      target: normalizeId(state.activeDialogueTarget),
    });
  }

  function updatePttButtonState() {
    if (!els.pttMicBtn) return;
    els.pttMicBtn.classList.toggle("recording-pulse", state.isPttRecording);
    els.pttMicBtn.setAttribute("aria-pressed", String(state.isPttRecording));
    els.pttMicBtn.textContent = state.isPttRecording ? "🎙️ 正在聆听..." : "🎙️ 按住指令";
    els.pttMicBtn.title = state.isPttRecording ? "正在聆听... 松开发送" : "按住说话，松开发送";
  }

  function stopSpeechRecognition() {
    if (!state.speechRecognition) return;
    if (!state.isPttRecording) return;
    state.isPttRecording = false;
    updatePttButtonState();
    try {
      state.speechRecognition.stop();
    } catch (_error) {
      state.isPttRecording = false;
      updatePttButtonState();
    }
  }

  function startSpeechRecognition() {
    if (!state.speechRecognition || state.isLoading) return;
    if (state.isPttRecording) return;
    state.isPttRecording = true;
    updatePttButtonState();
    try {
      state.speechRecognition.start();
    } catch (_error) {
      state.isPttRecording = false;
      updatePttButtonState();
    }
  }

  function handlePttPressStart(event) {
    if (!state.speechRecognition || state.isLoading) return;
    if (event && event.type === "mousedown" && event.button !== 0) return;
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    startSpeechRecognition();
  }

  function handlePttPressEnd(event) {
    if (!state.speechRecognition || state.isLoading) return;
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    stopSpeechRecognition();
  }

  function initSpeechRecognition() {
    if (!els.pttMicBtn) return;
    if (!SpeechRecognition) {
      state.speechRecognitionSupported = false;
      els.pttMicBtn.disabled = true;
      els.pttMicBtn.title = "当前浏览器不支持语音输入";
      return;
    }

    state.speechRecognitionSupported = true;
    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      state.isPttRecording = true;
      updatePttButtonState();
    };

    recognition.onresult = (event) => {
      const transcript = String(event?.results?.[0]?.[0]?.transcript || "").trim();
      if (!transcript) return;
      if (els.dialogueInput) {
        els.dialogueInput.value = transcript;
        els.dialogueInput.focus();
      }
      if (!state.isLoading) {
        if (state.activeDialogueTarget) {
          submitDialogueInput();
        } else if (els.userInput) {
          els.userInput.value = transcript;
          submitInput();
        }
      }
    };

    recognition.onerror = () => {
      state.isPttRecording = false;
      updatePttButtonState();
    };

    recognition.onend = () => {
      state.isPttRecording = false;
      updatePttButtonState();
    };

    state.speechRecognition = recognition;
    els.pttMicBtn.disabled = false;
    updatePttButtonState();
  }

  function interruptDialogueWithAttack() {
    if (state.isLoading || !state.activeDialogueTarget) return;
    els.dialogueInput.value = "";
    sendMessage("我直接拔出武器攻击！", null, null, {
      source: "dialogue_input",
      target: normalizeId(state.activeDialogueTarget),
    });
  }

  function toggleXrayPanel() {
    if (!els.mainLayout) return;
    const collapsed = els.mainLayout.classList.toggle("xray-collapsed");
    if (els.xrayToggleBtn) {
      els.xrayToggleBtn.setAttribute("aria-expanded", String(!collapsed));
      els.xrayToggleBtn.textContent = collapsed ? "X-Ray +" : "X-Ray";
    }
    window.setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
      if (window.BG3TacticalMap && typeof window.BG3TacticalMap.resize === "function") {
        window.BG3TacticalMap.resize();
      }
    }, 280);
  }

  function handleEnvironmentAction(event) {
    const actionButton = event.target.closest(".object-action");
    if (!actionButton) return;
    if (state.isLoading) return;
    if (actionButton.dataset.loot === "true") {
      openLootModalForTarget(actionButton.dataset.targetId || "");
      return;
    }
    const mapped = mapInteractableToStructuredAction({
      id: actionButton.dataset.targetId || "",
      type: actionButton.dataset.targetType || "",
      label: actionButton.dataset.targetLabel || "",
      name: actionButton.dataset.targetName || "",
    });
    if (!mapped) return;
    sendMessage(mapped.text || "", mapped.intent || null, mapped.character || null, {
      target: mapped.target || "",
      source: mapped.source || "ui_click",
    });
  }

  function handlePartyAction(event) {
    const button = event.target.closest(".item-action");
    const inventorySlot = event.target.closest(".party-view-inventory-slot[data-item-id]");
    const target = button || inventorySlot;
    if (!target || state.isLoading) return;
    if (inventorySlot && button) {
      event.stopPropagation();
    }

    const itemId = normalizeId(target.dataset.itemId);
    const action = normalizeId(target.dataset.partyAction);
    const characterId = normalizeId(target.dataset.ownerId) || "player";
    if (!itemId || !action) return;

    if (action === "inspect") {
      queueCommand("检查 " + itemId);
      return;
    }

    if (action === "equip") {
      const command = characterId === "player" ? "我要装备 " + itemId : "让 " + characterId + " 装备 " + itemId;
      sendMessage(command);
      return;
    }

    if (action === "use") {
      const command = characterId === "player" ? "我要使用 " + itemId : "让 " + characterId + " 使用 " + itemId;
      sendMessage(command);
      return;
    }

    if (action === "unequip") {
      const command = characterId === "player" ? "我要卸下 " + itemId : "让 " + characterId + " 卸下 " + itemId;
      sendMessage(command);
    }
  }

  function bindEvents() {
    els.tacticalToggleBtn.addEventListener("click", toggleTacticalOverlay);
    els.sendBtn.addEventListener("click", submitInput);
    els.userInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitInput();
      }
    });

    document.querySelector(".shortcut-bar").addEventListener("click", handleShortcutClick);
    els.restControls.addEventListener("click", handleRestClick);
    if (els.pttMicBtn) {
      els.pttMicBtn.addEventListener("mousedown", handlePttPressStart);
      els.pttMicBtn.addEventListener("touchstart", handlePttPressStart, { passive: false });
      els.pttMicBtn.addEventListener("mouseup", handlePttPressEnd);
      els.pttMicBtn.addEventListener("mouseleave", handlePttPressEnd);
      els.pttMicBtn.addEventListener("touchend", handlePttPressEnd, { passive: false });
      els.pttMicBtn.addEventListener("touchcancel", handlePttPressEnd, { passive: false });
    }
    els.dialogueSendBtn.addEventListener("click", submitDialogueInput);
    els.dialogueAttackBtn.addEventListener("click", interruptDialogueWithAttack);
    els.dialogueInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitDialogueInput();
      }
    });
    els.xrayToggleBtn.addEventListener("click", toggleXrayPanel);
    els.logFilterBar.addEventListener("click", handleLogFilterClick);
    els.partyRoster.addEventListener("click", handlePartyAction);
    els.partyViewContent.addEventListener("click", handlePartyAction);
    els.environmentList.addEventListener("click", handleEnvironmentAction);

    els.closePartyViewBtn.addEventListener("click", () => setPartyView(false));
    els.partyViewModal.addEventListener("click", (event) => {
      if (event.target === els.partyViewModal) {
        setPartyView(false);
      }
    });
    els.partyViewTabs.addEventListener("click", (event) => {
      const button = event.target.closest(".party-view-tab");
      if (!button) return;
      state.activePartyViewTab = normalizeId(button.dataset.partyTab || "inventory");
      renderPartyView();
    });

    els.closeLootBtn.addEventListener("click", hideLootModal);
    els.lootModal.addEventListener("click", (event) => {
      if (event.target === els.lootModal) {
        hideLootModal();
      }
    });

    els.lootAllBtn.addEventListener("click", () => {
      const targetId = normalizeId(state.currentLootTargetId);
      hideLootModal();
      if (!targetId) return;
      state.seenLootTargets.add(targetId);
      sendMessage("我要搜刮 " + targetId, "ui_action_loot", "player", {
        target: targetId,
        source: "ui_click",
      });
    });

    document.addEventListener("keydown", (event) => {
      if (isEditableTarget(event.target)) return;
      if (event.key === "Escape" && state.partyViewOpen) {
        event.preventDefault();
        setPartyView(false);
        return;
      }
      if (event.key === "Tab" || event.key.toLowerCase() === "i") {
        event.preventDefault();
        togglePartyView();
        return;
      }
      if (event.code === "Space" || event.key === " ") {
        event.preventDefault();
        toggleTacticalOverlay();
      }
    });

    ["keydown", "pointerdown"].forEach((eventName) => {
      document.addEventListener(
        eventName,
        () => {
          if (!state.isLoading) {
            resetIdleTimer();
          }
        },
        { passive: true }
      );
    });
  }

  async function syncInitialState() {
    if (state.hasSyncedInitialState || state.isLoading) return;
    state.hasSyncedInitialState = true;

    const data = await sendMessage("", "init_sync", null, {
      incrementTurn: false,
      skipLogUpdate: true,
    });

    if (!data) {
      state.hasSyncedInitialState = false;
      return;
    }

    appendLogEntry("system", "存档同步", "已接入当前世界状态，战术桌完成初始校准。", {
      color: "#73c6c3",
      sigil: "◌",
      logType: "system",
    });
  }

  async function pollDialogueState() {
    if (state.isLoading) return;
    try {
      const response = await fetchWithTimeout(
        STATE_URL + "?session_id=" + encodeURIComponent(SESSION_ID),
        {},
        BACKEND_REQUEST_TIMEOUT_MS,
      );
      if (!response.ok) return;
      const data = await response.json();
      const partyStatus = safeObject(data.party_status);
      const environmentObjects = safeObject(data.environment_objects);
      const combatState = safeObject(data.combat_state);
      const prevPollParty = { ...state.partyStatus };
      if (Object.keys(partyStatus).length) state.partyStatus = partyStatus;
      if (Object.keys(environmentObjects).length) state.environmentObjects = environmentObjects;
      state.combatState = combatState;
      updateDialogueOverlay(data);
      updateRestControls(state.combatState);
      updateXrayPanel(data);
      /* P1-1: dispatch HUD events from state polling too */
      dispatchUIEventsFromResponse(data, { party_status: prevPollParty });
    } catch (error) {
      if (error && error.name === "AbortError") {
        setNetworkState("链路在线", "ok");
      }
      // Dialogue polling is an enhancement; chat responses remain the source of truth.
    }
  }

  function startDialoguePolling() {
    if (IS_QA_MODE) return;
    window.clearInterval(state.dialoguePollTimer);
    state.dialoguePollTimer = window.setInterval(() => {
      void pollDialogueState();
    }, DIALOGUE_POLL_MS);
  }

  function submitDockInput() {
    if (!els.dockInput) return;
    const text = els.dockInput.value.trim();
    if (!text) return;
    els.dockInput.value = "";
    clearTransientInteractionContext({ keepDialogueTarget: true });
    sendMessage(text, null, null, { source: "dock_input" });
  }

  function bindDockEvents() {
    if (els.dockInput) {
      els.dockInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          submitDockInput();
        }
      });
    }
    if (els.dockSendBtn) {
      els.dockSendBtn.addEventListener("click", submitDockInput);
    }
  }

  function initNewModules() {
    /* Initialize Director Trace Panel */
    if (window.BG3DirectorTrace && typeof window.BG3DirectorTrace.init === "function") {
      window.BG3DirectorTrace.init();
    }

    /* Load and normalize map */
    let normalizedMap = null;
    if (window.BG3TiledAdapter) {
      normalizedMap = window.BG3TiledAdapter.normalizeTiledMap(null);
    }

    /* Initialize Input Controller for WASD */
    if (window.BG3InputController && normalizedMap) {
      window.BG3InputController.init({
        normalizedMap,
        playerStart: normalizedMap.playerStart,
        onNarrativeTrigger: (trigger) => {
          if (QA_NO_IDLE) return;
          const data = trigger && trigger.data ? trigger.data : {};
          const triggerId = (trigger && trigger.id) ? String(trigger.id) : "unknown";
          sendMessage(
            "我踩到了一个触发区域: " + triggerId,
            "trigger_zone",
            null,
            {
              target: triggerId,
              source: "trigger_zone",
            }
          );
        },
        onInteraction: (interactable) => {
          const mapped = mapInteractableToStructuredAction(interactable);
          if (!mapped) return;
          sendMessage(mapped.text || "", mapped.intent || null, mapped.character || null, {
            target: mapped.target || "",
            source: mapped.source || "interaction",
          });
        },
      });
    }

    /* Show initial act progress */
    if (window.BG3HudRenderers) {
      window.BG3HudRenderers.updateActProgress(1);
    }

    state.mapId = MAP_ID;
  }

  /**
   * isNarrativeRequest — determines if an intent/text/source should
   * activate the Director Trace panel.
   *
   * Only these sources activate it:
   *   - trigger zones (intent: trigger_zone)
   *   - E-key interactions (source: interaction)
   *   - dialogue / choices (intent contains 'dialogue', 'choice', 'talk')
   *   - companion interrupts (intent: companion_interrupt)
   *   - explicit user commands (non-empty text without system intents)
   *
   * These do NOT activate it:
   *   - init_sync
   *   - trigger_idle_banter
   *   - ui_action_loot (loot pickup is a UI action, not narrative)
   *   - state polling
   */
  function isNarrativeRequest(intent, text, source) {
    const i = String(intent || "").toLowerCase().trim();
    const t = String(text || "").trim();
    const s = String(source || "").toLowerCase().trim();

    /* Explicit non-narrative intents */
    const NON_NARRATIVE = ["init_sync", "trigger_idle_banter", "ui_action_loot"];
    if (NON_NARRATIVE.includes(i)) return false;

    /* Known narrative sources */
    if (s === "interaction" || s === "trigger_zone") return true;
    if (i === "trigger_zone" || i === "companion_interrupt") return true;
    if (/dialogue|choice|talk|speak|converse/i.test(i)) return true;

    /* User typed something meaningful */
    if (t.length > 0 && !i) return true;
    if (t.length > 0 && i) return true;

    return false;
  }

  function dispatchUIEventsFromResponse(data, previousState) {
    if (!window.BG3UIEventAdapter || !window.BG3HudRenderers) return;
    const events = window.BG3UIEventAdapter.extractUIEvents(data, previousState);
    window.BG3HudRenderers.dispatchUIEvents(events);
  }

  async function boot() {
    const qa = readQaActions();
    initSpeechRecognition();
    bindEvents();
    bindDockEvents();
    initNewModules();
    setTacticalOverlay(false);
    renderChrome(LOCATION_LABELS[MAP_ID] || "废弃死灵实验室");
    renderPartyRoster();
    renderEnvironmentObjects();
    renderTacticalGrid(state.partyStatus, state.environmentObjects, state.mapData);
    renderInitiativeTracker(state.combatState, false);
    updateRestControls(state.combatState);
    updateXrayPanel({});
    appendLogEntry("system", "终端接入", "已进入 " + (LOCATION_LABELS[MAP_ID] || MAP_ID) + "。WASD 移动探索，E 键交互。", {
      color: "#d0ab67",
      sigil: "◎",
      logType: "system",
    });

    if (qa.shouldToggleXray) {
      window.setTimeout(() => {
        const isCollapsed = els.mainLayout && els.mainLayout.classList.contains("xray-collapsed");
        const shouldToggle =
          qa.xrayMode === "toggle"
          || (qa.xrayMode === "collapse" && !isCollapsed)
          || (qa.xrayMode === "expand" && isCollapsed);
        if (shouldToggle) {
          toggleXrayPanel();
        }
      }, qa.xrayDelay);
    }

    if (qa.traceCommand || qa.traceIntent) {
      if (qa.previewTrace) {
        clearXrayNodeTraceAnimation();
        applyXrayNodeClasses([], "");
        window.setTimeout(() => {
          const previewTrace = inferNodeTrace({}, qa.traceCommand, qa.traceIntent || "");
          setXrayNodeTrace(previewTrace, { animate: true });
        }, 120);
      }

      window.setTimeout(() => {
        void sendMessage(qa.traceCommand, qa.traceIntent || null);
      }, qa.traceDelay);
    }

    if (!IS_QA_MODE) {
      await syncInitialState();
      startDialoguePolling();
    }
  }

  function exposeTestApi() {
    if (window.__BG3_ENABLE_TEST_API__ !== true) return;
    window.__BG3_APP_TEST_API__ = {
      boot,
      sendMessage,
      sendStructuredAction,
      buildChatPayload,
      pollDialogueState,
      updateDialogueOverlay,
      updateXrayPanel,
      interruptDialogueWithAttack,
      inferNodeTrace,
      normalizeNodeName,
      isNarrativeRequest,
      dispatchUIEventsFromResponse,
      state,
      els,
      MAP_ID,
      SESSION_ID,
      ITEM_META,
    };
  }

  exposeTestApi();

  document.addEventListener("DOMContentLoaded", () => {
    void boot();
  });
})();
