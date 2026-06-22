/**
 * input-controller.js — WASD movement, E interaction, trigger detection.
 * Key rule: WASD moves are 100% local — NO /api/chat call.
 * Fix: trigger_once dedup — each trigger fires only once until player leaves and re-enters.
 * Exposed on window.BG3InputController.
 */
(() => {
  "use strict";
  let normalizedMap = null;
  let playerPos = { x: 2, y: 2 };
  let lastMoveAt = 0;
  const COOLDOWN = 150;
  let onNarrativeTrigger = null;
  let onInteraction = null;
  let onPlayerMoved = null;
  let onHighlightChanged = null;
  let formatInteractionHint = null;
  let hintEl = null;
  let enabled = true;
  let currentHighlightedInteractable = null;

  /**
   * trigger_once dedup:
   * activeTriggerIds — set of trigger IDs the player is currently standing on.
   * firedTriggerIds  — set of trigger IDs that have already fired and not yet exited.
   * A trigger only fires when: entered AND not in firedTriggerIds.
   * It is removed from firedTriggerIds when the player leaves the trigger zone.
   */
  const activeTriggerIds = new Set();
  const firedTriggerIds = new Set();

  function safeArr(v) { return Array.isArray(v) ? v : []; }
  function safeObj(v) { return v && typeof v === "object" ? v : {}; }
  function normalizeId(v) { return String(v || "").trim().toLowerCase(); }

  function isBlocked(x, y) {
    if (!normalizedMap) return true;
    const { collision, width, height } = normalizedMap;
    if (x < 0 || y < 0 || x >= width || y >= height) return true;
    if (!isVisibleMovementCell(x, y)) return true;
    return Boolean(collision && collision[y] && collision[y][x]);
  }

  function pointInRoom(x, y, room) {
    const r = safeObj(room);
    const rx = Number(r.x) || 0;
    const ry = Number(r.y) || 0;
    const rw = Math.max(1, Number(r.w) || 1);
    const rh = Math.max(1, Number(r.h) || 1);
    return x >= rx && x < rx + rw && y >= ry && y < ry + rh;
  }

  function distanceToInteractable(interactable) {
    const it = safeObj(interactable);
    const ix = Math.round(Number(it.x) || 0);
    const iy = Math.round(Number(it.y) || 0);
    const iw = Math.max(1, Math.round(Number(it.w ?? it.width ?? safeObj(it.data).w ?? safeObj(it.data).width) || 1));
    const ih = Math.max(1, Math.round(Number(it.h ?? it.height ?? safeObj(it.data).h ?? safeObj(it.data).height) || 1));
    const px = Math.round(Number(playerPos.x) || 0);
    const py = Math.round(Number(playerPos.y) || 0);
    const dx = px < ix ? ix - px : (px >= ix + iw ? px - (ix + iw - 1) : 0);
    const dy = py < iy ? iy - py : (py >= iy + ih ? py - (iy + ih - 1) : 0);
    const rectDistance = dx + dy;
    const cells = safeArr(it.interaction_cells || safeObj(it.data).interaction_cells);
    if (!cells.length) return rectDistance;
    const cellDistance = cells.reduce((best, cell) => {
      const cx = Math.round(Number(safeObj(cell).x) || 0);
      const cy = Math.round(Number(safeObj(cell).y) || 0);
      return Math.min(best, Math.abs(px - cx) + Math.abs(py - cy));
    }, Number.POSITIVE_INFINITY);
    return Math.min(rectDistance, cellDistance);
  }

  function isVisibleMovementCell(x, y) {
    const map = safeObj(normalizedMap);
    const rooms = safeArr(map.rooms);
    if (!rooms.length) return true;
    const visibleRoomIds = safeArr(map.visible_rooms || map.visibleRooms)
      .map((roomId) => normalizeId(roomId))
      .filter(Boolean);
    if (!visibleRoomIds.length) return true;
    const room = rooms.find((candidate) => pointInRoom(x, y, candidate));
    if (!room) return false;
    return visibleRoomIds.includes(normalizeId(safeObj(room).id));
  }

  function refreshTriggerOccupancy(x, y) {
    if (!normalizedMap) return;
    const currentIds = new Set();
    safeArr(normalizedMap.triggers).forEach((t) => {
      const tid = t.id || "";
      if (x >= t.x && x < t.x + (t.w || 1) && y >= t.y && y < t.y + (t.h || 1)) {
        currentIds.add(tid);
      }
    });
    firedTriggerIds.forEach((tid) => {
      if (!currentIds.has(tid)) {
        firedTriggerIds.delete(tid);
      }
    });
    activeTriggerIds.clear();
    currentIds.forEach((tid) => activeTriggerIds.add(tid));
  }

  function movePlayer(dx, dy) {
    if (!enabled) return false;
    if (Date.now() - lastMoveAt < COOLDOWN) return false;
    const nx = playerPos.x + dx, ny = playerPos.y + dy;
    if (isBlocked(nx, ny)) return false;
    const previousPos = { x: playerPos.x, y: playerPos.y };
    lastMoveAt = Date.now();
    playerPos = { x: nx, y: ny };
    if (window.BG3TacticalMap && typeof window.BG3TacticalMap.movePlayerLocal === "function") {
      window.BG3TacticalMap.movePlayerLocal(nx, ny);
    }
    if (window.BG3DirectorTrace && typeof window.BG3DirectorTrace.setIdle === "function") {
      window.BG3DirectorTrace.setIdle({ force: true });
    }
    checkTriggers(nx, ny, previousPos);
    updateHint();
    if (typeof onPlayerMoved === "function") onPlayerMoved(nx, ny);
    return true;
  }

  function checkTriggers(x, y, previousPos) {
    if (!normalizedMap) return;

    /* Determine which trigger zones the player is currently inside */
    const currentIds = new Set();
    safeArr(normalizedMap.triggers).forEach((t) => {
      const tid = t.id || "";
      if (x >= t.x && x < t.x + (t.w || 1) && y >= t.y && y < t.y + (t.h || 1)) {
        currentIds.add(tid);
        /* Fire only if not already fired for this entry */
        if (!firedTriggerIds.has(tid)) {
          firedTriggerIds.add(tid);
          if (typeof onNarrativeTrigger === "function") {
            onNarrativeTrigger(t, {
              triggerId: tid,
              from: previousPos ? { x: previousPos.x, y: previousPos.y } : null,
              to: { x, y },
            });
          }
        }
      }
    });

    /* Clear fired state for triggers the player has left */
    firedTriggerIds.forEach((tid) => {
      if (!currentIds.has(tid)) {
        firedTriggerIds.delete(tid);
      }
    });

    /* Update active set */
    activeTriggerIds.clear();
    currentIds.forEach((tid) => activeTriggerIds.add(tid));
  }

  function isTrapInteractable(interactable) {
    const it = safeObj(interactable);
    const id = normalizeId(it.id);
    const type = normalizeId(it.type || safeObj(it.data).type);
    return type === "trap" || id.includes("trap");
  }

  function isTrapVisible(interactable) {
    const it = safeObj(interactable);
    const status = normalizeId(it.status);
    const isHidden = Boolean(it.isHidden === true || it.is_hidden === true || status === "hidden");
    const revealed = Boolean(
      it.revealed === true
      || it.is_revealed === true
      || it.discovered === true
      || it.is_discovered === true
      || status === "revealed"
      || status === "discovered"
    );
    return !isHidden || revealed;
  }

  function resolvePlayerRoomId() {
    const map = safeObj(normalizedMap);
    const rooms = safeArr(map.rooms);
    if (!rooms.length) return "";
    const px = Number(playerPos.x);
    const py = Number(playerPos.y);
    const room = rooms.find((candidate) => {
      const r = safeObj(candidate);
      const rx = Number(r.x) || 0;
      const ry = Number(r.y) || 0;
      const rw = Math.max(1, Number(r.w) || 1);
      const rh = Math.max(1, Number(r.h) || 1);
      return px >= rx && px < rx + rw && py >= ry && py < ry + rh;
    });
    return room ? String(safeObj(room).id || "") : "";
  }

  function resolveInteractableRoomId(interactable) {
    const it = safeObj(interactable);
    const data = safeObj(it.data);
    return String(it.room_id || data.room_id || data.roomId || "").trim();
  }

  function isExitDoor(interactable) {
    const it = safeObj(interactable);
    const id = normalizeId(it.id);
    return id === "heavy_oak_door_1" || id === "exit_door";
  }

  function connectedRoomIds(interactable) {
    const it = safeObj(interactable);
    const data = safeObj(it.data);
    return [
      it.room_id,
      data.room_id,
      data.roomId,
      it.connects_from,
      data.connects_from,
      it.connects_to,
      data.connects_to,
    ].map((roomId) => normalizeId(roomId)).filter(Boolean);
  }

  function roomCZonePriority(id) {
    const px = Math.round(Number(playerPos.x) || 0);
    const py = Math.round(Number(playerPos.y) || 0);
    if (id === "necromancer_diary" && px <= 2 && py <= 11) return -6;
    if (id === "chemical_notes" && px >= 3 && py <= 11) return -6;
    if (id === "iron_key_sketch" && px <= 2 && py >= 12) return -6;
    if ((id === "study_chest" || id === "chest_1") && px >= 3 && py >= 12) return -6;
    return 0;
  }

  function isRoomCStudyProp(interactable) {
    const it = safeObj(interactable);
    const id = normalizeId(it.id);
    return id === "necromancer_diary"
      || id === "chemical_notes"
      || id === "iron_key_sketch"
      || id === "study_chest"
      || id === "chest_1";
  }

  function maxInteractionDistance(interactable) {
    const playerRoomId = normalizeId(resolvePlayerRoomId());
    if (playerRoomId === "room_c_secret_study" && isRoomCStudyProp(interactable)) return 2;
    return 1;
  }

  function getInteractablePriority(interactable) {
    const it = safeObj(interactable);
    const type = normalizeId(it.type || safeObj(it.data).type);
    const id = normalizeId(it.id);
    const playerRoomId = normalizeId(resolvePlayerRoomId());
    const targetRoomId = normalizeId(resolveInteractableRoomId(it));
    const connectedRooms = connectedRoomIds(it);

    if (isTrapInteractable(it)) return 20;

    if (id === "cracked_wall") return -1;

    if (playerRoomId === "room_c_secret_study") {
      if (id === "necromancer_diary") return roomCZonePriority(id);
      if (id === "chemical_notes") return roomCZonePriority(id) + 1;
      if (id === "iron_key_sketch") return roomCZonePriority(id) + 1;
      if (id === "study_chest" || id === "chest_1") return roomCZonePriority(id) + 2;
      if (id === "door_b_to_c" || connectedRooms.includes("room_b_corridor")) return 8;
      if (targetRoomId && targetRoomId !== "room_c_secret_study") return 12;
      if (type === "readable") return 3;
      if (type === "chest" || type === "container") return 4;
    }

    if (playerRoomId === "room_d_lab" || targetRoomId === "room_d_lab" || connectedRooms.includes("room_d_lab")) {
      if (id === "gribbo" || type === "npc" || type === "character") return 0;
      if (id === "poison_valve" || id === "potion_tank" || type === "poison_valve") return 1;
      if (isExitDoor(it)) return 2;
      if (id === "door_b_to_d" || id === "door_b_to_c") return 9;
    }

    if (type === "door" || id.includes("door")) return 0;
    if (type === "readable" || id === "necromancer_diary") return 1;
    if (type === "npc" || type === "character") return 2;
    if (type === "loot" || type === "chest" || type === "corpse" || type === "container") return 3;
    return 4;
  }

  function findNearbyDiscoveredTrap() {
    if (!normalizedMap) return null;
    const candidates = safeArr(normalizedMap.interactables)
      .filter((it) => isTrapInteractable(it) && isTrapVisible(it))
      .map((it, index) => {
        const distance = distanceToInteractable(it);
        return { it, index, distance };
      })
      .filter(({ distance }) => distance <= 1)
      .sort((left, right) => {
        if (left.distance !== right.distance) return left.distance - right.distance;
        return left.index - right.index;
      });
    return candidates.length ? candidates[0].it : null;
  }

  function findNearbyInteractable() {
    if (!normalizedMap) return null;
    const candidates = safeArr(normalizedMap.interactables)
      .map((it, index) => {
        const distance = distanceToInteractable(it);
        return { it, index, distance };
      })
      .filter(({ it, distance }) => distance <= maxInteractionDistance(it))
      .filter(({ it }) => {
        if (!isTrapInteractable(it)) return true;
        return isTrapVisible(it);
      })
      .sort((left, right) => {
        const priorityDelta = getInteractablePriority(left.it) - getInteractablePriority(right.it);
        if (priorityDelta !== 0) return priorityDelta;
        if (left.distance !== right.distance) return left.distance - right.distance;
        return left.index - right.index;
      });
    return candidates.length ? candidates[0].it : null;
  }

  function interact() {
    if (!enabled) return;
    const target = currentHighlightedInteractable;
    if (target && typeof onInteraction === "function") onInteraction(target);
  }

  function updateHint() {
    if (!hintEl) hintEl = document.getElementById("interaction-hint");
    if (!hintEl) return;
    const previousId = currentHighlightedInteractable ? String(currentHighlightedInteractable.id || "") : "";
    const t = findNearbyInteractable();
    currentHighlightedInteractable = t;
    if (t) {
      const fallbackText = "E 交互：" + (t.label || t.name || t.id || "未知目标") + " [" + (t.id || "") + "]";
      const formatter = typeof formatInteractionHint === "function"
        ? formatInteractionHint
        : null;
      hintEl.textContent = String(
        formatter ? formatter({ ...safeObj(t) }, { x: playerPos.x, y: playerPos.y }) : fallbackText
      );
      hintEl.classList.toggle("hint-danger", isTrapInteractable(t));
      hintEl.classList.remove("hint-hidden");
    } else {
      currentHighlightedInteractable = null;
      const nearbyTrap = findNearbyDiscoveredTrap();
      if (nearbyTrap) {
        const label = nearbyTrap.label || nearbyTrap.name || "危险陷阱";
        const trapId = nearbyTrap.id || "";
        hintEl.textContent = "危险：" + label + (trapId ? " [" + trapId + "]" : "");
        hintEl.classList.add("hint-danger");
        hintEl.classList.remove("hint-hidden");
      } else {
        hintEl.textContent = "";
        hintEl.classList.add("hint-hidden");
        hintEl.classList.remove("hint-danger");
      }
    }
    const nextId = currentHighlightedInteractable ? String(currentHighlightedInteractable.id || "") : "";
    if (previousId !== nextId && typeof onHighlightChanged === "function") {
      onHighlightChanged(currentHighlightedInteractable ? { ...currentHighlightedInteractable } : null);
    }
  }

  function isTextFocused() {
    const a = document.activeElement;
    if (!a) return false;
    const tag = a.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || a.isContentEditable;
  }

  function isMapControlKey(k) {
    return k === "w"
      || k === "a"
      || k === "s"
      || k === "d"
      || k === "e"
      || k === "arrowup"
      || k === "arrowdown"
      || k === "arrowleft"
      || k === "arrowright";
  }

  function shouldUseMapControlFromTextFocus(event, k) {
    const a = document.activeElement;
    if (!a || !isMapControlKey(k)) return false;
    if (event.metaKey || event.ctrlKey || event.altKey) return false;
    if (!["dock-input", "user-input"].includes(String(a.id || ""))) return false;
    const value = typeof a.value === "string" ? a.value : "";
    return value.trim().length === 0;
  }

  function isOverlayActive() {
    const d = document.getElementById("dialogue-overlay");
    if (d && !d.classList.contains("hidden") && d.classList.contains("dialogue-overlay--blocking")) return true;
    const l = document.getElementById("loot-modal");
    if (l && !l.classList.contains("hidden")) return true;
    const t = document.getElementById("tactical-pause-overlay");
    if (t && t.classList.contains("active")) return true;
    const p = document.getElementById("party-view-modal");
    if (p && p.classList.contains("active")) return true;
    return false;
  }

  function handleKeyDown(e) {
    if (!enabled || isOverlayActive()) return;
    const k = e.key.toLowerCase();
    if (isTextFocused()) {
      if (!shouldUseMapControlFromTextFocus(e, k)) return;
      const active = document.activeElement;
      if (active && typeof active.blur === "function") active.blur();
    }
    if (k === "w" || k === "arrowup") { e.preventDefault(); movePlayer(0, -1); }
    else if (k === "s" || k === "arrowdown") { e.preventDefault(); movePlayer(0, 1); }
    else if (k === "a" || k === "arrowleft") { e.preventDefault(); movePlayer(-1, 0); }
    else if (k === "d" || k === "arrowright") { e.preventDefault(); movePlayer(1, 0); }
    else if (k === "e") { e.preventDefault(); interact(); }
  }

  function init(opts) {
    const o = opts && typeof opts === "object" ? opts : {};
    if (o.normalizedMap) normalizedMap = o.normalizedMap;
    if (o.playerStart) playerPos = { x: Number(o.playerStart.x) || 0, y: Number(o.playerStart.y) || 0 };
    if (typeof o.onNarrativeTrigger === "function") onNarrativeTrigger = o.onNarrativeTrigger;
    if (typeof o.onInteraction === "function") onInteraction = o.onInteraction;
    if (typeof o.onPlayerMoved === "function") onPlayerMoved = o.onPlayerMoved;
    if (typeof o.onHighlightChanged === "function") onHighlightChanged = o.onHighlightChanged;
    if (typeof o.formatInteractionHint === "function") formatInteractionHint = o.formatInteractionHint;
    firedTriggerIds.clear();
    activeTriggerIds.clear();
    document.addEventListener("keydown", handleKeyDown);
    updateHint();
  }

  function setMap(m) { normalizedMap = m; firedTriggerIds.clear(); activeTriggerIds.clear(); currentHighlightedInteractable = null; updateHint(); }
  function setPlayerPosition(x, y) { playerPos = { x: Number(x) || 0, y: Number(y) || 0 }; updateHint(); }
  function rollbackPlayerTo(x, y) {
    playerPos = { x: Number(x) || 0, y: Number(y) || 0 };
    if (window.BG3TacticalMap && typeof window.BG3TacticalMap.rollbackPlayerLocal === "function") {
      window.BG3TacticalMap.rollbackPlayerLocal(playerPos.x, playerPos.y);
    }
    refreshTriggerOccupancy(playerPos.x, playerPos.y);
    updateHint();
  }
  function getPlayerPosition() { return { ...playerPos }; }
  function getCurrentHighlightedInteractable() {
    return currentHighlightedInteractable ? { ...currentHighlightedInteractable } : null;
  }
  function setEnabled(v) { enabled = Boolean(v); }
  function setHintFormatter(fn) { formatInteractionHint = typeof fn === "function" ? fn : null; updateHint(); }
  function destroy() {
    document.removeEventListener("keydown", handleKeyDown);
    firedTriggerIds.clear();
    activeTriggerIds.clear();
    currentHighlightedInteractable = null;
    onHighlightChanged = null;
    formatInteractionHint = null;
  }

  window.BG3InputController = Object.freeze({
    init, setMap, setPlayerPosition, getPlayerPosition, setEnabled,
    movePlayer, interact, findNearbyInteractable, getCurrentHighlightedInteractable,
    rollbackPlayerTo, updateHint, setHintFormatter, destroy,
  });
})();
