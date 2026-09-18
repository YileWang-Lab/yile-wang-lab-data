"""One-file A/B harness: is CANDIDATE better than BASELINE? Self-play + pool.

    python arena.py <candidate.py>                        # vs submission/main.py
    python arena.py <candidate.py> --baseline <base.py>
    python arena.py <candidate.py> --engine both          # + real-engine gate
    python arena.py <candidate.py> --quick                # 6 seeds, hard pool

Everything in here is a HANDOFF rule made executable. Read this docstring before
reading a number out of the report, because every section answers a DIFFERENT
question and three of them can only fail.

IDENTITY CONTROL (rule 1 / section 21).  `base vs base` must come back at
exactly +0 paired, on every seed. The v3 lineage keeps `_WEED_STATE`,
`_SHIFT_STATE`, `_KAWA_LAYOUT_FALLBACK` and the `_IV` market dict at module
level keyed by seat, so a module reused between episodes silently carries
yesterday's game into today's. If this row is not +0 the harness is leaking and
NOTHING else in the run is evidence -- the run aborts rather than reporting.

SELF-PLAY IS SCORED BY PAIRED MARGIN, NEVER WIN RATE (rule 1).  An agent
against a byte-identical copy of itself wins seat 0 only 15% of the time, mean
margin -$66: `_end_of_day` rolls player 0's weeds first and `_process_market`
resolves atomic HIRE/BUY_LAND in player order. Both seat orders per seed are
summed, so a true mirror scores exactly 0 instead of losing.

THE POOL DELTA IS THE DECISION, AND IT IS PAIRED (rule 1, section 29).  Both
arms play the same opponent on the same seed in the SAME worker (common random
numbers), so the difference is the change and not the seed. Reported two ways:
paired margin, the project standard, and paired WIN RATE, which section 29
measured as more sensitive on every real effect and still exactly zero on the
null -- margin variance is carried by a few blow-out games (sd ~32,500 per
paired game at genome level) while a win rate caps each seed at +-1. Ties are
excluded from the rate and reported, the standard sign-test treatment.

FIRING RATE, NOT GAMES PLAYED (rule 4 -- the most expensive rule here).  The
bucket-0 tape swap changes behaviour in ~13% of games. Its first gate ran 180
paired games, comfortably past the >=100 bar, but only ~28 of them fired, and it
returned -18 for something worth +858 at 630 paired. So this reports how often
the candidate actually diverged from the baseline and the CONDITIONAL
distribution on those games. A concentrated change is judged on its firing
games; the unconditional mean is a dilution of it, not a measurement of it.

EXPLORATION IS NOT PROMOTION. Small screens may falsify a mechanism, but a
positive screen is never labelled an improvement. Formal promotion requires
at least 288 paired pool cells on a declared, previously unused holdout block,
with at least 100 firing cells. This keeps repeated 9/18-cell variants from
turning ordinary winner's-curse noise into a selected policy.

AGENTS ARE LOADED BY FILE PATH AND RESOLVED THE WAY KAGGLE DOES (rule 3).
`get_last_callable` walks the namespace in INSERTION order, so rebinding `agent`
in an appended layer does not move it and the last *newly defined* callable
wins. Reproducing that here is the point: an appended layer changes which entry
runs, and this harness runs whatever Kaggle would run rather than a name we hope
is still there. Every episode loads its agents under a fresh module name.

TWO ENGINES, AND THEY ARE NOT INTERCHANGEABLE.  `planner.simulate` runs an
episode in ~0.31s against the real engine's ~4.8s, which is what makes a
600-game paired run cost a minute. It is not bit-identical in absolute bank:
v3_base vs kawa on seed 9000 is (87,332 / 86,890) real and (87,519 / 87,077)
sim -- both banks off by the same +187, so the MARGIN is identical and paired
work is unaffected. Screen on `sim`; gate a submission decision on `real`
(`--engine both` runs the subset and cross-checks that the two agree in sign).

26 WORKERS, NEVER 52 (CLAUDE.md).  Physical cores. 48 workers on 26 cores took
6+ minutes to not finish what 26 do in 30s.

DO NOT EDIT THE CANDIDATE FILE WHILE THIS IS RUNNING (CLAUDE.md).  Workers
re-exec it per evaluation, so an edit mid-run silently corrupts the signal.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import multiprocessing as mp
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

DEFAULT_BASELINE = os.path.join(ROOT, "submission", "main.py")
PROMOTION_CELLS = 288
PROMOTION_FIRING_CELLS = 100


def _reserve_promotion_holdout(seed0, count, holdout_id):
    """Reject reused formal seed blocks and allocate sequential alpha spend."""
    import glob

    requested = set(range(int(seed0), int(seed0) + int(count)))
    prior = []
    for path in sorted(glob.glob(os.path.join(
            ROOT, "logs", "arena", "*.json"))):
        try:
            with open(path) as stream:
                record = json.load(stream)
        except Exception:
            continue
        protocol = record.get("evaluation_protocol") or {}
        if protocol.get("stage") != "promotion":
            continue
        prior.append((path, record, protocol))
        if str(protocol.get("holdout_id")) == str(holdout_id):
            raise ValueError(
                "holdout id %r was already used in %s"
                % (holdout_id, os.path.relpath(path, ROOT))
            )
        overlap = requested & {
            int(seed) for seed in record.get("seeds", ())
        }
        if overlap:
            raise ValueError(
                "promotion seed block overlaps %s at seed %d"
                % (os.path.relpath(path, ROOT), min(overlap))
            )
    attempt = len(prior) + 1
    # alpha_k = .05/[k(k+1)] is a transparent sequential spending rule:
    # sum_k alpha_k = .05, so repeated formal attempts cannot silently
    # recreate the multiple-comparison problem outside the screening stage.
    alpha = 0.05 / float(attempt * (attempt + 1))
    critical_z = statistics.NormalDist().inv_cdf(1.0 - alpha)
    return attempt, alpha, float(critical_z)

# Deduplicated per HANDOFF section 15. Three matchups are the same agent under
# three names -- rank-top10-read-the-market == 3000-socre == ttv1 -- and
# boatlee's "V20-Adaptive-R1" is kawa itself, so none of them are listed twice.
# Ordered by measured strength against our build (paired margin, 20 seeds, both
# seats): kawa is in a class of its own at +1,176 where the next-hardest is
# +13,311, and `frontier` takes 7 of 20 seeds off us, so it exercises the agent
# differently from the kawa family.
POOLS = {
    # The three that actually contest a game. Use for iteration, not decisions.
    "hard": ["kaggriculture-multi-route-farming-agent",
             "kaggriculture-frontier-the-soil-remembers-rain",
             "v111-8c4s-economic-core-premium-lead"],
    # The project's standard six (dynamic/metric_test.py, dynamic/tape/v3_bench.py).
    "standard": ["kaggriculture-multi-route-farming-agent",
                 "kaggriculture-frontier-the-soil-remembers-rain",
                 "v111-8c4s-economic-core-premium-lead",
                 "kaggriculture-3000-socre",
                 "kaggriculture-rank-your-agent",
                 "strong-barnyard-economist"],
    # All nine loadable references (route/tournament.py REFS).
    "full": ["kaggriculture-multi-route-farming-agent",
             "kaggriculture-frontier-the-soil-remembers-rain",
             "v111-8c4s-economic-core-premium-lead",
             "kaggriculture-breaking-the-tie-2883-score",
             "kaggriculture-rank-your-agent",
             "kaggriculture-3000-socre",
             "15-16-strict-future-v25-meta-reset",
             "strong-barnyard-economist",
             "kaggriculture-pure-architecture-2600-elo-v3"],
}

_loads = [0]


# --------------------------------------------------------------- agent loading

def _isolate_local_package(path):
    """Forget a local package before loading one of its file agents.

    Version wrappers are deliberately tiny and import their implementation from
    ``whitebox.*``.  Giving only the wrapper a unique module name therefore did
    not isolate the mutable plan/market trackers in those imported modules: two
    seats, and later episodes in the same worker, shared one package instance.
    Remove that package tree before executing each wrapper so every returned
    callable closes over an independent implementation graph.  Existing
    callables retain their old module objects, so clearing ``sys.modules`` does
    not mutate an episode already being assembled.
    """
    rel = os.path.relpath(os.path.realpath(path), ROOT)
    package = rel.split(os.path.sep, 1)[0]
    package_dir = os.path.join(ROOT, package)
    local_package = (
        not rel.startswith(os.pardir + os.path.sep)
        and os.path.isfile(os.path.join(package_dir, "__init__.py"))
    )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            header = handle.read(1024)
    except (OSError, UnicodeError):
        header = ""
    whitebox_bundle = (
        "Generated transparent Kaggriculture bundle" in header
        and "_BUNDLE_SOURCES" in header
    )
    if not local_package and not whitebox_bundle:
        return
    # Modular whitebox agents close over ``route.router`` as well as
    # ``whitebox.*``.  Its exact-tour LRU is semantically valid within one
    # episode, but retaining it from the candidate episode into the baseline
    # episode changes how much soft-deadline refinement the latter completes.
    # Reset both dependency trees so a paired cell compares equal cold starts.
    is_whitebox = package == "whitebox" or whitebox_bundle
    packages = (("whitebox", "route") if is_whitebox else (package,))
    if is_whitebox:
        # A generated submission installs its private finder at index zero.
        # Clearing sys.modules alone is insufficient: that stale finder would
        # simply re-inject the previous bundle into the next modular candidate.
        # Conversely, a bundle loaded after a wrapper must not reuse the
        # wrapper's source modules.  Existing callables already close over
        # their module graph, so removing the finder here cannot mutate a
        # running episode.
        sys.meta_path[:] = [
            finder for finder in sys.meta_path
            if finder.__class__.__name__ != "_WhiteboxBundleFinder"
        ]
    for dependency in packages:
        prefix = dependency + "."
        for name in list(sys.modules):
            if name == dependency or name.startswith(prefix):
                del sys.modules[name]


def load_agent(path):
    """Load a file agent and resolve its entry the way Kaggle does (rule 3).

    Kaggle's `get_last_callable` walks the module namespace in INSERTION order,
    so a name rebound by an appended layer keeps its original position and the
    last *newly defined* callable is what runs. Loaded under a unique module
    name every single call and never imported: these agents hold per-seat state
    in module globals, and sharing a module across episodes carries it.
    """
    _isolate_local_package(path)
    _loads[0] += 1
    spec = importlib.util.spec_from_file_location(
        "arena_%d_%d" % (os.getpid(), _loads[0]), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    picked = None
    for name, value in vars(m).items():
        if callable(value) and not name.startswith("__"):
            picked = (name, value)
    if picked is None:
        raise RuntimeError("no callable in %s" % path)
    return picked


def entry_name(path):
    return load_agent(path)[0]


def opp_path(name):
    return name if os.path.sep in name else os.path.join(ROOT, "opponents", name + ".py")


# ---------------------------------------------------------------------- engines

def play_sim(path_a, path_b, seed):
    """One episode through planner.simulate. Returns (bank0, bank1)."""
    from planner.simulate import Simulator
    a = load_agent(path_a)[1]
    b = load_agent(path_b)[1]
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    return sim.run_episode(a, b)


def play_real(path_a, path_b, seed):
    """One episode through kaggle_environments, BY FILE PATH (rule 3).

    Status is returned as well as banks, and it is not decoration: an agent that
    raises is not scored 0 for the turn, it is marked INVALID and forfeits --
    and a forfeit still produces a plausible-looking bank, so the status field
    is the only thing that distinguishes it from a loss.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        from kaggle_environments import make
        env = make("kaggriculture",
                   configuration={"episodeSteps": 720, "seed": seed}, debug=False)
        env.run([path_a, path_b])
    f = env.steps[-1]
    return ((float(f[0].observation["farms"][0]["money"]),
             float(f[1].observation["farms"][1]["money"])),
            tuple(s.status for s in f))


