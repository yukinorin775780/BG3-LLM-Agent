# Content Sprint 1 Playable Demo Freeze

## 1. Demo Identity
- Demo 名称：Necromancer Lab / 死灵法师废弃实验室。
- 当前状态：Frozen playable baseline。
- 冻结范围：Content Sprint 1 Thread A/B/C/D/E 已落地能力与 golden 验收集。

## 2. Official Entry Points

### 2.1 API 启动（正式入口）
- 通过 `/api/chat` 启动新会话时传入：
  - `map_id=necromancer_lab`
  - `intent=init_sync`
- 请求示例：

```bash
curl -X POST http://127.0.0.1:8010/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo_freeze_smoke",
    "intent": "init_sync",
    "user_input": "",
    "map_id": "necromancer_lab"
  }'
```

### 2.2 Eval 启动（正式验收入口）

```bash
python -m core.eval.runner --suite golden
```

### 2.3 CLI 说明
- 当前 CLI 未提供稳定 `map_id` 启动参数。
- Content Sprint 1 正式入口以 API/Eval 为准。

## 3. Four-Act Playable Flow

### Act1 - 毒气陷阱与暗中观察
- 进入实验室触发开场感知。
- Astarion 预警毒气陷阱，Shadowheart 感知死灵残留并进入警惕状态。
- 保持 ActorView 可见性隔离，不直接向玩家暴露隐藏陷阱全量元数据。

### Act2 - 死灵日记与危险知识
- 阅读 `necromancer_diary` 触发 INT/Investigation/Arcana 判定。
- 成功/失败分支均可回放，成功分支写入 scoped memory，失败分支仅碎片知识。

### Act3 - 谈判、拱火与站队
- 与 Gribbo 谈判时，Astarion 通过 Party Turn 插话。
- 玩家站队 Astarion 或训斥 Astarion，都会触发战斗，但 affection/memory 后果不同。

### Act4 - 搜刮钥匙与逃脱
- Gribbo 战败后搜刮 `heavy_iron_key`，关键转移路径经 DomainEvent/EventDrain。
- 触发战后 companion banter/reflection。
- 用钥匙打开 `heavy_oak_door_1`，`demo_cleared=true` 并写入完成标记。

## 4. Act-to-Golden Mapping
- Act1：
  - `necromancer_lab_act1_trap_perception`
- Act2：
  - `necromancer_lab_act2_diary_int_success`
  - `necromancer_lab_act2_diary_int_failure`
- Act3：
  - `necromancer_lab_act3_side_with_astarion`
  - `necromancer_lab_act3_rebuke_astarion`
- Act4：
  - `necromancer_lab_act4_loot_key_and_escape`

## 5. Key Flags (Freeze Contract)
- `necromancer_lab_intro_seen`
- `necromancer_lab_diary_read`
- `necromancer_lab_diary_decoded`
- `necromancer_lab_player_sided_with_astarion`
- `necromancer_lab_gribbo_combat_triggered`
- `necromancer_lab_gribbo_key_looted`
- `necromancer_lab_escape_complete`
- `content_sprint_1_complete`

## 6. Key Items
- `heavy_iron_key`
- `healing_potion`

## 7. Key NPCs
- Gribbo
- Shadowheart
- Astarion
- Lae’zel

## 8. Acceptance Baseline
- `pytest -q`
- `python -m core.eval.runner --suite golden`
- `make check`
- 当前冻结基线：
  - `pytest -q: 276 passed`
  - `golden suite: case_count=24, failed_count=0, ok=true`
  - `make check: passed`

## 9. Known Retained Risks
- 通用 loot 仍存在 legacy direct mutation 路径。
- Act3/Act4 触发主要依赖 deterministic keyword/context。
- Act1 perception 当前是轻量规则，不是统一 skill-check framework。
- scoped memory 在状态侧已闭环，但向量层长期策略仍可后续统一。

## 10. Freeze Decision
- Content Sprint 1 四幕剧情基线已冻结为 playable demo baseline。
- 后续变更若影响上述四幕主链或关键 golden，不可降级为 smoke，必须保持 deterministic golden 验收。
