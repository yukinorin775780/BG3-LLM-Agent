# V1 Contract Freeze

## 冻结日期
- 2026-04-24

## 当前验证命令与结果
- `pytest -q`: `218 passed in 4.32s`
- `python -m core.eval.runner --suite golden`: `case_count=5, failed_count=0, ok=true`
- `make check`: `passed`

> 说明：以上为冻结基线结果；本次冻结执行会再次跑同样命令，结果以后文“冻结执行复验”记录为准。

## 冻结对象与稳定承诺

### 1) ActorView
冻结范围：`ActorView` / `ActorSelfState` / `PublicEntityView` / `VisibleMessage` 的语义边界。

稳定承诺：
- Prompt 相关主路径必须经由 `ActorView` 消费可见状态，不得直接依赖 raw state 暴露 peer 私密字段。
- `self_state` 仅承载当前 actor 私有字段；`other_entities` 仅承载 public 视图字段。
- `visible_flags`、`visible_history`、`recent_public_events` 继续保持“可见即最小”的裁剪语义。

breaking change（V1 内禁止）：
- 将 peer 私密字段（如 `inventory` / `dynamic_states` / `secret_objective`）加入 `PublicEntityView` 或默认注入 prompt。
- 将 prompt 组装入口改为可绕过 `ActorView` 直接读取完整 `state["entities"]` 的私密字段。
- 修改 `ActorView` 关键字段含义导致现有节点语义变化（即使字段名未变）。

允许的兼容扩展：
- 仅新增可选字段，且默认值不改变现有构造与消费路径。
- 新增字段必须保持“默认不泄漏私密信息”。
- 允许在不改变现有字段语义的前提下增加辅助只读元数据。

### 2) MemoryService / actor-scoped retrieval
冻结范围：`MemoryService.retrieve_for_actor`、`ActorScopedMemoryRetriever` 以及 actor scope 隔离策略。

稳定承诺：
- actor 检索必须包含 `actor_private:<actor_id>` scope，且维持 actor-private / party_shared / world 的策略边界。
- director 检索不得访问任何 `actor_private:*` scope。
- actor 检索接口语义保持 actor-scoped，不退化为全局共享检索。

breaking change（V1 内禁止）：
- actor 路径移除 `actor_id` 作用域或改为跨 actor 共享私有记忆。
- director 路径读取 actor 私有作用域。
- 修改 scope key 规则导致已有私有记忆不可隔离或被错误混检。

允许的兼容扩展：
- 在保持隔离规则不变前提下调整重排打分细节（importance/recency/location 等）。
- 新增公共 scope（非私有）作为补充召回源，默认不影响私有隔离。
- 新增检索 telemetry 字段，但不移除现有核心字段语义。

### 3) ActorRuntime / ActorDecision / ReflectionRequest
冻结范围：`ActorRuntime` 协议、`ActorDecision`、`ReflectionRequest` 的交互契约。

稳定承诺：
- `decide(actor_view) -> ActorDecision`：运行时输出决策，不直接写世界状态。
- `reflect(request) -> Tuple[DomainEvent, ...]`：反思输出事件，不直接写世界状态。
- `ActorDecision.emitted_events` 与 `requested_reflections` 仍是 runtime 对外副作用的唯一结构化出口。

breaking change（V1 内禁止）：
- 将 runtime 输出从“事件/请求”改为直接 mutation state。
- 改变 `ActorDecision.kind` 既有语义导致路由或下游处理失效。
- 破坏 `ReflectionRequest` 必填字段语义（`actor_id`/`reason`/`priority`/`source_turn`）。

允许的兼容扩展：
- 新增可选决策元字段（默认不影响既有路由）。
- 新增可选反思 payload 扩展字段。
- 在不破坏现有事件消费方的前提下增加新的 decision telemetry。

### 4) DomainEvent / EventDrain
冻结范围：`DomainEvent` 数据结构、`event_drain_node` 作为事件写回 patch 的主入口。

稳定承诺：
- ActorRuntime 与反思产生的事件先进入 `pending_events`，再由 `event_drain_node` 统一落盘为 state patch。
- `event_drain_node` 继续承担 DomainEvent -> state patch 的集中转换职责。
- 无 pending events 时，`event_drain_node` 保持无副作用快速返回。

breaking change（V1 内禁止）：
- 绕过 EventDrain 在其他路径直接消费/改写 `pending_events` 造成双写或顺序不可控。
- 更改 `DomainEvent` 基础字段语义导致现有 apply 逻辑失配。
- 将反思队列处理与无事件 drain 逻辑耦合，破坏当前行为边界。

