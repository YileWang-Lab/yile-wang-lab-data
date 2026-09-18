"""A policy you can read, edit, and still train with PPO.

THE PROBLEM WITH THE MLP. A 2.5M-parameter network is a black box: no weight in
it answers "what does this agent do when cash runs low". If the requirement is
that every part of the agent stays inspectable and hand-editable, that network
fails it however well it scores.

THE OBSERVATION MAKES A WHITE-BOX POLICY FREE. The sell head already sees ONLY
the 86 named scalars from `encode.scalar_names()` -- cash, day, crew, shed fill,
and per product the inventory offset, price, local slope, town drain rate, our
holding, and the opponent belief interval. No raw board. So a linear-softmax
over those features is not a simplification of the input, only of the mapping,
and every coefficient reads directly:

    STRAWBERRY.opp_max  ->  sell 100%   +0.41
    "the more strawberry the opponent might still dump, the more we sell now"

which is the suppression rule from `market_model`, learned rather than asserted.

IT SHOULD ALSO TRAIN BETTER HERE. The measured bottleneck is variance, not
capacity: one terminal reward shared across an episode gives advantages that are
mostly noise, which froze the MLP under a tight KL leash and degraded it under a
loose one (self-play win rate 50.8% -> 32%). This has 86*9*4 = 3,096 coefficients
against 2.5M -- three orders of magnitude fewer directions for noise to push.

IT IS THE SAME PPO. `logits = W @ x + b` is differentiable, so the existing
update, KL leash and identity initialisation all apply unchanged. The identity
init is exact: W = 0 and b pointing at "offer the scheduler's own quantity"
reproduces the scheduler bit for bit, which is the acceptance test the MLP had
to pass too.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from dynamic.rl import encode as E
from dynamic.rl import policy_api as PA


class LinearSellNet(nn.Module):
    """One linear map from named features to per-product sell levels.

    Optionally a small set of hand-written INTERACTION features is appended --
    products of two named scalars -- so a genuinely non-linear rule like "sell
    when their belief upper bound is high AND the book is still above the floor"
    is expressible while every term keeps a readable name.
    """

    def __init__(self, obs=E.SCALAR_SIZE, interactions=()):
        super().__init__()
        self.names = list(E.scalar_names())
        self.inter = list(interactions)
        for a, b in self.inter:
            self.names.append(f"{a} x {b}")
        self.idx = [(self.names.index(a) if a in self.names[:obs] else 0,
                     self.names.index(b) if b in self.names[:obs] else 0)
                    for a, b in self.inter]
        n_in = obs + len(self.inter)
        self.n_in = n_in
        self.head = nn.Linear(n_in, len(PA.PRODUCTS) * len(PA.SELL_LEVELS))
        self.value = nn.Linear(n_in, 1)
        self.init_identity()

    def init_identity(self, logit=6.0):
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)
        b = self.head.bias.data.view(len(PA.PRODUCTS), len(PA.SELL_LEVELS))
        b[:, PA.SELL_LEVELS.index(1.0)] = logit
        nn.init.zeros_(self.value.weight)
        nn.init.zeros_(self.value.bias)

    def expand(self, x):
        if not self.idx:
            return x
        extra = [x[..., i:i + 1] * x[..., j:j + 1] for i, j in self.idx]
        return torch.cat([x] + extra, dim=-1)

    def forward(self, x):
        z = self.expand(x)
        logits = self.head(z).view(*x.shape[:-1], len(PA.PRODUCTS),
                                   len(PA.SELL_LEVELS))
        return logits, self.value(z).squeeze(-1)

    # ------------------------------------------------------------- readable
    def rules(self, top=6, min_abs=0.05):
        """The policy as text: for each product, the features that most move it
        toward selling more, and toward selling less."""
        W = self.head.weight.data.view(len(PA.PRODUCTS), len(PA.SELL_LEVELS),
                                       self.n_in)
        full = PA.SELL_LEVELS.index(1.0)
        none = PA.SELL_LEVELS.index(0.0)
        out = []
        for pi, item in enumerate(PA.PRODUCTS):
            # net pull toward "sell everything" versus "sell nothing"
            pull = (W[pi, full] - W[pi, none]).tolist()
            ranked = sorted(range(self.n_in), key=lambda i: -abs(pull[i]))
            lines = []
            for i in ranked[:top]:
                if abs(pull[i]) < min_abs:
                    break
                arrow = "sell MORE" if pull[i] > 0 else "sell LESS"
                lines.append(f"      {self.names[i]:<26} {pull[i]:+7.3f}  {arrow}")
            if lines:
                out.append(f"  {item}:")
                out.extend(lines)
        return "\n".join(out) if out else "  (still at the scheduler identity)"


# Interactions worth having available, each justified by the market model rather
# than guessed: suppression pays only where the opponent still has supply AND
# the book can still be pushed (slope > 0), and metering only matters while the
# town is refilling the book.
DEFAULT_INTERACTIONS = tuple(
    [(f"{p}.opp_max", f"{p}.slope") for p in PA.PRODUCTS]
    + [(f"{p}.we_hold", f"{p}.drain") for p in PA.PRODUCTS]
    + [("shed_fill", "day")]
)


class NumpyLinearPolicy(PA.Policy):
    """Inference side: pure numpy, so the submission needs no torch."""

    def __init__(self, weights, names, inter_idx, explore=True, seed=0,
                 daily=None):
        import numpy as np
        self.np = np
        self.W = {k: np.ascontiguousarray(v, dtype=np.float32)
                  for k, v in weights.items()}
        self.hw = np.ascontiguousarray(self.W["head.weight"].T)
        self.hb = self.W["head.bias"]
        self.vw = np.ascontiguousarray(self.W["value.weight"].T)
        self.vb = self.W["value.bias"]
        self.names = names
        self.idx = inter_idx
        self.explore = explore
        self.rng = np.random.default_rng(seed)
        self.daily_pol = daily
        self.traj = {"daily": [], "sell": []}

    def reset(self):
        self.traj = {"daily": [], "sell": []}
        if self.daily_pol is not None:
            self.daily_pol.reset()

    def daily(self, obs_vec):
        if self.daily_pol is None:
            return PA.Decision()
        d = self.daily_pol.daily(obs_vec)
        self.traj["daily"] = self.daily_pol.traj["daily"]
        return d

    def sell(self, market_vec, holdings):
        np = self.np
        x = np.asarray(market_vec, dtype=np.float32)
        if self.idx:
            x = np.concatenate([x, np.array([x[i] * x[j] for i, j in self.idx],
                                            dtype=np.float32)])
        z = (x @ self.hw + self.hb).reshape(len(PA.PRODUCTS),
                                            len(PA.SELL_LEVELS))
        z = z - z.max(-1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(-1, keepdims=True)
        idx, logp = [], 0.0
        for i in range(len(PA.PRODUCTS)):
            j = (int(self.rng.choice(len(p[i]), p=p[i] / p[i].sum()))
                 if self.explore else int(p[i].argmax()))
            idx.append(j)
            logp += float(np.log(p[i, j] + 1e-9))
        v = float((x @ self.vw + self.vb)[0])
        self.traj["sell"].append((market_vec, idx, logp, v))
        return {item: PA.SELL_LEVELS[idx[i]]
                for i, item in enumerate(PA.PRODUCTS)}


class LinearDailyNet(nn.Module):
    """The daily head, white-box.

        z_a = w_a . x + b_a          x in R^122, one weight per NAMED feature
        pi(a|x) = softmax_a(z_a)

    The 122 inputs are 36 board STATISTICS (counts per role for both players,
    mean growth stage per crop, weeds, empty tiles, watered fraction, mean
    distance to shed, quadrant densities) plus the 86 named scalars. The raw
    10x10xC planes are gone, which were the only reason this head could not be
    read -- the sell head was already scalar-only.

    Every coefficient is a rule: w[our.WHEAT, crop=STRAWBERRY] = +0.02 says one
    more wheat tile raises the strawberry logit by 0.02.
    """

    def __init__(self, obs=None):
        super().__init__()
        obs = obs or E.WHITEBOX_SIZE
        self.names = list(E.whitebox_names())
        self.n_in = obs
        self.heads = nn.ModuleDict({
            name: nn.Linear(obs, n) for name, n in PA.DAILY_HEADS.items()})
        self.value = nn.Linear(obs, 1)
        self.init_identity()

    def init_identity(self, logit=6.0):
        for name, head in self.heads.items():
            nn.init.zeros_(head.weight)
            nn.init.zeros_(head.bias)
            if name == "crew_delta":
                head.bias.data[PA.CREW_DELTAS.index(0)] = logit
            elif name == "buy_land":
                head.bias.data[0] = logit
            elif name == "animal":
                head.bias.data[PA.ANIMAL_CHOICES.index(None)] = logit
            # crop_pref stays all-zero: uniform softmax IS weight 1.0, the identity
        nn.init.zeros_(self.value.weight)
        nn.init.zeros_(self.value.bias)

    def forward(self, x):
        return ({k: h(x) for k, h in self.heads.items()},
                self.value(x).squeeze(-1))

    def explain(self, head="crop_pref", top=8, min_abs=0.01):
        """Print the weight table for one head, largest magnitude first."""
        W = self.heads[head].weight.data
        labels = (PA.CROPS if head == "crop_pref" else
                  [str(d) for d in PA.CREW_DELTAS] if head == "crew_delta" else
                  [str(a) for a in PA.ANIMAL_CHOICES] if head == "animal" else
                  ["no", "yes"])
        out = []
        for ai, lab in enumerate(labels[:W.shape[0]]):
            col = W[ai].tolist()
            ranked = sorted(range(self.n_in), key=lambda i: -abs(col[i]))
            lines = [f"      {self.names[i]:<26} {col[i]:+7.4f}"
                     for i in ranked[:top] if abs(col[i]) >= min_abs]
            if lines:
                out.append(f"  {head} -> {lab}:")
                out.extend(lines)
        return "\n".join(out) or f"  ({head} still at the identity)"


class NumpyWhiteBox(PA.Policy):
    """Both heads, pure numpy, white-box. This is what rollouts and the
    submission run: no torch, and every coefficient still has a name.

    WHITEBOX=True tells `agent_rl` to feed the 122 named features to the daily
    head instead of the 4,286-dim vector.
    """

    WHITEBOX = True

    def __init__(self, dw, sw, names_d, names_s, inter_idx, explore=True, seed=0):
        import numpy as np
        self.np = np
        self.dw = {k: np.ascontiguousarray(v, dtype=np.float32) for k, v in dw.items()}
        self.sw = {k: np.ascontiguousarray(v, dtype=np.float32) for k, v in sw.items()}
        self.dh = {k: (np.ascontiguousarray(self.dw[f"heads.{k}.weight"].T),
                       self.dw[f"heads.{k}.bias"]) for k in PA.DAILY_HEADS}
        self.dv = (np.ascontiguousarray(self.dw["value.weight"].T), self.dw["value.bias"])
        self.sh = (np.ascontiguousarray(self.sw["head.weight"].T), self.sw["head.bias"])
        self.sv = (np.ascontiguousarray(self.sw["value.weight"].T), self.sw["value.bias"])
        self.names_d, self.names_s, self.idx = names_d, names_s, inter_idx
        self.explore = explore
        self.rng = np.random.default_rng(seed)
        self.traj = {"daily": [], "sell": []}

    def reset(self):
        self.traj = {"daily": [], "sell": []}

    def _soft(self, z):
        z = z - z.max(-1, keepdims=True)
        e = self.np.exp(z)
        return e / e.sum(-1, keepdims=True)

    def _pick(self, p):
        if not self.explore:
            return int(p.argmax())
        return int(self.rng.choice(len(p), p=p / p.sum()))

    def daily(self, obs_vec):
        np = self.np
        x = np.asarray(obs_vec, dtype=np.float32)
        picks, logp, probs = {}, 0.0, {}
        for k in PA.DAILY_HEADS:
            w, b = self.dh[k]
            p = self._soft(x @ w + b)
            i = self._pick(p)
            picks[k] = i
            probs[k] = p
            logp += float(np.log(p[i] + 1e-9))
        w, b = self.dv
        v = float((x @ w + b)[0])
        self.traj["daily"].append((obs_vec, picks, logp, v))
        wq = probs["crop_pref"]
        return PA.Decision(
            crop_pref={c: float(wq[i]) * len(PA.CROPS) for i, c in enumerate(PA.CROPS)},
            crew_delta=PA.CREW_DELTAS[picks["crew_delta"]],
            buy_land=bool(picks["buy_land"]),
            animal=PA.ANIMAL_CHOICES[picks["animal"]])

    def sell(self, market_vec, holdings):
        np = self.np
        x = np.asarray(market_vec, dtype=np.float32)
        if self.idx:
            x = np.concatenate([x, np.array([x[i] * x[j] for i, j in self.idx],
                                            dtype=np.float32)])
        w, b = self.sh
        z = (x @ w + b).reshape(len(PA.PRODUCTS), len(PA.SELL_LEVELS))
        p = self._soft(z)
        idx, logp = [], 0.0
        for i in range(len(PA.PRODUCTS)):
            j = self._pick(p[i])
            idx.append(j)
            logp += float(np.log(p[i, j] + 1e-9))
        w, b = self.sv
        v = float((x @ w + b)[0])
        self.traj["sell"].append((market_vec, idx, logp, v))
        return {it: PA.SELL_LEVELS[idx[i]] for i, it in enumerate(PA.PRODUCTS)}


def whitebox_weights(dnet, snet):
    d = {k: v.detach().cpu().numpy() for k, v in dnet.state_dict().items()}
    s = {k: v.detach().cpu().numpy() for k, v in snet.state_dict().items()}
    return d, s
