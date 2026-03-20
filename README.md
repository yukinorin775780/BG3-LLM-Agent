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