允许的兼容扩展：
- 新增 event_type（需保持旧类型行为不变）。
- 为 payload 新增可选键（旧消费者默认忽略）。
- 新增 event telemetry 统计字段，不改变现有 patch 结果结构。

### 5) GameService `process_chat_turn`
冻结范围：`process_chat_turn` 对 API/CLI/Eval 暴露的响应结构与关键 intent 路径语义。

稳定承诺：
- 返回结构保持包含：`responses`、`journal_events`、`current_location`、`environment_objects`、`party_status`、`player_inventory`、`combat_state`。
- `init_sync` / `background_step` / `process_reflections` / `ui_action_loot` 的高层语义保持不变。
- API 层继续轻委托到应用服务，不引入协议层结构破坏。

breaking change（V1 内禁止）：
- 删除或重命名上述响应主键。
- 将键类型从稳定结构改为不兼容类型（例如 `responses` 从 list 改为 dict）。
- 修改 intent 行为导致 CLI/API/Eval 消费路径失效。

允许的兼容扩展：
- 新增可选响应字段。
- 在 `combat_state` / `environment_objects` 内新增可选子字段。
- 保留旧字段兼容的前提下扩展 stream payload 元信息。

### 6) Eval YAML schema / Golden replay behavior
冻结范围：`EVAL_CASE_YAML_SCHEMA`、Golden suite 发现与 replay 补丁行为。

稳定承诺：
- Golden suite 继续由 `evals/golden/*.yml|*.yaml` 发现并执行。
- replay 的时钟、随机数、LLM script patch 语义保持 deterministic。
- runner 继续输出 transcript/telemetry/final_state/summary 工件。

breaking change（V1 内禁止）：
- 修改 schema 必填层级导致现有 golden 用例无法加载。
- 取消或破坏 replay patch 目标集合，导致回放不稳定。
- 变更 runner 输出工件契约导致下游校验脚本失效。

允许的兼容扩展：
- 仅新增可选 YAML 字段，默认值保持现有行为。
- 新增断言类别时保持旧断言语义与键路径不变。
- 新增工件内容但不删除既有工件文件类型。

## Contract Guard 覆盖检查

### Guard A: prompt 路径不能绕过 ActorView 读取 raw state 中其他 NPC 私密信息
已覆盖测试文件：
- `tests/test_actor_view_builder.py`
- `tests/test_generation_actor_view.py`
- `tests/test_dialogue_actor_view.py`

### Guard B: MemoryService 必须 actor-scoped
已覆盖测试文件：
- `tests/test_memory_retrieval_policy.py`
- `tests/test_actor_memory_provider.py`
- `tests/test_actor_view_builder.py`（memory provider 调用 actor_id）

### Guard C: EventDrain 是 DomainEvent 写回主入口
已覆盖测试文件：
- `tests/test_actor_invocation_node.py`（事件写入 `pending_events`）
- `tests/test_graph_routers.py`（runtime 分支路由至 `event_drain`）
- `tests/test_event_drain.py`（DomainEvent -> state patch）
- `tests/test_background_step.py`（`process_reflections` 路径通过 `event_drain_node` 落盘）

### Guard D: Golden eval runner 能稳定 replay
已覆盖测试文件：
- `tests/test_eval_replay.py`
- `tests/test_eval_runner.py`
- `tests/test_golden_suite_smoke.py`

### Guard E: GameService 响应结构不破坏 API/CLI/Eval
已覆盖测试文件：
- `tests/test_game_service.py`
- `tests/test_server_api.py`
- `tests/test_main_cli.py`

结论：当前 guard 无明显测试缺口，本次冻结不新增测试，仅冻结文档化。

## V1.1 Backlog（冻结后可迭代）
- 为 `ActorView` / `ChatTurnResult` 引入显式 `schema_version` 与兼容性声明。
- 为 `DomainEvent` 增加版本化演进策略（event_type registry + payload validator）。
- 在不破坏 actor-scope 的前提下补齐检索重排（importance/recency/location）与可观测性。
- 增加 eval case schema 静态校验命令（CI gate），提升 YAML 变更安全性。
- 补充 replay 一致性回归（同 case 多次运行 artifacts 比对）。

## 冻结执行复验
- `pytest -q`: `218 passed in 3.99s`
- `python -m core.eval.runner --suite golden`: `case_count=5, passed_count=5, failed_count=0, ok=true`
- `make check`: `passed`（子步骤：`pytest -q` 218 passed；golden suite `ok=true`）

## V1.1 补充文档
- Runtime Actor Registry 配置化与 routing marker 契约见：
  - `docs/v1_1_runtime_registry.md`
- Runtime NPC 准入 SOP（Thread D Freeze）见：
  - `docs/v1_1_runtime_npc_sop.md`
