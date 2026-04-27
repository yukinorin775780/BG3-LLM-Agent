# V1.3 Social Action / Item Transaction Protocol

## 目标
在不改主图拓扑与外部 API 结构的前提下，为 Runtime NPC 增加可回放的社交物品动作协议，覆盖：
- gift_offer / gift_accept / gift_reject
- item_transfer / item_use / consume
- reject/no_op 不吞物品
- EventDrain 统一写回 inventory / HP / memory notes

## 设计选择

### 1) 模型放置
协议模型放在 `core/events/models.py`：
- `SocialAction`
  - `action_type`
  - `actor_id`
  - `target_actor_id`
  - `item_id`
  - `quantity`
  - `reason`
- `ItemTransaction`
  - `transaction_type`: `transfer` / `return` / `consume` / `no_op`
  - `from_entity`
  - `to_entity`
  - `item`
  - `quantity`
  - `accepted`
  - `reason`

对应 DomainEvent 类型扩展为：
- `actor_item_transaction_requested`

### 2) Runtime 与 EventDrain 责任边界
- Runtime (`core/actors/runtime.py`) 只做决策，不直接改 state：
  - 产出 `actor_spoke`
  - 产出 `actor_item_transaction_requested`
  - 产出 `actor_memory_update_requested`
- EventDrain (`core/graph/nodes/event_drain.py` + `core/events/apply.py`) 是唯一写回入口：
  - 解析 transaction payload
  - 通过 `core/engine/physics.apply_physics(...)` 落地 inventory/HP 变化
  - reject/no_op 仅写日志，不扣物品

### 3) 接受/拒绝/退回/消耗语义
- 接受礼物 (`gift_accept`):
  - transaction: `transfer` (`player -> actor`)
  - EventDrain 写回 player/NPC 背包
- 拒绝礼物 (`gift_reject`):
  - transaction: `no_op` (`accepted=false`)
  - EventDrain 只记录拒绝事件，不扣玩家背包
- 消耗 (`item_use`):
  - transaction: `consume` (`actor -> consumed`)
  - 可携带 `hp_changes`，由 EventDrain 经 physics 统一结算
- 退回 (`return`):
  - 协议已支持（transaction_type），语义等价反向 transfer

### 4) 与 legacy physical_action 的兼容
- Generation 旧路径 `physical_action`（`use_item` / `consume` / `transfer_item`）保持不变。
- Runtime 新协议通过 DomainEvent 写回，不替换旧 JSON action 机制。
- 现有 `use_item/consume` 相关测试不变，继续通过。

## 新增测试
- `tests/test_event_drain.py`
  - accepted transaction 会写回 inventory
  - rejected/no_op 不扣 player_inventory
- `tests/test_actor_invocation_node.py`
  - Astarion 拒礼只产出 event，不直接改 state
  - Shadowheart 接受礼物由 EventDrain 完成写回

## 新增 Golden
- `evals/golden/astarion_rejects_unwanted_gift.yaml`
- `evals/golden/shadowheart_accepts_healing_potion.yaml`

覆盖点：runtime marker、state、visibility、memory、telemetry（含 transaction outcome）