def _play(engine, path_a, path_b, seed):
    """(bank0, bank1, status_tuple). `sim` reports status as DONE/DONE."""
    if engine == "real":
        banks, status = play_real(path_a, path_b, seed)
        return banks[0], banks[1], status
    b0, b1 = play_sim(path_a, path_b, seed)
    return b0, b1, ("DONE", "DONE")


# ---------------------------------------------------------------------- workers

def mirror_job(job):
    """One same-tape episode. `arm, seed, seat -> our margin`, seat un-swapped.

    Un-swapping means the returned margin is always ours-minus-theirs whichever
    seat `left` actually sat in, so the two seat orders of a seed can be summed
    into the paired margin rule 1 requires.
    """
    engine, arm, left, right, seed, seat = job
    try:
        a, b = (left, right) if seat == 0 else (right, left)
        m0, m1, status = _play(engine, a, b, seed)
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (arm, seed, seat, us - them, status, None)
    except Exception:
        import traceback
        return (arm, seed, seat, 0.0, ("ERROR", "ERROR"), traceback.format_exc()[-400:])


def pool_job(job):
    """BOTH arms against one opponent, one seed, one seat, in ONE worker.

    Same worker and same seed is the common-random-numbers part: the two arms
    see an identical episode, so a difference between them is the change and not
    the draw. Splitting them across workers would still be deterministic, but it
    makes a mismatch attributable to the worker rather than to the arm.
    """
    engine, cand, base, opp, seed, seat = job
    try:
        op = opp_path(opp)
        out = {}
        for arm, path in (("cand", cand), ("base", base)):
            a, b = (path, op) if seat == 0 else (op, path)
            m0, m1, status = _play(engine, a, b, seed)
            us, them = (m0, m1) if seat == 0 else (m1, m0)
            mine = status[0] if seat == 0 else status[1]
            out[arm] = (us, them, mine)
        return (opp, seed, seat, out["cand"], out["base"], None)
    except Exception:
        import traceback
        return (opp, seed, seat, None, None, traceback.format_exc()[-400:])


