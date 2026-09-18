# Kaggriculture

这是 Kaggle **Kaggriculture** 的完全白盒实现（2-player、720 turns）。当前
生产架构只依赖每一步的 observation、公开引擎规则和自身跨回合状态；不读取
replay、action tape、seed、episode id、对手身份、榜单排名或拟合参数。

**新会话先读 [`HANDOFF.md`](HANDOFF.md)**；数学模型和模块边界分别见
[`MODEL.md`](MODEL.md) 与 [`WHITEBOX_ARCHITECTURE.md`](WHITEBOX_ARCHITECTURE.md)。

---

## What ships

- `whitebox/agent.py`：模块化生产入口 `_whitebox_entry`。
- `whitebox/versions/v218_certified_shed_cluster.py`：当前 V218 白盒包装器，
  在 V204 的协同资本、任务/路线、现金流、市场和终局证书上，加入仅由
  公开 shed-access 几何与完整服务证书准入的动物中心化布局。
- `submission/whitebox_v218_certified_shed_cluster.py`：由
  `scripts/package_whitebox.py` 生成的单文件提交包，只内嵌可审计的
  `whitebox/` 与 `route/` 源码。

V218 是当前发布的白盒研究版本，并非已宣称晋级的胜率保证；V204 保留为
可复现基线，V214/V215 仅作研究对照。

重新生成当前白盒提交包：

```bash
/home/yilewang/kagg-env/bin/python scripts/package_whitebox.py \
  --entry whitebox.versions.v218_certified_shed_cluster \
  --callable whitebox_v218_certified_shed_cluster \
  --output submission/whitebox_v218_certified_shed_cluster.py
```

## Historical tape-era measurements (not production)

The table below is retained only for provenance. It describes the old tape
lineage and must not be imported by the current runtime. Public-state-router
notebooks were used to derive rule-level hypotheses (capacity, route feasibility,
and state repair), never as an action source.

### Ladder

| submission | what it is | score |
|---|---|---|
| 55600561 `v3` | kawa + our market layer | **2394** (37 games, 32-5, **86%**) |
| 55594505 | unmodified kawa | 2326 |
| 55597426 | unmodified kawa | 1970 |
| 55587826 | our own planner (all-crop GA) | 483 |

Both of the earlier user submissions were verified as unmodified kawa by
extracting their tape from replays and matching frame-for-frame.

### Local, paired margin (both seat orders per seed, summed)

Our build against the whole evaluation pool, 20 seeds:

| opponent | paired margin | paired wins |
|---|---|---|
| kawa (multi-route) | **+1,176** | 19/20 |
| frontier-the-soil-remembers-rain | +13,311 | 13/20 |
| v111 / V16-RC5 | +14,798 | 15/20 |
| breaking-the-tie-2883 | +17,284 | 15/20 |
| Kaito Fukami v25 | +27,512 | 20/20 |
| strong-barnyard-economist | +33,887 | 20/20 |
| pure-architecture-2600-elo | +39,589 | 20/20 |

kawa is in a class of its own — the next-hardest opponent is 11x further away.

### What each change was worth

| change | paired margin vs kawa |
|---|---|
| plain kawa | 0 (baseline) |
| `_PREEMPT_MIN_FUTURE_QUANTITY` 4→0, `_PREEMPT_MAX_BATCH` 12→30 | +464 |
| + market intervention, lead 1, dump 40% | +1,221 |
| + lead 3 and FERTILIZER | +1,428 |
| + dump 80% | **+1,611** |

Refinements tested and **rejected** (all measured, none shipped): exact
repayment/volume conservation, staged dumping, near-mirror gating, wheat
starvation squeeze, structural yield forecast, floor-price gate, sell-slot
reordering, and every attempt to touch the tape.

## Layout and reusable evaluation

```
whitebox/               visible-state policy modules, equations and tests
whitebox/versions/      versioned white-box wrappers (V204 is current)
route/router.py         deterministic multi-worker daily route solver
route/match.py          shared seeded match loader and result object
arena.py                paired-seat A/B harness with common random numbers
scripts/package_whitebox.py   self-contained bundle generator
scripts/audit_whitebox_runtime.py  AST closure audit
submission/whitebox_v204.py     generated Kaggle entry

incoming/, archive/, dynamic/tape/ and legacy files are offline research
material. They are not reachable from the production bundle and are excluded
from the white-box packaging path.
```

## The self-built planner

`route/router.py` is the reusable daily routing solver: it assigns rule-derived
tasks to workers and orders stops with deterministic nearest-neighbour/2-opt
logic. It is called by the white-box planner online; no offline route or action
array is loaded.

Best measured: **-8,192 paired margin** against the reference pool after 124
generations, improved from -34,720. Still negative; it does not beat kawa.
Checkpoints in `route/checkpoints/`.

The old tape-era planner and opponent pool remain only as historical diagnostics;
they are not part of the production import closure.

## Reproducing checks

```bash
/home/yilewang/kagg-env/bin/python scripts/audit_whitebox_runtime.py \
  --entry whitebox.versions.v204_retained_land_commitment \
  --callable whitebox_v204_retained_land_commitment
/home/yilewang/kagg-env/bin/python -m unittest discover -s whitebox -p 'test_*.py'
/home/yilewang/kagg-env/bin/python -m compileall -q whitebox route planner arena.py
git diff --check
```
