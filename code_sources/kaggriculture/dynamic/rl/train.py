"""PPO over the scheduler's decision points, against an opponent pool.

REWARD IS THE MATCH OUTCOME, not the margin. `publicScore` is a skill rating
driven by wins (HANDOFF section 7), and section 31 measured a change worth
win-rate t=12 whose mean margin was exactly zero -- the two objectives genuinely
disagree, and the ladder scores the first one. So terminal reward is +1 / -1 on
the paired result, with a small margin term only as a tie-breaker inside a
result, never large enough to trade a win for a bigger loss.

PAIRED EPISODES. Seat asymmetry is real here (HANDOFF rule 1: a byte-identical
mirror wins seat 0 only 15% of the time), so every rollout plays the SAME seed
from BOTH seats against the same opponent and the reward is the paired outcome.
That removes the seat term from the gradient instead of asking the network to
learn around it.

SELF-PLAY IS REQUIRED FOR THE SIGN TERM TO CARRY INFORMATION. Against the
reference pool alone the agent loses 100% of paired episodes, so sign(paired) is
a constant and only the margin term teaches anything. Playing a FROZEN SNAPSHOT
of the current policy puts the win rate at 50% by construction, which is where a
win/loss signal has the most information in it. The references stay in the mix
so the policy cannot drift into beating only itself -- that is the Lux AI
opponent-pool lesson, and it is also why the snapshot is frozen and refreshed on
a delay rather than being the live weights.

OPPONENT POOL, not pure self-play. Lux AI's lesson, and it matches the local
evidence: our pool of reference agents differs in style, and an agent tuned
against one family transfers badly. Snapshots of the training policy are added
to the pool as it improves, so it does not overfit to the newest version of
itself.

Rollouts are CPU (26 cores, ~37k games/hour); the GPU only does the update. The
nets are small enough that per-decision inference is ~1 ms, so batching them
onto a GPU would need a vectorised environment -- a rewrite with a fidelity risk
this project has repeatedly paid for.
"""
import os as _os
# BLAS THREADS MUST BE PINNED TO 1 BEFORE numpy/torch IS IMPORTED. Each rollout
# worker runs 4286x256 matmuls and OpenBLAS spawns a thread pool inside every
# one of the 26 processes. Measured: load average 583 on 52 logical cores, each
# worker at 220-270% CPU, and 119s an iteration against the ~19s the same work
# needs single-threaded -- the processes were thrashing, not working.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    _os.environ.setdefault(_v, "1")

import json
import math
import multiprocessing as mp
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") not in
               (_HERE, os.path.join(ROOT, "dynamic"))]
sys.path.insert(0, ROOT)

import torch                                        # noqa: E402
import torch.nn.functional as F                     # noqa: E402

from dynamic.rl import policy_api as PA             # noqa: E402
from dynamic.rl.net import (DailyNet, SellNet, NumpyPolicy, export_numpy,     # noqa: E402
                            n_params, to_numpy_weights)
from dynamic.rl.linear_policy import (DEFAULT_INTERACTIONS,                   # noqa: E402
                                      LinearDailyNet, LinearSellNet,
                                      NumpyWhiteBox, whitebox_weights)

AGENT = os.path.join(ROOT, "dynamic", "rl", "agent_rl.py")
CKPT_DIR = os.path.join(ROOT, "logs", "rl")
PHI_SCALE = 60000.0      # bank difference at which the potential saturates
SHAPE_BETA = 1.0         # weight on the potential term
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
_cache = {}


def _base_genome():
    from route.search import to_params
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome3.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1
    p["SHED_PANIC_FRACTION"] = 0.40      # HANDOFF section 31
    return p


