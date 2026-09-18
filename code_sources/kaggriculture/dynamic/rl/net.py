"""Policy and value networks, and the numpy export path for a submission.

TWO NETWORKS, matching the two decision cadences in `policy_api.py`:

  DailyNet  4,286 -> strategic heads (crop preference, crew delta, buy land,
            animal) plus a value head. Runs 30 times a game.
  SellNet   86 -> one 4-way head per product (offer 0 / 25 / 50 / 100% of
            holdings) plus its own value head. Runs every turn, so it is kept
            deliberately tiny.

The board goes in as a flat vector rather than through convolutions. The farm is
10x10 and the decisions here are economic rather than spatial -- which crop,
how many hands, whether to sell -- and the spatial part of the problem (which
tile a unit walks to) is already solved by the router, which the policy does not
touch. A conv tower would spend parameters on structure the scheduler handles.

INITIALISED TO THE IDENTITY, which is the whole design. A randomly initialised
policy overwrites a heavily tuned scheduler and starts ~70,000 paired margin
BELOW it (measured: -143,838 against the scheduler's -73,390, 0.0% win rate), so
it has to climb all the way back before it can add anything. Instead every head
is zero-initialised with its bias pointed at the action that means "do what the
scheduler would have done":

  crop_pref   a UNIFORM softmax already gives weight 1.0 per crop, which
              multiplies the allocator's ENPV by one -- so zero weights and zero
              bias is exactly the identity.
  crew_delta  index of 0 in CREW_DELTAS.
  sell        index of 1.0 in SELL_LEVELS, i.e. offer the scheduler's own qty.

At init the policy is byte-identical to `agent4`, verified by an identity A/B
that must return exactly +0. Training then starts AT the baseline rather than
below it, and can only add -- the same additive shape that is the only thing
that has produced a confirmed gain in this project.

SIZE IS A SHIPPING CONSTRAINT, not a taste. The submission carries its weights,
so the target is single-digit MB: at the default widths this is ~1.4M
parameters, about 2.8 MB in fp16. `export_numpy` writes exactly the arrays the
stdlib/numpy inference path needs, so nothing torch-shaped reaches Kaggle.
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from dynamic.rl import policy_api as PA


def _mlp(sizes, act=nn.GELU):
    layers = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(act())
    return nn.Sequential(*layers)


class DailyNet(nn.Module):
    """Strategic head: once a day, full observation.

    The value function gets its OWN trunk. Sharing one made the value loss
    reshape the very features the policy depends on: the value head starts at
    zero against returns near -0.5, so its early gradients are large, and vf had
    to be cut 0.5 -> 0.25 to keep the policy stable at all. Separate trunks cost
    ~1.2M parameters, which at fp16 is ~2.4 MB on a budget that has room, and
    remove the coupling entirely.
    """

    def __init__(self, obs=PA.DAILY_OBS, width=256, depth=3):
        super().__init__()
        self.trunk = _mlp([obs] + [width] * depth)
        self.norm = nn.LayerNorm(width)
        self.vtrunk = _mlp([obs] + [width] * depth)
        self.vnorm = nn.LayerNorm(width)
        self.heads = nn.ModuleDict({
            name: nn.Linear(width, n) for name, n in PA.DAILY_HEADS.items()})
        self.value = nn.Linear(width, 1)
        self.init_identity()

    def init_identity(self, logit=6.0):
        """Zero the heads and point each bias at the scheduler-identity action."""
        for name, head in self.heads.items():
            nn.init.zeros_(head.weight)
            nn.init.zeros_(head.bias)
            if name == "crew_delta":
                head.bias.data[PA.CREW_DELTAS.index(0)] = logit
            elif name == "buy_land":
                head.bias.data[0] = logit          # 0 == leave it to the agent
            elif name == "animal":
                head.bias.data[PA.ANIMAL_CHOICES.index(None)] = logit
            # crop_pref stays all-zero: a uniform softmax is weight 1.0, which
            # multiplies ENPV by one and is therefore already the identity.
        nn.init.zeros_(self.value.weight)
        nn.init.zeros_(self.value.bias)

    def forward(self, x):
        h = self.norm(F.gelu(self.trunk(x)))
        v = self.vnorm(F.gelu(self.vtrunk(x)))
        return {k: head(h) for k, head in self.heads.items()}, self.value(v).squeeze(-1)


class SellNet(nn.Module):
    """Sell head: every turn, market scalars only.

    This is the network that matters most. The branch it replaces offers 79% of
    all units we sell, and a single CONSTANT in it is worth 88.6% paired win
    rate (HANDOFF section 31) -- so a state-dependent policy here has the most
    headroom of any decision the scheduler makes.
    """

    def __init__(self, obs=PA.SELL_OBS, width=128, depth=2):
        super().__init__()
        self.trunk = _mlp([obs] + [width] * depth)
        self.norm = nn.LayerNorm(width)
        self.vtrunk = _mlp([obs] + [width] * depth)
        self.vnorm = nn.LayerNorm(width)
        self.head = nn.Linear(width, len(PA.PRODUCTS) * len(PA.SELL_LEVELS))
        self.value = nn.Linear(width, 1)
        self.init_identity()

    def init_identity(self, logit=6.0):
        """Offer the scheduler's own quantity (fraction 1.0) with probability ~1."""
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)
        full = PA.SELL_LEVELS.index(1.0)
        b = self.head.bias.data.view(len(PA.PRODUCTS), len(PA.SELL_LEVELS))
        b[:, full] = logit
        nn.init.zeros_(self.value.weight)
        nn.init.zeros_(self.value.bias)

    def forward(self, x):
        h = self.norm(F.gelu(self.trunk(x)))
        v = self.vnorm(F.gelu(self.vtrunk(x)))
        logits = self.head(h).view(*x.shape[:-1], len(PA.PRODUCTS),
                                   len(PA.SELL_LEVELS))
        return logits, self.value(v).squeeze(-1)


