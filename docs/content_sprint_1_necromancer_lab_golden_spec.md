# Content Sprint 1 - Necromancer Lab Golden Acceptance Spec

## 1. Purpose
- 目标：为四幕剧情提供可回放、可断言、可扩展的 golden 蓝图。
- 范围：定义 case 规格与断言要求，不在本线程直接实现完整业务逻辑。
- 约束：deterministic replay；不依赖真实 LLM/真实时间/真实随机数/网络。

## 2. Global Replay Contract

### 2.1 Recommended Determinism Block
- `strict: false`（与当前 golden 基线保持一致，避免脚本耗尽引发假失败）
- `perf_counter`: 固定序列
- `now_iso`: 固定时间戳（例如 `2026-01-01T00:00:00+00:00`）
- `randint` / `choice_indices` / `random_values`: 预置脚本化序列
- `llm.dm`: 固定 action_type / responders / reason

### 2.2 Shared Fixture Baseline
- `session.map_id: necromancer_lab`
- 队伍包含 `player/shadowheart/astarion/laezel`
- `gribbo` 初始 `faction=neutral`，持有 `heavy_iron_key`
- `gas_trap_1` 初始 `is_hidden=true`
- `demo_cleared=false`

### 2.3 Mandatory Assertion Dimensions (Each Case)
- `routing/runtime marker`：如 `actor_invocation_mode`, `actor_invocation_reason`
- `state`：flags/entities/inventory/combat/demo_cleared
- `memory`：actor_private / party_shared 写入与隔离
- `visibility`：ActorView 上下文不泄露不可见信息
- `event_drain`：pending events 被 drain，写回生效
- `telemetry`：包含关键 event markers

## 3. Proposed Golden Cases

## 3.1 `necromancer_lab_act1_trap_perception`

Status: landed in Thread B（case 文件：`evals/golden/necromancer_lab_act1_trap_perception.yaml`）。

### Initial State
- `session.map_id=necromancer_lab`
- `gas_trap_1.is_hidden=true`
- `flags.necromancer_lab_intro_seen` 未设置

### Input Steps
1. `init_sync`（首次）
2. `init_sync`（再次同步，用于验证不重复触发）

### Mock LLM Output
- 不依赖 LLM（`llm: {}`）。

### Mock Dice / Random
- 固定 determinism 脚本（`strict: false` + 固定 perf/time/random），但该 case 不消费真实随机分支。

### Assertions
- state:
  - 首次 `init_sync` 后：
    - `necromancer_lab_intro_seen=true`
    - `world_necromancer_lab_intro_entered=true`
    - `world_necromancer_lab_trap_warned=true`
    - `astarion_detected_gas_trap` / `shadowheart_senses_necromancy` policy flag 生效
    - `shadowheart.status_effects` 含 `tense`
  - 第二次 `init_sync`：
    - intro 不重复（`game_state.journal_events.3` 不存在）
- visibility:
  - 玩家响应 `environment_objects` 不包含 `gas_trap_1`（hidden trap metadata 不外泄）
- routing/telemetry:
  - `turn_finished(intent=init_sync, success=true)` 可稳定回放

## 3.2 `necromancer_lab_act2_diary_int_success`

Status: landed in Thread C（case 文件：`evals/golden/necromancer_lab_act2_diary_int_success.yaml`）。

### Initial State
- `necromancer_diary` 可读
- 日记未读取标志为 false
- `session.map_id=necromancer_lab`

### Input Steps
1. 玩家输入：`用奥术知识阅读 necromancer_diary。`

### Mock LLM Output
- `dm`:
  - `action_type: READ`
  - `action_target: necromancer_diary`
  - `reason: scripted_read_necromancer_diary_success`

### Mock Dice / Random
- `randint`: 成功值（当前 golden 使用 `16`，INT=10 + Arcana +2 可稳定成功）

### Assertions
- state:
  - `flags.necromancer_lab_diary_read=true`
  - `flags.necromancer_lab_diary_decoded=true`
  - `flags.necromancer_lab_antidote_formula_fragment_known.visibility.scope=actor`
  - `flags.necromancer_lab_key_hint_known.visibility.scope=party`
  - `latest_roll.intent=READ`
  - `latest_roll.skill=arcana`
  - `latest_roll.result.is_success=true`
- memory:
  - `actor_runtime_state.player.memory_notes` 写入完整危险知识（Gribbo/毒气/heavy_iron_key/解药中断）
  - `actor_runtime_state.__party_shared__.memory_notes` 写入可共享摘要
- visibility:
  - 响应 `environment_objects` 不暴露 `gas_trap_1` hidden metadata
- event_drain:
  - `event_count=2`（private + party_shared memory events）
- routing/telemetry:
  - `turn_finished(intent=chat, success=true)`
  - `event_drain` telemetry 存在且可重放

## 3.3 `necromancer_lab_act2_diary_int_failure`

Status: landed in Thread C（case 文件：`evals/golden/necromancer_lab_act2_diary_int_failure.yaml`）。

### Initial State
- 同 `act2 success`

### Input Steps
1. 玩家输入：`阅读 necromancer_diary。`

### Mock LLM Output
- `dm`:
  - READ 目标固定为 `necromancer_diary`
  - `reason: scripted_read_necromancer_diary_failure`

### Mock Dice / Random
- `randint`: 失败值（当前 golden 使用 `6`，INT=10 + Intelligence +0 无法过 DC14）

### Assertions
- state:
  - `flags.necromancer_lab_diary_read=true`
  - `flags.necromancer_lab_diary_decoded=false`
  - `latest_roll.skill=intelligence`
  - `latest_roll.result.is_success=false`
