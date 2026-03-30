# 🎲 BG3 Multi-Agent Narrative Engine

> An Industrial-Grade AI Narrative Engine powered by LangGraph.
> 基于 LangGraph 构建的工业级多智能体 (Multi-Agent) 跑团与叙事引擎。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-orange)
![SQLite](https://img.shields.io/badge/SQLite-Persistence-lightgrey)
![Multi-Agent](https://img.shields.io/badge/Architecture-Multi_Agent-success)

## 📖 Introduction | 项目简介

本项目旨在探索“大语言模型（LLM）”与“传统 CRPG 刚性规则（Hard Rules）”的深度融合。通过构建一个支持**多角色动态群聊、实体状态隔离 (ECS)、动态好感度结算**以及**防幻觉叙事锁**的高级 AI 引擎，试图还原《博德之门 3》中极具沉浸感的跑团体验。

系统采用 **LangGraph 图状态机架构**，彻底解耦了“感知（DM）”、“规则（Mechanics）”与“表达（Generation）”。无论是单挑检定，还是多角色“争风吃醋”的群口相声，都在严格的底层机制下平滑流转。

---

## ✨ Core Architectures | 核心架构亮点

### 1. 👥 数据驱动的多智能体群聊 (Data-Driven Multi-Agent Banter)
* **痛点**：传统 AI 游戏往往只能进行 1v1 单线对话，缺乏小队成员间的互动与插嘴机制。
* **解法**：引入 `speaker_queue` 发言队列机制与“单例 LLM 轮询”架构。DM 节点不仅分析玩家意图，还能像戏剧导演一样评估“谁该做出反应”。结合“旁观者清醒补丁（Bystander Syndrome Patch）”，NPC 能够精准识别自己的立场，实现极度自然的群嘲、插嘴、甚至是用物理动作（如翻白眼）代替废话的精彩演出。

### 2. 🧩 实体组件隔离与数据驱动 (ECS & Data-Driven Persona)
* 摒弃了硬编码的 Python 节点。所有角色的属性、背包、好感度与性格提示词均通过 YAML 配置文件动态加载。
* 状态机内部实现了严格的 `entities` 隔离，确保阿斯代伦和影心各自拥有独立的 HP、Buff、背包和好感度结算体系，互不干扰。

### 3. 🎲 悬念拉满的 D20 机制与演出 (Visible D20 Mechanics & Animation)
* 判定不再是暗箱操作。当 DM 识别到威胁 (`INTIMIDATION`)、欺瞒 (`DECEPTION`) 等动作意图时，强制路由至 `mechanics` 节点。
* 结合终端 UI (Rich)，实现了**明牌化的 D20 掷骰子悬念动画**。AI 必须基于底层的“大成功 (Critical Success)”或“失败 (Failure)”标签来生成对应的狂喜或吃瘪台词，真正做到了“系统规则主导叙事”。

### 4. 🛡️ 话题标签与记忆防爆机制 (Topic Tags & Sliding Window Memory)
* **双轨意图判定**：将“动作 (Action)”与“话题 (Topic)”正交分离（`is_probing_secret`）。刺探隐私仍会走正常技能检定；是否拒绝或透露由 **LLM + `story_rules` / 角色模板** 决定，不再由 Python 注入 `[SYSTEM OVERRIDE]`。
* **记忆滑动窗口**：废弃了早期的全局文本摘要，采用精确的 `messages[-20:]` 与 `journal_events[-5:]` 切片截断。结合持久化的 SqliteSaver 数据库，既保证了跨会话的长期记忆，又彻底消除了长时间游玩导致的 LLM 上下文爆炸与幻觉。

---

## 🧠 Graph State, Dialogue Triggers & Data Bridging | 图状态、对话触发与数据桥接

本节说明跑团引擎在 **LangGraph 状态流转**中的关键设计：在 LLM 开口之前先结算“硬规则”，在节点返回时合并“全局大盘”，并在 **dict** 与领域对象之间做无损转换，保证数值与叙事同源、不割裂。

### 1. 对话触发器管线 (Dialogue Trigger Pipeline)

* **执行时机**：在 Generation 节点调用角色 `render_prompt` **之前**，由 `core/systems/mechanics.py` 中的 `process_dialogue_triggers` 根据 YAML `dialogue_triggers`（关键字匹配等）先行结算。
* **可写回内容**：原地更新 **Flags**、通过 `inventory.give:*` 效果在玩家与当前 NPC 之间转移物品、产出 `journal_entries` 剧情日志，并汇总 **`relationship_delta`**（机制侧好感修正）。
* **与 LLM 的叠加**：机制层先把 `relationship_delta` 并入当前 NPC 的 **`affection`**，再进入系统提示词与 JSON 解析；回合末尾 LLM 输出的 `state_changes.affection_delta` 再叠加到**同一实体**上，使 **「规则加减」与「情感推断」** 落在同一数值管道，避免“系统加了两点、台词却当没发生”的割裂感。

### 2. 多智能体状态合并 (Graph State Overlay)

* **问题背景**：多角色轮流发言时，若某节点只返回“当前说话人”的切片，整表覆盖 `entities` 会冲掉 DM / 其他节点刚写入的他人好感度或背包。
* **防御性策略**（`core/graph/nodes/utils.py`）：
  - **`merge_entities_with_defaults`**：与 Input 节点对齐，将 `characters/*.yaml` 中尚未出现在存档里的 NPC **补键**，避免缺键被误当作 `affection: 0`。
  - **`overlay_entity_state(state_entities, node_entities)`**：以 **进入本节点时的 `state["entities"]` 为底**（含 DM 刚写入的全局好感），再按 NPC id 用本节点算出的变更 **覆盖**；未出现在本节点输出中的角色 **原样保留**，从而消除多智能体并发对话场景下的 **状态覆盖 / 丢失**。
* **工程语义**：当前说话 NPC 的变更被安全地“贴回”全局 `entities` 大盘，再随 Checkpoint 持久化，保证 API / CLI 读到的 `party_status` 与跑团规则一致。

### 3. 数据结构无缝转换 (Dict ↔ Domain Objects)

* **图状态侧**：`GameState` 中的 `player_inventory`、各实体 `inventory` 以 **`Dict[str, int]`**（物品 id → 数量）流转，便于 LangGraph 序列化与 SqliteSaver 存档。
* **机制侧**：`process_dialogue_triggers` 等物品逻辑使用 **`Inventory`** 实例（`remove` / `add`、堆叠规则与注册表一致）。
* **桥接方式**：在 Generation 节点内对触发器分支使用 **`Inventory.from_dict(...)`** 注入、`to_dict()` 写回，与既有 **`merge_entities_with_defaults` / `overlay_entity_state`** 衔接；从而在不动图状态契约的前提下，让底层机制复用强类型背包行为，实现 **dict 与领域对象**之间的平滑转换。

---

## 🚀 V2 引擎迭代亮点 (The V2 Engine Evolution)

在 V2 版本中，系统从「多智能体聊天机器人」正式跃迁为**真正的 TRPG (桌面角色扮演游戏) 引擎**。我们重构了底层状态机，并引入了物理与数值守恒法则。

- 🌍 **物理法则与资产守恒 (Physics & Assets Engine)**
  - 彻底解耦物理结算逻辑 (`core/engine/physics.py`)。
  - 实装 HP (生命值) 系统与越界保护，支持伤害与治疗判定。
  - 引入「世界掉落 (World Drop)」后门，允许玩家通过探索环境 (`INVESTIGATION`) 无中生有地获取战利品。
- 🧠 **高精度意图识别 (Fine-Grained Intent Routing)**
  - DM 节点精准区分对人社交、环境探索 (`PERCEPTION` / `STEALTH`) 与 免费互动 (`Free Action`)。
  - 队友间赠送物品判定为静默流转，彻底消灭「过度检定 (Over-rolling)」。
- 🎭 **MVC 场记与防幻觉系统 (Context Attribution)**
  - 引入 `TextProcessor`，强制剥离 LLM 生成的冗余前缀（如 `[Shadowheart]说:`），由后台 Python 统一打标签。
  - 彻底解决多 Agent 并发交流时大模型容易「认错人」的人格分裂 Bug，确保前端 UI 渲染绝对纯净。
- 🧱 **坚如磐石的状态契约 (Industrial-Grade Graph State)**
  - 基于 LangGraph 的 `TypedDict` 与 `Annotated` Reducer 重构状态总线。
  - 严格区分持久化存档数据 (`[PERSISTENT]`) 与单局瞬时上下文 (`[TRANSIENT]`)，彻底扫清 V3 扩展障碍。

---

## 🛠️ Tech Stack | 技术栈

- **Core Framework**: `LangGraph`, `LangChain`
- **Persistence**: `sqlite3` (LangGraph Checkpoint for Cross-Session Memory)
- **UI & Rendering**: `Rich` (Terminal Dashboard, Dice Animations & Incremental Logs)
- **Prompt Engineering**: `Jinja2` (Dynamic Persona Injection)
- **Data Configuration**: `YAML` (Zero-code character & item integration)

---

## 🚀 Getting Started | 快速开始

```bash
# 1. Clone the repository
git clone [https://github.com/yourusername/BG3-LLM-Agent.git](https://github.com/yourusername/BG3-LLM-Agent.git)
cd BG3-LLM-Agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API Keys
# Create a .env file and add your LLM API keys (e.g., OPENAI_API_KEY)

# 4. Run the V2 Multi-Agent Engine
python main.py