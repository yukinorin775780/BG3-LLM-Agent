/**
 * necromancer-meta.js
 * ───────────────────────────────────────────────────────
 * Necromancer Lab demo-specific metadata.
 * Loaded before app.js so the main orchestrator can merge these
 * into its global registries.
 *
 * Exposed on window.BG3NecromancerMeta for cross-module access.
 */
(() => {
  "use strict";

  /* ── map_id 配置（URL 参数优先，默认 necromancer_lab） ── */
  const MAP_ID =
    new URLSearchParams(window.location.search).get("map_id") ||
    "necromancer_lab";

  /* ── 追加角色 Speaker 元数据 ── */
  const SPEAKER_META_EXTENSIONS = {
    gribbo: { name: "格里波", color: "#8bc34a", sigil: "🐸" },
  };

  /* ── 追加物品元数据 ── */
  const ITEM_META_EXTENSIONS = {
    heavy_iron_key: { label: "沉重铁钥匙", icon: "🗝" },
    necromancer_diary: { label: "死灵法师日记", icon: "📓" },
    antidote_formula: { label: "解毒配方残页", icon: "📜" },
  };

  /* ── 追加位置标签 ── */
  const LOCATION_LABEL_EXTENSIONS = {
    necromancer_lab: "死灵法师的废弃实验室",
  };

  /* ── 场景对象友好标签 ── */
  const OBJECT_LABELS = {
    gas_trap_1: "毒气陷阱",
    heavy_oak_door_1: "通往地表的沉重大门",
    necromancer_diary: "沾满血污的日记本",
    chest_1: "死灵法师的战利品箱",
  };

  /* ── 四幕目标 ── */
  const ACT_OBJECTIVES = Object.freeze([
    {
      act: 1,
      title: "陷阱感知",
      summary: "发现毒气陷阱，Astarion 气泡提醒，Shadowheart tense 状态。",
      keywords: ["gas_trap", "毒气", "trap", "陷阱感知", "tense"],
    },
    {
      act: 2,
      title: "解读日记",
      summary: "读日记 — INT / Arcana / Investigation 检定，解读死灵法师笔记。",
      keywords: [
        "necromancer_diary",
        "日记",
        "arcana",
        "investigation",
        "diary",
      ],
    },
    {
      act: 3,
      title: "Gribbo 交涉",
      summary: "Astarion 插话，选择站队，好感度变化与 Gribbo hostile 转变。",
      keywords: ["gribbo", "交涉", "站队", "插话", "hostile"],
    },
    {
      act: 4,
      title: "逃离实验室",
      summary: "搜刮 heavy_iron_key，钥匙入包，开门，Demo Cleared。",
      keywords: [
        "heavy_iron_key",
        "heavy_oak_door",
        "开门",
        "escape",
        "cleared",
      ],
    },
  ]);

  /* ── 推断当前幕数（基于 journal_events / flags） ── */
  function inferCurrentAct(journalEvents, flags) {
    const events = Array.isArray(journalEvents) ? journalEvents : [];
    const f = flags && typeof flags === "object" ? flags : {};
    const text = events.join(" ").toLowerCase();

    if (
      f.necromancer_lab_escape_complete ||
      /demo.*cleared|通关/i.test(text)
    ) {
      return 4;
    }
    if (
      f.world_necromancer_lab_gribbo_defeated ||
      f.necromancer_lab_gribbo_combat_triggered ||
      /gribbo.*hostile|gribbo.*战斗/i.test(text)
    ) {
      return 4;
    }
    if (
      f.necromancer_lab_gribbo_negotiation_started ||
      /gribbo.*交涉|gribbo.*对话/i.test(text)
    ) {
      return 3;
    }
    if (
      f.necromancer_lab_diary_read ||
      /日记|diary|arcana|investigation/i.test(text)
    ) {
      return 2;
    }
    if (
      f.world_necromancer_lab_trap_warned ||
      /毒气|gas_trap|陷阱感知/i.test(text)
    ) {
      return 1;
    }
    return 1;
  }

  /* ── Public API ── */
  window.BG3NecromancerMeta = Object.freeze({
    MAP_ID,
    SPEAKER_META_EXTENSIONS,
    ITEM_META_EXTENSIONS,
    LOCATION_LABEL_EXTENSIONS,
    OBJECT_LABELS,
    ACT_OBJECTIVES,
    inferCurrentAct,
  });
})();
