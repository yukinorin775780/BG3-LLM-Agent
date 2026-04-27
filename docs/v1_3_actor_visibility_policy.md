# V1.3 Actor Visibility Policy

## 目标
- 将 `ActorView` 的 flag/env 可见性从前缀过滤升级为 policy-based。
- 保持旧前缀语义向后兼容：`world_/quest_/combat_/public_`。
- 保持 deterministic，便于 golden replay。

## Policy 放置位置
- 实现入口：`core/actors/visibility.py`
- ActorView 接入点：`core/actors/builders.py`（`build_actor_view`）

## Flag Schema（兼容双格式）
- 旧格式（兼容）:
  - `flags["world_goblin_camp_known"] = true`
- 新格式（policy）:
  - `flags["shadowheart_artifact_secret"] = {"value": true, "visibility": {...}}`

## visibility.scope 语义
- `public`: 所有 actor 可见
- `party`: 仅队伍成员可见（`player/shadowheart/astarion/laezel` 或实体 faction=`party|player`）
- `actor`: 仅 `visibility.actors` 中 actor 可见
- `hidden` / `private`: 默认不可见；需满足 reveal 条件才可见

## reveal condition 语义
- 字段：`visibility.reveal_when`（别名 `reveal_condition`）
- 支持最小表达：
  - `{"flag":"world_party_mercy_choice","equals":true}`
  - `{"all":[...]}`
  - `{"any":[...]}`
  - `{"not": {...}}`
  - `{"actor_in":["shadowheart"]}`
  - `{"turn_at_least": 3}`

## Legacy Prefix Fallback
- 无 `visibility` policy 时：
  - 以 `world_/quest_/combat_/public_` 开头 => 视为 `public`
  - 其他 key => 视为 `hidden`（不可见）
- 该行为与旧版一致，不破坏既有测试。

## Environment Object 过滤
- `filter_environment_objects_for_actor` 复用同一 scope/reveal 语义。
- 对可见对象会剥离 `visibility/_visibility` 元数据，避免 ActorView 泄露隐藏策略细节。
- 无 policy 的 trap 保持旧语义：`hidden` trap 默认不可见。

## ActorView 责任边界
- 只在 `build_actor_view` 阶段输出过滤后的 `visible_flags`/`visible_environment_objects`。
- runtime/generation/dialogue 仅读取 ActorView，不直读 raw state。

## Breaking Change 定义
- 本次为向后兼容扩展，不是 breaking change：
  - 旧 flags 语义不变。
  - API 响应结构不变。
  - 图拓扑不变。

## 新增验证
- 单元测试覆盖：
  - actor/party/public/hidden/reveal
  - legacy prefix fallback
  - metadata 不泄露
  - runtime 路径接收的 ActorView 已过滤
- Golden 覆盖：
  - `shadowheart_artifact_secret_actor_visibility`
  - `world_flag_reveal_to_visible_party`（升级）
