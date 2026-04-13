(() => {
  const GRID_SIZE = 10;
  const FALLBACK_STATE = {
    partyStatus: {
      player: { name: "玩家", faction: "player", x: 4, y: 5 },
    },
    environmentObjects: {
      goblin_1: { name: "地精", faction: "hostile", status: "alive", x: 6, y: 5 },
    },
  };

  const controller = {
    scene: null,
    latestState: FALLBACK_STATE,
    update(partyStatus, environmentObjects) {
      this.latestState = {
        partyStatus: safeObject(partyStatus),
        environmentObjects: safeObject(environmentObjects),
      };
      if (this.scene) {
        this.scene.syncState(this.latestState.partyStatus, this.latestState.environmentObjects);
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

  function gridCoord(value, fallback) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.max(0, Math.min(GRID_SIZE - 1, Math.round(num)));
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

  function collectEntities(partyStatus, environmentObjects) {
    const entities = [];

    Object.entries(safeObject(partyStatus)).forEach(([id, data]) => {
      const entity = safeObject(data);
      if (entity.x === undefined || entity.y === undefined) return;
      entities.push({
        id,
        data: entity,
        source: "party",
        kind: tokenKind(id, entity, "party"),
        x: gridCoord(entity.x, 0),
        y: gridCoord(entity.y, 0),
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
        x: gridCoord(entity.x, 0),
        y: gridCoord(entity.y, 0),
      });
    });

    if (entities.length > 0) return entities;
    return collectEntities(FALLBACK_STATE.partyStatus, FALLBACK_STATE.environmentObjects);
  }

  if (!window.Phaser) {
    console.warn("Phaser 未加载，战术地图 Canvas 暂不可用。");
    return;
  }

  class MainScene extends Phaser.Scene {
    constructor() {
      super("MainScene");
      this.gridGraphics = null;
      this.board = { x: 0, y: 0, size: 640, cell: 64 };
      this.tokens = new Map();
    }

    preload() {
      // Placeholder-only scene: geometry is drawn in create/update, no external assets needed.
    }

    create() {
      this.gridGraphics = this.add.graphics();
      this.scale.on("resize", this.handleResize, this);
      this.handleResize({ width: this.scale.width, height: this.scale.height });
      controller.scene = this;
      this.syncState(controller.latestState.partyStatus, controller.latestState.environmentObjects);
    }

    handleResize(gameSize) {
      const width = gameSize.width || this.scale.width;
      const height = gameSize.height || this.scale.height;
      const size = Math.min(width, height) * 0.84;
      this.board = {
        x: (width - size) / 2,
        y: (height - size) / 2,
        size,
        cell: size / GRID_SIZE,
      };
      this.drawGrid();
      this.positionAllTokens(false);
    }

    drawGrid() {
      const { x, y, size, cell } = this.board;
      this.gridGraphics.clear();
      this.gridGraphics.fillStyle(0x12161b, 0.82);
      this.gridGraphics.fillRoundedRect(x, y, size, size, 14);
      this.gridGraphics.lineStyle(2, 0xd0ab67, 0.72);
      this.gridGraphics.strokeRoundedRect(x, y, size, size, 14);

      for (let i = 0; i <= GRID_SIZE; i += 1) {
        const pos = Math.round(i * cell);
        const alpha = i === 0 || i === GRID_SIZE ? 0.72 : 0.28;
        this.gridGraphics.lineStyle(1, 0x73c6c3, alpha);
        this.gridGraphics.lineBetween(x + pos, y, x + pos, y + size);
        this.gridGraphics.lineBetween(x, y + pos, x + size, y + pos);
      }

      this.gridGraphics.lineStyle(1, 0xffd28a, 0.12);
      for (let i = 0; i < GRID_SIZE; i += 1) {
        this.gridGraphics.strokeRect(x + i * cell + 4, y + i * cell + 4, cell - 8, cell - 8);
      }
    }

    syncState(partyStatus, environmentObjects) {
      const entities = collectEntities(partyStatus, environmentObjects);
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
      const shadow = this.add.circle(0, 5, 20, 0x000000, 0.32);
      const shape = entity.kind === "object"
        ? this.add.rectangle(0, 0, 34, 34, 0xe67e22, 1)
        : this.add.circle(0, 0, 20, 0x4a90e2, 1);
      const label = this.add.text(0, 0, firstGlyph(entity.id, entity.data), {
        fontFamily: "Georgia, serif",
        fontSize: "18px",
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
