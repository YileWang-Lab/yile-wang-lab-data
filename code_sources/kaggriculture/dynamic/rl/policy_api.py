"""The decision interface between the scheduler and a policy.

WHAT THE POLICY CONTROLS, AND WHY THESE
---------------------------------------
Not the 72 global parameters. Those are what the GA and coordinate descent
already search, and that space is measured to hold only small gains: 20 GA
generations produced nothing, and 94 single-parameter A/Bs produced no candidate
that replicated. Parameter search cannot reach the decisions below because they
are constants or hardcoded orderings in the current code, not tunable numbers.

  SELL      today: `shed_used > SHED_PANIC_FRACTION * 100` -> dump everything.
            One constant governs 79% of all units we sell. A policy that can see
            market inventory, the local price slope, the town's drain rate and
            the opponent's belief interval has vastly more to say here than a
            threshold does, and it is the single highest-volume decision.
  CROP      today: the ENPV argmax over feasible crops. Correct myopically, but
            blind to the fact that its own future plantings move the price.
  CREW      today: sized to the current task list, which is circular -- a small
            crew makes a small task list which justifies a small crew.
  BUY       today: a hardcoded product order, and land on a cash multiple.

TWO CADENCES, because encoding is not free. Measured: the full observation costs
0.29 ms, which at 720 steps a game would roughly double the cost of the game
itself. The strategic head runs ONCE A DAY on the full observation (30 calls a
game); the sell head runs every turn on the market scalars only (86 floats),
which is ~25x cheaper.

The interface is deliberately a plain object with numpy-free types so the same
agent file can run under a torch policy in training and a numpy policy in a
submission, with no branch in the scheduler itself.
"""

from dynamic.rl import encode as E

CROPS = E.CROPS
PRODUCTS = E.PRODUCTS
SELL_LEVELS = (0.0, 0.25, 0.5, 1.0)      # fraction of holdings to offer
CREW_DELTAS = (-3, -2, -1, 0, 1, 2, 3)   # relative to the scheduler's estimate
ANIMAL_CHOICES = (None, "COW", "SHEEP", "GOOSE")


class Decision:
    """One day's strategic answer, plus the sell policy used until the next."""

    __slots__ = ("crop_pref", "crew_delta", "buy_land", "animal", "sell_level")

    def __init__(self, crop_pref=None, crew_delta=0, buy_land=False,
                 animal=None, sell_level=None):
        # crop_pref: {crop: weight}; the allocator picks argmax(ENPV * weight)
        self.crop_pref = crop_pref or {c: 1.0 for c in CROPS}
        self.crew_delta = int(crew_delta)
        self.buy_land = bool(buy_land)
        self.animal = animal
        # sell_level: {product: fraction}, refreshed per turn by the sell head
        self.sell_level = sell_level or {p: 1.0 for p in PRODUCTS}


class Policy:
    """Base class. `daily` and `sell` are the only two entry points."""

    def daily(self, obs_vec):
        """obs_vec -> Decision (crop_pref / crew_delta / buy_land / animal)."""
        raise NotImplementedError

    def sell(self, market_vec, holdings):
        """market_vec + what we hold -> {product: fraction to offer now}."""
        raise NotImplementedError

    def reset(self):
        pass


class ScriptedPolicy(Policy):
    """The current scheduler's own behaviour, expressed through the interface.

    This is the identity control for the whole RL line: an agent driven by this
    policy must reproduce the unmodified scheduler exactly. If it does not, the
    interface is changing behaviour on its own and every later comparison is
    meaningless.
    """

    def daily(self, obs_vec):
        return Decision()

    def sell(self, market_vec, holdings):
        return {p: 1.0 for p in PRODUCTS}


class RandomPolicy(Policy):
    """Uniform over the action space. Used to measure rollout throughput and to
    give a floor: anything trained must beat random by a wide margin."""

    def __init__(self, seed=0):
        import random
        self.rng = random.Random(seed)

    def daily(self, obs_vec):
        return Decision(
            crop_pref={c: self.rng.random() for c in CROPS},
            crew_delta=self.rng.choice(CREW_DELTAS),
            buy_land=self.rng.random() < 0.1,
            animal=self.rng.choice(ANIMAL_CHOICES),
        )

    def sell(self, market_vec, holdings):
        return {p: self.rng.choice(SELL_LEVELS) for p in PRODUCTS}


def market_vector(obs, farm, private, opp_state, day, hour):
    """The compact observation for the per-turn sell head: the scalar block
    only, no board. 86 floats against the full 4,286."""
    return E.encode_scalars(obs, farm, private,
                            (obs.get("farms") or [None, None])[1 - obs.get("player", 0)],
                            opp_state, day, hour)


# Sizes a network needs to know up front.
DAILY_OBS = E.OBS_SIZE
SELL_OBS = E.SCALAR_SIZE
DAILY_HEADS = {
    "crop_pref": len(CROPS),          # softmax weights
    "crew_delta": len(CREW_DELTAS),   # categorical
    "buy_land": 2,                    # categorical
    "animal": len(ANIMAL_CHOICES),    # categorical
}
SELL_HEADS = {p: len(SELL_LEVELS) for p in PRODUCTS}
