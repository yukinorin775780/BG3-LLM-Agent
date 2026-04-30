# UI Sprint 1 E2E Stabilization Checklist

## 1. Server Startup (统一命令)

```bash
python server.py
```

如需并行跑隔离测试会话，可切换到 8010：

```bash
BG3_PORT=8010 python server.py
```

## 2. Browser QA Session

使用全新会话并启用静默参数：

```text
http://127.0.0.1:8000/web_ui/?session_id=ui_sprint1_e2e_01&qa_no_idle=1
```

确认点：
- 无 `trigger_idle_banter` 自动请求。
- 无自动 `trigger_zone` 剧情 POST（仅玩家主动行为触发）。
- `init_sync` 不产生新增日志/台词/弹窗事件。

## 3. Four-Act Closed Loop

1. Act1：进入实验室后，仅保留状态同步，无 idle noise。
2. Act2：与 `necromancer_diary` 交互，前端请求应携带 `intent=READ` + `target=necromancer_diary`。
3. Act3：与 `gribbo` 交互，前端请求应携带 `intent=CHAT` + `target=gribbo`；  
   再执行 side/rebuke 分支，确认无长时间 loading，无 500。
4. Act4：搜刮 `gribbo/chest` 获取 `heavy_iron_key` 后交互 `heavy_oak_door_1`，  
   请求应携带 `intent=INTERACT` + `target=heavy_oak_door_1`，最终 `demo_cleared=true` 且出现 banner。

## 4. Regression Commands

```bash
pytest -q
python -m core.eval.runner --suite golden
make check
npm test
```
