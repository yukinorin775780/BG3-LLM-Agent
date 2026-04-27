# BG3 Multi-Agent Narrative Engine

> A LangGraph-powered CRPG narrative engine that combines LLM-driven roleplay with hard-rule state transitions.
> 基于 LangGraph 的多角色跑团叙事引擎：LLM 负责感知与表达，规则/物理系统负责真实状态落地。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-orange)
![SQLite](https://img.shields.io/badge/SQLite-Checkpoint-lightgrey)
![FastAPI](https://img.shields.io/badge/API-FastAPI-green)
![YAML](https://img.shields.io/badge/Data-YAML-yellow)

## Project Overview

`BG3_LLM_Agent` 是一个以《博德之门 3》式队伍互动为目标的 AI 跑团引擎。项目重点不是“让模型自由聊天”，而是把 LLM 放进一套可追踪、可持久化、可验证的游戏状态机中：

- DM 节点识别玩家意图、检定难度、参与回应的 NPC。
- Mechanics 节点执行 D20 检定，产出客观成功/失败结果。
- Physics 系统负责物品、HP、环境交互、移动等硬状态变更。
- Generation 节点根据角色 YAML、历史、检定、背包和环境生成台词。
- SQLite Checkpoint 保存跨回合状态，ChromaDB 保存长期语义记忆。

当前架构已经引入 `GameService` 应用服务层。CLI 和 FastAPI 都只是前端适配器，真正的“单回合编排”统一由 `core/application/game_service.py` 管理。

## Current Architecture

```text
Frontend / Transport
├── main.py                 # Rich CLI：输入循环、流式节点渲染、记忆沉淀
├── server.py               # FastAPI：HTTP 参数适配、异常映射、响应模型
└── web_ui/index.html       # 浏览器 UI 原型

Application Service
└── core/application/game_service.py
    ├── 加载 / 初始化 session checkpoint
    ├── 空存档 Genesis
    ├── 特殊 UI intent 分发，如 ui_action_loot
    ├── 调用 graph.ainvoke / graph.astream
    └── 整形 ChatTurnResult

Graph Engine
├── core/graph/graph_state.py       # GameState 状态契约
├── core/graph/graph_builder.py     # LangGraph 构建与节点连接
├── core/graph/graph_routers.py     # 条件路由
└── core/graph/nodes/
    ├── input.py                    # slash command、输入预处理、world tick
    ├── dm.py                       # DM 意图分析、旁白、speaker 推进
    ├── mechanics.py                # 技能检定节点
    └── generation.py               # NPC 台词、tool loop、physical_action 解析

Domain Systems
├── core/systems/mechanics.py       # D20 检定、属性/关系修正、dialogue triggers
├── core/engine/physics.py          # 物品流转、HP、环境交互、loot、move
├── core/systems/inventory.py       # ItemRegistry 与背包领域对象
├── core/systems/world_init.py      # 初始世界状态
└── core/systems/memory_rag.py      # ChromaDB 长期记忆

Data / Prompt
├── characters/*.yaml               # 角色卡、动态状态、剧情规则、触发器
├── characters/persona_template.j2  # 角色提示词模板
├── core/llm/prompts/*.j2           # DM / narration / system rules / banter prompts
├── config/items.yaml               # 物品静态真相源
└── data/player.json                # 玩家初始数据
```

## Turn Lifecycle

一次玩家输入的主流程如下：

```text
main.py / server.py
  -> GameService.process_chat_turn(...)
    -> load checkpoint by session_id
    -> run Genesis if entities missing
    -> handle ui_action_loot directly when requested
    -> graph.ainvoke(...) or graph.astream(...)
      -> input_processing
      -> world_tick
      -> dm_analysis
      -> mechanics_processing when needed
      -> narration or generation
      -> advance_speaker -> generation while speaker_queue is not empty
    -> build ChatTurnResult
```

`ChatTurnResult` 是 CLI/API 共用的应用层输出：

```python
{
    "responses": [{"speaker": "astarion", "text": "..."}],
    "journal_events": ["Skill Check | ..."],
    "current_location": "幽暗地域营地 (Underdark Camp)",
    "environment_objects": {...},
    "party_status": {...},
}
```

## Core Design Principles

### 1. GameService owns application orchestration

`main.py` 和 `server.py` 不再直接管理 Graph checkpoint、Genesis 或状态整形。后续如果要扩展 API、SSE、回放、存档列表、多人 session，应优先扩展 `GameService`，而不是把编排逻辑重新塞回入口文件。

### 2. GameState is the state contract

`GameState` 是 LangGraph 节点之间传递的唯一状态总线：

- `messages` 使用 LangGraph `add_messages` reducer 追加历史。
- `journal_events` 使用 `merge_events` reducer 累积事件日志。
- `entities` 保存多角色 ECS 状态，包括 HP、buff、好感、背包、位置和角色专属动态状态。
- `latest_roll` 保存最近一次检定，用于 UI 骰子动画与后续叙事约束。
- `speaker_queue` / `current_speaker` / `speaker_responses` 支撑多 NPC 顺序发言。

### 3. LLM can suggest actions; physics executes them

Generation 节点可以让 LLM 输出 `physical_action`，但真实状态修改必须落到 `core/engine/physics.py`：

- `transfer_item` 处理物品流转。
- `consume` / `use_item` 处理消耗。
- `interact_object` 处理环境对象状态。
- `move_to` 更新语义位置。
- `loot` 从环境容器转移物品到角色背包。

不要只在台词里描述“拿走了”“喝下了”“打开了”，却不写回 state。

### 4. Mechanics decides success; generation expresses it

`core/systems/mechanics.py` 是检定真相源。DM 可以估计 `difficulty_class`，但是否成功由 D20 结果决定。Generation 节点应基于 `latest_roll` 表达结果，不能推翻 Mechanics。

### 5. Characters and items are data-driven

新增角色优先写 `characters/<id>.yaml`，而不是加硬编码分支。新增物品优先写 `config/items.yaml`，并通过 `ItemRegistry` 查询名称、类型、效果和堆叠规则。

## Main Modules

### Application Layer

- `core/application/game_service.py`
  - `process_chat_turn(...)`：单回合入口。
  - `get_session_state(...)`：读取当前 session 状态，可自动 Genesis。
  - `_process_loot_action(...)`：处理 UI 直连拾取。
  - `_build_chat_result(...)`：把 Graph state 转为稳定 API/CLI 输出。

### Graph Layer

- `core/graph/graph_builder.py`
  - 构建 LangGraph 节点和路由。
  - 节点顺序：Input -> World Tick -> DM -> Mechanics -> Narration/Generation。
- `core/graph/graph_routers.py`
  - `route_after_dm`：动作类意图或秘密刺探进入 Mechanics。
  - `route_after_mechanics`：社交结果交给 NPC，环境/战斗结果交给 DM 旁白。
  - `route_after_narration`：根据掷骰结果和概率决定是否触发队友吐槽。
- `core/graph/nodes/generation.py`
  - 当前最复杂节点，负责角色 prompt、tool 调用、JSON 解析、physical action 和多角色发言合并。

### LLM / Prompt Layer

- `core/llm/dm.py`
  - 懒加载 OpenAI 客户端，避免仅导入模块就要求 API key。
  - 使用受限 AST 安全求值 YAML `narrative_rules`，不再直接 `eval`。
  - 解析 DM JSON 后做字段规范化、responders 过滤、flags/hp/items 安全提取。
- `core/utils/text_processor.py`
  - `parse_llm_json` 支持 Markdown fenced block、正文嵌入 JSON、非法正号前缀清洗。
  - `clean_npc_dialogue` 清理模型输出里的多余说话人前缀。
  - `format_history_message` 统一历史消息归因，降低 NPC 身份幻觉。

## Data Model Notes

### Entity shape

运行时实体大致形态：

```python
entities = {
    "shadowheart": {
        "hp": 10,
        "active_buffs": [],
        "affection": 50,
        "inventory": {"healing_potion": 1},
        "position": "camp_center",
        "shar_faith": 90,
        "memory_awakening": 10,
    }
}
```

### Inventory shape

Graph state 内背包统一用 `Dict[str, int]`：

```python
player_inventory = {
    "healing_potion": 2,
    "gold_coin": 50,
}
```

物品的中文名、效果、类型和堆叠规则来自 `config/items.yaml`。

## Development Guide For LLMs

给后续 LLM 继续开发时，请遵守这些边界：

- 新增请求入口或 session 级逻辑：优先改 `GameService`。
- 新增 API 字段：优先扩展 `ChatTurnResult` 和 `server.py` 的 Pydantic response。
- 新增回合内流程：改 `core/graph/graph_builder.py` 和 `graph_routers.py`。
- 新增状态字段：先更新 `GameState`，再确保 Genesis / overlay / API 输出一致。
- 新增检定规则：改 `core/systems/mechanics.py`。
- 新增物理状态变更：改 `core/engine/physics.py`。
- 新增角色、剧情状态、触发器：优先改 `characters/*.yaml`。
- 新增物品：改 `config/items.yaml` 并通过 `ItemRegistry` 使用。
- 不要让 UI/API 层直接修改业务状态，除非通过 `GameService` 封装成明确应用用例。

## Governance Docs

- V1 Contract Freeze: `docs/v1_contract_freeze.md`
- V1.1 Runtime Registry Governance: `docs/v1_1_runtime_registry.md`
- V1.1 Runtime NPC SOP (Frozen): `docs/v1_1_runtime_npc_sop.md`
- V1.3 Social Action / Item Transactions: `docs/v1_3_social_item_transactions.md`
- V1.3 Party Turn Coordinator: `docs/v1_3_party_turn_coordinator.md`
- V1.3 Actor Visibility Policy: `docs/v1_3_actor_visibility_policy.md`
- V1.3 Capability Freeze: `docs/v1_3_capability_freeze.md`

## Tech Stack

- Python 3.10+
- LangGraph / LangChain Core / LangChain OpenAI
- FastAPI
- Rich
- SQLite checkpoint via `langgraph-checkpoint-sqlite`
- ChromaDB for episodic memory
- Jinja2 prompt templates
- YAML data configuration

## Getting Started

```bash
pip install -r requirements.txt
```

配置 `.env`：

```bash
BAILIAN_API_KEY=...
DASHSCOPE_API_BASE=...
MODEL_NAME=qwen-plus
```

运行 CLI：

```bash
python main.py
```

运行 API：

```bash
python server.py
```

默认服务地址：

```text
POST http://localhost:8000/api/chat
```

请求示例：

```json
{
  "session_id": "demo_save_01",
  "user_input": "影心，你觉得这个铁箱子里有什么？"
}
```

UI 直连拾取示例：

```json
{
  "session_id": "demo_save_01",
  "intent": "ui_action_loot",
  "character": "shadowheart"
}
```

## Testing

项目已有隔离测试覆盖若干关键边界：

- `tests/test_text_processor.py`：LLM JSON 解析与文本清洗。
- `tests/test_v2_architecture.py`：物理黑洞防御、工具参数、失败拒绝倾向。
- `tests/test_tools_llm.py`：工具循环行为桩测试。

运行：

```bash
pytest
```

## Eval / Checks

本地检查：

```bash
make check
```

只跑单元测试：

```bash
make test
```

只跑 Golden Eval：

```bash
make eval
```

详细说明见 `docs/evals.md`。

## Current Caveats

- `core/graph/nodes/generation.py` 仍是职责最重的节点，后续扩展复杂行为时应优先拆分，而不是继续堆逻辑。
- `core/engine/__init__.py` 仍保留对 `archive/v1_legacy/engine.py` 的兼容 re-export。
- `DEBUG_ALWAYS_PASS_CHECKS` 当前在 `core/engine/physics.py` 中为开发测试开关，真实规则验收前应检查其值。
- `memory.db` 是本地 checkpoint 文件，不应作为代码逻辑依赖。
