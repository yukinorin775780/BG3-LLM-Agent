# V1.3 Capability Freeze

## 冻结日期
- 2026-04-27

## 冻结范围
V1.3 冻结覆盖以下能力与其 golden baseline：

1. Social Action / Item Transaction Protocol
2. Party Turn Coordinator
3. Policy-based Actor Visibility
4. Golden baseline（`case_count=17`）

---

## 稳定契约（Capability Contracts）

### 1) Social Action / Item Transaction Protocol
输入/输出边界：
- 输入：ActorRuntime 基于 `ActorView` 产出 `ActorDecision` 与 `DomainEvent`。
- 输出：交易/消耗相关副作用必须表示为 `DomainEvent`（例如 `actor_item_transaction_requested`）。

状态写回责任边界：
- ActorRuntime：只能产出 decision/event，不能直接改 `entities/player_inventory/flags`。
- DomainEvent/EventDrain：唯一写回入口，负责把 transaction/event 落地为 state patch。
- 物理变更：通过 EventDrain 内部兼容路径（physics）落地，不允许 runtime 直接 mutate world。

兼容要求：
- `use_item/consume` legacy 语义必须保持可用。

### 2) Party Turn Coordinator
输入/输出边界：
- 输入：`current_speaker + speaker_queue`、当前 state、registry。
- 输出：同回合多 actor 的 decision/event 聚合结果、fallback 列表、deterministic 顺序响应。

状态写回责任边界：
- Coordinator：只做编排，不直接写 inventory/hp/flags。
- EventDrain：统一处理多 actor 事件写回。

稳定性要求：
- 同一输入下响应顺序 deterministic。
- legacy fallback 仍可用且必须有明确 marker/telemetry，不可静默降级。

### 3) Policy-based Actor Visibility
输入/输出边界：
- 输入：raw `flags`/`environment_objects` + actor_id + state（用于 reveal 判定）。
- 输出：仅返回该 actor 可见的 `ActorView.visible_flags` 与 `visible_environment_objects`。

责任边界：
- ActorView 构建阶段负责过滤。
- generation/dialogue/runtime 只消费 filtered ActorView，不绕过读取 raw state 私密内容。

兼容要求：
- legacy prefix fallback（`world_/quest_/combat_/public_`）必须保持兼容。
- `visibility` policy metadata 不得泄露到 ActorView 可见字段。

### 4) Deterministic Replay 契约
- Golden replay 必须 deterministic。
- 禁止真实 LLM、真实时间、真实随机数、网络依赖进入 replay 路径。
- eval 结果必须可复现并可用于回归门禁。

---

## Breaking Change 定义（V1.3 冻结后禁止）

以下变更在 V1.3 冻结后视为 breaking change：

1. Runtime 直接修改 state。
2. 绕过 EventDrain 写回 transaction/event。
3. Party coordinator 响应顺序变为非确定性。
4. ActorView 泄露 hidden/private flag。
5. 删除 legacy prefix fallback 且无迁移策略。
6. 破坏 `use_item/consume` 兼容。
7. 破坏 Eval YAML 向后兼容。

---

## 新增内容准入门槛（Admission Gates）

任何新增能力/机制必须同时满足：

1. 必须有单元测试（或更高层测试）覆盖关键契约。
2. 必须新增 golden case，或扩展现有 golden 并包含真实断言。
3. 必须通过以下门禁：
   - `pytest -q`
   - `python -m core.eval.runner --suite golden`
   - `make check`
4. 不允许依赖真实 LLM、真实时间、真实随机数、网络调用。
5. 不允许绕过 `ActorView`、`MemoryService`、`EventDrain`。

---

## 当前 Golden Baseline（冻结值）

- `case_count=17`

V1.3 新增/升级关键 case：
- `astarion_rejects_unwanted_gift`
- `shadowheart_accepts_healing_potion`
- `party_banter_after_player_choice`
- `laezel_disagrees_with_mercy_choice`
- `shadowheart_artifact_secret_actor_visibility`
- `world_flag_reveal_to_visible_party`

---

## V1.4 Backlog（冻结后迭代方向）

1. 统一 policy engine。
2. policy audit log。
3. field-level entity visibility。
4. richer party turn scoring/tension strategy。
5. more social action types。
6. content authoring tools / lint。

---

## 冻结结论

在 `pytest`、golden suite、`make check` 全通过前提下，V1.3 Capability Contract 可视为正式冻结。
