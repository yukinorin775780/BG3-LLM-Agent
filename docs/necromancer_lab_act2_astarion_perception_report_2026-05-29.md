# Necromancer Lab V2 Act2 Astarion Perception Roll Report

日期：2026-05-29

## 修改文件列表

- `core/campaigns/necromancer_lab.py`
- `core/graph/nodes/dm.py`
- `core/graph/nodes/mechanics.py`
- `core/systems/mechanics.py`
- `web_ui/app.js`
- `web_ui/ui-event-adapter.js`
- `web_ui/tests/app.test.js`
- `tests/test_necromancer_lab_act2_corridor.py`
- `tests/test_necromancer_lab_trap_agentic.py`
- `evals/golden/necromancer_lab_act2_astarion_reveals_gas_trap.yaml`
- `evals/golden/necromancer_lab_astarion_trap_intervention.yaml`

未修改 Unity。`data/chroma_db_legacy/` 未纳入本次变更。

## 新的 Act2 perception roll 状态机

1. 玩家打开 A-B 门并进入 Act2 corridor 后，移动到 `gas_trap_1` 三格内时，系统检查 `act2_astarion_perception_checked`。
2. 如果尚未检查、陷阱仍 unresolved、Astarion 存活，则触发一次且只触发一次 Astarion 专属 `PERCEPTION` mechanics roll。
3. roll 使用 `gas_trap_1.detect_dc`，当前为 `13`；Act2 trap perception 使用 `modifier/perception_bonus=5`，并写入 `latest_roll`。
4. 成功或失败都会写 `act2_astarion_perception_checked=true` 和 `act2_astarion_perception_success=<bool>`。
5. 成功时 reveal trap；失败时 trap 保持 hidden/armed。checked 后再次靠近不会重 roll、不会重放 dice card、不会重复 journal。
6. Astarion disarm 仍是后续独立 `DISARM` 动作：disarm 成功 disabled，失败 triggered。
7. Web UI 中 revealed trap 只显示 amber suspicious marker；绿色 poison overlay 只由 `trap_triggered` 事件或 triggered 状态驱动。

## latest_roll 示例字段

```json
{
  "intent": "PERCEPTION",
  "actor": "astarion",
  "target": "gas_trap_1",
  "skill": "perception",
  "ability": "WIS",
  "dc": 13,
  "modifier": 5,
  "source": "trap_awareness",
  "result": {
    "raw_roll": 12,
    "total": 17,
    "dc": 13,
    "modifier": 5,
    "is_success": true
  }
}
```

## Success / Failure 行为差异

成功：

- `act2_astarion_perception_checked=true`
- `act2_astarion_perception_success=true`
- `act2_gas_trap_revealed=true`
- `necromancer_lab_poison_trap_revealed=true`
- `gas_trap_1.status=revealed`
- `gas_trap_1.is_hidden=false`
- journal 写入 `[陷阱感知] astarion -> gas_trap_1`

失败：

- `act2_astarion_perception_checked=true`
- `act2_astarion_perception_success=false`
- `gas_trap_1` 保持 hidden/armed
- 不写 reveal flag，不显示 trap marker
- journal 写入 `[陷阱感知失败] astarion -> gas_trap_1`
- 后续踩中陷阱仍会触发 `trap_triggered`、poisoned 状态和绿色毒气 UI overlay

## 自动化结果

- `pytest tests/test_necromancer_lab_act2_corridor.py tests/test_necromancer_lab_trap_agentic.py -q`：32 passed
- `pytest -q`：473 passed
- `npm test -- --runInBand`：290 passed
- `python -m core.eval.runner --suite golden`：50/50 passed
- `make check`：通过；内部 `pytest -q` 为 473 passed，golden 为 50/50 passed

## 体验风险

- Act2 perception bonus 当前按需求固定为 `+5` 并在 `latest_roll` 可见；未来若角色卡技能系统完善，可以替换为 actor skill bonus。
- 如果玩家第一次靠近时直接走到陷阱触发格，perception 会先解析；失败会在同次移动中继续触发陷阱，成功则 reveal trap。当前未实现“成功察觉后自动打断移动”的额外 UX。
- 旧的 direct trap-insight event 路径保留兼容；正常 DM/Web 路径现在通过 `PERCEPTION` mechanics roll，不再走 deterministic reveal。
