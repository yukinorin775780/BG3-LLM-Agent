# Content Sprint 1 - Necromancer Lab Story Bible

## 1. Scope
- 目标：把 `necromancer_lab` 从旧 demo 固化为可支撑约 15 分钟游玩的四幕剧情主线。
- 约束：不改主图拓扑；不绕过 ActorView / MemoryService / EventDrain；不引入真实 LLM/网络依赖。
- 本文定位：剧情与状态契约（design freeze），不是完整业务实现。
- 启动方式：新会话可通过 `map_id=necromancer_lab` 初始化该剧情地图；未传 `map_id` 保持默认地图行为。
- 当前落地：Act 1 开场感知 + Act 2 日记判定/知识沉淀 + Act 3 谈判分支已实现；Act 4 维持设计冻结待后续线程实现。

## 2. Four-Act Overview

### Act 1 - 毒气陷阱与暗中观察
- 场景：玩家刚进入实验室，闻到刺鼻化学味。
- 核心动作：后台触发陷阱感知流程；Astarion 优先给出“毒气陷阱”预警；Shadowheart 感知死灵残留并进入警惕。
- 信息边界：未识别陷阱前，玩家只获得“危险感/异味”而非精确 trap id、坐标、DC。

### Act 2 - 死灵日记与危险知识
- 场景：玩家阅读 `necromancer_diary`（`lore_id=necromancer_diary_1`）。
- 核心动作：触发 INT / Investigation / Arcana 解读分歧。
- 结果分支：
  - 失败：仅得到碎片词句（地精、毒气、钥匙）。
  - 成功：读出 Gribbo、毒气联动、heavy_iron_key、未完成解药线索。
- 记忆边界：关键信息先写入阅读者 actor-scoped memory，再按策略决定是否写入 party_shared。

### Act 3 - 谈判、群聊拱火与站队抉择
- 场景：玩家与 Gribbo 交涉重铁钥匙。
- 核心动作：Party Turn Coordinator 触发 Astarion 插话；玩家站队形成分支。
- 分支 A（顺着 Astarion 嘲笑）：
  - `astarion` affection `+2`
  - `gribbo.patience -> 0`
  - 谈判立即破裂并开战
- 分支 B（训斥 Astarion）：
  - `astarion` affection `-3`
  - 写入 Astarion 长期负面记忆
  - Gribbo 因 paranoia/药剂后遗症仍破裂开战
- 关键约束：两分支都开战，但社交后果与 memory 必须不同。

### Act 4 - 搜刮与战后反思
- 场景：Gribbo 死亡后，玩家搜刮 `heavy_iron_key`，开启 `heavy_oak_door_1` 逃离。
- 核心动作：物品转移走 ItemTransaction/DomainEvent/EventDrain；触发战后 banter/reflection。
- 收束条件：`demo_cleared = true`。

## 3. Player Goals By Act
- Act 1：识别并规避毒气陷阱，确认队友预警来源。
- Act 2：读取日记并提炼可执行线索（钥匙、陷阱、Gribbo 触发关系）。
- Act 3：在“压迫谈判效率”与“队内关系成本”之间做站队选择。
- Act 4：取得钥匙、开门离开、完成战后认知闭环。

## 4. Core NPC Motives

### Gribbo
- 外显目标：守住内室钥匙，不让外来者突破实验室出口。
- 行为驱动：高傲 + 被药剂改变后的偏执；受羞辱时耐心快速归零。
- 破裂逻辑：即使玩家试图修复氛围，在 paranoia 高位时也可能强制战斗收束。

### Astarion
- 倾向：偏好嘲讽、功利、短平快结果；对“仁慈/拖延”不耐烦。
- 戏剧职责：Act 1 预警者、Act 3 拱火者、Act 4 战后嘲讽反思者。

### Shadowheart
- 倾向：对死灵/禁忌线索敏感，强调风险控制与后果承担。
- 戏剧职责：Act 1 紧张氛围锚点、Act 2 解读对照、Act 3/4 价值观制衡。

### Lae'zel
- 倾向：效率与武力优先，容忍度低。
- 戏剧职责：Act 3/4 对“仁慈/拖延”提供高压反馈，维持队伍分歧张力。