def _load_agent(genome, policy, tag):
    import importlib.util
    spec = importlib.util.spec_from_file_location(tag, AGENT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.configure(genome)
    m.set_policy(policy)
    return m.agent


def _load_opp(name):
    if name not in _cache:
        import importlib.util
        p = os.path.join(ROOT, "opponents", f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"opp_{name}", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _cache[name] = getattr(m, "_submission_entry", None) or m.agent
    return _cache[name]


_W = {}
_RUNGDIR = os.path.join(ROOT, "opponents", "rungs")
# THE LADDER HAS A TOP, AND ABOVE IT A WALL. Handicapping by action dropout
# grades our own scheduler smoothly (-160k to -51k over seven rungs) because it
# re-plans from the observed board every day -- a dropped action just means one
# tile goes unserviced and tomorrow re-sorts it.
#
# It does NOT grade anything schedule-rigid. Measured against their own
# unhandicapped selves, dropping just 5% of actions costs the kawa tape
# -149,914, frontier -152,878, 3000-socre -157,758 and strong-barnyard
# -132,578, and raising the rate to 50% barely changes that. It is a step, not
# a gradient: a fixed 719-step schedule desynchronises downstream from any
# perturbation, which is HANDOFF sections 4 and 11 arriving from a new angle.
#
# And the strong builds do not grade each OTHER either. Over 8 seeds x both
# seats they sit between -61,628 and -71,875 with us winning 0 or 1 of 8 against
# every one, so ordering them is ordering noise.
#
# So: seven graded rungs up to our own scheduler, then the full set of real
# opponents as one final tier. Training against all of them beats training
# against six, even though the tier cannot be climbed a step at a time.
FINAL_TIER = [p for p in (
    "submission/main.py", "deliver/ALT_struct.py",
    "opponents/kaggriculture-multi-route-farming-agent.py",
    "opponents/v111-8c4s-economic-core-premium-lead.py",
    "opponents/kaggriculture-frontier-the-soil-remembers-rain.py",
    "opponents/kaggriculture-3000-socre.py",
    "opponents/kaggriculture-rank-your-agent.py",
    "opponents/strong-barnyard-economist.py",
) if os.path.exists(os.path.join(ROOT, p))]

LADDER = ([os.path.join("rungs", f[:-3]) for f in
           sorted(os.listdir(_RUNGDIR))
           if f.startswith("rung_") and f.endswith(".py")]
          if os.path.isdir(_RUNGDIR) else [])


def _rung_name(i):
    """Name the rung, or say GRADUATED.

    rung == len(LADDER) means the graded ladder is cleared and the opponent is
    drawn from FINAL_TIER instead, so there is no LADDER entry to name.
    Indexing it crashed the run at exactly the moment it succeeded -- iter 69,
    rung 6, self-play 57.1% and pool 78.7% -- and the supervisor then restarted
    from the checkpoint with the curriculum reset to the bottom.
    """
    if i < len(LADDER):
        return os.path.basename(LADDER[i])
    return f"GRADUATED -> FINAL TIER, {len(FINAL_TIER)} full-strength builds"


def _worker_init(weights, snapshot, kind="mlp"):
    # Workers run the NUMPY forward, not torch: measured 1,917 us against 25 us
    # for a SellNet call, because torch pays a Python dispatch and a kernel
    # launch per op on 128-element tensors. Over a game that is 2.72 s against
    # 1.87 s, and it is the same code path the submission has to use anyway.
    _W["weights"] = weights
    _W["snapshot"] = snapshot
    _W["kind"] = kind
    _W["genome"] = _base_genome()


# Workers re-import this module; torch's intra-op pool must be 1 there too.
torch.set_num_threads(1)

def _mkpol(weights, seed):
    """One policy object from whatever the run is training."""
    if _W.get("kind") == "linear":
        dw, sw, nd, ns, idx = weights
        return NumpyWhiteBox(dw, sw, nd, ns, idx, explore=True, seed=seed)
    return NumpyPolicy(weights, explore=True, seed=seed)


def rollout(job):
    """One PAIRED episode: the same seed from both seats. Returns the two
    trajectories and the paired outcome."""
    seed, opp_name, wid = job
    from planner.simulate import Simulator
    out = []
    margins = []
    shapes = []
    try:
        for seat in (0, 1):
            pol = _mkpol(_W["weights"], (seed * 7 + seat * 13 + wid) & 0x7fffffff)
            me = _load_agent(_W["genome"], pol, f"rl_{os.getpid()}_{seat}")
            if opp_name == "__self__":
                opp_pol = _mkpol(_W["snapshot"],
                                 (seed * 11 + seat * 17 + wid) & 0x7fffffff)
                op = _load_agent(_W["genome"], opp_pol, f"rlopp_{os.getpid()}_{seat}")
            else:
                op = _load_opp(opp_name)
            pair = [me, op] if seat == 0 else [op, me]
            sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
            # Stepped rather than run_episode, to sample the bank difference once
            # a day. That is the potential the dense shaping is built from, and
            # a day is the right granularity: both heads decide once a day now,
            # so every decision gets its own shaping term.
            from planner.simulate import _agent_caller
            c0, c1 = _agent_caller(pair[0]), _agent_caller(pair[1])
            phis = []
            while sim.step < 719:
                a0 = c0(sim.observation_for(0), sim.cfg)
                a1 = c1(sim.observation_for(1), sim.cfg)
                sim.step_actions(a0, a1)
                if sim.step % 24 == 0:
                    b0, b1 = sim.farms[0]["money"], sim.farms[1]["money"]
                    d = (b0 - b1) if seat == 0 else (b1 - b0)
                    phis.append(math.tanh(d / PHI_SCALE))
            m0, m1 = sim.farms[0]["money"], sim.farms[1]["money"]
            us, them = (m0, m1) if seat == 0 else (m1, m0)
            margins.append(us - them)
            out.append(pol.traj)
            shapes.append(phis)
    except Exception:
        import traceback
        return None, traceback.format_exc()[-200:]
    paired = margins[0] + margins[1]
    # THE REWARD MUST HAVE VARIANCE, and the first version did not. It was
    #     r = sign(paired) + 0.25 * clamp(paired / 60000)
    # and against this opponent pool the agent loses every paired episode while
    # margins run near -76,000, so BOTH terms pinned: the sign at -1 and the
    # clamp at -1. Every episode returned exactly -1.25, advantages normalised
    # to zero, and PPO learned nothing -- 0.0% win rate over three iterations
    # was not a hard problem, it was no gradient at all.
    #
    # tanh keeps the margin term informative at any scale, and the divisor is
    # taken from the spread actually observed rather than guessed.
    r = (1.0 if paired > 0 else -1.0 if paired < 0 else 0.0)
    r += 0.75 * math.tanh(paired / 120000.0)
    return (out, r, paired, opp_name == "__self__", shapes), None


def _flatten(trajs, reward, gamma=0.999, lam=0.95, shaping=None, beta=SHAPE_BETA):
    """GAE per head, with POTENTIAL-BASED dense shaping.

    The terminal reward alone gives one informative signal per episode shared by
    every decision in it, which is the measured bottleneck: tighten the KL leash
    and the policy never moves, loosen it and it walks off a tuned strategy
    along a gradient that is mostly noise.

    Shaping fixes the density, but an arbitrary dense bonus changes what the
    optimal policy IS -- the agent starts maximising the proxy. A POTENTIAL
    function does not (Ng, Harada & Russell 1999):

        F(s, s') = gamma * Phi(s') - Phi(s)

    telescopes over the episode, so the return changes by a constant and the
    argmax is provably unchanged. Phi here is tanh of the bank difference, which
    is the quantity the terminal reward already scores, so the dense term is a
    smoothed early view of the same objective rather than a different one.

    Deliberately NOT in Phi: asset value and held stock. The shed caps at 100
    items and discards the overflow, and holding stock for price measured
    -32,749 -- rewarding inventory would teach exactly the behaviour that was
    already refuted.
    """
    batches = {"daily": [], "sell": []}
    for ti, traj in enumerate(trajs):
        phis = (shaping or [])[ti] if shaping and ti < len(shaping) else []
        for key in ("daily", "sell"):
            seq = traj[key]
            if not seq:
                continue
            vals = [t[3] for t in seq] + [0.0]
            # map decision index onto the per-day potential samples
            def phi(i, n=len(seq), P=phis):
                if not P:
                    return 0.0
                return P[min(len(P) - 1, int(i * len(P) / max(1, n)))]
            adv, gae = [0.0] * len(seq), 0.0
            for i in reversed(range(len(seq))):
                r = reward if i == len(seq) - 1 else 0.0
                if beta and phis:
                    nxt = phi(i + 1) if i + 1 < len(seq) else phi(len(seq) - 1)
                    r += beta * (gamma * nxt - phi(i))
                delta = r + gamma * vals[i + 1] - vals[i]
                gae = delta + gamma * lam * gae
                adv[i] = gae
            for i, t in enumerate(seq):
                batches[key].append((t[0], t[1], t[2], adv[i], adv[i] + vals[i]))
    return batches


def ppo_update(dnet, snet, opt, batches, device, clip=0.2, epochs=3,
               vf=0.5, ent=0.001, mb=4096, kl=0.05, ref=None):
    """PPO, with a KL leash back to the INITIAL policy.

    The policy is initialised to the scheduler identity, which is a tuned
    strategy, not a blank slate. Two forces were pulling it off that point
    faster than the reward could justify:

      ENTROPY. At the identity the sell head has 0.052 nats against a uniform
      1.386, so -ent*H is a large constant gradient pushing p(identity) down,
      and one paired reward spread over 749 decisions cannot oppose it.
      Measured: win rate fell 32.3% -> 19.8% -> 12.5% over three iterations,
      about 4 sigma, monotone. Coefficient cut 0.01 -> 0.001.

      VALUE LOSS. The value head shares the trunk and starts at zero against
      returns near -0.5, so early value gradients reshape the very features the
      policy needs. vf 0.5 -> 0.25.

    The KL term makes the prior explicit rather than implicit: deviate from the
    scheduler only where the advantage pays for it. `ref` is a frozen copy of
    the initial nets.
    """
    stats = {"d_loss": 0.0, "s_loss": 0.0, "n": 0, "p_identity": 0.0, "n_id": 0}
    for key, net in (("daily", dnet), ("sell", snet)):
        data = batches[key]
        if not data:
            continue
        obs = torch.tensor([d[0] for d in data], dtype=torch.float32, device=device)
        oldlp = torch.tensor([d[2] for d in data], dtype=torch.float32, device=device)
        adv = torch.tensor([d[3] for d in data], dtype=torch.float32, device=device)
        ret = torch.tensor([d[4] for d in data], dtype=torch.float32, device=device)
        adv = (adv - adv.mean()) / (adv.std() + 1e-6)
        if key == "daily":
            acts = {k: torch.tensor([d[1][k] for d in data], device=device)
                    for k in PA.DAILY_HEADS}
        else:
            acts = torch.tensor([d[1] for d in data], device=device)
        n = len(data)
        for _ in range(epochs):
            perm = torch.randperm(n, device=device)
            for i in range(0, n, mb):
                idx = perm[i:i + mb]
                if key == "daily":
                    logits, v = net(obs[idx])
                    lp = 0.0
                    entropy = 0.0
                    for k in PA.DAILY_HEADS:
                        ls = F.log_softmax(logits[k], dim=-1)
                        lp = lp + ls.gather(1, acts[k][idx, None]).squeeze(1)
                        entropy = entropy + -(ls.exp() * ls).sum(-1).mean()
                else:
                    logits, v = net(obs[idx])
                    ls = F.log_softmax(logits, dim=-1)
                    lp = ls.gather(2, acts[idx].unsqueeze(-1)).squeeze(-1).sum(-1)
                    entropy = -(ls.exp() * ls).sum(-1).mean()
                    # How much probability still sits on "do what the scheduler
                    # would have done"? This is the number that showed the
                    # policy being pulled off its initialisation.
                    stats["p_identity"] += float(
                        ls[..., PA.SELL_LEVELS.index(1.0)].exp().mean())
                    stats["n_id"] += 1
                kl_pen = 0.0
                if ref is not None and kl > 0.0:
                    with torch.no_grad():
                        rlog, _ = (ref[0] if key == "daily" else ref[1])(obs[idx])
                    if key == "daily":
                        for k in PA.DAILY_HEADS:
                            q = F.log_softmax(rlog[k], dim=-1)
                            kl_pen = kl_pen + F.kl_div(
                                F.log_softmax(logits[k], dim=-1), q,
                                log_target=True, reduction="batchmean")
                    else:
                        q = F.log_softmax(rlog, dim=-1)
                        kl_pen = kl_pen + F.kl_div(
                            F.log_softmax(logits, dim=-1), q,
                            log_target=True, reduction="batchmean")
                ratio = (lp - oldlp[idx]).exp()
                a = adv[idx]
                pl = -torch.min(ratio * a,
                                ratio.clamp(1 - clip, 1 + clip) * a).mean()
                vl = F.mse_loss(v, ret[idx])
                loss = pl + vf * vl - ent * entropy + kl * kl_pen
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
                stats[f"{key[0]}_loss"] += float(loss)
                stats["n"] += 1
    return stats


def main():
    torch.set_num_threads(8)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=10000)
    ap.add_argument("--episodes", type=int, default=192)   # paired episodes/iter
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--ent", type=float, default=0.001)
    ap.add_argument("--curriculum", type=float, default=0.7,
                    help="share of non-self-play episodes drawn from the rung ladder")
    ap.add_argument("--advance_at", type=float, default=60.0,
                    help="pool win rate over --smooth iters that promotes a rung")
    ap.add_argument("--policy", choices=("mlp", "linear"), default="linear",
                    help="linear = white-box: every coefficient is a named rule")
    ap.add_argument("--save_every", type=int, default=20)
    ap.add_argument("--id_logit", type=float, default=6.0,
                    help="strength of the identity prior at init; 6.0 puts",
                    )
    ap.add_argument("--smooth", type=int, default=10)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--vf", type=float, default=0.25)
    ap.add_argument("--kl", type=float, default=0.05,
                    help="KL leash back to the scheduler-identity init")
    ap.add_argument("--self_play", type=float, default=0.6,
                    help="fraction of episodes played against a frozen self")
    ap.add_argument("--snapshot_every", type=int, default=10)
    ap.add_argument("--snapshot_keep", type=int, default=5)
    args = ap.parse_args()

    os.makedirs(CKPT_DIR, exist_ok=True)
    # A 6,259-coefficient policy belongs on the CPU. The update is a handful of
    # small matmuls and a GPU kernel launch costs more than the arithmetic --
    # the same effect that made torch 77x slower than numpy for these nets.
    # The MLP is large enough for the GPU to pay; the white-box one is not.
    device = ("cpu" if args.policy == "linear"
              else ("cuda" if torch.cuda.is_available() else "cpu"))
    if args.policy == "linear":
        dnet, snet = LinearDailyNet(), LinearSellNet(interactions=DEFAULT_INTERACTIONS)
        # The identity prior is a HYPERPARAMETER, not a constant. At logit 6.0 it
        # puts 99.3% of the probability on "do what the scheduler would do", and
        # measured over 706 iterations the policy never left: p_id stayed
        # 0.990-0.993 at every rung. The tight prior and tight KL were both
        # chosen for a 2.5M-parameter MLP that walked off a tuned strategy along
        # a noisy gradient. With 6,259 coefficients that risk is three orders of
        # magnitude smaller, so the leash can be loosened.
        dnet.init_identity(args.id_logit)
        snet.init_identity(args.id_logit)
    else:
        dnet, snet = DailyNet(), SellNet()
    dnet, snet = dnet.to(device), snet.to(device)
    opt = torch.optim.Adam(list(dnet.parameters()) + list(snet.parameters()),
                           lr=args.lr)
    print(f"params {n_params(dnet, snet):,}  device {device}  "
          f"{args.episodes} paired episodes/iter x {args.workers} workers",
          flush=True)

    rng = random.Random(20260820)
    t0 = time.time()
    log = open(os.path.join(CKPT_DIR, "train.log"), "a")
    best = -9e9
    recent = []
    rung, pool_hist = [0], []
    snapshots = []
    # Frozen copy of the identity init: the prior the KL term pulls back to.
    import copy as _copy
    dref, sref = _copy.deepcopy(dnet).eval(), _copy.deepcopy(snet).eval()
    for _pp in list(dref.parameters()) + list(sref.parameters()):
        _pp.requires_grad_(False)

    _lat = os.path.join(CKPT_DIR, "latest.pt")
    if getattr(args, "resume", False) and os.path.exists(_lat):
        _ck = torch.load(_lat, map_location=device, weights_only=False)
        dnet.load_state_dict(_ck["daily"])
        snet.load_state_dict(_ck["sell"])
        if "opt" in _ck:
            opt.load_state_dict(_ck["opt"])
        best = float(_ck.get("best", -9e9))
        # The curriculum position must survive a restart too, or the
        # supervisor keeps the weights and throws away the rung, re-climbing a
        # ladder the agent has already cleared.
        rung[0] = int(_ck.get("rung", 0))
        print("resumed from iter %d (best %.1f%%, rung %d)"
              % (_ck.get("iter", 0), best, rung[0]), flush=True)
    for it in range(args.iters):
        if time.time() - t0 > args.hours * 3600:
            print("time budget reached", flush=True)
            break
        if args.policy == "linear":
            _dw, _sw = whitebox_weights(dnet, snet)
            weights = (_dw, _sw, dnet.names, snet.names, snet.idx)
        else:
            weights = to_numpy_weights(dnet, snet)
        # A frozen self from a few iterations back. Refreshed on a delay so the
        # opponent is a fixed target within an iteration rather than a moving
        # one, which is what keeps self-play from chasing its own tail.
        if it % args.snapshot_every == 0 or not snapshots:
            import copy as _cp
            snapshots.append(_cp.deepcopy(weights))
            del snapshots[:-args.snapshot_keep]
        snapshot = snapshots[rng.randrange(len(snapshots))]
        def _pick_opp():
            # CURRICULUM. Grading every agent on disk found 115 of 117 beating us
            # 95%+ of the time and exactly TWO in the 20-80% band, so the ladder
            # has no bottom and one had to be built: handicap.py wraps a strong
            # agent in action dropout, which is smooth and monotone in eps and
            # keeps the SHAPE of competent play at every rung.
            #
            # The rung advances on the POOL win rate, not the blended one -- the
            # self-play share is what made a blended number unreadable.
            if rng.random() < args.self_play:
                return "__self__"
            if LADDER and rng.random() < args.curriculum:
                if rung[0] < len(LADDER):
                    return LADDER[rung[0]]
                # past the graded rungs: everything strong we have, including
                # our own submitted and historical builds
                return rng.choice(FINAL_TIER or POOL)
            return rng.choice(POOL)
        jobs = [(rng.randrange(10 ** 6, 2 ** 31 - 1), _pick_opp(), w)
                for w in range(args.episodes)]
        with mp.get_context("forkserver").Pool(
                args.workers, initializer=_worker_init,
                initargs=(weights, snapshot, args.policy)) as pool:
            res = pool.map(rollout, jobs, chunksize=1)
        errs = [e for _, e in res if e]
        good = [r for r, e in res if e is None]
        if not good:
            print(f"iter {it}: all rollouts failed; first {errs[0]}", flush=True)
            break
        batches = {"daily": [], "sell": []}
        rewards, paireds = [], []
        # SEPARATE THE TWO OPPONENT KINDS. Mixed together they are unreadable:
        # a frozen identity policy scores 0.6*50% + 0.4*0% = 30% overall and
        # 0.6*0 + 0.4*(-68,847) = -27,539 paired, which is exactly what 150
        # iterations of "learning nothing" looked like. Worse, the self-play
        # share varies by +-5 episodes a batch (sd = sqrt(96*0.6*0.4) = 4.8), and
        # that alone swings the blended win rate several points -- which is what
        # produced a spurious t=+3.94 "UP" reading.
        #
        # Split out, the question is direct: self-play win rate above 50% means
        # the policy beats the frozen snapshot of itself, i.e. it is improving.
        sp_res, pool_res = [], []
        for trajs, r, paired, is_self, shapes in good:
            b = _flatten(trajs, r, shaping=shapes)
            batches["daily"] += b["daily"]
            batches["sell"] += b["sell"]
            rewards.append(r)
            paireds.append(paired)
            (sp_res if is_self else pool_res).append(paired)
        stats = ppo_update(dnet, snet, opt, batches, device,
                           vf=args.vf, ent=args.ent, kl=args.kl,
                           ref=(dref, sref))
        wins = sum(1 for p in paireds if p > 0)
        wr = 100.0 * wins / len(paireds)
        sp_wr = (100.0 * sum(1 for p in sp_res if p > 0) / len(sp_res)
                 if sp_res else float("nan"))
        pool_wr = (100.0 * sum(1 for p in pool_res if p > 0) / len(pool_res)
                   if pool_res else float("nan"))
        line = (f"iter {it:>5} winrate {wr:>5.1f}%  paired {statistics.mean(paireds):>+9,.0f}  "
                f"reward {statistics.mean(rewards):>+5.2f}  "
                f"selfwr {sp_wr:>5.1f}%  poolwr {pool_wr:>5.1f}%  "
                f"rung {rung[0]}  "
                f"p_id {stats['p_identity'] / max(1, stats['n_id']):.3f}  "
                f"samples d{len(batches['daily']):,}/s{len(batches['sell']):,}  "
                f"{len(errs)} err  {time.time()-t0:.0f}s")
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
        # BEST IS ON A MOVING AVERAGE, not a single iteration. Win rate over 96
        # paired episodes has se ~5pp, so scoring on one iteration locks 'best'
        # onto whichever early iteration got lucky and then never beats it.
        # promote when the current rung is comfortably beaten, demote if buried
        if pool_wr == pool_wr:
            pool_hist.append(pool_wr)
            del pool_hist[:-args.smooth]
        if len(pool_hist) >= args.smooth:
            m = statistics.mean(pool_hist)
            if m >= args.advance_at and rung[0] < len(LADDER):
                rung[0] += 1
                pool_hist.clear()
                print(f"  -> promoted to rung {rung[0]} "
                      f"({_rung_name(rung[0])})", flush=True)
            elif m < 10.0 and rung[0] > 0:
                rung[0] -= 1
                pool_hist.clear()
                print(f"  -> demoted to rung {rung[0]}", flush=True)
        recent.append(wr)
        del recent[:-args.smooth]
        smooth = statistics.mean(recent)

        def _save(tag):
            torch.save({"daily": dnet.state_dict(), "sell": snet.state_dict(),
                        "opt": opt.state_dict(), "iter": it, "winrate": wr,
                        "smooth": smooth, "best": best, "rung": rung[0]},
                       os.path.join(CKPT_DIR, tag + ".pt"))
            export_numpy(dnet.cpu(), snet.cpu(),
                         os.path.join(CKPT_DIR, tag + ".npz"))
            dnet.to(device)
            snet.to(device)

        if len(recent) >= args.smooth and smooth > best:
            best = smooth
            _save("best")
        # An unattended run must not lose ten hours to a crash at hour ten, and
        # it must be resumable, so 'latest' lands on a fixed cadence whatever
        # the score is doing.
        if it % args.save_every == 0:
            _save("latest")


if __name__ == "__main__":
    main()
