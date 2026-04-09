(() => {
  const API_URL = "/api/chat";
  const SESSION_ID = "test_consume_003";
  const IDLE_MS = 30000;

  const SPEAKER_META = {
    player: { name: "玩家", color: "#6eb5ff", sigil: "⌘" },
    shadowheart: { name: "影心", color: "#9b84c6", sigil: "✦" },
    astarion: { name: "阿斯代伦", color: "#c97a75", sigil: "🜂" },
    laezel: { name: "莱埃泽尔", color: "#70b99d", sigil: "⚔" },
    dm: { name: "地下城主", color: "#d0ab67", sigil: "☍" },
    npc: { name: "同行者", color: "#b29f7e", sigil: "◈" },
  };

  const ITEM_META = {
    gold: { label: "金币", icon: "🪙" },
    gold_coin: { label: "金币", icon: "🪙" },
    rusty_dagger: { label: "生锈匕首", icon: "🗡" },
    burnt_map: { label: "烧焦地图", icon: "🗺" },
    healing_potion: { label: "治疗药水", icon: "🧪" },
    mysterious_artifact: { label: "神秘遗物", icon: "🜄" },
    rusty_key: { label: "锈钥匙", icon: "🗝" },
  };

  const LOCATION_LABELS = {
    camp_center: "营地中央",
    camp_fire: "篝火",
    iron_chest: "铁箱",
  };

  const state = {
    partyStatus: {},
    environmentObjects: {},
    playerInventory: {},
    activeLogFilters: new Set(["dialogue", "system", "narration"]),
    hasSyncedInitialState: false,
    turnCount: 0,
    idleTimer: null,
    isLoading: false,
    currentLootTargetId: "",
    seenLootTargets: new Set(),
  };

  const els = {
    currentLocation: document.getElementById("current-location"),
    networkState: document.getElementById("network-state"),
    turnCounter: document.getElementById("turn-counter"),
    tacticalGrid: document.getElementById("tactical-grid"),
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
  };

  function setNetworkState(text, mode) {
    els.networkState.textContent = text;
    els.networkState.dataset.state = mode;
  }

  function safeObject(value) {
    return value && typeof value === "object" ? value : {};
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

  function getInitials(id) {
    const clean = normalizeId(id).replace(/[^a-z0-9]/g, "");
    if (!clean) return "??";
    return clean.slice(0, 2).toUpperCase();
  }

  function formatLocation(raw) {
    const key = normalizeId(raw);
    return LOCATION_LABELS[key] || raw || "未知地标";
  }

  function itemMeta(itemId) {
    const key = normalizeId(itemId);
    return ITEM_META[key] || { label: prettifyId(itemId), icon: "◻" };
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function normalizeGridCoord(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return null;
    return clamp(Math.round(num), 0, 9);
  }

  function readGridPosition(data) {
    const entity = safeObject(data);
    const x = normalizeGridCoord(entity.x);
    const y = normalizeGridCoord(entity.y);
    if (x === null || y === null) return null;
    return { x, y };
  }

  function tokenLabel(id, data) {
    const name = String(safeObject(data).name || id || "").trim();
    if (!name) return "?";
    const cjkMatch = name.match(/[\u4e00-\u9fff]/);
    if (cjkMatch) return cjkMatch[0];
    const alnumMatch = name.match(/[A-Za-z0-9]/);
    return alnumMatch ? alnumMatch[0].toUpperCase() : name.slice(0, 1).toUpperCase();
  }

  function tokenClass(id, data, source) {
    const entity = safeObject(data);
    if (normalizeId(id) === "player") return "token-player";
    if (source === "environment") {
      return normalizeId(entity.faction) === "hostile" ? "token-hostile" : "token-object";
    }
    return normalizeId(entity.faction) === "hostile" ? "token-hostile" : "token-neutral";
  }

  function objectEntries(obj) {
    return Object.entries(safeObject(obj)).filter(([, value]) => value && typeof value === "object");
  }

  function inventoryEntries(inv) {
    return Object.entries(safeObject(inv)).filter(([, count]) => Number(count) > 0);
  }

  function canLootTarget(target) {
    const data = safeObject(target);
    const status = normalizeId(data.status);
    return inventoryEntries(data.inventory).length > 0 && (status === "open" || status === "opened" || status === "dead");
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

  function renderTacticalGrid(partyStatus, environmentObjects) {
    const host = els.tacticalGrid;
    if (!host) return;

    const occupants = [];
    const registerOccupant = (id, rawData, source) => {
      const position = readGridPosition(rawData);
      if (!position) return;
      occupants.push({ id, data: safeObject(rawData), source, x: position.x, y: position.y });
    };

    objectEntries(partyStatus).forEach(([id, data]) => {
      registerOccupant(id, data, "party");
    });

    objectEntries(environmentObjects).forEach(([id, data]) => {
      registerOccupant(id, data, "environment");
    });

    host.querySelectorAll(".grid-cell").forEach((cell) => cell.remove());
    const cellFragment = document.createDocumentFragment();

    for (let y = 0; y < 10; y += 1) {
      for (let x = 0; x < 10; x += 1) {
        const cell = document.createElement("div");
        cell.className = "grid-cell";
        cell.dataset.x = String(x);
        cell.dataset.y = String(y);
        cellFragment.appendChild(cell);
      }
    }

    host.appendChild(cellFragment);

    const activeTokenIds = new Set();
    occupants.forEach(({ id, data, source, x, y }) => {
      const tokenId = "token-" + normalizeId(id);
      let token = document.getElementById(tokenId);

      if (!token) {
        token = document.createElement("div");
        token.id = tokenId;
        token.dataset.entityId = normalizeId(id);
        token.className = "token " + tokenClass(id, data, source);
        token.textContent = tokenLabel(id, data);
        token.title = safeObject(data).name || prettifyId(id);
        token.style.left = x * 10 + "%";
        token.style.top = y * 10 + "%";
        host.appendChild(token);
      }

      token.className = "token " + tokenClass(id, data, source);
      token.textContent = tokenLabel(id, data);
      token.title = safeObject(data).name || prettifyId(id);
      token.style.left = x * 10 + "%";
      token.style.top = y * 10 + "%";

      activeTokenIds.add(normalizeId(id));
    });

    host.querySelectorAll(".token[data-entity-id]").forEach((token) => {
      if (!activeTokenIds.has(token.dataset.entityId || "")) {
        token.remove();
      }
    });
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

    const pack = document.createElement("div");
    pack.className = "party-pack";

    const invItems = inventoryEntries(data.inventory).slice(0, 4);
    if (invItems.length === 0) {
      pack.appendChild(makeItemTag("空背包", "⟡"));
    } else {
      invItems.forEach(([itemId, count]) => {
        const metaItem = itemMeta(itemId);
        pack.appendChild(makeItemTag(metaItem.label + " x" + count, metaItem.icon));
      });
    }

    content.appendChild(head);
    content.appendChild(bars);
    content.appendChild(pack);

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
    const playerData = {
      ...safeObject(party.player),
      hp: safeObject(party.player).hp ?? 20,
      max_hp: safeObject(party.player).max_hp ?? safeObject(party.player).hp ?? 20,
      affection: safeObject(party.player).affection ?? 100,
      position: safeObject(party.player).position || "camp_center",
      inventory: state.playerInventory,
    };
    fragment.appendChild(createPartyCard("player", playerData));

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
    els.userInput.disabled = loading;
    els.sendBtn.disabled = loading;
    els.sendBtn.textContent = loading ? "命运演算中…" : "执行指令";
    els.shortcutButtons.forEach((button) => {
      button.disabled = loading;
    });
    Array.from(document.querySelectorAll(".object-action")).forEach((button) => {
      button.disabled = loading;
    });
    els.lootAllBtn.disabled = loading;
    if (loading) {
      setNetworkState("命运演算中", "loading");
    }
  }

  function resetIdleTimer() {
    window.clearTimeout(state.idleTimer);
    state.idleTimer = window.setTimeout(() => {
      sendMessage("", "trigger_idle_banter");
    }, IDLE_MS);
  }

  async function sendMessage(text, intent, character, options = {}) {
    const userLine = String(text || "").trim();
    const intentValue = intent ? String(intent).trim() : "";
    const opts = options && typeof options === "object" ? options : {};

    if (!userLine && !intentValue) {
      return;
    }

    setLoading(true);

    const payload = {
      user_input: userLine,
      intent: intentValue || null,
      session_id: SESSION_ID,
    };

    const characterId = character ? normalizeId(character) : "";
    if (characterId) {
      payload.character = characterId;
    }

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorText = await response.text();
        setNetworkState("通讯受阻", "error");
        appendLogEntry("system", "链路故障", "HTTP " + response.status + " · " + errorText, {
          color: "#e28a80",
          sigil: "⚠",
        });
        return;
      }

      const data = await response.json();
      if (opts.incrementTurn !== false) {
        state.turnCount += 1;
      }
      state.partyStatus = safeObject(data.party_status);
      state.environmentObjects = safeObject(data.environment_objects);
      state.playerInventory = safeObject(data.player_inventory);

      if (data.current_location) {
        renderChrome(data.current_location);
      } else {
        renderChrome(els.currentLocation.textContent);
      }

      renderPartyRoster();
      renderEnvironmentObjects();
      renderTacticalGrid(state.partyStatus, state.environmentObjects);
      if (!opts.skipLogUpdate) {
        updateWorldLog(data, userLine || null);
      }
      maybeShowLootModal(data.environment_objects);
      setNetworkState("链路在线", "ok");
      return data;
    } catch (error) {
      setNetworkState("通讯受阻", "error");
      appendLogEntry("system", "网络异常", String(error.message || error), {
        color: "#e28a80",
        sigil: "⚠",
        logType: "system",
      });
    } finally {
      setLoading(false);
      resetIdleTimer();
    }
  }

  function submitInput() {
    const text = els.userInput.value.trim();
    if (!text) return;
    els.userInput.value = "";
    sendMessage(text, null);
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

  function handleEnvironmentAction(event) {
    const actionButton = event.target.closest(".object-action");
    if (!actionButton) return;
    if (actionButton.dataset.loot === "true") {
      openLootModalForTarget(actionButton.dataset.targetId || "");
      return;
    }
    queueCommand(actionButton.dataset.command || "");
  }

  function bindEvents() {
    els.sendBtn.addEventListener("click", submitInput);
    els.userInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitInput();
      }
    });

    document.querySelector(".shortcut-bar").addEventListener("click", handleShortcutClick);
    els.logFilterBar.addEventListener("click", handleLogFilterClick);
    els.environmentList.addEventListener("click", handleEnvironmentAction);

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
      sendMessage("我要搜刮 " + targetId, "ui_action_loot", "player");
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

  async function boot() {
    bindEvents();
    renderChrome("幽暗地域营地");
    renderPartyRoster();
    renderEnvironmentObjects();
    renderTacticalGrid(state.partyStatus, state.environmentObjects);
    appendLogEntry("system", "终端接入", "战术桌已连入 `/api/chat`。发出第一条指令后，主叙事区会开始记录世界变化。", {
      color: "#d0ab67",
      sigil: "◎",
      logType: "system",
    });
    await syncInitialState();
  }

  document.addEventListener("DOMContentLoaded", () => {
    void boot();
  });
})();