- memory:
  - 仅写入阅读者碎片记忆（地精/箱子/毒气）
  - 不生成 `party_shared` diary 记忆
- visibility:
  - `flags.necromancer_lab_antidote_formula_fragment_known` 不存在
  - `flags.necromancer_lab_key_hint_known` 不存在
  - 响应 `environment_objects` 不暴露 `gas_trap_1`
- event_drain:
  - `event_count=1`（仅碎片 private memory event）
- routing/telemetry:
  - `turn_finished(intent=chat, success=true)`
  - `event_drain` telemetry 存在且可重放

## 3.4 `necromancer_lab_act3_side_with_astarion`

Status: landed in Thread D（case 文件：`evals/golden/necromancer_lab_act3_side_with_astarion.yaml`）。

### Initial State
- `gribbo` 存活、可对话、持有 `heavy_iron_key`
- `gribbo.dynamic_states.patience` 初值 > 0
- 队友在场，Party Turn Coordinator 可触发

### Input Steps
1. `START_DIALOGUE` 对 `gribbo`
2. 玩家输入：`阿斯代伦说得对，你这地精真可笑。把钥匙交出来。`

### Mock LLM Output
- `dm`:
  - step1: `START_DIALOGUE -> gribbo`
  - step2: `CHAT` + responders `astarion/shadowheart`（party turn runtime）
  - `reason: scripted_act3_side_with_astarion`
- runtime:
  - Astarion 插话嘲讽并产出 negotiation outcome / affection / memory events。

### Mock Dice / Random
- 固定 `choice_indices` 与 `random_values`，确保响应顺序稳定

### Assertions
- state:
  - `astarion.affection` 增量 `+2`
  - `gribbo.patience` 归零（或等价触发条件）
  - `combat_active=true`
  - `necromancer_lab_gribbo_combat_triggered=true`
- memory:
  - Astarion 写入“玩家支持其嘲讽策略”的 actor_private 记忆
- visibility:
  - 其他 actor 不应获得 Astarion 私密反应全文
- event_drain:
  - 多 actor DomainEvents 被统一写回，`pending_events=[]`
- routing/telemetry:
  - `actor_invocation_reason=party_turn_runtime_multi`

## 3.5 `necromancer_lab_act3_rebuke_astarion`

Status: landed in Thread D（case 文件：`evals/golden/necromancer_lab_act3_rebuke_astarion.yaml`）。

### Initial State
- 同上

### Input Steps
1. `START_DIALOGUE` 对 `gribbo`
2. 玩家输入：`阿斯代伦，闭嘴。我们在谈判，不是来羞辱人的。`

### Mock LLM Output
- `dm`:
  - step1: `START_DIALOGUE -> gribbo`
  - step2: `CHAT` + responders `astarion/shadowheart`
  - `reason: scripted_act3_rebuke_astarion`
- runtime:
  - Astarion 输出被训斥后的负面回应并产出 paranoia 破裂事件。

### Mock Dice / Random
- 固定脚本，确保同样最终触发谈判破裂并开战

### Assertions
- state:
  - `astarion.affection` 增量 `-3`
  - `combat_active=true`
  - `necromancer_lab_gribbo_combat_triggered=true`
- memory:
  - Astarion 写入长期负面记忆（可标注 `memory_type=relationship`）
- visibility:
  - 其他 NPC 不应读取该私密记忆内容
- event_drain:
  - memory/event 写回成功且 `pending_events=[]`
- routing/telemetry:
  - 同回合多 actor marker 保持存在
  - journal 中包含 `paranoia` 破裂理由

## 3.6 `necromancer_lab_act4_loot_key_and_escape`

### Initial State
- `gribbo.status=dead`
- `gribbo.inventory.heavy_iron_key=1`
- `heavy_oak_door_1.is_open=false`
- `demo_cleared=false`

### Input Steps
1. 玩家输入：`搜刮 Gribbo 的尸体，拿钥匙。`
2. 玩家输入：`用 heavy_iron_key 打开 heavy_oak_door_1。`
3. 队友战后一句反思/banter（用于 runtime + event_drain 验证）

### Mock LLM Output
- `dm`:
  - step1 映射到 `LOOT` 或等价 transaction 触发
  - step2 映射到 `INTERACT`（门）
  - step3 触发 companion runtime 回应

### Mock Dice / Random
- 固定 `randint` 保证开门/交互结果稳定

### Assertions
- state:
  - `player_inventory.heavy_iron_key >= 1`
  - `gribbo.inventory.heavy_iron_key == 0`
  - `heavy_oak_door_1.is_open=true`
  - `demo_cleared=true`
- memory:
  - 至少一名 companion 写入战后反思记忆
- visibility:
  - 私密战后情绪不应在其他 actor prompt 中泄露
- event_drain:
  - 键物品转移由 DomainEvent/EventDrain 落地（而非 runtime 直接改 state）
  - telemetry 存在 `event_drain` 且 event_count 符合步骤规模
- routing/telemetry:
  - loot/door 路径 marker 清晰；runtime 步骤 marker 正常

## 4. Suggested Rollout Plan (Next Thread)
- 先落 Act 3 两个 case（已与 Party Turn 能力最贴合，回归价值最高）。
- 再落 Act 4（验证 transaction/event_drain 主链路）。
- 再落 Act 1/2（依赖 Perception/INT/Arcana 判定语义补强）。
- 每新增 1 case 即跑一次 `pytest -q` + `python -m core.eval.runner --suite golden`，最后跑 `make check`。