# ---------------------------------------------------------------------- reports

def pair_by_seed(rows):
    """{(key): seat0 + seat1 margin} -- only seeds that produced both seats."""
    per = {}
    for key, margin in rows:
        per.setdefault(key, []).append(margin)
    return {k: sum(v) for k, v in per.items() if len(v) == 2}


def stats(diffs):
    """Paired margin and paired win rate for one list of per-seed differences.

    Both metrics on the same sample, because section 29 measured the win rate as
    more sensitive on every real effect (+29% to +45% t on the noisy ones) while
    still returning exactly 0.00 on an exact null. Ties -- seeds where the change
    did not fire at all -- are excluded from the rate, not counted as losses.
    """
    n = len(diffs)
    if not n:
        return dict(n=0, mean=0.0, se=0.0, t=0.0, w=0, l=0, ties=0,
                    p=0.5, wse=0.0, wt=0.0, fired=0, fire_rate=0.0, cond=0.0)
    mean = statistics.mean(diffs)
    se = (statistics.pstdev(diffs) / (n ** 0.5)) if n > 1 else 0.0
    t = mean / se if se > 1e-9 else 0.0
    w = sum(1 for x in diffs if x > 0)
    l = sum(1 for x in diffs if x < 0)
    ties = n - w - l
    n_eff = w + l
    if n_eff:
        p = w / n_eff
        wse = (0.25 / n_eff) ** 0.5
        wt = (p - 0.5) / wse
    else:
        p, wse, wt = 0.5, 0.0, 0.0
    fired = [x for x in diffs if x != 0]
    return dict(n=n, mean=mean, se=se, t=t, w=w, l=l, ties=ties,
                p=p, wse=wse, wt=wt, fired=len(fired),
                fire_rate=len(fired) / float(n),
                cond=statistics.mean(fired) if fired else 0.0)


