# Necromancer Lab V2 Act2 Trap Interrupt Report

日期：2026-05-29

## 修改文件

- `web_ui/app.js`
- `web_ui/input-controller.js`
- `web_ui/game.js`
- `web_ui/tests/app.test.js`

本轮没有修改后端、GameService API 或 LangGraph 主拓扑。Unity 未修改。

## 成功 / 失败移动处理差异

Perception success：

- 玩家从安全格进入 `gas_trap_1` trigger tile 时，前端先发送 `source=trap_awareness`，不立即发送 `source=trap_trigger`。
- 后端返回 success / revealed 后，前端执行本地 movement interrupt。
- `player` 回滚到触发前安全格，例如 real map smoke 中从 `5,11` 回到 `5,12`。
- 同一轮不发送 trap trigger，不出现 green poison overlay。
- 保留 Astarion dice card / bark / amber suspicious marker。
- companion token 不通过二次 `movePlayerLocal` 重算，继续保留 `local_party_trail` 投影。

Perception failure：

- 前端同样先发送 `source=trap_awareness`。
- 若 response flags、`latest_roll.result.is_success=false` 或 `[陷阱感知失败] astarion -> gas_trap_1` 表示失败，且玩家仍在 trigger tile，则补发 `source=trap_trigger`。
- trap 保持 hidden/armed，随后由 trigger response 显示 green poison overlay / poisoned feedback。

Disarm：

- `gas_trap_1.status=disabled` 或 `necromancer_lab_poison_trap_disarmed=true` 后进入 trigger tile 不发送 trigger。
- disarm failure 仍由 `trap_triggered` 驱动 green poison overlay 和 poisoned feedback。

## 测试结果

- `npm test -- --runInBand`：293 passed
- `git diff --check`：通过
- 未跑 Python targeted：本轮没有后端改动。

## Browser Smoke

本地服务：`python server.py --host 127.0.0.1 --port 8010`

结果：

- Fresh session 打开 A-B 门后，从 `5,12` 直接向 `gas_trap_1` trigger tile 移动。
- Dev mode 下 perception 自动大成功：Astarion bark + Perception roll 出现，trap revealed，debug 显示 `inputPlayer={"x":5,"y":12}`，未触发 trap，未出现 poison gas。
- 因当前服务 `DEBUG_ALWAYS_PASS_CHECKS=True`，真实浏览器无法自然得到 perception failure；failure continuation 由 Jest mocked backend 覆盖。
- 为验证 triggered visual，success 后再次主动踩入 revealed trap：出现 `Poison Gas Released` card，debug 显示 `inputPlayer={"x":5,"y":11}`，World State Diff 显示 `毒气陷阱.status revealed -> triggered` 和 `玩家.status += poisoned`。

截图：

- `/private/tmp/bg3_act2_trap_success.png`
- `/private/tmp/bg3_act2_trap_triggered.png`