## 5. Gribbo Private Agenda (Freeze)
- 固化文本来源：`characters/gribbo.yaml -> attributes.secret_objective`。
- 契约要点：
  - 目标：守护 `heavy_iron_key`。
  - 机制锚：毒气陷阱口令（Myrkul's Breath）属于私密知识。
  - 泄露条件：仅在被严重威吓或高额利益诱导下可能松口（后续线程实现细化）。

## 6. Companion Reaction Matrix (Optional Variants)

### Act 1
- Astarion：先手提醒“前方有陷阱/有毒气味”，建议绕路或先处理机关。
- Shadowheart：进入警惕（Tense）语气，提示死灵残留与不洁仪式痕迹。
- Lae'zel：催促快进，倾向“直接推进，别磨蹭”。

### Act 2
- Astarion：嘲讽日志书写者，提炼“钥匙/陷阱”实用信息。
- Shadowheart：关注禁忌仪式与信仰污染线索。
- Lae'zel：将信息转译为战术目标（拿钥匙、清障、撤离）。

### Act 3
- Astarion：插话拱火（讥讽 Gribbo），推高冲突。
- Shadowheart：提醒长期后果，不完全站队挑衅。
- Lae'zel：偏向强压式解决，容忍谈判失败。

### Act 4
- Astarion：战后评价“谈判终局可预测”，强调效率。
- Shadowheart：提示善后与危险残留。
- Lae'zel：催促立即离开，减少逗留风险。

## 7. State Contract (Flags / Memory / Events / Transactions)

### 7.1 Key Flags (建议命名，供后续实现对齐)
- `necromancer_lab_intro_seen`：Act 1 开场感知已触发（防重复）。
- `world_necromancer_lab_intro_entered`：进入实验室序章。
- `world_necromancer_lab_trap_warned`：队友已发出毒气陷阱预警。
- `astarion_detected_gas_trap`：Astarion 识别毒气机关（actor-scope: astarion）。
- `shadowheart_senses_necromancy`：Shadowheart 感知死灵残留（actor-scope: shadowheart）。
- `necromancer_lab_diary_read`：日记已被阅读。
- `necromancer_lab_diary_decoded`：本次解读是否成功。
- `necromancer_lab_antidote_formula_fragment_known`：解药残缺线索（policy actor-scope，默认只对阅读者可见）。
- `necromancer_lab_key_hint_known`：钥匙关键线索（policy party-scope，可被在场队友共享）。
- `world_necromancer_lab_negotiation_started`：与 Gribbo 谈判开始。
- `world_necromancer_lab_negotiation_collapsed`：谈判破裂（A/B 均可触发）。
- `world_necromancer_lab_gribbo_defeated`：Gribbo 已倒下。
- `world_necromancer_lab_heavy_key_obtained`：已获得 `heavy_iron_key`。
- `world_necromancer_lab_escape_opened`：`heavy_oak_door_1` 已开启。
- `demo_cleared`：剧情闭环完成。

### 7.2 Key Memories
- `actor_private`：
  - 阅读者成功/失败解读结论（Act 2）。
  - Astarion 在 Act 3 的站队结果与情绪沉淀（含长期负面记忆）。
  - Shadowheart 对死灵残留的主观判断。
- `party_shared`：
  - “Gribbo + 毒气 + 钥匙”的可公开摘要（仅在成功解读后）。
  - 谈判破裂并转战斗的公共事实。

### 7.3 Key DomainEvents
- `actor_spoke`：队友预警、插话、战后评论。
- `actor_memory_update_requested`：分角色记忆写入请求。
- `world_flag_changed`：剧情推进旗标。
- `actor_item_transaction_requested`：钥匙转移/拒绝/回退等事务请求。
- `actor_reflection_requested`：战后反思排队（可选）。

### 7.4 Key Item Transactions
- `transfer`：`gribbo -> player`（`heavy_iron_key`，Act 4）。
- `no_op/return`：若社交拒绝发生，保证“不吞物品/不误扣”。
- `consume`：保留药剂类消耗语义（与已有 use_item/consume 兼容）。
- 写回边界：Gribbo 交涉给钥匙走 `DomainEvent -> EventDrain`；`dialogue` 只产出事件，不直接改背包。
- 兼容说明：`mechanics.execute_loot_action` 旧搜刮路径暂保留，后续再统一事件化。

