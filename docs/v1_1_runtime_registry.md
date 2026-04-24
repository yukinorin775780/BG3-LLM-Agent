# V1.1 Runtime Registry Governance

## Scope
本文件补充 V1.1 Thread B 的两类治理内容：
- Runtime Actor Registry 配置化
- `actor_invocation_mode` / `actor_invocation_reason` 路由标记契约

SOP 冻结文档：
- `docs/v1_1_runtime_npc_sop.md`

## Runtime Actor Registry 配置位置
- 配置文件：`config/runtime_actor_registry.yaml`
- 配置键：`runtime_enabled_actors`
- 当前配置：
  - `shadowheart`
  - `astarion`
  - `laezel`

Registry 读取入口：
- `core/actors/registry.py`
  - `load_runtime_actor_ids(...)`
  - `get_default_actor_registry()`

兼容策略：
- 配置缺失、YAML 解析失败、或配置为空时，回退到内置兼容列表（当前为 `shadowheart` + `astarion`）。
- actor 未启用 runtime 时，保持 legacy fallback 行为，不破坏主流程。

## 新增 Actor 接入步骤
1. 在 `config/runtime_actor_registry.yaml` 的 `runtime_enabled_actors` 列表中加入 actor id（小写 canonical id，如 `laezel`）。
2. 确认该 actor 的角色配置与 `entities` 中 id 一致。
3. 运行回归：
   - `pytest -q`
   - `python -m core.eval.runner --suite golden`
   - `make check`
4. 如需行为锁定，新增/扩展一个 golden case 覆盖该 actor 的 runtime path、memory scope 与 event_drain 写回。
5. 确认 fallback 监控仍有效（未注册 actor 应产出 `actor_invocation_mode=fallback` 与 `actor_invocation_reason=runtime_missing`）。

## Routing Marker 契约

### `actor_invocation_mode`
语义：当前发言 actor 在本轮采用的 invocation 路径。

可用值：
- `runtime`：命中 ActorRuntime，走 DomainEvent + EventDrain 链路。
- `fallback`：runtime 不可用或执行失败，回落到 legacy generation 路径。
- `legacy`：保留别名（router 兼容），语义等同 fallback。

### `actor_invocation_reason`
语义：解释为何进入该路径。

当前值：
- `runtime_enabled`：成功命中 runtime。
- `runtime_missing`：registry 未启用该 actor runtime。
- `runtime_failed`：runtime 调用异常。
- `actor_id_missing`：当前 speaker 缺失。

约束：
- marker 由 `actor_invocation_node` 写入。
- marker 必须在后续 patch（含 `event_drain`）后保留，不得被静默清除。

## Breaking Change 定义
以下变更在 V1.1 内视为 breaking change：
- 移除或重命名 `config/runtime_actor_registry.yaml` 的 `runtime_enabled_actors` 键且不提供兼容读取。
- 改变 `actor_invocation_mode` 既有值语义，导致路由行为变化（`runtime` 不再进入 `event_drain`，或 `fallback/legacy` 不再进入 generation）。
- 删除 `actor_invocation_reason` 或改变其现有原因值语义，导致 fallback 可观测性下降。
- 让未启用 runtime 的 actor 不再产生可观测 fallback marker/telemetry（静默回退）。

## 测试锚点
- registry 配置读取与默认配置：`tests/test_actor_registry.py`
- runtime/fallback marker 与 event_drain 保留（含 shadowheart/astarion/laezel）：`tests/test_actor_invocation_node.py`
- shadowheart runtime marker：`tests/test_shadowheart_runtime_integration.py`
- route 对 `runtime` / `fallback` / `legacy` 的分流：`tests/test_graph_routers.py`
- prompt 隔离（含 laezel）：`tests/test_generation_actor_view.py`
- golden runtime registry 演练：`evals/golden/laezel_runtime_registry.yaml`