def print_mirror(label, rows, note=""):
    errs = [r for r in rows if r[5]]
    paired = pair_by_seed([(r[1], r[3]) for r in rows if not r[5]])
    total = sum(paired.values())
    nonzero = [s for s, v in paired.items() if v != 0]
    bad_status = [r for r in rows if r[4] != ("DONE", "DONE")]
    print("  %-16s paired %+13s   nonzero %2d/%-3d   %s%s"
          % (label, "{:,.0f}".format(total), len(nonzero), len(paired), note,
             "  ERRORS %d" % len(errs) if errs else ""))
    if bad_status:
        print("      %d episodes not DONE/DONE -- first %s"
              % (len(bad_status), bad_status[0][4]))
    if errs:
        print("      first error: " + errs[0][5].strip().splitlines()[-1])
    return total, nonzero, errs, paired


# --------------------------------------------------------------------- the run

def main():
    ap = argparse.ArgumentParser(
        description="Self-play + opponent-pool A/B for a Kaggriculture agent.")
    ap.add_argument("candidate", help="agent file to test")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE,
                    help="what to beat (default submission/main.py)")
    ap.add_argument("--pool", default="standard",
                    help="hard | standard | full | comma-separated names/paths")
    ap.add_argument("--seeds", type=int, default=24, help="seeds per opponent")
    ap.add_argument("--seed0", type=int, default=9000)
    ap.add_argument("--self-seeds", type=int, default=None,
                    help="seeds for the self-play block (default = --seeds)")
    ap.add_argument("--engine", choices=("sim", "real", "both"), default="sim")
    ap.add_argument("--real-seeds", type=int, default=6,
                    help="seeds per opponent for the real-engine gate under --engine both")
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--no-selfplay", action="store_true")
    ap.add_argument("--no-pool", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="6 seeds on the hard pool -- iteration only, never a decision")
    ap.add_argument("--stage", choices=("screen", "promotion"),
                    default="screen",
                    help="screens can falsify only; promotion enforces the independent 288-cell gate")
    ap.add_argument("--holdout-id", default=None,
                    help="required for promotion: identifier of a previously unused seed block")
    ap.add_argument("--json", default=None, help="write the full result (default logs/arena/)")
    args = ap.parse_args()

    if args.quick:
        if args.stage == "promotion":
            ap.error("--quick cannot be used for promotion")
        args.seeds, args.pool = 6, "hard"
    cand = os.path.abspath(args.candidate)
    base = os.path.abspath(args.baseline)
    for p in (cand, base):
        if not os.path.exists(p):
            raise SystemExit("missing: %s" % p)
    pool = POOLS.get(args.pool) or [s.strip() for s in args.pool.split(",") if s.strip()]
    if args.stage == "promotion":
        if args.no_pool:
            ap.error("promotion requires the opponent pool")
        if not args.holdout_id:
            ap.error("promotion requires --holdout-id for a previously unused seed block")
        if len(pool) * int(args.seeds) < PROMOTION_CELLS:
            ap.error(
                "promotion requires at least %d paired pool cells; requested %d"
                % (PROMOTION_CELLS, len(pool) * int(args.seeds))
            )
    promotion_attempt = None
    promotion_alpha = None
    promotion_critical_z = 2.0
    if args.stage == "promotion":
        try:
            (promotion_attempt, promotion_alpha,
             promotion_critical_z) = _reserve_promotion_holdout(
                args.seed0, args.seeds, args.holdout_id,
            )
        except ValueError as exc:
            ap.error(str(exc))
    self_seeds_n = args.self_seeds if args.self_seeds is not None else args.seeds
    t0 = time.time()

    print("=" * 78)
    print("ARENA   candidate vs baseline, self-play + pool")
    print("=" * 78)
    print("  candidate  %s  (%d bytes)" % (os.path.relpath(cand, ROOT), os.path.getsize(cand)))
    print("  baseline   %s  (%d bytes)" % (os.path.relpath(base, ROOT), os.path.getsize(base)))
    if cand == base:
        print("  NOTE candidate IS baseline -- this is the null run; every row must be +0")

    # Preflight in the parent, before a single job is scheduled. An opponent
    # that raises at import (several here carry a top-level IPython import)
    # otherwise produces one dead job per (seed, seat) and the run reports a
    # wall of tracebacks that read like divergences.
    try:
        print("  kaggle entry  candidate -> %s" % entry_name(cand))
        print("  kaggle entry  baseline  -> %s" % entry_name(base))
    except Exception as exc:
        raise SystemExit("cannot resolve an entry point: %s: %s" % (type(exc).__name__, exc))
    ok = []
    for name in pool:
        try:
            load_agent(opp_path(name))
            ok.append(name)
        except Exception as exc:
            print("  dropped  %-46s %s: %s" % (name[:46], type(exc).__name__, str(exc)[:40]))
    if not ok and not args.no_pool:
        raise SystemExit("no usable opponents")
    pool = ok
    print("  pool (%s, %d)  %s" % (args.pool, len(pool), ", ".join(p[:34] for p in pool)))

    engines = ["sim", "real"] if args.engine == "both" else [args.engine]
    seeds = [args.seed0 + i for i in range(args.seeds)]
    self_seeds = [args.seed0 + i for i in range(self_seeds_n)]
    result = {"candidate": cand, "baseline": base, "pool": pool,
              "seeds": seeds, "engines": engines, "arms": {}}
    result["evaluation_protocol"] = {
        "stage": str(args.stage),
        "holdout_id": args.holdout_id,
        "promotion_cells_required": PROMOTION_CELLS,
        "promotion_firing_cells_required": PROMOTION_FIRING_CELLS,
        "promotion_attempt": promotion_attempt,
        "sequential_alpha": promotion_alpha,
        "critical_win_z": promotion_critical_z,
        "declared_independent": bool(
            args.stage == "promotion" and args.holdout_id
        ),
    }
    verdict_lines = []
    aborted = False

    ctx = mp.get_context("forkserver")
    for engine in engines:
        eseeds = ([args.seed0 + i for i in range(args.real_seeds)]
                  if engine == "real" and args.engine == "both" else seeds)
        eself = ([args.seed0 + i for i in range(min(args.real_seeds, self_seeds_n))]
                 if engine == "real" and args.engine == "both" else self_seeds)

        mirror_jobs = []
        if not args.no_selfplay:
            arms = [("base_vs_base", base, base)]
            if cand != base:
                arms += [("cand_vs_cand", cand, cand), ("cand_vs_base", cand, base)]
            mirror_jobs = [(engine, a, l, r, s, t)
                           for a, l, r in arms for s in eself for t in (0, 1)]
        pool_jobs = ([] if args.no_pool else
                     [(engine, cand, base, o, s, t)
                      for o in pool for s in eseeds for t in (0, 1)])

        print("\n" + "=" * 78)
        print("ENGINE  %s   %d self-play + %d pool episodes (%d games) on %d workers"
              % (engine.upper(), len(mirror_jobs), 2 * len(pool_jobs),
                 len(mirror_jobs) + 2 * len(pool_jobs), args.workers))
        print("=" * 78, flush=True)

        te = time.time()
        with ctx.Pool(args.workers) as p:
            mirror = p.map(mirror_job, mirror_jobs, chunksize=1) if mirror_jobs else []
            pooled = p.map(pool_job, pool_jobs, chunksize=1) if pool_jobs else []
        print("  %.1f min" % ((time.time() - te) / 60.0))

        arm = {}
        # ---------------------------------------------------- self-play block
        if mirror:
            print("\n  HEAD-TO-HEAD + MIRRORS")
            print("    Same-version mirror win rate is seat bias and is used only as")
            print("    an identity check. Candidate-vs-baseline win rate is meaningful.")
            by = {}
            for r in mirror:
                by.setdefault(r[0], []).append(r)
            id_total, id_nonzero, id_errs, _ = print_mirror(
                "base_vs_base", by.get("base_vs_base", []), "IDENTITY CONTROL")
            if id_total != 0 or id_nonzero or id_errs:
                print("\n  ABORT  the identity control is not +0. The harness is carrying")
                print("         per-seat module state between episodes, so no other row")
                print("         in this run is evidence. Fix that before reading anything.")
                aborted = True
            if "cand_vs_cand" in by:
                cc_total, cc_nonzero, _, _ = print_mirror(
                    "cand_vs_cand", by["cand_vs_cand"], "candidate's own mirror")
                if cc_total != 0 or cc_nonzero:
                    print("      WARNING candidate is not deterministic against itself;")
                    print("              every paired number below inherits that noise.")
            if "cand_vs_base" in by:
                h2h_total, h2h_nz, _, h2h_paired = print_mirror(
                    "cand_vs_base", by["cand_vs_base"], "HEAD TO HEAD")
                st = stats(list(h2h_paired.values()))
                episode_st = stats([r[3] for r in by["cand_vs_base"] if not r[5]])
                print("      episode WIN %.1f%%  W-L-T %d-%d-%d"
                      % (100 * episode_st["p"], episode_st["w"],
                         episode_st["l"], episode_st["ties"]))
                print("      paired  WIN %.1f%%  W-L-T %d-%d-%d   margin %s"
                      "  se %s  t %.2f"
                      % (100 * st["p"], st["w"], st["l"], st["ties"],
                         "{:+,.0f}".format(st["mean"]), "{:,.0f}".format(st["se"]),
                         st["t"]))
                arm["selfplay"] = {"total": h2h_total, "nonzero_seeds": len(h2h_nz),
                                   "seeds": len(h2h_paired), **{k: st[k] for k in
                                   ("mean", "se", "t", "p", "w", "l", "ties")},
                                   "episode": {k: episode_st[k] for k in
                                               ("n", "p", "w", "l", "ties")}}
                verdict_lines.append(
                    ("%s self-play vs baseline" % engine,
                     "episode WIN %.1f%%; paired WIN %.1f%%; margin %s over %d seeds"
                     % (100 * episode_st["p"], 100 * st["p"],
                        "{:+,.0f}".format(h2h_total), len(h2h_paired))))

        # --------------------------------------------------------- pool block
        if pooled:
            errs = [r for r in pooled if r[5]]
            bad_status = [r for r in pooled if not r[5] and
                          (r[3][2] != "DONE" or r[4][2] != "DONE")]
            if errs:
                print("\n  %d errored episodes; first:\n    %s"
                      % (len(errs), errs[0][5].strip().splitlines()[-1]))
            if bad_status:
                print("  %d episodes did not finish DONE -- a forfeit still banks a"
                      " plausible number, so these are excluded" % len(bad_status))
            live = [r for r in pooled if not r[5] and r not in bad_status]

            c_rows = {}
            b_rows = {}
            c_games = {}
            b_games = {}
            for opp, seed, seat, c, b, _ in live:
                cm, bm = c[0] - c[1], b[0] - b[1]
                c_rows.setdefault(opp, []).append(((opp, seed), cm))
                b_rows.setdefault(opp, []).append(((opp, seed), bm))
                c_games.setdefault(opp, []).append(cm)
                b_games.setdefault(opp, []).append(bm)

            print("\n  POOL   candidate vs baseline, common random numbers.")
            print("         game = actual episode win rate; pair = both seat margins summed.")
            print("         A>B  = candidate improves on baseline in the paired cell.")
            print("         fire  = % of paired seeds where the two actually differ"
                  " (rule 4)\n")
            print("  %-30s %5s %7s %7s %7s %7s %7s %11s %5s"
                  % ("opponent", "seeds", "candG", "candP", "baseG",
                     "baseP", "A>B", "delta", "fire"))
            all_diffs, all_cp, all_bp = [], [], []
            all_c_games, all_b_games, per_opp = [], [], {}
            for opp in pool:
                if opp not in c_rows:
                    continue
                cp = pair_by_seed(c_rows[opp])
                bp = pair_by_seed(b_rows[opp])
                keys = [k for k in cp if k in bp]
                if not keys:
                    continue
                diffs = [cp[k] - bp[k] for k in keys]
                all_diffs.extend(diffs)
                cp_vals, bp_vals = [cp[k] for k in keys], [bp[k] for k in keys]
                all_cp.extend(cp_vals); all_bp.extend(bp_vals)
                all_c_games.extend(c_games[opp]); all_b_games.extend(b_games[opp])
                st, cpair, bpair = stats(diffs), stats(cp_vals), stats(bp_vals)
                cgame, bgame = stats(c_games[opp]), stats(b_games[opp])
                per_opp[opp] = {"delta": st, "candidate_game": cgame,
                                "candidate_pair": cpair, "baseline_game": bgame,
                                "baseline_pair": bpair}
                print("  %-30s %5d %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%% %11s %4.0f%%"
                      % (opp[:30], len(keys), 100 * cgame["p"], 100 * cpair["p"],
                         100 * bgame["p"], 100 * bpair["p"], 100 * st["p"],
                         "{:+,.0f}".format(st["mean"]), 100 * st["fire_rate"]))
            tot = stats(all_diffs)
            cpair_tot, bpair_tot = stats(all_cp), stats(all_bp)
            cgame_tot, bgame_tot = stats(all_c_games), stats(all_b_games)
            print("  " + "-" * 92)
            print("  %-30s %5d %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%% %11s %4.0f%%"
                  % ("TOTAL", tot["n"], 100 * cgame_tot["p"], 100 * cpair_tot["p"],
                     100 * bgame_tot["p"], 100 * bpair_tot["p"], 100 * tot["p"],
                     "{:+,.0f}".format(tot["mean"]), 100 * tot["fire_rate"]))

            # Rule 4. The unconditional mean of a concentrated change is a
            # dilution of it, not a measurement of it.
            fired = [d for d in all_diffs if d != 0]
            print("\n  FIRING (rule 4)  %d of %d paired seeds diverged (%.0f%%)."
                  % (len(fired), tot["n"], 100 * tot["fire_rate"]))
            if fired:
                fst = stats(fired)
                print("    CONDITIONAL on firing:  mean %s   se %s   t %.2f"
                      "   W-L %d-%d  (%.1f%%)"
                      % ("{:+,.0f}".format(fst["mean"]), "{:,.0f}".format(fst["se"]),
                         fst["t"], fst["w"], fst["l"], 100 * fst["p"]))
                print("    Report this, not just the total: a change that fires in 13%%")
                print("    of games and is worth +858 there reads as -18 unconditionally.")
            arm["pool"] = {"total": {k: tot[k] for k in
                                     ("n", "mean", "se", "t", "p", "wt", "w", "l",
                                      "ties", "fired", "fire_rate", "cond")},
                           "candidate": {"game": {k: cgame_tot[k] for k in
                                                    ("n", "p", "w", "l", "ties")},
                                         "pair": {k: cpair_tot[k] for k in
                                                    ("n", "p", "w", "l", "ties", "mean")}},
                           "baseline_absolute": {"game": {k: bgame_tot[k] for k in
                                                            ("n", "p", "w", "l", "ties")},
                                                 "pair": {k: bpair_tot[k] for k in
                                                            ("n", "p", "w", "l", "ties", "mean")}},
                           "per_opponent": per_opp,
                           "errors": len(errs), "not_done": len(bad_status)}
            verdict_lines.append(
                ("%s pool delta" % engine,
                 "candidate game/pair WIN %.1f%%/%.1f%%; baseline %.1f%%/%.1f%%; "
                 "A>B %.1f%%; margin %s"
                 % (100 * cgame_tot["p"], 100 * cpair_tot["p"],
                    100 * bgame_tot["p"], 100 * bpair_tot["p"], 100 * tot["p"],
                    "{:+,.0f}".format(tot["mean"]))))
        result["arms"][engine] = arm

    # ------------------------------------------------------------------ verdict
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    for label, line in verdict_lines:
        print("  %-28s %s" % (label, line))

    call = "INCONCLUSIVE"
    if aborted:
        call = "ABORTED -- identity control failed, nothing here is evidence"
    else:
        prim = (
            result["arms"].get("sim", {}).get("pool")
            if args.stage == "promotion" else
            result["arms"].get("real", {}).get("pool") or
            result["arms"].get("sim", {}).get("pool")
        )
        if prim:
            t = prim["total"]
            notes = []
            promotion_ready = bool(
                args.stage == "promotion"
                and t["n"] >= PROMOTION_CELLS
                and t["fired"] >= PROMOTION_FIRING_CELLS
                and int(prim.get("errors", 0)) == 0
                and int(prim.get("not_done", 0)) == 0
            )
            if args.stage == "promotion":
                if t["n"] < PROMOTION_CELLS:
                    notes.append(
                        "PROMOTION UNDERPOWERED: %d paired cells; require >=%d"
                        % (t["n"], PROMOTION_CELLS)
                    )
                if t["fired"] < PROMOTION_FIRING_CELLS:
                    notes.append(
                        "PROMOTION UNDER-FIRED: %d firing cells; require >=%d"
                        % (t["fired"], PROMOTION_FIRING_CELLS)
                    )
                if prim.get("errors") or prim.get("not_done"):
                    notes.append(
                        "PROMOTION INVALID: %d errors and %d non-DONE episodes"
                        % (prim.get("errors", 0), prim.get("not_done", 0))
                    )
            elif t["n"] < 100 or t["fired"] < 30:
                notes.append(
                    "SCREEN ONLY: %d paired / %d firing cells; no promotion inference"
                    % (t["n"], t["fired"])
                )
            decision_z = (
                float(promotion_critical_z)
                if args.stage == "promotion" else 2.0
            )
            # WIN RATE IS THE VERDICT. Margin is reported and is advisory.
            #
            # Section 29 measured the paired win rate as more sensitive than the
            # margin on every real effect (+29% to +45% t on the noisy ones) and
            # still exactly 0.00 on an exact null, because margin variance is
            # carried by a handful of blow-out games while a win rate caps each
            # seed at +-1. The ladder scores wins, not banks.
            #
            # A change that RAISES the margin while LOWERING the win rate is a
            # regression: it is winning its wins by more and losing more often,
            # which is the shape of a variance increase, not an improvement.
            if t["wt"] >= decision_z:
                call = "IMPROVEMENT"
                if t["t"] < 0:
                    notes.append("win rate up but MARGIN DOWN (%s): the change "
                                 "wins more often and loses bigger"
                                 % "{:+,.0f}".format(t["mean"]))
            elif t["wt"] <= -decision_z:
                call = "REGRESSION"
                if t["mean"] > 0:
                    notes.append("MARGIN UP (%s) but win rate down: counted as a "
                                 "REGRESSION -- see section 29"
                                 % "{:+,.0f}".format(t["mean"]))
            elif t["mean"] > 0 and t["p"] < 0.5:
                call = "REGRESSION -- margin up, win rate below 50%"
            elif t["fired"] == 0:
                call = "INERT -- the candidate never diverged from the baseline. " \
                       "Section 21: identical rows mean a parameter is inert, " \
                       "not that the idea is neutral."
            else:
                call = "NEUTRAL -- not separable from the baseline at this n"
            if call == "IMPROVEMENT" and args.stage != "promotion":
                call = "POSITIVE SCREEN -- NOT PROMOTED"
            elif call == "IMPROVEMENT" and not promotion_ready:
                call = "INCONCLUSIVE -- PROMOTION SAMPLE GATE FAILED"
            for n_ in notes:
                print("  ! " + n_)
            if "real" in result["arms"] and "sim" in result["arms"]:
                sp = result["arms"]["sim"].get("pool")
                rp = result["arms"]["real"].get("pool")
                if sp and rp:
                    agree = (sp["total"]["mean"] > 0) == (rp["total"]["mean"] > 0)
                    print("  %s sim %s/seed vs real %s/seed"
                          % ("engines AGREE in sign:" if agree else
                             "! ENGINES DISAGREE IN SIGN:",
                             "{:+,.0f}".format(sp["total"]["mean"]),
                             "{:+,.0f}".format(rp["total"]["mean"])))
                    if not agree:
                        call = "INCONCLUSIVE -- sim and real disagree; trust real, " \
                               "and raise n before deciding"
    print("\n  %s" % call)
    result["verdict"] = call
    print("=" * 78)

    out = args.json or os.path.join(
        ROOT, "logs", "arena", "arena_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("  %.1f min total   %s" % ((time.time() - t0) / 60.0, os.path.relpath(out, ROOT)))
    return 0 if call.startswith(("IMPROVEMENT", "NEUTRAL", "INERT")) else 1


if __name__ == "__main__":
    sys.exit(main())