class TorchPolicy(PA.Policy):
    """Runs both nets on CPU inside a rollout worker.

    `explore=True` samples and records log-probs for PPO; `explore=False` takes
    the argmax, which is what an evaluation or a submission does.
    """

    def __init__(self, daily: DailyNet, sell: SellNet, explore=True, seed=0):
        self.dnet, self.snet = daily, sell
        self.explore = explore
        self.gen = torch.Generator().manual_seed(seed)
        self.traj = {"daily": [], "sell": []}

    def reset(self):
        self.traj = {"daily": [], "sell": []}

    @torch.no_grad()
    def daily(self, obs_vec):
        x = torch.tensor(obs_vec, dtype=torch.float32)
        logits, v = self.dnet(x)
        picks, logps = {}, 0.0
        for name, lg in logits.items():
            p = F.softmax(lg, dim=-1)
            if self.explore:
                i = int(torch.multinomial(p, 1, generator=self.gen).item())
            else:
                i = int(torch.argmax(p).item())
            picks[name] = i
            logps = logps + float(torch.log(p[i] + 1e-9))
        self.traj["daily"].append((obs_vec, picks, logps, float(v)))
        crop_logits = logits["crop_pref"]
        w = F.softmax(crop_logits, dim=-1)
        return PA.Decision(
            crop_pref={c: float(w[i]) * len(PA.CROPS) for i, c in enumerate(PA.CROPS)},
            crew_delta=PA.CREW_DELTAS[picks["crew_delta"]],
            buy_land=bool(picks["buy_land"]),
            animal=PA.ANIMAL_CHOICES[picks["animal"]],
        )

    @torch.no_grad()
    def sell(self, market_vec, holdings):
        x = torch.tensor(market_vec, dtype=torch.float32)
        logits, v = self.snet(x)
        p = F.softmax(logits, dim=-1)
        if self.explore:
            idx = torch.multinomial(p, 1, generator=self.gen).squeeze(-1)
        else:
            idx = torch.argmax(p, dim=-1)
        lp = float(torch.log(p[torch.arange(len(PA.PRODUCTS)), idx] + 1e-9).sum())
        self.traj["sell"].append((market_vec, idx.tolist(), lp, float(v)))
        return {item: PA.SELL_LEVELS[int(idx[i])]
                for i, item in enumerate(PA.PRODUCTS)}


def n_params(*mods):
    return sum(p.numel() for m in mods for p in m.parameters())


def export_numpy(daily: DailyNet, sell: SellNet, path):
    """Write fp16 weights for the stdlib/numpy inference path.

    Kaggle runs the submission without torch, so the shipped agent reimplements
    the forward pass in numpy against exactly these arrays.
    """
    import numpy as np
    out = {}
    for tag, mod in (("d", daily), ("s", sell)):
        for k, v in mod.state_dict().items():
            out[f"{tag}.{k}"] = v.detach().cpu().numpy().astype(np.float16)
    np.savez_compressed(path, **out)
    return sum(a.nbytes for a in out.values())


# --------------------------------------------------------------- numpy path

