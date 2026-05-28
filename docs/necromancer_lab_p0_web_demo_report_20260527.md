# Necromancer Lab P0 Web Demo 验收报告

日期：2026-05-27  
范围：Web UI + 后端行动路由 + Necromancer Lab P0 主线 golden 验收

## 结论

本轮 P0 修复已完成，自动化验收通过。核心问题是 Web Demo 中局部 UI 行为和后端状态不同步，尤其是 A-B 门、自然语言移动、陷阱/物体目标识别，以及空文本结构化意图在输入节点被降级的问题。修复后，A-B 门通过 UI 的 E 键打开会同步到后端，文本 `move to 5,12` 会落到后端玩家坐标 `(5,12)`，完整 Act 2 到 Act 4 真相交涉路径 golden 通过。

## 本轮修复

- 后端机制层：补强门状态同步，统一 `environment_objects` 与 `entities` 的开门状态；A-B 门开启时设置 `act2_corridor_entered`；自然语言靠近门/陷阱时落到相邻可站立格，明确坐标移动仍直达目标坐标。
- 输入与 DM 路由：增加 `door_a_to_b`、`door_b_to_d`、`heavy_oak_door_1`、`gas_trap_1`、`chest_1`、`cracked_wall`、`gribbo` 等显式别名；保留结构化坐标 MOVE、READ、DISARM、LOOT、INTERACT 目标；空文本结构化意图不再被误降级为 chat/pending。
- Web UI：A-B 门 E 键交互后发送后端同步请求；门文本归一化保留真实目标；文本移动响应后回填本地玩家位置，供后续 payload 使用；禁用普通闲聊导致的合成陷阱感知注入。
- 测试与 golden：新增 P0 后端 owner 测试，扩展前端 Jest 覆盖，更新 Necromancer Lab 相关 golden 期望。

## 浏览器验收

验收入口：

`http://127.0.0.1:8010/web_ui/?session_id=owner_web_acceptance_8010_final_1779893968872&map_id=necromancer_lab&qa_no_idle=1&qa_backend_timeout_ms=30000&qa_acceptance=1`

已验证路径：

1. 初始进入 Act 1，地图和队伍初始化正常。
2. 使用真实 UI 按键 `W`、`W`、`E` 打开 A-B 门。
3. 后端状态确认：
   - `environment_objects.door_a_to_b.status = open`
   - `environment_objects.door_a_to_b.is_open = true`
   - `entities.door_a_to_b.status = open`
   - `entities.door_a_to_b.is_open = true`
   - `flags.act2_corridor_entered = true`
4. 通过文本命令 `move to 5,12`，后端确认玩家坐标为 `(5,12)`，`latest_roll.intent = MOVE`，`latest_roll.target = 5,12`。

截图证据：

- `/private/tmp/bg3_owner_acceptance_final_initial.png`
- `/private/tmp/bg3_owner_acceptance_final_after_ab.png`
- `/private/tmp/bg3_owner_acceptance_final_move_512.png`

## 自动化结果

- `npm test -- --runInBand`：通过，288 passed。
- `pytest tests/test_owner_web_playtest_p0.py -q`：通过，10 passed。
- `make check`：通过。
  - `pytest -q`：468 passed。
  - `python -m core.eval.runner --suite golden`：50/50 passed。
- 单独 full-path golden 曾验证通过：
  - `necromancer_lab_full_path_act2_to_act4_truth_negotiation`：18/18 steps passed。

## 注意事项

- Playwright CLI 路径受网络/第三方包执行限制影响，未作为最终浏览器工具使用；本轮改用 Codex in-app Browser 完成 UI 验收。
- 浏览器输入环境的剪贴板能力不可用，因此手动 UI 验收采用真实按键和 ASCII 文本输入。完整 Act 2 到 Act 4 路线由 golden 套件覆盖。
- 当前工作区还存在 Unity 端文件变更、`data/chroma_db_legacy/` 和 `ObjectiveMarker` 相关未跟踪文件；本报告不把它们归入本轮 Web Demo P0 修复结论。
