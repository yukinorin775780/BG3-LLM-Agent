# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BG3 多角色跑团叙事引擎 - LLM 负责感知与表达，规则系统负责状态落地。

## Commands

```bash
# 安装依赖
pip install -r requirements.txt

# 运行 CLI
python main.py

# 运行 API 服务
python -m uvicorn server:app --host 127.0.0.1 --port 8010

# 运行测试
pytest
```

## Architecture

```
Frontend: main.py (CLI), server.py (FastAPI)
Application: core/application/game_service.py (单回合编排入口)
Graph: core/graph/ (LangGraph 节点与路由)
Domain: core/systems/ (mechanics, inventory, memory_rag)
        core/engine/physics.py (物品/HP/环境状态变更)
Data: characters/*.yaml (角色卡), config/items.yaml (物品)
```

## Key Design Rules

- **GameService 管编排** - 新入口/session 逻辑优先改 GameService
- **GameState 是状态总线** - 新状态字段先更新 GameState
- **LLM 建议，Physics 执行** - 状态修改必须落到 physics.py
- **Mechanics 定成功，Generation 表达** - 检定结果不可推翻
- **数据驱动** - 新角色改 characters/*.yaml，新物品改 config/items.yaml

## Development Boundaries

| 修改类型 | 目标文件 |
|---------|---------|
| 新 API 字段 | ChatTurnResult + server.py |
| 新回合流程 | graph_builder.py + graph_routers.py |
| 新检定规则 | core/systems/mechanics.py |
| 新物理状态变更 | core/engine/physics.py |
| 新角色/触发器 | characters/*.yaml |
| 新物品 | config/items.yaml + ItemRegistry |

## Tech Stack

Python 3.10+, LangGraph, FastAPI, Rich, SQLite checkpoint, ChromaDB, Jinja2, YAML
