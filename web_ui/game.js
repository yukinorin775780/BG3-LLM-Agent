(() => {
  const DEFAULT_MAP_DATA = {
    id: "",
    width: 10,
    height: 10,
    obstacles: [],
    grid: [],
    collision: [],
    los_blockers: [],
    ground_types: [],
  };

  const FALLBACK_STATE = {
    partyStatus: {
      player: { name: "玩家", faction: "player", x: 4, y: 5 },
    },
    environmentObjects: {
      goblin_1: { name: "地精", faction: "hostile", status: "alive", x: 6, y: 5 },
    },
    mapData: DEFAULT_MAP_DATA,
  };

  const SPRITE_KEYS = Object.freeze({
    tiles: "dungeon_tiles",
    actors: "dungeon_characters",
  });

  const SPRITE_SHEETS = Object.freeze({
    tiles: {
      path: "assets/2D Pixel Dungeon Asset Pack/character and tileset/Dungeon_Tileset.png",
      frameWidth: 16,
      frameHeight: 16,
    },
    actors: {
      path: "assets/2D Pixel Dungeon Asset Pack/character and tileset/Dungeon_Character.png",
      frameWidth: 16,
      frameHeight: 16,
    },
  });

  const DEPTH_LAYERS = Object.freeze({
    floor: 0,
    ambience: 0.35,
    environment: 1,
    overlay: 1.6,
    actors: 2,
    interactFx: 3,
  });

  const TILE_FRAMES = Object.freeze({
    floor: [11, 12, 13, 21, 22, 23, 31, 32, 33, 61, 62, 63, 71, 72, 73],
    wall: [0, 1, 2, 3, 4, 10, 20, 30, 40, 41, 42, 43, 44, 50, 51, 52, 53, 55],
    rubble: [49, 59, 64, 68],
    campfire: [90, 91, 92, 93],
    prop: [80, 81, 83],
    trap: [65, 77],
    doorClosed: 39,
    doorOpen: 57,
    chestClosed: 84,
    chestOpen: 85,
    loot: [86, 87, 89, 97, 98],
    poison: 97,
    locked: 88,
  });

  const WALL_FRAME = 1;
  const FLOOR_FRAME = 11;

  const ACTOR_FRAMES = Object.freeze({
    player: [1, 4, 15, 18],
    hostile: [11, 12, 13, 25, 26, 27],
    neutral: [2, 3, 16, 17],
    object: [9, 10, 23, 24],
    partyById: {
      player: 1,
      astarion: 12,
      shadowheart: 16,
      laezel: 18,
      lae_zel: 18,
      gribbo: 27,
    },
    hostileById: {
      goblin_1: 11,
    },
  });

  const ACTOR_TINTS = Object.freeze({
    player: 0xf4e1b8,
    astarion: 0xd29f93,
    shadowheart: 0xc9b9f8,
    laezel: 0x9fdcb2,
    lae_zel: 0x9fdcb2,
    gribbo: 0xa7d8bf,
  });

  const GROUND_TYPE_TINTS = Object.freeze({
    default: 0xffffff,
    toxic: 0x79d89f,
  });

  const REGION_THEMES = Object.freeze([
    { key: "entrance_hall", x: 0, y: 14, w: 12, h: 11, color: 0x6f4f2e, alpha: 0.1 },
    { key: "poison_corridor", x: 1, y: 8, w: 8, h: 6, color: 0x3d7d4d, alpha: 0.13 },
    { key: "study", x: 18, y: 8, w: 7, h: 6, color: 0x5a4c80, alpha: 0.1 },
    { key: "surgery_exit", x: 9, y: 0, w: 8, h: 6, color: 0x4e6a82, alpha: 0.12 },
  ]);

  const controller = {
    game: null,
    scene: null,
    latestState: FALLBACK_STATE,
    update(partyStatus, environmentObjects, mapData) {
      const nextMapData = normalizeMapData(mapData);
      const previousMapId = normalizeId(this.latestState && this.latestState.mapData && this.latestState.mapData.id);
      const nextMapId = normalizeId(nextMapData.id);
      const mapChanged = Boolean(previousMapId && nextMapId && previousMapId !== nextMapId);

      this.latestState = {
        partyStatus: safeObject(partyStatus),
        environmentObjects: safeObject(environmentObjects),
        mapData: nextMapData,
      };
      if (this.scene) {
        this.scene.syncState(this.latestState, { mapChanged });
      }
    },
    playProjectile(start, target, color) {
      if (!this.scene) return;
      this.scene.playProjectileBetweenCells(start, target, color);
    },
    playAoE(center) {
      if (!this.scene) return;
      this.scene.playAoEAtCell(center);
    },
    playKnockback(entityId, target, options = {}) {
      if (!this.scene) return;
      const point = safeObject(target);
      this.scene.playKnockbackAnimation(entityId, point.x, point.y, options);
    },
    playStatusDamage(entityId, label) {
      if (!this.scene) return;
      this.scene.playFloatingTextOverToken(entityId, label || "中毒", {
        color: "#76ff8a",
        stroke: "#062d10",
        yOffset: -0.72,
      });
    },
    playAdvantage(entityId) {
      if (!this.scene) return;
      this.scene.playFloatingTextOverToken(entityId, "ADVANTAGE!", {
        color: "#ffd86b",
        stroke: "#3c2500",
        yOffset: -0.92,
      });
    },
    playVictoryBanner() {
      if (!this.scene) return;
      this.scene.playVictoryBanner();
    },
    playSpeechBubble(entityId, text) {
      if (!this.scene) return;
      this.scene.playSpeechBubble(entityId, text);
    },
    playMapTransition() {
      if (!this.scene) return;
      this.scene.playMapTransition();
    },
    playShortRest() {
      if (!this.scene) return;
      this.scene.playShortRestTransition();
    },
    playLongRest() {
      if (!this.scene) return;
      this.scene.playLongRestTransition();
    },
    /** Move player token locally (no backend call). Called by input-controller. */
    movePlayerLocal(gridX, gridY) {
      if (!this.scene) return;
      const token = this.scene.tokens.get("player");
      if (!token) return;
      token.entity.x = gridX;
      token.entity.y = gridY;
      this.scene.moveToken(token, gridX, gridY, true);
      this.scene.updateCameraFollow();
      /* Also update latestState so sync doesn't snap back */
      if (this.latestState && this.latestState.partyStatus && this.latestState.partyStatus.player) {
        this.latestState.partyStatus.player.x = gridX;
        this.latestState.partyStatus.player.y = gridY;
      }
    },
    /** Get current player grid position */
    getPlayerGridPosition() {
      if (!this.scene) return { x: 0, y: 0 };
      const token = this.scene.tokens.get("player");
      if (!token) return { x: 0, y: 0 };
      return { x: token.entity.x, y: token.entity.y };
    },
    /** Draw red overlay on LoS-blocked tiles */
    drawLoSBlockerOverlay(blockedTiles) {
      if (!this.scene || typeof this.scene.drawLoSOverlay !== "function") return;
      this.scene.drawLoSOverlay(blockedTiles);
    },
    /** Clear LoS overlay */
    clearLoSBlockerOverlay() {
      if (!this.scene || typeof this.scene.clearLoSOverlay !== "function") return;
      this.scene.clearLoSOverlay();
    },
    setInteractionFocus(interactable) {
      if (!this.scene || typeof this.scene.setInteractionFocus !== "function") return;
      this.scene.setInteractionFocus(interactable);
    },
    setTrapSenseMode(enabled) {
      if (!this.scene || typeof this.scene.setTrapSenseMode !== "function") return;
      this.scene.setTrapSenseMode(enabled);
    },
    resize() {
      if (!this.game) return;
      const size = gameViewportSize();
      this.game.scale.resize(size.width, size.height);
      if (this.scene) {
        this.scene.handleResize(size);
      }
    },
  };

  window.BG3TacticalMap = controller;

  function safeObject(value) {
    return value && typeof value === "object" ? value : {};
  }

  function normalizeId(id) {
    return String(id || "").trim().toLowerCase();
  }

  function hashString(value) {
    const text = String(value || "");
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
      hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
    }
    return Math.abs(hash);
  }

  function pickFrame(frames, seed) {
    if (!Array.isArray(frames) || frames.length === 0) return 0;
    return frames[hashString(seed) % frames.length];
  }

  function isDialogueOverlayActive() {
    if (window.BG3DialogueActive === true) return true;
    const overlay = document.getElementById("dialogue-overlay");
    return Boolean(overlay && !overlay.classList.contains("hidden"));
  }

  function gameViewportSize() {
    const host = document.getElementById("game-viewport") || document.getElementById("map-container");
    return {
      width: Math.max(320, Math.round((host && host.clientWidth) || window.innerWidth * 0.65)),
      height: Math.max(320, Math.round((host && host.clientHeight) || window.innerHeight)),
    };
  }

  function normalizeMapData(rawMapData) {
    const outer = safeObject(rawMapData);
    const data = outer.map_data && typeof outer.map_data === "object"
      ? safeObject(outer.map_data)
      : outer;
    const id = String(data.id || data.map_id || data.key || data.name || "").trim();
    const parsedGrid = normalizeGridData(
      data.grid || data.map_grid || data.layout || data.tiles || data.rows,
    );
    const parsedCollision = normalizeCollisionData(
      data.collision || data.collision_grid || data.blocked_movement_grid || [],
    );
    const parsedLosBlockers = normalizeCollisionData(
      data.los_blockers || data.losBlockers || data.los || [],
    );
    const parsedGroundTypes = normalizeNumericGridData(
      data.ground_types || data.groundTypes || data.ground || data.terrain || [],
    );
    const gridHeight = parsedGrid.length;
    const gridWidth = parsedGrid.reduce((max, row) => Math.max(max, row.length), 0);
    const collisionHeight = parsedCollision.length;
    const collisionWidth = parsedCollision.reduce((max, row) => Math.max(max, row.length), 0);
    const losHeight = parsedLosBlockers.length;
    const losWidth = parsedLosBlockers.reduce((max, row) => Math.max(max, row.length), 0);
    const groundHeight = parsedGroundTypes.length;
    const groundWidth = parsedGroundTypes.reduce((max, row) => Math.max(max, row.length), 0);
    const width = Math.max(
      1,
      Math.round(Number(data.width) || 0),
      losWidth || 0,
      groundWidth || 0,
      collisionWidth || 0,
      gridWidth || DEFAULT_MAP_DATA.width,
    );
    const height = Math.max(
      1,
      Math.round(Number(data.height) || 0),
      losHeight || 0,
      groundHeight || 0,
      collisionHeight || 0,
      gridHeight || DEFAULT_MAP_DATA.height,
    );
    const obstacles = Array.isArray(data.obstacles) ? data.obstacles : [];
    const collision = normalizeCollisionShape(parsedCollision, width, height);
    const losBlockers = normalizeCollisionShape(parsedLosBlockers, width, height);
    const groundTypes = normalizeNumericGridShape(parsedGroundTypes, width, height);
    const grid = parsedGrid.length
      ? normalizeGridShape(parsedGrid, width, height)
      : gridFromCollision(collision, width, height);
    return {
      id,
      width,
      height,
      obstacles,
      grid,
      collision,
      los_blockers: losBlockers,
      ground_types: groundTypes,
    };
  }

  function normalizeGridData(rawGrid) {
    if (Array.isArray(rawGrid)) {
      if (rawGrid.every((row) => typeof row === "string")) {
        return rawGrid.map((row) => row.split(""));
      }
      if (rawGrid.every((row) => Array.isArray(row))) {
        return rawGrid.map((row) => row.map((cell) => String(cell || "").charAt(0)));
      }
    }
    if (typeof rawGrid === "string") {
      const rows = rawGrid
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
      return rows.map((row) => row.split(""));
    }
    return [];
  }

  function normalizeGridShape(parsedGrid, width, height) {
    if (!Array.isArray(parsedGrid) || parsedGrid.length === 0) return [];
    const out = [];
    for (let y = 0; y < height; y += 1) {
      const row = Array.isArray(parsedGrid[y]) ? parsedGrid[y] : [];
      const normalized = [];
      for (let x = 0; x < width; x += 1) {
        const value = String(row[x] || "").toUpperCase();
        normalized.push(value === "W" ? "W" : ".");
      }
      out.push(normalized);
    }
    return out;
  }

  function normalizeCollisionData(rawCollision) {
    if (!Array.isArray(rawCollision)) return [];
    if (rawCollision.every((row) => Array.isArray(row))) {
      return rawCollision.map((row) => row.map((cell) => Boolean(cell)));
    }
    return [];
  }

  function normalizeNumericGridData(rawGrid) {
    if (!Array.isArray(rawGrid)) return [];
    if (rawGrid.every((row) => Array.isArray(row))) {
      return rawGrid.map((row) => row.map((cell) => Number(cell) || 0));
    }
    return [];
  }

  function normalizeCollisionShape(parsedCollision, width, height) {
    if (!Array.isArray(parsedCollision) || parsedCollision.length === 0) {
      return [];
    }
    const out = [];
    for (let y = 0; y < height; y += 1) {
      const row = Array.isArray(parsedCollision[y]) ? parsedCollision[y] : [];
      const normalized = [];
      for (let x = 0; x < width; x += 1) {
        normalized.push(Boolean(row[x]));
      }
      out.push(normalized);
    }
    return out;
  }

  function normalizeNumericGridShape(parsedGrid, width, height) {
    if (!Array.isArray(parsedGrid) || parsedGrid.length === 0) {
      return [];
    }
    const out = [];
    for (let y = 0; y < height; y += 1) {
      const row = Array.isArray(parsedGrid[y]) ? parsedGrid[y] : [];
      const normalized = [];
      for (let x = 0; x < width; x += 1) {
        normalized.push(Number(row[x]) || 0);
      }
      out.push(normalized);
    }
    return out;
  }

  function gridFromCollision(collision, width, height) {
    const out = [];
    for (let y = 0; y < height; y += 1) {
      const row = Array.isArray(collision[y]) ? collision[y] : [];
      const next = [];
      for (let x = 0; x < width; x += 1) {
        next.push(Boolean(row[x]) ? "W" : ".");
      }
      out.push(next);
    }
    return out;
  }

  function gridCoord(value, fallback, max) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.max(0, Math.min(max - 1, Math.round(num)));
  }

  function tokenKind(id, data, source) {
    const entity = safeObject(data);
    if (isTrap(id, entity)) return "trap";
    if (isLootDrop(id, entity)) return "loot";
    if (isDoor(id, entity)) return "door";
    if (isChest(id, entity)) return "chest";
    if (normalizeId(id) === "player") return "player";
    if (normalizeId(entity.faction) === "hostile") return "hostile";
    if (source === "environment") return "object";
    return "neutral";
  }

  function isTrap(id, data) {
    const entity = safeObject(data);
    const key = normalizeId(id);
    const type = normalizeId(entity.type || entity.kind || entity.object_type || entity.category);
    return type === "trap" || key.includes("trap");
  }

  function isEntityHidden(data) {
    const entity = safeObject(data);
    const hidden = entity.is_hidden ?? entity.hidden;
    if (typeof hidden === "boolean") return hidden;
    if (typeof hidden === "string") {
      return ["true", "yes", "hidden", "concealed"].includes(normalizeId(hidden));
    }
    return false;
  }

  function isDoor(id, data) {
    const entity = safeObject(data);
    const key = normalizeId(id);
    const type = normalizeId(entity.type || entity.kind || entity.object_type || entity.category);
    return key.includes("door")
      || type === "door"
      || type === "gate"
      || type === "locked_door"
      || type.endsWith("_door");
  }

  function isDoorOpen(data) {
    const entity = safeObject(data);
    const explicit = entity.is_open ?? entity.open ?? entity.opened;
    if (typeof explicit === "boolean") return explicit;
    if (typeof explicit === "string") {
      const value = normalizeId(explicit);
      if (["true", "yes", "open", "opened"].includes(value)) return true;
      if (["false", "no", "closed", "locked"].includes(value)) return false;
    }

    const status = normalizeId(entity.status);
    if (["open", "opened"].includes(status)) return true;
    if (["closed", "locked", "sealed"].includes(status)) return false;
    return false;
  }

  function isChest(id, data) {
    const entity = safeObject(data);
    const key = normalizeId(id);
    const type = normalizeId(entity.type || entity.kind || entity.object_type || entity.category);
    return key.includes("chest") || type === "chest" || type === "locked_chest";
  }

  function isLocked(data) {
    const entity = safeObject(data);
    const explicit = entity.is_locked ?? entity.locked;
    if (typeof explicit === "boolean") return explicit;
    if (typeof explicit === "string") {
      const value = normalizeId(explicit);
      if (["true", "yes", "locked"].includes(value)) return true;
      if (["false", "no", "unlocked", "open", "opened"].includes(value)) return false;
    }

    const status = normalizeId(entity.status);
    if (["unlocked", "open", "opened"].includes(status)) return false;
    if (["locked", "sealed"].includes(status)) return true;

    const type = normalizeId(entity.type || entity.kind || entity.object_type || entity.category);
    return type === "locked_chest";
  }

  function isLootDrop(id, data) {
    const key = normalizeId(id);
    const type = normalizeId(safeObject(data).type);
    return key.includes("loot_drop")
      || type === "loot_drop"
      || type === "loot"
      || type === "treasure"
      || type === "drop";
  }

  function normalizeStatusEffects(data) {
    const effects = safeObject(data).status_effects;
    if (Array.isArray(effects)) {
      return effects.map((effect) => {
        if (typeof effect === "string") return normalizeId(effect);
        const record = safeObject(effect);
        return normalizeId(record.id || record.type || record.name);
      });
    }
    if (effects && typeof effects === "object") {
      return Object.entries(effects)
        .filter(([, enabled]) => Boolean(enabled))
        .map(([effect]) => normalizeId(effect));
    }
    return [];
  }

  function collectEntities(partyStatus, environmentObjects, mapData) {
    const entities = [];
    const map = normalizeMapData(mapData);

    Object.entries(safeObject(partyStatus)).forEach(([id, data]) => {
      const entity = safeObject(data);
      if (entity.x === undefined || entity.y === undefined) return;
      entities.push({
        id,
        data: entity,
        source: "party",
        kind: tokenKind(id, entity, "party"),
        x: gridCoord(entity.x, 0, map.width),
        y: gridCoord(entity.y, 0, map.height),
      });
    });

    Object.entries(safeObject(environmentObjects)).forEach(([id, data]) => {
      const entity = safeObject(data);
      if (entity.x === undefined || entity.y === undefined) return;
      if (isTrap(id, entity) && isEntityHidden(entity)) return;
      entities.push({
        id,
        data: entity,
        source: "environment",
        kind: tokenKind(id, entity, "environment"),
        x: gridCoord(entity.x, 0, map.width),
        y: gridCoord(entity.y, 0, map.height),
      });
    });

    if (entities.length > 0) return entities;
    return collectEntities(FALLBACK_STATE.partyStatus, FALLBACK_STATE.environmentObjects, map);
  }

  function obstacleCoordinates(obstacle, mapData) {
    const map = normalizeMapData(mapData);
    const coords = Array.isArray(obstacle.coordinates) ? obstacle.coordinates : [];
    return coords
      .filter((coord) => Array.isArray(coord) && coord.length >= 2)
      .map(([x, y]) => ({ x: Math.round(Number(x)), y: Math.round(Number(y)) }))
      .filter(({ x, y }) => {
        return Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0 && x < map.width && y < map.height;
      });
  }

  if (!window.Phaser) {
    console.warn("Phaser 未加载，战术地图 Canvas 暂不可用。");
    return;
  }

  class MainScene extends Phaser.Scene {
    constructor() {
      super("MainScene");
      this.floorLayer = null;
      this.ambienceLayer = null;
      this.environmentLayer = null;
      this.overlayLayer = null;
      this.entityLayer = null;
      this.floorSprites = [];
      this.ambientSprites = [];
      this.toxicFogSprites = [];
      this.losSprites = [];
      this.obstacleSprites = [];
      this.obstacleFxTweens = [];
      this.overlayTweens = [];
      this.interactionRing = null;
      this.highlightedInteractableId = "";
      this.trapSenseMode = false;
      this.mapData = DEFAULT_MAP_DATA;
      this.board = { x: 0, y: 0, width: 640, height: 640, cell: 64 };
      this.tokens = new Map();
      this.highlightTween = null;
      this.externalLosOverlaySprites = [];
      this.transitionOverlay = null;
      this.lastTransitionAt = -Infinity;
    }

    preload() {
      this.load.spritesheet(SPRITE_KEYS.tiles, SPRITE_SHEETS.tiles.path, {
        frameWidth: SPRITE_SHEETS.tiles.frameWidth,
        frameHeight: SPRITE_SHEETS.tiles.frameHeight,
      });
      this.load.spritesheet(SPRITE_KEYS.actors, SPRITE_SHEETS.actors.path, {
        frameWidth: SPRITE_SHEETS.actors.frameWidth,
        frameHeight: SPRITE_SHEETS.actors.frameHeight,
      });
    }

    create() {
      this.floorLayer = this.add.layer().setDepth(DEPTH_LAYERS.floor);
      this.ambienceLayer = this.add.layer().setDepth(DEPTH_LAYERS.ambience);
      this.environmentLayer = this.add.layer().setDepth(DEPTH_LAYERS.environment);
      this.overlayLayer = this.add.layer().setDepth(DEPTH_LAYERS.overlay);
      this.entityLayer = this.add.layer().setDepth(DEPTH_LAYERS.actors);
      this.interactionRing = this.add.graphics().setDepth(DEPTH_LAYERS.interactFx);
      this.interactionRing.setVisible(false);
      this.transitionOverlay = this.add.rectangle(0, 0, 1, 1, 0x000000, 0)
        .setOrigin(0, 0)
        .setDepth(500)
        .setVisible(false);
      this.input.on("pointerdown", (pointer) => {
        if (!isDialogueOverlayActive()) return;
        if (pointer && pointer.event && typeof pointer.event.stopPropagation === "function") {
          pointer.event.stopPropagation();
        }
      });
      this.scale.on("resize", this.handleResize, this);
      controller.scene = this;
      this.syncState(controller.latestState);
      this.cameras.main.setZoom(2.5);
      this.updateCameraFollow();
    }

    syncState(nextState, options = {}) {
      const state = safeObject(nextState);
      this.mapData = normalizeMapData(state.mapData);
      this.handleResize({ width: this.scale.width, height: this.scale.height });

      const entities = collectEntities(state.partyStatus, state.environmentObjects, this.mapData);
      const active = new Set();

      entities.forEach((entity) => {
        active.add(normalizeId(entity.id));
        this.upsertToken(entity);
      });

      this.tokens.forEach((token, id) => {
        if (!active.has(id)) {
          this.destroyToken(token);
          this.tokens.delete(id);
        }
      });
      this.refreshInteractionHighlight();
      this.updateCameraFollow();

      if (options.mapChanged) {
        this.playMapTransition();
      }
    }

    handleResize(gameSize) {
      const width = gameSize.width || this.scale.width;
      const height = gameSize.height || this.scale.height;
      const map = normalizeMapData(this.mapData);
      const cell = Math.min(width * 0.86 / map.width, height * 0.86 / map.height);
      const boardWidth = cell * map.width;
      const boardHeight = cell * map.height;

      this.board = {
        x: 0,
        y: 0,
        width: boardWidth,
        height: boardHeight,
        cell,
      };

      this.drawFloorTiles();
      this.drawAmbienceLayers();
      this.drawObstacleTiles();
      this.drawLosBlockers();
      this.tokens.forEach((token) => {
        this.updateTokenScale(token);
        this.updateIdleTween(token, true);
      });
      this.positionAllTokens(false);
      this.refreshInteractionHighlight();
      if (this.transitionOverlay) {
        this.transitionOverlay
          .setPosition(0, 0)
          .setSize(width, height)
          .setDisplaySize(width, height);
      }
      this.updateCameraBounds();
    }

    destroySpriteList(items) {
      items.forEach((item) => item.destroy());
      items.length = 0;
    }

    scaleForTile(ratio = 1) {
      return (this.board.cell / SPRITE_SHEETS.tiles.frameWidth) * ratio;
    }

    drawFloorTiles() {
      const map = normalizeMapData(this.mapData);
      this.destroySpriteList(this.floorSprites);
      const grid = Array.isArray(map.grid) ? map.grid : [];
      const hasGrid = grid.length > 0;
      const collision = Array.isArray(map.collision) ? map.collision : [];
      const groundTypes = Array.isArray(map.ground_types) ? map.ground_types : [];

      for (let y = 0; y < map.height; y += 1) {
        for (let x = 0; x < map.width; x += 1) {
          const cell = hasGrid ? String((grid[y] && grid[y][x]) || ".").toUpperCase() : ".";
          const blocked = Boolean(collision[y] && collision[y][x]);
          const isWall = cell === "W" || blocked;
          const groundType = Number(groundTypes[y] && groundTypes[y][x]) || 0;
          const isToxic = groundType >= 2 && !isWall;
          const frame = isWall
            ? pickFrame(TILE_FRAMES.wall, `wall:${x}:${y}`)
            : pickFrame(TILE_FRAMES.floor, `floor:${x}:${y}`);
          const world = this.gridToWorld(x, y);
          const tile = this.add.image(world.x, world.y, SPRITE_KEYS.tiles, frame)
            .setScale(this.scaleForTile(1.02))
            .setDepth(isWall ? DEPTH_LAYERS.environment : DEPTH_LAYERS.floor);
          if (isWall) {
            tile.setTint(0xc9b8a0);
          } else if (isToxic) {
            tile.setTint(GROUND_TYPE_TINTS.toxic);
            tile.setAlpha(0.95);
          } else {
            tile.setTint(GROUND_TYPE_TINTS.default);
          }
          if (isWall) {
            this.environmentLayer.add(tile);
          } else {
            this.floorLayer.add(tile);
          }
          this.floorSprites.push(tile);
        }
      }
    }

    drawAmbienceLayers() {
      this.destroySpriteList(this.ambientSprites);
      this.destroySpriteList(this.toxicFogSprites);
      this.destroySpriteList(this.losSprites);
      this.overlayTweens.forEach((tween) => tween.stop());
      this.overlayTweens = [];

      const map = normalizeMapData(this.mapData);
      REGION_THEMES.forEach((region) => {
        if (region.x >= map.width || region.y >= map.height) return;
        const width = Math.min(region.w, map.width - region.x) * this.board.cell;
        const height = Math.min(region.h, map.height - region.y) * this.board.cell;
        const center = this.gridToWorld(
          region.x + Math.min(region.w, map.width - region.x) / 2 - 0.5,
          region.y + Math.min(region.h, map.height - region.y) / 2 - 0.5,
        );
        const overlay = this.add.rectangle(center.x, center.y, width, height, region.color, region.alpha)
          .setDepth(DEPTH_LAYERS.ambience);
        this.ambienceLayer.add(overlay);
        this.ambientSprites.push(overlay);
      });

      const ground = Array.isArray(map.ground_types) ? map.ground_types : [];
      const collision = Array.isArray(map.collision) ? map.collision : [];
      for (let y = 0; y < map.height; y += 1) {
        for (let x = 0; x < map.width; x += 1) {
          const groundType = Number(ground[y] && ground[y][x]) || 0;
          if (groundType < 2 || Boolean(collision[y] && collision[y][x])) continue;
          const world = this.gridToWorld(x, y);
          const fog = this.add.ellipse(world.x, world.y, this.board.cell * 0.72, this.board.cell * 0.52, 0x65cf87, 0.18)
            .setDepth(DEPTH_LAYERS.ambience);
          this.ambienceLayer.add(fog);
          this.toxicFogSprites.push(fog);
          this.overlayTweens.push(
            this.tweens.add({
              targets: fog,
              alpha: 0.34,
              scaleX: 1.1,
              scaleY: 1.1,
              duration: 1200 + ((x + y) % 4) * 140,
              yoyo: true,
              repeat: -1,
              ease: "Sine.easeInOut",
            }),
          );
        }
      }

      const vignette = this.add.rectangle(
        this.board.width * 0.5,
        this.board.height * 0.5,
        this.board.width,
        this.board.height,
        0x000000,
        0.12,
      ).setDepth(DEPTH_LAYERS.ambience);
      this.ambienceLayer.add(vignette);
      this.ambientSprites.push(vignette);

      const exitGlow = this.add.ellipse(
        this.board.width * 0.5,
        this.board.cell * 1.35,
        this.board.cell * 6.4,
        this.board.cell * 2.4,
        0x85a5be,
        0.24,
      ).setDepth(DEPTH_LAYERS.overlay);
      this.overlayLayer.add(exitGlow);
      this.ambientSprites.push(exitGlow);
      this.overlayTweens.push(
        this.tweens.add({
          targets: exitGlow,
          alpha: 0.42,
          duration: 1800,
          yoyo: true,
          repeat: -1,
          ease: "Sine.easeInOut",
        }),
      );

      if (this.trapSenseMode) {
        this.drawTrapSenseHints();
      }
    }

    drawTrapSenseHints() {
      const map = normalizeMapData(this.mapData);
      const ground = Array.isArray(map.ground_types) ? map.ground_types : [];
      for (let y = 0; y < map.height; y += 1) {
        for (let x = 0; x < map.width; x += 1) {
          const groundType = Number(ground[y] && ground[y][x]) || 0;
          if (groundType < 2) continue;
          const world = this.gridToWorld(x, y);
          const hint = this.add.text(world.x, world.y - this.board.cell * 0.16, "!", {
            fontFamily: "Georgia, serif",
            fontSize: Math.max(10, this.board.cell * 0.24) + "px",
            fontStyle: "bold",
            color: "#9ce2b0",
            stroke: "#0c1810",
            strokeThickness: 2,
          }).setOrigin(0.5).setDepth(DEPTH_LAYERS.overlay);
          hint.setAlpha(0.24);
          this.overlayLayer.add(hint);
          this.ambientSprites.push(hint);
          this.overlayTweens.push(
            this.tweens.add({
              targets: hint,
              alpha: 0.58,
              duration: 900 + ((x * 13 + y * 7) % 5) * 110,
              yoyo: true,
              repeat: -1,
              ease: "Sine.easeInOut",
            }),
          );
        }
      }
    }

    drawLosBlockers() {
      const map = normalizeMapData(this.mapData);
      const blockers = Array.isArray(map.los_blockers) ? map.los_blockers : [];
      for (let y = 0; y < map.height; y += 1) {
        for (let x = 0; x < map.width; x += 1) {
          if (!Boolean(blockers[y] && blockers[y][x])) continue;
          const world = this.gridToWorld(x, y);
          const shadow = this.add.rectangle(
            world.x,
            world.y - this.board.cell * 0.18,
            this.board.cell * 0.9,
            this.board.cell * 0.34,
            0x0f1114,
            0.48,
          ).setDepth(DEPTH_LAYERS.environment + 0.05);
          const edge = this.add.rectangle(
            world.x,
            world.y - this.board.cell * 0.32,
            this.board.cell * 0.76,
            this.board.cell * 0.08,
            0x8da5b7,
            0.34,
          ).setDepth(DEPTH_LAYERS.environment + 0.06);
          this.environmentLayer.add(shadow);
          this.environmentLayer.add(edge);
          this.losSprites.push(shadow, edge);
        }
      }
    }

    setTrapSenseMode(enabled) {
      const nextValue = Boolean(enabled);
      if (this.trapSenseMode === nextValue) return;
      this.trapSenseMode = nextValue;
      this.drawAmbienceLayers();
      this.refreshInteractionHighlight();
    }

    setInteractionFocus(interactable) {
      const target = safeObject(interactable);
      this.highlightedInteractableId = normalizeId(target.id || "");
      this.refreshInteractionHighlight();
    }

    resolveFocusWorldPoint(id) {
      const key = normalizeId(id);
      if (!key) return null;
      const token = this.tokens.get(key);
      if (token && token.container) {
        return { x: token.container.x, y: token.container.y };
      }
      const entity = safeObject(
        safeObject(controller.latestState.environmentObjects)[key]
        || safeObject(controller.latestState.partyStatus)[key],
      );
      const x = Number(entity.x);
      const y = Number(entity.y);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        return this.gridToWorld(
          gridCoord(x, 0, this.mapData.width || 1),
          gridCoord(y, 0, this.mapData.height || 1),
        );
      }
      return null;
    }

    refreshInteractionHighlight() {
      if (!this.interactionRing) return;
      if (this.highlightTween) {
        this.highlightTween.stop();
        this.highlightTween = null;
      }
      this.interactionRing.clear();
      const point = this.resolveFocusWorldPoint(this.highlightedInteractableId);
      if (!point) {
        this.interactionRing.setVisible(false);
        return;
      }
      const radius = this.board.cell * 0.46;
      this.interactionRing
        .lineStyle(3, 0xf0ca7b, 0.88)
        .strokeCircle(point.x, point.y, radius)
        .lineStyle(1, 0x61c7bc, 0.6)
        .strokeCircle(point.x, point.y, radius * 0.72)
        .setVisible(true)
        .setAlpha(0.78);
      this.highlightTween = this.tweens.add({
        targets: this.interactionRing,
        alpha: 0.28,
        duration: 720,
        yoyo: true,
        repeat: -1,
        ease: "Sine.easeInOut",
      });
    }

    drawLoSOverlay(blockedTiles) {
      this.clearLoSOverlay();
      const tiles = Array.isArray(blockedTiles) ? blockedTiles : [];
      tiles.forEach((cell) => {
        const point = safeObject(cell);
        const x = Number(point.x);
        const y = Number(point.y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) return;
        const world = this.gridToWorld(gridCoord(x, 0, this.mapData.width || 1), gridCoord(y, 0, this.mapData.height || 1));
        const mark = this.add.rectangle(world.x, world.y, this.board.cell * 0.88, this.board.cell * 0.88, 0xa11616, 0.32)
          .setDepth(DEPTH_LAYERS.overlay + 0.2);
        this.overlayLayer.add(mark);
        this.externalLosOverlaySprites.push(mark);
      });
    }

    clearLoSOverlay() {
      this.externalLosOverlaySprites.forEach((sprite) => sprite.destroy());
      this.externalLosOverlaySprites = [];
    }

    updateCameraBounds() {
      const map = normalizeMapData(this.mapData);
      const mapTotalWidth = map.width * this.board.cell;
      const mapTotalHeight = map.height * this.board.cell;
      this.cameras.main.setBounds(0, 0, mapTotalWidth, mapTotalHeight);
    }

    updateCameraFollow() {
      const player = this.tokens.get("player")?.container;
      if (!player) return;
      this.cameras.main.startFollow(player, true, 0.16, 0.16);
      this.updateCameraBounds();
    }

    obstacleFrame(obstacle, x, y) {
      const entry = safeObject(obstacle);
      const kind = normalizeId(entry.type);
      if (kind.includes("campfire") || kind.includes("torch")) {
        return pickFrame(TILE_FRAMES.campfire, `${kind}:${x}:${y}`);
      }
      if (kind.includes("trap") || kind.includes("spike")) {
        return pickFrame(TILE_FRAMES.trap, `${kind}:${x}:${y}`);
      }
      if (entry.blocks_movement === true && entry.blocks_los === true) {
        return pickFrame(TILE_FRAMES.wall, `hard:${kind}:${x}:${y}`);
      }
      if (entry.blocks_movement === true) {
        return pickFrame(TILE_FRAMES.prop, `soft:${kind}:${x}:${y}`);
      }
      return pickFrame(TILE_FRAMES.rubble, `rubble:${kind}:${x}:${y}`);
    }

    drawObstacleTiles() {
      this.destroySpriteList(this.obstacleSprites);
      this.obstacleFxTweens.forEach((tween) => tween.stop());
      this.obstacleFxTweens = [];

      const obstacles = Array.isArray(this.mapData.obstacles) ? this.mapData.obstacles : [];
      obstacles.forEach((rawObstacle) => {
        const obstacle = safeObject(rawObstacle);
        const kind = normalizeId(obstacle.type);

        obstacleCoordinates(obstacle, this.mapData).forEach(({ x, y }) => {
          const world = this.gridToWorld(x, y);
          const sprite = this.add.image(world.x, world.y, SPRITE_KEYS.tiles, this.obstacleFrame(obstacle, x, y))
            .setScale(this.scaleForTile(0.95))
            .setDepth(DEPTH_LAYERS.environment);
          this.environmentLayer.add(sprite);
          this.obstacleSprites.push(sprite);

          if (kind.includes("campfire") || kind.includes("torch")) {
            const flicker = this.tweens.add({
              targets: sprite,
              alpha: 0.66,
              duration: 150,
              yoyo: true,
              repeat: -1,
              ease: "Sine.easeInOut",
            });
            this.obstacleFxTweens.push(flicker);
          }
        });
      });
    }

    playProjectileAnimation(startX, startY, targetX, targetY, color = 0x00ffff) {
      const radius = Math.max(5, this.board.cell * 0.09);
      const projectile = this.add.graphics().setDepth(180);

      projectile.fillStyle(color, 0.95);
      projectile.fillCircle(0, 0, radius);
      projectile.lineStyle(2, 0xffffff, 0.72);
      projectile.strokeCircle(0, 0, radius * 1.35);
      projectile.setPosition(startX, startY);

      this.tweens.add({
        targets: projectile,
        x: targetX,
        y: targetY,
        duration: 300,
        ease: "Quad.easeOut",
        onComplete: () => projectile.destroy(),
      });
    }

    playAoEAnimation(centerX, centerY) {
      const size = this.board.cell * 3;
      // 两次闪烁，总时长约 400ms：4 个半程 * 100ms（上升/回落 + repeat）
      const flashHalfStepMs = 100;
      const blast = this.add.graphics().setDepth(150);

      blast.fillStyle(0xff0000, 0.4);
      blast.fillRect(-size / 2, -size / 2, size, size);
      blast.lineStyle(2, 0xffb3a7, 0.78);
      blast.strokeRect(-size / 2, -size / 2, size, size);

      for (let i = -1; i <= 1; i += 1) {
        const offset = i * this.board.cell;
        blast.lineStyle(1, 0xffd2cc, 0.38);
        blast.lineBetween(offset, -size / 2, offset, size / 2);
        blast.lineBetween(-size / 2, offset, size / 2, offset);
      }

      blast.setPosition(centerX, centerY);
      blast.setAlpha(0.4);
      this.cameras.main.shake(120, 0.004);

      this.tweens.add({
        targets: blast,
        alpha: 0.8,
        duration: flashHalfStepMs,
        ease: "Sine.easeInOut",
        yoyo: true,
        repeat: 1,
        onComplete: () => blast.destroy(),
      });
    }

    playProjectileBetweenCells(start, target, color) {
      const map = normalizeMapData(this.mapData);
      const startCell = safeObject(start);
      const targetCell = safeObject(target);
      const startWorld = this.gridToWorld(
        gridCoord(startCell.x, 0, map.width),
        gridCoord(startCell.y, 0, map.height),
      );
      const targetWorld = this.gridToWorld(
        gridCoord(targetCell.x, 0, map.width),
        gridCoord(targetCell.y, 0, map.height),
      );
      this.playProjectileAnimation(startWorld.x, startWorld.y, targetWorld.x, targetWorld.y, color || 0x00ffff);
    }

    playAoEAtCell(center) {
      const map = normalizeMapData(this.mapData);
      const centerCell = safeObject(center);
      const centerWorld = this.gridToWorld(
        gridCoord(centerCell.x, 0, map.width),
        gridCoord(centerCell.y, 0, map.height),
      );
      this.playAoEAnimation(centerWorld.x, centerWorld.y);
    }

    playKnockbackAnimation(entityId, targetX, targetY, options = {}) {
      const id = normalizeId(entityId);
      const token = this.tokens.get(id);
      if (!token) return;

      const map = normalizeMapData(this.mapData);
      const gridX = gridCoord(targetX, token.entity.x, map.width);
      const gridY = gridCoord(targetY, token.entity.y, map.height);
      const target = this.gridToWorld(gridX, gridY);
      const originalDepth = token.container.depth;

      token.entity.x = gridX;
      token.entity.y = gridY;
      if (token.moveTween) {
        token.moveTween.stop();
        token.moveTween = null;
      }
      token.container.setDepth(Math.max(originalDepth, 175));

      token.moveTween = this.tweens.add({
        targets: token.container,
        x: target.x,
        y: target.y,
        duration: 200,
        ease: "Back.easeOut",
        onComplete: () => {
          token.moveTween = null;
          token.container.setDepth(originalDepth);
          if (options.terrainDamage) {
            this.playTerrainDamageFeedback(target.x, target.y, options.label || "火焰伤害");
          }
        },
      });
    }

    playTerrainDamageFeedback(x, y, label) {
      const burst = this.add.graphics().setDepth(205);
      burst.fillStyle(0xff7a1a, 0.34);
      burst.fillCircle(0, 0, this.board.cell * 0.42);
      burst.lineStyle(2, 0xffcf70, 0.78);
      burst.strokeCircle(0, 0, this.board.cell * 0.5);
      burst.setPosition(x, y);

      const text = this.add.text(x, y - this.board.cell * 0.28, label, {
        fontFamily: "Georgia, serif",
        fontSize: Math.max(14, this.board.cell * 0.24) + "px",
        fontStyle: "bold",
        color: "#ff9a2e",
        stroke: "#2a0800",
        strokeThickness: 4,
      }).setOrigin(0.5).setDepth(220);

      this.cameras.main.shake(100, 0.01);

      this.tweens.add({
        targets: burst,
        alpha: 0,
        scaleX: 1.45,
        scaleY: 1.45,
        duration: 220,
        ease: "Quad.easeOut",
        onComplete: () => burst.destroy(),
      });
      this.tweens.add({
        targets: text,
        y: text.y - this.board.cell * 0.55,
        alpha: 0,
        duration: 650,
        ease: "Cubic.easeOut",
        onComplete: () => text.destroy(),
      });
    }

    playFloatingTextOverToken(entityId, label, options = {}) {
      const token = this.tokens.get(normalizeId(entityId));
      if (!token) return;

      const yOffset = Number.isFinite(Number(options.yOffset)) ? Number(options.yOffset) : -0.78;
      const text = this.add.text(
        token.container.x,
        token.container.y + this.board.cell * yOffset,
        String(label || ""),
        {
          fontFamily: "Georgia, serif",
          fontSize: Math.max(14, this.board.cell * 0.22) + "px",
          fontStyle: "bold",
          color: options.color || "#ffffff",
          stroke: options.stroke || "#000000",
          strokeThickness: 4,
        },
      ).setOrigin(0.5).setDepth(240);

      this.tweens.add({
        targets: text,
        y: text.y - this.board.cell * 0.62,
        alpha: 0,
        duration: 600,
        ease: "Cubic.easeOut",
        onComplete: () => text.destroy(),
      });
    }

    playVictoryBanner() {
      const cx = this.scale.width / 2;
      const cy = this.scale.height * 0.28;
      const panel = this.add.graphics().setDepth(300);
      panel.fillStyle(0x080604, 0.72);
      panel.fillRoundedRect(-260, -46, 520, 92, 16);
      panel.lineStyle(2, 0xffd86b, 0.82);
      panel.strokeRoundedRect(-260, -46, 520, 92, 16);
      panel.setPosition(cx, cy);
      panel.setAlpha(0);

      const title = this.add.text(cx, cy - 10, "VICTORY", {
        fontFamily: "Georgia, serif",
        fontSize: "46px",
        fontStyle: "bold",
        color: "#ffd86b",
        stroke: "#2a1600",
        strokeThickness: 6,
      }).setOrigin(0.5).setDepth(301).setAlpha(0);

      const subtitle = this.add.text(cx, cy + 28, "战斗结束", {
        fontFamily: "Georgia, serif",
        fontSize: "20px",
        fontStyle: "bold",
        color: "#f4e0a2",
        stroke: "#100804",
        strokeThickness: 4,
      }).setOrigin(0.5).setDepth(301).setAlpha(0);

      this.tweens.add({
        targets: [panel, title, subtitle],
        alpha: 1,
        duration: 180,
        ease: "Quad.easeOut",
      });
      this.tweens.add({
        targets: [panel, title, subtitle],
        alpha: 0,
        delay: 1600,
        duration: 400,
        ease: "Quad.easeIn",
        onComplete: () => {
          panel.destroy();
          title.destroy();
          subtitle.destroy();
        },
      });
    }

    playMapTransition() {
      if (!this.transitionOverlay) return;
      const now = this.time ? this.time.now : Date.now();
      if (now - this.lastTransitionAt < 360) return;
      this.lastTransitionAt = now;

      this.tweens.killTweensOf(this.transitionOverlay);
      this.transitionOverlay
        .setVisible(true)
        .setAlpha(0)
        .setPosition(0, 0)
        .setSize(this.scale.width, this.scale.height)
        .setDisplaySize(this.scale.width, this.scale.height);

      this.tweens.add({
        targets: this.transitionOverlay,
        alpha: 1,
        duration: 250,
        ease: "Quad.easeIn",
        onComplete: () => {
          this.tweens.add({
            targets: this.transitionOverlay,
            alpha: 0,
            delay: 80,
            duration: 250,
            ease: "Quad.easeOut",
            onComplete: () => {
              this.transitionOverlay.setVisible(false);
            },
          });
        },
      });
    }

    playShortRestTransition() {
      const width = this.scale.width;
      const height = this.scale.height;
      const cx = width / 2;
      const cy = height * 0.34;
      const overlay = this.add.rectangle(0, 0, width, height, 0x07182f, 0)
        .setOrigin(0, 0)
        .setDepth(520);
      const clock = this.add.text(cx, cy - 28, "◷", {
        fontFamily: "Georgia, serif",
        fontSize: "54px",
        fontStyle: "bold",
        color: "#bfe7ff",
        stroke: "#07111f",
        strokeThickness: 5,
      }).setOrigin(0.5).setDepth(521).setAlpha(0);
      const label = this.add.text(cx, cy + 22, "1 Hour Later...", {
        fontFamily: "Georgia, serif",
        fontSize: "24px",
        fontStyle: "bold",
        color: "#d8ecff",
        stroke: "#07111f",
        strokeThickness: 4,
      }).setOrigin(0.5).setDepth(521).setAlpha(0);

      this.tweens.add({
        targets: overlay,
        alpha: 0.42,
        duration: 160,
        ease: "Quad.easeOut",
      });
      this.tweens.add({
        targets: clock,
        alpha: 1,
        angle: 720,
        duration: 800,
        ease: "Cubic.easeInOut",
      });
      this.tweens.add({
        targets: label,
        alpha: 1,
        y: label.y - 8,
        duration: 220,
        ease: "Quad.easeOut",
      });
      this.tweens.add({
        targets: [overlay, clock, label],
        alpha: 0,
        delay: 620,
        duration: 180,
        ease: "Quad.easeIn",
        onComplete: () => {
          overlay.destroy();
          clock.destroy();
          label.destroy();
        },
      });
    }

    playLongRestTransition() {
      const width = this.scale.width;
      const height = this.scale.height;
      const cx = width / 2;
      const cy = height * 0.36;
      const overlay = this.add.rectangle(0, 0, width, height, 0x000000, 0)
        .setOrigin(0, 0)
        .setDepth(530);
      const title = this.add.text(cx, cy - 10, "一夜过去", {
        fontFamily: "Georgia, serif",
        fontSize: "48px",
        fontStyle: "bold",
        color: "#f4e0a2",
        stroke: "#120c05",
        strokeThickness: 7,
      }).setOrigin(0.5).setDepth(531).setAlpha(0);
      const subtitle = this.add.text(cx, cy + 42, "The Next Day", {
        fontFamily: "Georgia, serif",
        fontSize: "22px",
        fontStyle: "bold",
        color: "#d0ab67",
        stroke: "#120c05",
        strokeThickness: 4,
      }).setOrigin(0.5).setDepth(531).setAlpha(0);

      this.tweens.add({
        targets: overlay,
        alpha: 1,
        duration: 360,
        ease: "Quad.easeIn",
      });
      this.tweens.add({
        targets: [title, subtitle],
        alpha: 1,
        delay: 260,
        duration: 240,
        ease: "Quad.easeOut",
      });
      this.tweens.add({
        targets: [overlay, title, subtitle],
        alpha: 0,
        delay: 1120,
        duration: 380,
        ease: "Quad.easeOut",
        onComplete: () => {
          overlay.destroy();
          title.destroy();
          subtitle.destroy();
        },
      });
    }

    playSpeechBubble(entityId, text) {
      const token = this.tokens.get(normalizeId(entityId));
      const line = String(text || "").trim();
      if (!token || !line) return;

      this.clearSpeechBubble(token);

      const maxWidth = Math.max(120, Math.min(260, this.board.cell * 3.4));
      const paddingX = 12;
      const paddingY = 9;
      const bubble = this.add.container(token.container.x, token.container.y - this.board.cell * 0.9).setDepth(260);
      const label = this.add.text(0, 0, line, {
        fontFamily: "Georgia, serif",
        fontSize: Math.max(13, this.board.cell * 0.18) + "px",
        color: "#1b1710",
        lineSpacing: 4,
        wordWrap: { width: maxWidth },
      });
      const width = Math.min(maxWidth, Math.max(80, label.width)) + paddingX * 2;
      const height = Math.max(34, label.height) + paddingY * 2;
      const background = this.add.graphics();

      background.fillStyle(0xfff5dc, 0.96);
      background.fillRoundedRect(-width / 2, -height, width, height, 12);
      background.fillTriangle(-10, 0, 10, 0, 0, 12);
      background.lineStyle(2, 0x2c2418, 0.24);
      background.strokeRoundedRect(-width / 2, -height, width, height, 12);
      label.setPosition(-width / 2 + paddingX, -height + paddingY);

      bubble.add([background, label]);
      bubble.setScale(0.82);
      bubble.setAlpha(0);
      token.speechBubble = bubble;

      this.tweens.add({
        targets: bubble,
        scaleX: 1,
        scaleY: 1,
        alpha: 1,
        duration: 200,
        ease: "Back.easeOut",
      });

      token.speechBubbleTimer = this.time.delayedCall(2400, () => {
        this.tweens.add({
          targets: bubble,
          y: bubble.y - 20,
          alpha: 0,
          duration: 300,
          ease: "Quad.easeIn",
          onComplete: () => {
            bubble.destroy();
            if (token.speechBubble === bubble) {
              token.speechBubble = null;
              token.speechBubbleTimer = null;
            }
          },
        });
      });
    }

    clearSpeechBubble(token) {
      if (token.speechBubbleTimer) {
        token.speechBubbleTimer.remove(false);
        token.speechBubbleTimer = null;
      }
      if (token.speechBubble) {
        token.speechBubble.destroy();
        token.speechBubble = null;
      }
    }

    upsertToken(entity) {
      const id = normalizeId(entity.id);
      let token = this.tokens.get(id);
      if (!token) {
        token = this.createToken(entity);
        this.tokens.set(id, token);
      }

      token.entity = entity;
      this.applyTokenStyle(token, entity.kind);
      this.applyTokenVisual(token, entity);
      this.moveToken(token, entity.x, entity.y, true);
    }

    tokenLayerForKind(kind) {
      return this.entityLayer;
    }

    syncTokenLayer(token, kind) {
      const layer = this.tokenLayerForKind(kind);
      if (!layer || token.renderLayer === layer) return;
      if (token.renderLayer && typeof token.renderLayer.remove === "function") {
        token.renderLayer.remove(token.container);
      }
      layer.add(token.container);
      token.renderLayer = layer;
    }

    kindDepth(kind) {
      const depths = {
        player: DEPTH_LAYERS.actors + 1,
        hostile: DEPTH_LAYERS.actors + 1,
        neutral: DEPTH_LAYERS.actors + 1,
        object: DEPTH_LAYERS.actors,
        loot: DEPTH_LAYERS.actors,
        door: DEPTH_LAYERS.actors,
        trap: DEPTH_LAYERS.actors,
        chest: DEPTH_LAYERS.actors,
      };
      return depths[kind] || DEPTH_LAYERS.actors;
    }

    kindBaseScale(kind) {
      const scales = {
        player: 1.08,
        hostile: 1.06,
        neutral: 1.04,
        object: 0.94,
        loot: 0.84,
        door: 1,
        trap: 0.9,
        chest: 0.94,
      };
      return scales[kind] || 1;
    }

    updateTokenScale(token) {
      const baseScale = this.scaleForTile(token.baseScale || 1);
      token.baseWorldScale = baseScale;
      token.container.setScale(baseScale);
    }

    createToken(entity) {
      const container = this.add.container(0, 0);
      const sprite = this.add.image(0, 0, SPRITE_KEYS.actors, pickFrame(ACTOR_FRAMES.neutral, entity.id)).setOrigin(0.5);
      const poisonIcon = this.add.image(5, -6, SPRITE_KEYS.tiles, TILE_FRAMES.poison)
        .setOrigin(0.5)
        .setScale(0.52);
      poisonIcon.setVisible(false);
      const lockBadge = this.add.image(5, -6, SPRITE_KEYS.tiles, TILE_FRAMES.locked)
        .setOrigin(0.5)
        .setScale(0.52);
      lockBadge.setVisible(false);

      container.add([sprite, poisonIcon, lockBadge]);
      container.setDepth(this.kindDepth(entity.kind));
      return {
        container,
        sprite,
        poisonIcon,
        entity,
        pulseTween: null,
        moveTween: null,
        lootTween: null,
        trapTween: null,
        doorTween: null,
        doorOpenState: null,
        lockBadge,
        speechBubble: null,
        speechBubbleTimer: null,
        currentKind: null,
        baseScale: this.kindBaseScale(entity.kind),
        baseWorldScale: 1,
        hasSpawned: false,
        renderLayer: null,
      };
    }

    applyTokenStyle(token, kind) {
      this.syncTokenLayer(token, kind);
      token.baseScale = this.kindBaseScale(kind);
      token.container.setDepth(this.kindDepth(kind));
      this.updateTokenScale(token);
      if (token.currentKind !== kind) {
        token.currentKind = kind;
        this.updateIdleTween(token, true);
      }
    }

    updateIdleTween(token, forceReset = false) {
      if (forceReset && token.pulseTween) {
        token.pulseTween.stop();
        token.pulseTween = null;
      }
      if (forceReset && token.lootTween) {
        token.lootTween.stop();
        token.lootTween = null;
      }
      if (forceReset && token.trapTween) {
        token.trapTween.stop();
        token.trapTween = null;
      }

      token.container.setScale(token.baseWorldScale);
      token.sprite.setAlpha(1);

      if (token.currentKind === "player" && !token.pulseTween) {
        token.pulseTween = this.tweens.add({
          targets: token.container,
          scaleX: token.baseWorldScale * 1.06,
          scaleY: token.baseWorldScale * 1.06,
          duration: 900,
          yoyo: true,
          repeat: -1,
          ease: "Sine.easeInOut",
        });
      }

      if (token.currentKind !== "loot" && token.lootTween) {
        token.lootTween.stop();
        token.lootTween = null;
      }
      if (token.currentKind === "loot" && !token.lootTween) {
        token.lootTween = this.tweens.add({
          targets: token.sprite,
          alpha: 0.62,
          duration: 760,
          ease: "Sine.easeInOut",
          yoyo: true,
          repeat: -1,
        });
      }

      if (token.currentKind !== "trap" && token.trapTween) {
        token.trapTween.stop();
        token.trapTween = null;
      }
      if (token.currentKind === "trap" && !token.trapTween) {
        token.trapTween = this.tweens.add({
          targets: token.sprite,
          alpha: 0.52,
          duration: 660,
          ease: "Sine.easeInOut",
          yoyo: true,
          repeat: -1,
        });
      }
    }

    resetTokenSpriteTransform(token) {
      token.sprite.setScale(1, 1);
      token.sprite.setAngle(0);
      token.sprite.setAlpha(1);
      if (typeof token.sprite.clearTint === "function") token.sprite.clearTint();
    }

    resolveActorFrame(entity) {
      const kind = entity.kind;
      const id = normalizeId(entity.id);
      const data = safeObject(entity.data);
      const hint = normalizeId(data.name || data.type || data.kind || id);
      if (ACTOR_FRAMES.partyById[id] !== undefined) {
        return ACTOR_FRAMES.partyById[id];
      }
      if (kind === "player") {
        return pickFrame(ACTOR_FRAMES.player, id || hint);
      }
      if (kind === "hostile") {
        if (ACTOR_FRAMES.hostileById[id] !== undefined) return ACTOR_FRAMES.hostileById[id];
        if (hint.includes("goblin")) return 11;
        if (hint.includes("skeleton")) return 13;
        if (hint.includes("vampire")) return 12;
        return pickFrame(ACTOR_FRAMES.hostile, id || hint);
      }
      if (kind === "neutral") {
        return pickFrame(ACTOR_FRAMES.neutral, id || hint);
      }
      return pickFrame(ACTOR_FRAMES.object, id || hint);
    }

    applyTokenVisual(token, entity) {
      this.resetTokenSpriteTransform(token);
      if (token.poisonIcon) token.poisonIcon.setVisible(false);
      if (token.lockBadge) token.lockBadge.setVisible(false);

      if (entity.kind === "door") {
        this.applyDoorVisual(token, entity.data);
        return;
      }
      if (entity.kind === "trap") {
        this.applyTrapVisual(token, entity);
        return;
      }
      if (entity.kind === "chest") {
        this.applyChestVisual(token, entity.data);
        return;
      }
      if (entity.kind === "loot") {
        token.sprite.setTexture(SPRITE_KEYS.tiles, pickFrame(TILE_FRAMES.loot, normalizeId(entity.id)));
        return;
      }
      if (entity.kind === "object") {
        token.sprite.setTexture(SPRITE_KEYS.tiles, pickFrame(TILE_FRAMES.prop, normalizeId(entity.id)));
        return;
      }

      token.sprite.setTexture(SPRITE_KEYS.actors, this.resolveActorFrame(entity));
      this.applyStatusEffects(token, entity.data);
    }

    applyTrapVisual(token, entity) {
      token.sprite.setTexture(SPRITE_KEYS.tiles, pickFrame(TILE_FRAMES.trap, normalizeId(entity.id)));
      token.sprite.setAlpha(0.96);
    }

    applyChestVisual(token, data) {
      const locked = isLocked(data);
      token.sprite.setTexture(SPRITE_KEYS.tiles, locked ? TILE_FRAMES.chestClosed : TILE_FRAMES.chestOpen);
      if (token.lockBadge) token.lockBadge.setVisible(locked);
    }

    applyDoorVisual(token, data) {
      const open = isDoorOpen(data);
      const frame = open ? TILE_FRAMES.doorOpen : TILE_FRAMES.doorClosed;
      const changed = token.doorOpenState !== null && token.doorOpenState !== open;
      token.doorOpenState = open;
      if (token.doorTween) {
        token.doorTween.stop();
        token.doorTween = null;
      }
      if (!changed) {
        token.sprite.setTexture(SPRITE_KEYS.tiles, frame);
        token.sprite.setAlpha(open ? 0.76 : 1);
        return;
      }
      token.doorTween = this.tweens.add({
        targets: token.sprite,
        alpha: 0.34,
        duration: 90,
        ease: "Sine.easeInOut",
        onComplete: () => {
          token.sprite.setTexture(SPRITE_KEYS.tiles, frame);
          token.doorTween = this.tweens.add({
            targets: token.sprite,
            alpha: open ? 0.76 : 1,
            duration: 90,
            ease: "Sine.easeInOut",
            onComplete: () => {
              token.doorTween = null;
            },
          });
        },
      });
    }

    applyStatusEffects(token, data) {
      const actorId = normalizeId(safeObject(token.entity).id || "");
      const effects = normalizeStatusEffects(data);
      const isPoisoned = effects.includes("poisoned");
      const isProne = effects.includes("prone");

      if (token.poisonIcon) {
        token.poisonIcon.setVisible(isPoisoned);
      }
      token.sprite.setScale(isProne ? 1.16 : 1, isProne ? 0.68 : 1);
      token.sprite.setAngle(isProne ? 90 : 0);

      if (isPoisoned) {
        token.sprite.setAlpha(0.9);
        if (typeof token.sprite.setTint === "function") token.sprite.setTint(0xa2ff9e);
      } else {
        token.sprite.setAlpha(1);
        const baseTint = ACTOR_TINTS[actorId];
        if (baseTint !== undefined && typeof token.sprite.setTint === "function") {
          token.sprite.setTint(baseTint);
        } else if (typeof token.sprite.clearTint === "function") {
          token.sprite.clearTint();
        }
      }
    }

    moveToken(token, gridX, gridY, animate) {
      const target = this.gridToWorld(gridX, gridY);
      const samePosition = Math.abs(token.container.x - target.x) < 0.5 && Math.abs(token.container.y - target.y) < 0.5;
      if (token.moveTween) {
        token.moveTween.stop();
        token.moveTween = null;
      }
      if (!animate || !token.hasSpawned) {
        token.container.setPosition(target.x, target.y);
        token.hasSpawned = true;
        return;
      }
      if (samePosition) {
        return;
      }
      token.moveTween = this.tweens.add({
        targets: token.container,
        x: target.x,
        y: target.y,
        duration: 180,
        ease: "Sine.easeOut",
        onComplete: () => {
          token.moveTween = null;
          token.hasSpawned = true;
        },
      });
    }

    positionAllTokens(animate) {
      this.tokens.forEach((token) => {
        this.moveToken(token, token.entity.x, token.entity.y, animate);
      });
    }

    destroyToken(token) {
      if (token.moveTween) token.moveTween.stop();
      if (token.pulseTween) token.pulseTween.stop();
      if (token.lootTween) token.lootTween.stop();
      if (token.trapTween) token.trapTween.stop();
      if (token.doorTween) token.doorTween.stop();
      this.clearSpeechBubble(token);
      token.container.destroy();
    }

    gridToWorld(gridX, gridY) {
      return {
        x: this.board.x + (gridX + 0.5) * this.board.cell,
        y: this.board.y + (gridY + 0.5) * this.board.cell,
      };
    }
  }

  const initialViewport = gameViewportSize();
  const config = {
    type: Phaser.AUTO,
    parent: "game-viewport",
    backgroundColor: "rgba(0,0,0,0)",
    transparent: true,
    render: {
      pixelArt: true,
      roundPixels: true,
    },
    width: initialViewport.width,
    height: initialViewport.height,
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    physics: {
      default: "arcade",
      arcade: { debug: false },
    },
    scene: [MainScene],
  };

  window.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("game-viewport")) return;
    controller.game = new Phaser.Game(config);
    window.addEventListener("resize", () => controller.resize());
  });
})();
