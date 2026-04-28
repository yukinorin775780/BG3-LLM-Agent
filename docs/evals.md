# Evals 与本地检查

## 常用命令

全量单元测试：

```bash
make test
```

Golden Eval：

```bash
make eval
```

完整本地检查（单测 + Golden Eval）：

```bash
make check
```

单个 Eval Case：

```bash
make eval-case CASE=shadowheart_artifact_probe
```

也可直接调用：

```bash
python -m core.eval.runner --suite golden
python -m core.eval.runner --case shadowheart_artifact_probe
```

## Artifacts 位置

Eval 结果输出到：

```text
artifacts/evals/<run_id>/
```

重点排查文件：

- `transcript.jsonl`
- `telemetry.jsonl`
- `final_state.json`
- `summary.json`

## Golden Eval vs Live Eval

- Golden Eval：使用仓库内固定用例 + 回放数据，结果可复现，不依赖真实在线模型与外网。
- Live Eval：连接真实模型服务，受模型版本、网络、账号配额等影响，结果可能波动。

## 为什么 PR 默认只跑 Golden Eval

- 保证 CI 稳定可复现。
- 不要求真实 API key。
- 避免外部网络和在线模型波动导致假失败。
- 控制 CI 成本和时延。

## Content Sprint 1 Baseline 约束

- `necromancer_lab` 的 Content Sprint 1 golden cases 是 playable demo baseline 的正式组成部分。
- 不允许将以下四幕主线 case 降级为 smoke：
  - `necromancer_lab_act1_trap_perception`
  - `necromancer_lab_act2_diary_int_success`
  - `necromancer_lab_act2_diary_int_failure`
  - `necromancer_lab_act3_side_with_astarion`
  - `necromancer_lab_act3_rebuke_astarion`
  - `necromancer_lab_act4_loot_key_and_escape`
- 若剧情机制调整影响上述 case，必须同步更新 deterministic 断言与回放脚本，不得删除验收维度。

## 什么时候补 Golden Case

以下改动建议同步新增或更新 golden case：

- 新增剧情分支（任务推进、剧情旗标、关键道具交互）。
- 新增 NPC（发言选择、关系变化、状态变更）。
- 修改 DM/Generation 行为且预期输出约束发生变化。
- 修复线上/回归 bug，并希望长期防回归。