class NumpyPolicy(PA.Policy):
    """The same forward pass in raw numpy, for rollouts AND for the submission.

    Measured: a SellNet forward costs 1,917 us under torch and 25 us here -- 77x
    -- because torch pays a Python dispatch and a kernel launch per op and these
    tensors are 128 elements wide. Over a game that is 1.409 s of policy
    overhead against 0.044 s, which roughly halves the cost of every rollout.

    It is also the path Kaggle needs: the submission runs without torch, so the
    shipped agent must reimplement the forward against exported arrays anyway.
    Using it in training too means the thing being trained is the thing being
    shipped, with no second implementation to diverge.
    """

    def __init__(self, weights, explore=True, seed=0):
        import numpy as np
        self.np = np
        W = {k: np.ascontiguousarray(v, dtype=np.float32)
             for k, v in weights.items()}
        # Pre-transpose and pre-bind. `h @ W.T` builds a non-contiguous view on
        # every call and every lookup was an f-string format in the hot path;
        # together those made a forward 5.3 ms instead of tens of microseconds.
        self.W = W
        self.L = {}
        for tag, depth in (("d", 3), ("s", 2)):
            self.L[tag] = [(np.ascontiguousarray(W[f"{tag}.trunk.{2 * i}.weight"].T),
                            W[f"{tag}.trunk.{2 * i}.bias"]) for i in range(depth)]
            self.L[tag + "_norm"] = (W[f"{tag}.norm.weight"], W[f"{tag}.norm.bias"])
            # value trunk; only needed to reproduce the value output, but kept so
            # the numpy path stays a faithful mirror of the torch one.
            if f"{tag}.vtrunk.0.weight" in W:
                self.L[tag + "_v"] = [
                    (np.ascontiguousarray(W[f"{tag}.vtrunk.{2 * i}.weight"].T),
                     W[f"{tag}.vtrunk.{2 * i}.bias"]) for i in range(depth)]
                self.L[tag + "_vnorm"] = (W[f"{tag}.vnorm.weight"],
                                          W[f"{tag}.vnorm.bias"])
        self.explore = explore
        self.rng = np.random.default_rng(seed)
        self.traj = {"daily": [], "sell": []}

    def reset(self):
        self.traj = {"daily": [], "sell": []}

    def _gelu(self, h):
        return h * 0.5 * (1.0 + self.np.tanh(0.7978845608 * (h + 0.044715 * h ** 3)))

    def _trunk(self, x, tag, depth, which=""):
        h = x
        layers = self.L[tag + which]
        for i, (w, b) in enumerate(layers):
            h = h @ w + b
            if i < len(layers) - 1:
                h = self._gelu(h)
        h = self._gelu(h)
        g, be = self.L[tag + ("_vnorm" if which == "_v" else "_norm")]
        m, v = h.mean(-1, keepdims=True), h.var(-1, keepdims=True)
        return (h - m) / self.np.sqrt(v + 1e-5) * g + be

    def _softmax(self, z):
        z = z - z.max(-1, keepdims=True)
        e = self.np.exp(z)
        return e / e.sum(-1, keepdims=True)

    def _pick(self, p):
        if not self.explore:
            return int(p.argmax())
        return int(self.rng.choice(len(p), p=p / p.sum()))

    def daily(self, obs_vec):
        x = self.np.asarray(obs_vec, dtype=self.np.float32)
        h = self._trunk(x, "d", 3)
        picks, logp = {}, 0.0
        for name in PA.DAILY_HEADS:
            z = h @ self.W[f"d.heads.{name}.weight"].T + self.W[f"d.heads.{name}.bias"]
            p = self._softmax(z)
            i = self._pick(p)
            picks[name] = i
            logp += float(self.np.log(p[i] + 1e-9))
        hv = self._trunk(x, "d", 3, "_v") if "d_v" in self.L else h
        v = float((hv @ self.W["d.value.weight"].T + self.W["d.value.bias"])[0])
        self.traj["daily"].append((obs_vec, picks, logp, v))
        zc = h @ self.W["d.heads.crop_pref.weight"].T + self.W["d.heads.crop_pref.bias"]
        w = self._softmax(zc)
        return PA.Decision(
            crop_pref={c: float(w[i]) * len(PA.CROPS) for i, c in enumerate(PA.CROPS)},
            crew_delta=PA.CREW_DELTAS[picks["crew_delta"]],
            buy_land=bool(picks["buy_land"]),
            animal=PA.ANIMAL_CHOICES[picks["animal"]],
        )

    def sell(self, market_vec, holdings):
        x = self.np.asarray(market_vec, dtype=self.np.float32)
        h = self._trunk(x, "s", 2)
        z = (h @ self.W["s.head.weight"].T + self.W["s.head.bias"]).reshape(
            len(PA.PRODUCTS), len(PA.SELL_LEVELS))
        p = self._softmax(z)
        idx, logp = [], 0.0
        for i in range(len(PA.PRODUCTS)):
            j = self._pick(p[i])
            idx.append(j)
            logp += float(self.np.log(p[i, j] + 1e-9))
        hv = self._trunk(x, "s", 2, "_v") if "s_v" in self.L else h
        v = float((hv @ self.W["s.value.weight"].T + self.W["s.value.bias"])[0])
        self.traj["sell"].append((market_vec, idx, logp, v))
        return {item: PA.SELL_LEVELS[idx[i]] for i, item in enumerate(PA.PRODUCTS)}


def to_numpy_weights(daily, sell):
    """state_dicts -> the flat float32 dict NumpyPolicy expects."""
    out = {}
    for tag, mod in (("d", daily), ("s", sell)):
        for k, v in mod.state_dict().items():
            out[f"{tag}.{k}"] = v.detach().cpu().numpy()
    return out