### 7.5 Act 1 已落地字段（Thread B）
- 触发点：`GameService.process_chat_turn` 在 `necromancer_lab` 且 `necromancer_lab_intro_seen != true` 时应用一次 intro patch。
- Shadowheart 警惕状态：`entities.shadowheart.status_effects` 追加 `{"type": "tense", "duration": 3}`（若已存在则续到至少 3）。
- 可见性边界：
  - `astarion_detected_gas_trap` / `shadowheart_senses_necromancy` 通过 policy actor-scope 限定。
  - `environment_objects` 对玩家响应默认过滤 hidden trap（不直接暴露 `gas_trap_1` metadata）。
- 对应 golden：`necromancer_lab_act1_trap_perception`。

### 7.6 Act 2 已落地字段（Thread C）
- 接入点：`core/graph/nodes/lore.py` 的 `READ necromancer_diary` 分支（未改主图拓扑）。
- 判定规则（deterministic）：
  - `INT >= 14`：自动成功（`AUTO_SUCCESS_INT`）。
  - `INT < 10`：自动失败（`AUTO_FAILURE_INT`）。
  - 其他：`d20 + INT 修正 + 技能加值(arcana=+2, investigation=+1)` 对抗 `DC 14`。
- 状态字段：
  - `flags.necromancer_lab_diary_read = true`
  - `flags.necromancer_lab_diary_decoded = true/false`
  - 成功时写入 policy flags：`necromancer_lab_antidote_formula_fragment_known`（actor）与 `necromancer_lab_key_hint_known`（party）
- Memory/Event：
  - 成功：产出 `actor_memory_update_requested`（`actor_private:player` + `party_shared`）并由 EventDrain 写回。
  - 失败：仅产出碎片化 `actor_private:player` 记忆，不写完整危险知识到共享域。
- 对应 golden：
  - `necromancer_lab_act2_diary_int_success`
  - `necromancer_lab_act2_diary_int_failure`

### 7.7 Act 3 已落地字段（Thread D）
- 触发接入：
  - `dm_node` 在 `active_dialogue_target=gribbo` 且命中 Act3 关键词时，使用 deterministic override 进入 `CHAT + party turn runtime` 路径。
  - 关键词分支：`side_with_astarion` / `rebuke_astarion`（也支持 `intent_context.act3_choice` 显式指定）。
- Party Turn：
  - 由 `actor_invocation_node -> run_party_turn` 调度 Astarion + Shadowheart 同回合 runtime。
  - marker：`actor_invocation_mode=runtime`，`actor_invocation_reason=party_turn_runtime_multi`。
- 状态写回（统一 DomainEvent/EventDrain）：
  - A 分支：`astarion.affection +2`，Astarion actor-private 正向记忆。
  - B 分支：`astarion.affection -3`，Astarion actor-private 负向长期记忆。
  - Gribbo：`dynamic_states.patience=0`，`faction=hostile`，并进入战斗（`combat_phase=IN_COMBAT`，`combat_active=true`）。
  - paranoia 语义：B 分支写入 “paranoia 爆发/被算计” 的破裂理由日志。
- Flags：
  - `necromancer_lab_gribbo_negotiation_started`
  - `necromancer_lab_astarion_mocked_gribbo`
  - `necromancer_lab_player_sided_with_astarion` (true/false)
  - `necromancer_lab_gribbo_combat_triggered`
- 对应 golden：
  - `necromancer_lab_act3_side_with_astarion`
  - `necromancer_lab_act3_rebuke_astarion`

## 8. Success / Failure Branches

### Act 1
- 成功：陷阱被提前识别，日志有“队友预警”来源，玩家可规避。
- 失败：未识别并触发陷阱；仍可推进但付出 HP/状态代价。

### Act 2
- 成功：解读到可执行线索并沉淀 memory。
- 失败：仅碎片信息，不足以稳定支持谈判优势。

### Act 3
- 分支 A/B 都进入战斗；差异只体现在 affection、memory、banter 语气与后续反思。

### Act 4
- 成功：通过事件写回获得钥匙并开门，`demo_cleared=true`。
- 失败：钥匙未取得或门未开，`demo_cleared=false`。

## 9. demo_cleared Contract
- 叙事准入（Content Sprint 1）建议条件：
  - `world_necromancer_lab_gribbo_defeated == true`
  - `world_necromancer_lab_heavy_key_obtained == true`
  - `heavy_oak_door_1.is_open == true`
  - `demo_cleared == true`
- 兼容说明：若引擎暂保留旧 demo 的快捷通关路径，后续线程需补“主线通关判定优先级”策略，避免绕过四幕主叙事。
