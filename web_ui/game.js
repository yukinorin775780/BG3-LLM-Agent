(() => {
  const DEFAULT_MAP_DATA = {
    id: "",
    width: 10,
    height: 10,
    obstacles: [],
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
    const data = safeObject(rawMapData);
    const id = String(data.id || data.map_id || data.key || data.name || "").trim();
    const width = Math.max(1, Math.round(Number(data.width) || DEFAULT_MAP_DATA.width));
    const height = Math.max(1, Math.round(Number(data.height) || DEFAULT_MAP_DATA.height));
    const obstacles = Array.isArray(data.obstacles) ? data.obstacles : [];
    return { id, width, height, obstacles };
  }

  function gridCoord(value, fallback, max) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.max(0, Math.min(max - 1, Math.round(num)));
  }

  function firstGlyph(id, data) {
    const name = String(safeObject(data).name || id || "?");
    const cjk = name.match(/[\u4e00-\u9fff]/);
    if (cjk) return cjk[0];
    const alpha = name.match(/[A-Za-z0-9]/);
    return alpha ? alpha[0].toUpperCase() : "?";
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
      this.gridGraphics = null;
      this.obstacleGraphics = null;
      this.obstacleLabels = [];
      this.mapData = DEFAULT_MAP_DATA;
      this.board = { x: 0, y: 0, width: 640, height: 640, cell: 64 };
      this.tokens = new Map();
      this.transitionOverlay = null;
      this.lastTransitionAt = -Infinity;
    }

    preload() {
      // Geometry-only prototype scene. No external assets are required yet.
    }

    create() {
      this.gridGraphics = this.add.graphics().setDepth(1);
      this.obstacleGraphics = this.add.graphics().setDepth(5);
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
        x: (width - boardWidth) / 2,
        y: (height - boardHeight) / 2,
        width: boardWidth,
        height: boardHeight,
        cell,
      };

      this.drawGrid();
      this.drawObstacles();
      this.positionAllTokens(false);
      if (this.transitionOverlay) {
        this.transitionOverlay
          .setPosition(0, 0)
          .setSize(width, height)
          .setDisplaySize(width, height);
      }
    }

    drawGrid() {
      const { x, y, width, height, cell } = this.board;
      const map = normalizeMapData(this.mapData);

      this.gridGraphics.clear();

      // The canvas outside this rounded board remains the dark "unreachable void".
      this.gridGraphics.fillStyle(0x08090c, 0.76);
      this.gridGraphics.fillRect(0, 0, this.scale.width, this.scale.height);

      this.gridGraphics.fillStyle(0x12161b, 0.86);
      this.gridGraphics.fillRoundedRect(x, y, width, height, 14);
      this.gridGraphics.lineStyle(2, 0xd0ab67, 0.72);
      this.gridGraphics.strokeRoundedRect(x, y, width, height, 14);

      for (let col = 0; col <= map.width; col += 1) {
        const px = x + col * cell;
        const alpha = col === 0 || col === map.width ? 0.78 : 0.28;
        this.gridGraphics.lineStyle(1, 0x73c6c3, alpha);
        this.gridGraphics.lineBetween(px, y, px, y + height);
      }

      for (let row = 0; row <= map.height; row += 1) {
        const py = y + row * cell;
        const alpha = row === 0 || row === map.height ? 0.78 : 0.28;
        this.gridGraphics.lineStyle(1, 0x73c6c3, alpha);
        this.gridGraphics.lineBetween(x, py, x + width, py);
      }
    }

    drawObstacles() {
      this.obstacleGraphics.clear();
      this.obstacleLabels.forEach((label) => label.destroy());
      this.obstacleLabels = [];

      const obstacles = Array.isArray(this.mapData.obstacles) ? this.mapData.obstacles : [];
      obstacles.forEach((rawObstacle) => {
        const obstacle = safeObject(rawObstacle);
        const blocksMovement = obstacle.blocks_movement === true;
        const blocksLos = obstacle.blocks_los === true;
        const kind = normalizeId(obstacle.type);

        obstacleCoordinates(obstacle, this.mapData).forEach(({ x, y }) => {
          const rect = this.gridRect(x, y, 0.16);

          if (blocksMovement && blocksLos) {
            this.obstacleGraphics.fillStyle(0x34373d, 0.96);
            this.obstacleGraphics.lineStyle(2, 0x6c7078, 0.9);
          } else if (blocksMovement) {
            this.obstacleGraphics.fillStyle(0xd66a22, 0.9);
            this.obstacleGraphics.lineStyle(2, 0xffb15e, 0.94);
          } else {
            this.obstacleGraphics.fillStyle(0x44606a, 0.62);
            this.obstacleGraphics.lineStyle(1, 0x73c6c3, 0.5);
          }

          this.obstacleGraphics.fillRoundedRect(rect.x, rect.y, rect.size, rect.size, 6);
          this.obstacleGraphics.strokeRoundedRect(rect.x, rect.y, rect.size, rect.size, 6);

          if (kind === "campfire" || (blocksMovement && !blocksLos)) {
            const label = this.add.text(rect.x + rect.size / 2, rect.y + rect.size / 2, "火", {
              fontFamily: "Georgia, serif",
              fontSize: Math.max(12, rect.size * 0.42) + "px",
              fontStyle: "bold",
              color: "#fff1c2",
            }).setOrigin(0.5).setDepth(6);
            this.obstacleLabels.push(label);
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
      token.label.setText(this.tokenGlyph(entity));
      this.applyTokenStyle(token, entity.kind);
      if (token.lockBadge) token.lockBadge.setVisible(false);
      if (entity.kind === "loot") {
        if (token.poisonIcon) token.poisonIcon.setVisible(false);
        token.shape.setScale(1, 1);
        token.shape.setAngle(0);
        token.shadow.setScale(1, 1);
      } else if (entity.kind === "door") {
        if (token.poisonIcon) token.poisonIcon.setVisible(false);
        this.applyDoorVisual(token, entity.data);
      } else if (entity.kind === "trap") {
        if (token.poisonIcon) token.poisonIcon.setVisible(false);
        this.applyTrapVisual(token);
      } else if (entity.kind === "chest") {
        if (token.poisonIcon) token.poisonIcon.setVisible(false);
        this.applyChestVisual(token, entity.data);
      } else {
        this.applyStatusEffects(token, entity.data);
      }
      this.moveToken(token, entity.x, entity.y, true);
    }

    tokenGlyph(entity) {
      if (entity.kind === "loot") return "✦";
      if (entity.kind === "door") return "门";
      if (entity.kind === "trap") return "⚠";
      if (entity.kind === "chest") return "箱";
      return firstGlyph(entity.id, entity.data);
    }

    createToken(entity) {
      const container = this.add.container(0, 0);
      const radius = Math.max(12, Math.min(22, this.board.cell * 0.31));
      const shadow = this.add.circle(0, radius * 0.25, radius, 0x000000, 0.32);
      let shape;
      if (entity.kind === "door") {
        shape = this.add.rectangle(0, 0, this.board.cell * 0.86, this.board.cell * 0.82, 0x5b341e, 1);
      } else if (entity.kind === "trap") {
        shape = this.add.rectangle(0, 0, this.board.cell * 0.78, this.board.cell * 0.78, 0x380909, 0.34);
      } else if (entity.kind === "object" || entity.kind === "loot" || entity.kind === "chest") {
        shape = this.add.rectangle(0, 0, radius * 1.7, radius * 1.7, 0xe67e22, 1);
      } else {
        shape = this.add.circle(0, 0, radius, 0x4a90e2, 1);
      }
      const label = this.add.text(0, 0, firstGlyph(entity.id, entity.data), {
        fontFamily: "Georgia, serif",
        fontSize: Math.max(12, radius * 0.88) + "px",
        fontStyle: "bold",
        color: "#ffffff",
      }).setOrigin(0.5);
      const poisonIcon = this.add.circle(radius * 0.62, -radius * 0.78, Math.max(4, radius * 0.22), 0x88ff88, 0.92);
      poisonIcon.setStrokeStyle(2, 0x163f1c, 0.86);
      poisonIcon.setVisible(false);
      const lockBadge = this.add.text(radius * 0.68, -radius * 0.78, "🔒", {
        fontFamily: "Georgia, serif",
        fontSize: Math.max(12, radius * 0.68) + "px",
        fontStyle: "bold",
        color: "#ffd86b",
        stroke: "#2a1600",
        strokeThickness: 3,
      }).setOrigin(0.5);
      lockBadge.setVisible(false);

      container.add([shadow, shape, label, poisonIcon, lockBadge]);
      container.setDepth(entity.kind === "player" ? 100 : 20);
      return {
        container,
        shadow,
        shape,
        label,
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
      };
    }

    applyTokenStyle(token, kind) {
      const colors = {
        player: { fill: 0x1f6fce, stroke: 0x8ab4f8, depth: 100 },
        hostile: { fill: 0xb02222, stroke: 0xf88a8a, depth: 50 },
        neutral: { fill: 0x5f7374, stroke: 0xd5dbdb, depth: 30 },
        object: { fill: 0x9a5a1f, stroke: 0xf39c12, depth: 25 },
        loot: { fill: 0xffd700, stroke: 0xfff0a8, depth: 45 },
        door: { fill: 0x5b341e, stroke: 0xc7904c, depth: 42 },
        trap: { fill: 0x380909, stroke: 0xff3b3b, depth: 44 },
        chest: { fill: 0x8a5524, stroke: 0xffcf70, depth: 35 },
      };
      const style = colors[kind] || colors.neutral;
      token.shape.setFillStyle(style.fill, 1);
      token.shape.setStrokeStyle(3, style.stroke, 1);
      token.label.setColor("#ffffff");
      token.container.setDepth(style.depth);

      if (kind === "player" && !token.pulseTween) {
        token.pulseTween = this.tweens.add({
          targets: token.container,
          scaleX: 1.08,
          scaleY: 1.08,
          duration: 1100,
          yoyo: true,
          repeat: -1,
          ease: "Sine.easeInOut",
        });
      }

      if (kind !== "player" && token.pulseTween) {
        token.pulseTween.stop();
        token.pulseTween = null;
        token.container.setScale(1);
      }

      if (kind === "loot" && !token.lootTween) {
        token.lootTween = this.tweens.add({
          targets: [token.shape, token.label],
          alpha: 0.6,
          duration: 820,
          ease: "Sine.easeInOut",
          yoyo: true,
          repeat: -1,
        });
      }

      if (kind !== "loot" && token.lootTween) {
        token.lootTween.stop();
        token.lootTween = null;
        token.shape.setAlpha(1);
        token.label.setAlpha(1);
      }

      if (kind === "trap" && !token.trapTween) {
        token.trapTween = this.tweens.add({
          targets: [token.shape, token.label],
          alpha: 0.48,
          duration: 760,
          ease: "Sine.easeInOut",
          yoyo: true,
          repeat: -1,
        });
      }

      if (kind !== "trap" && token.trapTween) {
        token.trapTween.stop();
        token.trapTween = null;
        token.shape.setAlpha(1);
        token.label.setAlpha(1);
      }
    }

    applyTrapVisual(token) {
      if (typeof token.shape.setSize === "function") {
        token.shape.setSize(this.board.cell * 0.78, this.board.cell * 0.78);
      }
      token.shape.setScale(1, 1);
      token.shape.setAngle(0);
      token.shape.setFillStyle(0x380909, 0.34);
      token.shape.setStrokeStyle(4, 0xff3b3b, 1);
      token.label.setColor("#ffb3a7");
      token.label.setAlpha(1);
      token.shadow.setScale(1.08, 0.82);
    }

    applyChestVisual(token, data) {
      if (typeof token.shape.setSize === "function") {
        token.shape.setSize(this.board.cell * 0.58, this.board.cell * 0.48);
      }
      token.shape.setScale(1, 1);
      token.shape.setAngle(0);
      token.shape.setAlpha(1);
      token.shape.setFillStyle(0x8a5524, 1);
      token.shape.setStrokeStyle(3, 0xffcf70, 0.95);
      token.label.setColor("#fff1c2");
      token.label.setAlpha(1);
      token.shadow.setScale(1, 0.72);
      if (token.lockBadge) {
        token.lockBadge.setVisible(isLocked(data));
        token.lockBadge.setPosition(this.board.cell * 0.22, -this.board.cell * 0.22);
      }
    }

    applyDoorVisual(token, data) {
      const open = isDoorOpen(data);
      if (typeof token.shape.setSize === "function") {
        token.shape.setSize(this.board.cell * 0.86, this.board.cell * 0.82);
      }
      const target = open
        ? { scaleX: 0.16, scaleY: 1.05, angle: 90, alpha: 0.48, labelAlpha: 0.58, shadowScaleX: 0.32, shadowScaleY: 0.9 }
        : { scaleX: 1, scaleY: 1, angle: 0, alpha: 1, labelAlpha: 0.92, shadowScaleX: 1.18, shadowScaleY: 0.72 };
      const changed = token.doorOpenState !== null && token.doorOpenState !== open;

      token.doorOpenState = open;
      if (token.doorTween) {
        token.doorTween.stop();
        token.doorTween = null;
      }

      if (!changed) {
        token.shape.setScale(target.scaleX, target.scaleY);
        token.shape.setAngle(target.angle);
        token.shape.setAlpha(target.alpha);
        token.label.setAlpha(target.labelAlpha);
        token.shadow.setScale(target.shadowScaleX, target.shadowScaleY);
        return;
      }

      token.doorTween = this.tweens.add({
        targets: token.shape,
        scaleX: target.scaleX,
        scaleY: target.scaleY,
        angle: target.angle,
        alpha: target.alpha,
        duration: 100,
        ease: "Sine.easeInOut",
        onComplete: () => {
          token.doorTween = null;
        },
      });
      this.tweens.add({
        targets: [token.label],
        alpha: target.labelAlpha,
        duration: 100,
        ease: "Sine.easeInOut",
      });
      this.tweens.add({
        targets: token.shadow,
        scaleX: target.shadowScaleX,
        scaleY: target.shadowScaleY,
        duration: 100,
        ease: "Sine.easeInOut",
      });
    }

    applyStatusEffects(token, data) {
      const effects = normalizeStatusEffects(data);
      const isPoisoned = effects.includes("poisoned");
      const isProne = effects.includes("prone");

      if (token.poisonIcon) {
        token.poisonIcon.setVisible(isPoisoned);
      }
      token.shape.setScale(isProne ? 1.35 : 1, isProne ? 0.55 : 1);
      token.shape.setAngle(isProne ? 90 : 0);
      token.shadow.setScale(isProne ? 1.4 : 1, isProne ? 0.55 : 1);
      token.label.setAlpha(isProne ? 0.72 : 1);

      if (isPoisoned && typeof token.shape.setFillStyle === "function") {
        token.shape.setAlpha(0.88);
        if (typeof token.label.setTint === "function") {
          token.label.setTint(0x88ff88);
        }
      } else {
        token.shape.setAlpha(1);
        if (typeof token.label.clearTint === "function") {
          token.label.clearTint();
        }
      }
    }

    moveToken(token, gridX, gridY, animate) {
      const target = this.gridToWorld(gridX, gridY);
      if (token.moveTween) {
        token.moveTween.stop();
        token.moveTween = null;
      }
      if (!animate) {
        token.container.setPosition(target.x, target.y);
        return;
      }
      token.moveTween = this.tweens.add({
        targets: token.container,
        x: target.x,
        y: target.y,
        duration: 360,
        ease: "Sine.easeInOut",
        onComplete: () => {
          token.moveTween = null;
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

    gridRect(gridX, gridY, insetRatio) {
      const inset = this.board.cell * insetRatio;
      return {
        x: this.board.x + gridX * this.board.cell + inset,
        y: this.board.y + gridY * this.board.cell + inset,
        size: this.board.cell - inset * 2,
      };
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
