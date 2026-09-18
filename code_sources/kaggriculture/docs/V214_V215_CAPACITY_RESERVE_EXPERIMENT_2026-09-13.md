# V214/V215 日界容量保护实验（2026-09-13）

## 目的

参考公开 Kaggle notebook 中的 `projected shed` / day-close room guard，
验证在每天第 23 小时根据当前可见状态清理一部分 shed 库存，是否能避免
次日自动入库时丢失携带产出。该机制只作为 V204 的研究后处理；V204
仍是生产基线。

## 白盒边界

- 运行时只读取当前 observation、当前 unit actions、当前市场订单和
  `state.project_unit_phase` 的确定性投影。
- 未读取 replay/action tape、episode id、seed、对手身份、榜单排名或未来动作。
- 只在 `hour == 23` 且未进入 endgame 时运行；未知/异常状态保持父订单。
- 只出售投影后已经在 shed 中的库存；携带库存本身不能直接 `SELL`。
- WHEAT 按当前 FEED 证书保留，FERTILIZER 按当前计划保留；不为同回合
  尚未承诺成功的 BUY_PRODUCT/BUY_ANIMAL 预留空间，避免为失败购买提前卖货。

## 候选版本

| 版本 | 变化 |
| --- | --- |
| V214 | V204 参数 + `capacity_reserve`，目标为 shed 99 个单位；按当前报价排序。 |
| V215 | 仅将容量清理顺序改为公开 room-guard 的规则级顺序：WOOL、MILK、EGG、销售型作物，WHEAT 最后。 |

两版均为 research-only，未替换 V204。

## 组件协同修正

检查发现，启用容量后处理的候选在资本层和市场层分别计算了同一
`project_unit_phase`。现在 `whitebox/agent.py` 在有资本 master 时把已经
生成的 `decision_snap` 直接交给容量层；无资本 master 时才单独生成一次。
这样任务、资本和市场使用同一个 post-unit 状态，避免重复计算和携带库存
口径漂移。该修正不改变 V204 的生产路径，也没有引入任何新信息源。

## 验证

```text
unittest discover -s whitebox: 399 passed
compileall / git diff --check: PASS
audit_whitebox_runtime (V214, V215): PASS, filesystem-free
```

快速筛选使用同一随机种子块和 hard pool（3 个公开对手、6 个种子、双座位；
自对战与 pool 共 108 局），仅用于筛选，不能作为晋级证据。

| 版本 | self-play 相对 V204 | pool 配对均值 | pool A>B | firing |
| --- | ---: | ---: | ---: | ---: |
| V214 | +3,100/seed，paired win 66.7% | +670/seed | 26.7% | 83.3% |
| V215 | +3,100/seed，paired win 66.7% | +670/seed | 26.7% | 83.3% |

pool 的实际候选胜率为 0%（公开 hard 对手显著强于 V204），因此 arena
给出 `REGRESSION -- margin up, win rate below 50%`。V215 与 V214 完全相同，
说明本屏触发状态下公开优先级没有改变最终订单选择，不能据此声称收益改善。

按筛选流程又对 V214 做了 108 个 hard-pool 配对 cell（3 个对手 × 36 个
种子 × 双座位；无 self-play）：A>B 为 54.3%，平均配对差额 +574，94/108
cell 实际触发（87%），触发条件下均值 +659、`t = 2.05`。由于这是同一
screen 家族、未声明独立 holdout，且实际游戏胜率仍为 0%，arena 判定为
`NEUTRAL -- not separable`，不构成晋级证据。

共享投影后的 V214 quick screen 与此前结果完全一致（self-play paired
margin +3,100、pool +670，触发率 83.3%），说明该改动是协同/运行时修正，
不是隐性改变策略信号。

## 结论

容量保护在配对金额上略有正向信号，但胜率不达标、样本也远低于正式门槛，
V214/V215 均不晋级。保留代码和实验记录，生产继续使用
`whitebox/versions/v204_retained_land_commitment.py`。后续若继续研究，
应先做逐触发的产品/数量归因，再考虑更窄的条件，而不是把公开 tape 行为
硬编码进策略。
