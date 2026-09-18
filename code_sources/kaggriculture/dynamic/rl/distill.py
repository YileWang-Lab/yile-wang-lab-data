"""Distil the tape into the white-box policy's coefficients.

WHAT IS BEING CLONED, AND WHY IT IS NOT THE THING THAT FAILED. HANDOFF section
21 records behavioural cloning from this same tape reaching 92.8% action
accuracy and banking $288 against the tape's $89k, with a control proving the
network was right and the failure was covariate shift. That experiment cloned
RAW ACTIONS -- which tile, which op, 719 steps of a fixed trajectory over a
100-tile board -- so one drifted state put the learner somewhere the expert had
never been.

This clones DECISION CONDITIONS instead, at the scheduler's own decision points:

    crop_pref   which crop the tape planted that day
    crew_delta  how many hands it hired, relative to our scheduler's estimate
    buy_land    whether it bought a quadrant
    animal      which animal it placed
    sell_level  per product, what fraction of its holdings it put on the market

Thirty decisions a day over 122 named features, executed by OUR scheduler. The
learner cannot walk off the expert's trajectory the way an action-cloner does,
because the scheduler still decides where every unit walks and what it touches.

THE FIT. The policy is a linear softmax, so maximum likelihood is convex:

    max_{W,b}  sum_t  log pi(a*_t | x_t),    pi(a|x) = softmax(W x + b)

i.e. plain multinomial logistic regression. There is no local optimum to worry
about and the result is a table of coefficients, each of which reads as a rule.

WHAT IT IS FOR. It moves the RL starting point off the scheduler baseline and
toward the tape, which is 80,210 paired margin higher. RL then optimises from
there -- and because crop_pref MULTIPLIES the scheduler's ENPV rather than
replacing it, a distilled coefficient is a correction on top of the derived
value, never a competing answer to it.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

import torch                                            # noqa: E402
import torch.nn.functional as F                         # noqa: E402

from dynamic.opp_state import OppState                  # noqa: E402
from dynamic.rl import encode as E                      # noqa: E402
from dynamic.rl import policy_api as PA                 # noqa: E402
from dynamic.rl.linear_policy import (DEFAULT_INTERACTIONS,  # noqa: E402
                                      LinearDailyNet, LinearSellNet)
from route.opponent import OpponentModel                # noqa: E402

TAPE = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
POOL = ["v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
OUT = os.path.join(ROOT, "logs", "rl", "distilled.pt")
_n = [0]


def _load(path):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"ds_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def _nearest(value, options):
    return min(range(len(options)), key=lambda i: abs(options[i] - value))


def collect(seed, opp_name):
    """One game with the TAPE in seat 0. Returns per-day (features, labels)."""
    from planner.simulate import Simulator, _agent_caller
    me, op = _load(TAPE), _load(os.path.join(ROOT, "opponents", f"{opp_name}.py"))
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    c0, c1 = _agent_caller(me), _agent_caller(op)
    st, om = OppState(), OpponentModel()
    rows = []
    day_plant, day_hire, day_land, day_animal = {}, 0, 0, None
    day_sold, day_shed0 = {}, {}
    my_prev = {}

    while sim.step < 719:
        o = sim.observation_for(0)
        day, hour = o["day"], o["hour"]
        shops = tuple(o["town"].get("unlocked_shops", []))
        om.observe(dict(sim.market["inventory"]), sim.step, shops, my_prev)
        if om.recent and om.recent[-1][0] == sim.step:
            st.record_sales(om.recent[-1][1])
        opp_farm = o["farms"][1]
        st.observe(opp_farm, day, hour)
        st.reconcile(o["market"].get("prices") or {},
                     len(opp_farm.get("hands") or []))

        if hour == 0:
            priv = sim.privates[0]
            feats = E.encode_whitebox(o, o["farms"][0], priv, opp_farm, st, day, hour)
            scal = E.encode_scalars(o, o["farms"][0], priv, opp_farm, st, day, hour)
            day_shed0 = dict(priv.get("shed") or {})
            day_plant, day_hire, day_land, day_animal = {}, 0, 0, None
            day_sold = {}
            pending = (feats, scal, dict(day_shed0), len(o["farms"][0].get("hands") or []))

        a = c0(o, sim.cfg)
        # read the tape's decisions out of the actions it just issued
        if isinstance(a, dict):
            for unit in [a.get("farmer")] + list(a.get("hands") or []):
                if unit and unit[0] == "PLANT" and len(unit) > 1:
                    day_plant[unit[1]] = day_plant.get(unit[1], 0) + 1
                if unit and unit[0] == "PLACE" and len(unit) > 1:
                    day_animal = unit[1]
            my_prev = {}
            for act in a.get("market") or []:
                if not act:
                    continue
                if act[0] == "HIRE":
                    day_hire += 1
                elif act[0] == "BUY_LAND":
                    day_land = 1
                elif act[0] == "SELL":
                    day_sold[act[1]] = day_sold.get(act[1], 0) + int(act[2])
                    my_prev[act[1]] = my_prev.get(act[1], 0) + int(act[2])
        sim.step_actions(a, c1(sim.observation_for(1), sim.cfg))

        if hour == 23 and pending:
            feats, scal, shed0, n_hands = pending
            # crop_pref target: what it actually planted (uniform if nothing)
            tot = sum(day_plant.values())
            crop_t = ([day_plant.get(c, 0) / tot for c in PA.CROPS] if tot
                      else [1.0 / len(PA.CROPS)] * len(PA.CROPS))
            # crew_delta target: hires today vs the crew it already had
            delta = max(-3, min(3, day_hire - max(1, n_hands)))
            # A product the tape is not holding produces NO label. Marking an
            # empty shed as "sell 100%" is not a decision, it is the absence of
            # one, and it made 90.8% of all sell labels identical -- which is
            # why six products came out with byte-identical coefficients.
            sell_t, sell_m = [], []
            for item in PA.PRODUCTS:
                held = float(shed0.get(item, 0))
                if held <= 0:
                    sell_t.append(0)
                    sell_m.append(0.0)
                    continue
                frac = min(1.0, day_sold.get(item, 0) / held)
                sell_t.append(_nearest(frac, PA.SELL_LEVELS))
                sell_m.append(1.0)
            rows.append({"x": feats, "s": scal, "crop": crop_t,
                         "crew": PA.CREW_DELTAS.index(delta),
                         "land": int(bool(day_land)),
                         "animal": PA.ANIMAL_CHOICES.index(day_animal)
                                   if day_animal in PA.ANIMAL_CHOICES else 0,
                         "sell": sell_t, "sell_mask": sell_m})
            pending = None
    return rows


def fit(rows, epochs=400, lr=0.05, l2=1e-3, kl_to_identity=0.0):
    """Multinomial logistic regression -- convex, so plain gradient descent on
    the exact objective. L2 keeps coefficients small enough to stay readable."""
    dnet = LinearDailyNet()
    snet = LinearSellNet(interactions=DEFAULT_INTERACTIONS)
    X = torch.tensor([r["x"] for r in rows], dtype=torch.float32)
    S = torch.tensor([r["s"] for r in rows], dtype=torch.float32)
    crop = torch.tensor([r["crop"] for r in rows], dtype=torch.float32)
    crew = torch.tensor([r["crew"] for r in rows])
    land = torch.tensor([r["land"] for r in rows])
    animal = torch.tensor([r["animal"] for r in rows])
    sell = torch.tensor([r["sell"] for r in rows])
    smask = torch.tensor([r["sell_mask"] for r in rows], dtype=torch.float32)

    opt = torch.optim.Adam(list(dnet.parameters()) + list(snet.parameters()),
                           lr=lr, weight_decay=l2)
    for ep in range(epochs):
        opt.zero_grad()
        logits, _ = dnet(X)
        loss = (F.kl_div(F.log_softmax(logits["crop_pref"], -1), crop,
                         reduction="batchmean")
                + F.cross_entropy(logits["crew_delta"], crew)
                + F.cross_entropy(logits["buy_land"], land)
                + F.cross_entropy(logits["animal"], animal))
        slog, _ = snet(S)
        ce = F.cross_entropy(slog.reshape(-1, len(PA.SELL_LEVELS)),
                             sell.reshape(-1), reduction="none")
        loss = loss + (ce * smask.reshape(-1)).sum() / smask.sum().clamp(min=1)
        loss.backward()
        opt.step()
        if ep % 100 == 0:
            print(f"  epoch {ep:>4}  loss {float(loss):.4f}", flush=True)
    return dnet, snet, float(loss)


def accuracy(dnet, snet, rows):
    X = torch.tensor([r["x"] for r in rows], dtype=torch.float32)
    S = torch.tensor([r["s"] for r in rows], dtype=torch.float32)
    with torch.no_grad():
        lg, _ = dnet(X)
        sl, _ = snet(S)
    out = {}
    for key, field in (("crew_delta", "crew"), ("buy_land", "land"),
                       ("animal", "animal")):
        t = torch.tensor([r[field] for r in rows])
        out[key] = float((lg[key].argmax(-1) == t).float().mean())
    t = torch.tensor([r["sell"] for r in rows])
    m = torch.tensor([r["sell_mask"] for r in rows], dtype=torch.float32)
    hit = (sl.argmax(-1) == t).float() * m
    out["sell"] = float(hit.sum() / m.sum().clamp(min=1))
    crop = torch.tensor([r["crop"] for r in rows], dtype=torch.float32)
    out["crop_pref"] = float((lg["crop_pref"].argmax(-1)
                              == crop.argmax(-1)).float().mean())
    return out


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    import random
    rng = random.Random(4242)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    games = []
    for i, sd in enumerate(seeds):
        for opp in POOL:
            games.append(collect(sd, opp))
        print(f"  seed {i + 1}/{n_seeds}: {sum(len(g) for g in games):,} day-rows",
              flush=True)
    cut = int(len(games) * 0.75)
    train = [r for g in games[:cut] for r in g]
    test = [r for g in games[cut:] for r in g]
    print(f"\nfitting on {len(train):,} day-rows, holding out {len(test):,} "
          f"(split by GAME, never by row)")
    dnet, snet, loss = fit(train)
    # ACCURACY ALONE MEANS NOTHING ON IMBALANCED LABELS. The tape hires the same
    # amount almost every day and buys land twice a season, so predicting the
    # majority class scores 96.6% and 93.1%. Section 21's behavioural cloning
    # hit 92.8% action accuracy and banked $288. Always report the lift.
    import collections as _c
    acc = accuracy(dnet, snet, test)
    base = {}
    for key, field in (("crew_delta", "crew"), ("buy_land", "land"),
                       ("animal", "animal")):
        cc = _c.Counter(r[field] for r in test)
        base[key] = cc.most_common(1)[0][1] / len(test)
    cc = _c.Counter(r["crop"].index(max(r["crop"])) for r in test)
    base["crop_pref"] = cc.most_common(1)[0][1] / len(test)
    sc = _c.Counter(j for r in test for j, mm in zip(r["sell"], r["sell_mask"]) if mm)
    tot = sum(sc.values()) or 1
    base["sell"] = sc.most_common(1)[0][1] / tot
    print("\nheld-out agreement (masked where the tape held nothing):")
    print(f"  {'head':<12}{'model':>8}{'majority':>10}{'lift':>8}")
    for k, v in acc.items():
        print(f"  {k:<12}{100 * v:>7.1f}%{100 * base[k]:>9.1f}%"
              f"{100 * (v - base[k]):>+7.1f}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    torch.save({"daily": dnet.state_dict(), "sell": snet.state_dict(),
                "loss": loss, "n_train": len(train)}, OUT)
    print(f"\nwrote {OUT}")
    print("\n--- the distilled policy, as rules ---")
    print(dnet.explain("crop_pref", top=5))
    print(dnet.explain("crew_delta", top=4))
    print(snet.rules(top=4))


if __name__ == "__main__":
    main()
