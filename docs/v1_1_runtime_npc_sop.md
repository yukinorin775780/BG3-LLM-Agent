# V1.1 Runtime NPC SOP (Frozen)

## 适用范围
本 SOP 适用于“新增 Runtime NPC”场景：
- 在不改主图拓扑、不改外部 API 契约的前提下，为新 NPC 启用 ActorRuntime 路径。
- 目标是将接入成本控制为：配置启用 + 最小测试 + golden case。

## 前置条件
- 角色配置已存在，且可在现有世界初始化/实体体系中被识别。
- `actor_id` 必须使用项目 canonical id（小写，例：`shadowheart` / `astarion` / `laezel`）。
- Runtime Actor Registry 已配置启用该 `actor_id`：
  - 配置文件：`config/runtime_actor_registry.yaml`
  - 配置键：`runtime_enabled_actors`

## 标准接入步骤
1. 确认角色 canonical `actor_id`。
2. 在 runtime actor registry 配置中启用该 `actor_id`。
3. 确保 prompt/context 只走 `ActorView`（禁止绕过读取 raw state 私密字段）。
4. 确保 memory retrieval 使用 actor-scoped query（`actor_id=<new_actor>`）。
5. 确保行为输出通过 `ActorDecision` / `DomainEvent`。
6. 确保状态写回通过 `EventDrain`。
7. 添加测试：隔离测试、memory 测试、event_drain 测试、routing marker 测试。
8. 添加 golden case（可回放、可断言 runtime path 与隔离语义）。
9. 运行 `make check` 并通过。

## 禁止事项
- 禁止绕过 `ActorView` 读取 raw state 私密信息。
- 禁止在 `graph_builder` / `graph_routers` 中散落硬编码 actor_id。
- 禁止新增真实 LLM/torch/transformers/SentenceTransformers 加载。
- 禁止修改 `GameService` 外部响应结构。
- 禁止修改 Eval YAML schema（除非提供向后兼容迁移）。

## 必须测试清单
- registry runtime-enabled（新 actor 可由配置启用并被 registry 识别）。
- `actor_invocation_mode` / `actor_invocation_reason` 正确。
- `ActorView` visibility isolation（不泄露其他 NPC 私密状态/背包/目标）。
- actor-scoped memory retrieval（检索 actor_id 为新 actor）。
- `DomainEvent` / `EventDrain` writeback 生效。
- unknown actor fallback marker 保持可观测。
- golden replay 通过。

## 验收门槛
- `pytest -q` 通过。
- `python -m core.eval.runner --suite golden` 通过。
- `make check` 通过。

## Breaking Change 定义
以下变更在 V1.1 SOP 下视为 breaking change：
- 删除/重命名 `ActorView` 字段（导致既有消费方行为变化）。
- 改变 actor-scoped memory 语义（退化为跨 actor 私有数据混检）。
- 绕过 `EventDrain` 写回 runtime event。
- 删除 `actor_invocation_mode` / `actor_invocation_reason` marker 或破坏其语义。
- 破坏 `GameService` / API / Eval 的外部契约。

## Routing Marker 语义补充
- `actor_invocation_mode`：`runtime` / `fallback` / `legacy`（legacy 为 fallback 兼容别名）。
- `actor_invocation_reason`：
  - `runtime_enabled`
  - `runtime_missing`
  - `runtime_failed`
  - `actor_id_missing`

## 当前基线（Freeze Snapshot）
- `pytest -q`: `233 passed in 5.53s`
- golden suite: `7/7 passed`
- `make check`: `passed`

## 关联文档
- `docs/v1_contract_freeze.md`
- `docs/v1_1_runtime_registry.md`
