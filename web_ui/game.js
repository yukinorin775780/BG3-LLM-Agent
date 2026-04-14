(() => {
  const DEFAULT_MAP_DATA = {
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
      this.latestState = {
        partyStatus: safeObject(partyStatus),
        environmentObjects: safeObject(environmentObjects),
        mapData: normalizeMapData(mapData),
      };
      if (this.scene) {
        this.scene.syncState(this.latestState);
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
  };

  window.BG3TacticalMap = controller;

  function safeObject(value) {
    return value && typeof value === "object" ? value : {};
  }

  function normalizeId(id) {
    return String(id || "").trim().toLowerCase();
  }

  function normalizeMapData(rawMapData) {
    const data = safeObject(rawMapData);
    const width = Math.max(1, Math.round(Number(data.width) || DEFAULT_MAP_DATA.width));
    const height = Math.max(1, Math.round(Number(data.height) || DEFAULT_MAP_DATA.height));
    const obstacles = Array.isArray(data.obstacles) ? data.obstacles : [];
    return { width, height, obstacles };
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
    if (normalizeId(id) === "player") return "player";
    if (normalizeId(entity.faction) === "hostile") return "hostile";
    if (source === "environment") return "object";
    return "neutral";
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
    }

    preload() {
      // Geometry-only prototype scene. No external assets are required yet.
    }

    create() {
      this.gridGraphics = this.add.graphics().setDepth(1);
      this.obstacleGraphics = this.add.graphics().setDepth(5);
      this.scale.on("resize", this.handleResize, this);
      controller.scene = this;
      this.syncState(controller.latestState);
    }

    syncState(nextState) {
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
          token.container.destroy();
          this.tokens.delete(id);
        }
      });
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

    upsertToken(entity) {
      const id = normalizeId(entity.id);
      let token = this.tokens.get(id);
      if (!token) {
        token = this.createToken(entity);
        this.tokens.set(id, token);
      }

      token.entity = entity;
      token.label.setText(firstGlyph(entity.id, entity.data));
      this.applyTokenStyle(token, entity.kind);
      this.moveToken(token, entity.x, entity.y, true);
    }

    createToken(entity) {
      const container = this.add.container(0, 0);
      const radius = Math.max(12, Math.min(22, this.board.cell * 0.31));
      const shadow = this.add.circle(0, radius * 0.25, radius, 0x000000, 0.32);
      const shape = entity.kind === "object"
        ? this.add.rectangle(0, 0, radius * 1.7, radius * 1.7, 0xe67e22, 1)
        : this.add.circle(0, 0, radius, 0x4a90e2, 1);
      const label = this.add.text(0, 0, firstGlyph(entity.id, entity.data), {
        fontFamily: "Georgia, serif",
        fontSize: Math.max(12, radius * 0.88) + "px",
        fontStyle: "bold",
        color: "#ffffff",
      }).setOrigin(0.5);

      container.add([shadow, shape, label]);
      container.setDepth(entity.kind === "player" ? 100 : 20);
      return { container, shadow, shape, label, entity, pulseTween: null };
    }

    applyTokenStyle(token, kind) {
      const colors = {
        player: { fill: 0x1f6fce, stroke: 0x8ab4f8, depth: 100 },
        hostile: { fill: 0xb02222, stroke: 0xf88a8a, depth: 50 },
        neutral: { fill: 0x5f7374, stroke: 0xd5dbdb, depth: 30 },
        object: { fill: 0x9a5a1f, stroke: 0xf39c12, depth: 25 },
      };
      const style = colors[kind] || colors.neutral;
      token.shape.setFillStyle(style.fill, 1);
      token.shape.setStrokeStyle(3, style.stroke, 1);
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
    }

    moveToken(token, gridX, gridY, animate) {
      const target = this.gridToWorld(gridX, gridY);
      if (!animate) {
        token.container.setPosition(target.x, target.y);
        return;
      }
      this.tweens.killTweensOf(token.container);
      this.tweens.add({
        targets: token.container,
        x: target.x,
        y: target.y,
        duration: 360,
        ease: "Sine.easeInOut",
      });
    }

    positionAllTokens(animate) {
      this.tokens.forEach((token) => {
        this.moveToken(token, token.entity.x, token.entity.y, animate);
      });
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

  const config = {
    type: Phaser.AUTO,
    parent: "map-container",
    backgroundColor: "rgba(0,0,0,0)",
    transparent: true,
    width: window.innerWidth,
    height: window.innerHeight,
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    physics: {
      default: "arcade",
      arcade: { debug: false },
    },
    scene: [MainScene],
  };

  window.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("map-container")) return;
    controller.game = new Phaser.Game(config);
  });
})();
