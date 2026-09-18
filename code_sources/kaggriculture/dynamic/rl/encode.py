"""Observation encoding for the RL policy: spatial tensor + scalars + belief.

The policy sits ON TOP of the scheduler, so it never sees raw ops. It sees the
board and the market, and it answers a handful of decisions the scheduler then
executes. That keeps the action space tiny and keeps every piece of derived
economics we already have (exact price curve, exact opponent harvests, ENPV,
opportunity cost) as PRE-COMPUTED input rather than something a network has to
rediscover.

THREE BLOCKS
------------
SPATIAL  (2, H, W, C) -- our board and theirs, same channel layout. Channels are
    fixed-width and float, so this is one flat numpy array with no dict walking.

SCALARS  a 1D vector: normalised money, day, hour, crew, shed occupancy, plus
    per-product market inventory offset from I0, price, our holdings, and the
    two derived quantities that matter most -- the local price SLOPE and the
    town's drain rate, which is what decides whether a book recovers.

BELIEF   the opponent's shed is private, so the honest representation is an
    INTERVAL, not a point estimate. `dynamic/opp_state.py` recovers their
    harvests exactly (intra-day yield_units drops) and their sales exactly
    except at the $1 floor, and the engine caps the shed at 100 items TOTAL
    with the overflow discarded. That gives real bounds:

        lo_i = max(0, harvested_i - sold_i)                 (floor sales unseen
                                                             can only lower it)
        hi_i = min(harvested_i, lo_i + unseen_floor_room)   and sum_i hi_i is
                                                             capped by the shed

    so the policy is fed `lo`, `hi` and the width `hi - lo` as an explicit
    confidence signal, rather than a number pretending to be certain.
"""
import math

from dynamic import market_model as MM

BOARD = 10
PRODUCTS = MM.PRODUCTS                     # 9, fixed order
CROPS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
ANIMALS = ["GOOSE", "COW", "SHEEP"]
SHED_CAP = 100
SEASON_DAYS = 30
TURNS_PER_DAY = 24

# Channel layout, per tile, per farm. Kept explicit so the encoder and any
# analysis of a trained policy read the same map.
CHANNELS = (
    ["unlocked", "empty", "weed", "structure_empty"]
    + [f"crop_{c}" for c in CROPS]
    + [f"animal_{a}" for a in ANIMALS]
    + ["yield_frac", "age_frac", "watered", "unwatered", "fed", "cared",
       "fert_ready", "care_bonus", "dist_shed"]
)
C = len(CHANNELS)
IDX = {name: i for i, name in enumerate(CHANNELS)}

_CROP_MAXY = {"WHEAT": 6, "CARROT": 4, "TOMATO": 4, "STRAWBERRY": 4, "MELON": 6}
_ANIMAL_MAXHELD = {"GOOSE": 4, "COW": 6, "SHEEP": 6}


def _shed_tiles():
    mid = BOARD // 2
    return [(mid - 1, mid - 1), (mid, mid - 1), (mid - 1, mid), (mid, mid)]


_SHED = _shed_tiles()
_DIST = [[min(abs(x - sx) + abs(y - sy) for sx, sy in _SHED) / float(2 * BOARD)
          for x in range(BOARD)] for y in range(BOARD)]


def encode_board(farm, day, out=None):
    """(H*W*C,) float list for one farm. `out` may be a preallocated list."""
    n = BOARD * BOARD * C
    if out is None:
        out = [0.0] * n
    else:
        for i in range(n):
            out[i] = 0.0
    tiles = (farm or {}).get("tiles") or []
    for y in range(min(BOARD, len(tiles))):
        row = tiles[y]
        for x in range(min(BOARD, len(row))):
            base = (y * BOARD + x) * C
            out[base + IDX["dist_shed"]] = _DIST[y][x]
            t = row[x]
            if t == "LOCKED":
                continue
            out[base + IDX["unlocked"]] = 1.0
            if t is None:
                out[base + IDX["empty"]] = 1.0
                continue
            if not isinstance(t, dict):
                continue
            kind = t.get("kind")
            if kind == "WEED":
                out[base + IDX["weed"]] = 1.0
                continue
            animal = t.get("animal")
            if animal:
                if animal in _ANIMAL_MAXHELD:
                    out[base + IDX[f"animal_{animal}"]] = 1.0
                    out[base + IDX["yield_frac"]] = min(
                        1.0, float(t.get("yield_units", 0)) / _ANIMAL_MAXHELD[animal])
                out[base + IDX["age_frac"]] = min(
                    1.0, max(0, day - int(t.get("placed_day", day))) / float(SEASON_DAYS))
                out[base + IDX["fed"]] = 1.0 if t.get("fed_today") else 0.0
                out[base + IDX["cared"]] = 1.0 if t.get("cared_today") else 0.0
                out[base + IDX["unwatered"]] = min(
                    1.0, float(t.get("consecutive_unfed", 0)) / 2.0)
                out[base + IDX["fert_ready"]] = 1.0 if t.get("fertilizer_available") else 0.0
                out[base + IDX["care_bonus"]] = min(
                    1.0, float(t.get("pending_care_bonus", 0)) / 4.0)
                continue
            if kind == "PLANT":
                crop = t.get("crop")
                if crop in _CROP_MAXY:
                    out[base + IDX[f"crop_{crop}"]] = 1.0
                    out[base + IDX["yield_frac"]] = min(
                        1.0, float(t.get("yield_units", 0)) / _CROP_MAXY[crop])
                out[base + IDX["age_frac"]] = min(
                    1.0, max(0, day - int(t.get("planted_day", day))) / float(SEASON_DAYS))
                out[base + IDX["watered"]] = 1.0 if t.get("watered_today") else 0.0
                out[base + IDX["unwatered"]] = min(
                    1.0, float(t.get("consecutive_unwatered", 0)) / 2.0)
                continue
            # an empty COOP or PASTURE, waiting for an animal
            out[base + IDX["structure_empty"]] = 1.0
    return out


def belief(state, prices):
    """Opponent holdings as an INTERVAL per product, plus its width.

    `state` is an `opp_state.OppState` observed every turn. The lower bound is
    the ledger; the upper bound adds back what could have been sold invisibly
    at the $1 floor, and the whole vector is capped by the shed.
    """
    lo, hi = {}, {}
    for item in PRODUCTS:
        h = float(state.harvested[item])
        s = float(state.sold[item])
        base = max(0.0, h - s)
        lo[item] = base
        # Sales at the floor are invisible, so `sold` may under-count -- but
        # only for a product currently AT the floor. Elsewhere the ledger is
        # exact and the interval collapses.
        at_floor = float((prices or {}).get(item, 999)) <= 1.0
        hi[item] = h if at_floor else base
    total_hi = sum(hi.values())
    if total_hi > SHED_CAP:
        k = SHED_CAP / total_hi
        for item in PRODUCTS:
            hi[item] *= k
            lo[item] = min(lo[item], hi[item])
    return lo, hi


def encode_scalars(obs, farm, private, opp_farm, opp_state, day, hour):
    """Global economic vector. Everything normalised to roughly [0, 2]."""
    market = obs.get("market") or {}
    inv = market.get("inventory") or {}
    prices = market.get("prices") or {}
    shops = tuple((obs.get("town") or {}).get("unlocked_shops") or ())
    shed = private.get("shed") or {}
    seeds = private.get("seeds") or {}

    v = [
        min(2.0, float(farm.get("money", 0)) / 50000.0),
        day / float(SEASON_DAYS),
        hour / float(TURNS_PER_DAY),
        min(1.0, len(farm.get("hands") or []) / 20.0),
        min(1.0, sum(shed.values()) / float(SHED_CAP)),
        len(farm.get("unlocked_quadrants", ["NW"])) / 4.0,
        min(2.0, float((opp_farm or {}).get("money", 0)) / 50000.0),
        min(1.0, len((opp_farm or {}).get("hands") or []) / 20.0),
        len(shops) / 8.0,
    ]
    lo, hi = belief(opp_state, prices)
    for item in PRODUCTS:
        q = int(inv.get(item, MM.MARKET_I0))
        off = (q - MM.MARKET_I0) / 500.0
        v.append(max(-2.0, min(2.0, off)))
        v.append(min(2.0, float(prices.get(item, 0)) / 250.0))
        v.append(MM.slope(item, q) / 8.0)
        v.append(MM.drain_rate(item, shops) / 32.0)
        v.append(min(1.0, float(shed.get(item, 0)) / 40.0))
        v.append(min(1.0, lo[item] / 40.0))
        v.append(min(1.0, hi[item] / 40.0))
        v.append(min(1.0, (hi[item] - lo[item]) / 40.0))
    for c in CROPS:
        v.append(min(1.0, float(seeds.get(c, 0)) / 20.0))
    return v


ROLES = list(CROPS) + ["GOOSE", "COW", "SHEEP"]


def board_feature_names():
    n = [f"our.{r}" for r in ROLES] + [f"opp.{r}" for r in ROLES]
    n += [f"our.stage.{c}" for c in CROPS]
    n += ["our.empty", "our.weeds", "opp.weeds", "our.watered_frac",
          "our.mean_dist_shed", "opp.mean_dist_shed",
          "our.ready", "opp.ready", "our.at_risk", "opp.at_risk",
          "our.producing"]
    n += [f"our.density.{q}" for q in ("NW", "NE", "SW", "SE")]
    return n


BOARD_FEATURES = len(board_feature_names())


def extract_board_features(farm, opp_farm, day):
    """The board as interpretable STATISTICS instead of 2,100 raw tile floats.

    Every entry is a count, a mean or a fraction with a name, so a linear policy
    over them reads as a rule. This replaces the two 10x10xC planes that were
    the only reason the daily head could not be white-box: the sell head was
    already scalar-only.

    Normalised to roughly [0, 1] so coefficients are comparable across features
    -- otherwise a raw tile count would dominate a fraction purely by scale.
    """
    def one(f):
        cnt = {r: 0 for r in ROLES}
        stage = {c: [] for c in CROPS}
        empty = weeds = watered = ready = at_risk = 0
        dists, quad = [], {"NW": 0, "NE": 0, "SW": 0, "SE": 0}
        tiles = (f or {}).get("tiles") or []
        for y, row in enumerate(tiles):
            for x, t in enumerate(row):
                if t == "LOCKED":
                    continue
                q = ("NW" if x < 5 and y < 5 else "NE" if y < 5 else
                     "SW" if x < 5 else "SE")
                if t is None:
                    empty += 1
                    continue
                if not isinstance(t, dict):
                    continue
                kind = t.get("kind")
                if kind == "WEED":
                    weeds += 1
                    continue
                a = t.get("animal")
                crop = t.get("crop") if kind == "PLANT" else None
                role = a or crop
                if role in cnt:
                    cnt[role] += 1
                    quad[q] += 1
                    dists.append(abs(x - 4) + abs(y - 4))
                if crop in stage:
                    age = day - int(t.get("planted_day", day))
                    stage[crop].append(min(1.0, age / 12.0))
                    if t.get("watered_today"):
                        watered += 1
                    if int(t.get("consecutive_unwatered", 0)) >= 1:
                        at_risk += 1
                if int(t.get("yield_units", 0) or 0) > 0:
                    ready += 1
                if a and int(t.get("consecutive_unfed", 0)) >= 1:
                    at_risk += 1
        n_role = sum(cnt.values())
        return cnt, stage, empty, weeds, watered, ready, at_risk, dists, quad, n_role

    (c1, st1, e1, w1, wat1, rd1, ar1, d1, q1, n1) = one(farm)
    (c2, _st2, _e2, w2, _wa2, rd2, ar2, d2, _q2, n2) = one(opp_farm)

    v = [c1[r] / 25.0 for r in ROLES] + [c2[r] / 25.0 for r in ROLES]
    v += [(sum(st1[c]) / len(st1[c])) if st1[c] else 0.0 for c in CROPS]
    v += [e1 / 50.0, w1 / 25.0, w2 / 25.0,
          (wat1 / n1) if n1 else 0.0,
          (sum(d1) / len(d1) / 8.0) if d1 else 0.0,
          (sum(d2) / len(d2) / 8.0) if d2 else 0.0,
          rd1 / 25.0, rd2 / 25.0, ar1 / 25.0, ar2 / 25.0, n1 / 75.0]
    v += [q1[q] / 25.0 for q in ("NW", "NE", "SW", "SE")]
    return v


def scalar_names():
    """Name every entry of `encode_scalars`, in order.

    This is what makes an interpretable policy possible: the sell head sees ONLY
    these, so a linear model over them reads as "this feature moves the
    probability of that action by this much" -- no hidden representation.
    """
    n = ["cash", "day", "hour", "crew", "shed_fill", "quadrants",
         "opp_cash", "opp_crew", "shops"]
    for item in PRODUCTS:
        n += [f"{item}.inv_offset", f"{item}.price", f"{item}.slope",
              f"{item}.drain", f"{item}.we_hold",
              f"{item}.opp_min", f"{item}.opp_max", f"{item}.opp_width"]
    for c in CROPS:
        n.append(f"seed.{c}")
    return n


SPATIAL_SIZE = BOARD * BOARD * C
SCALAR_SIZE = 9 + 8 * len(PRODUCTS) + len(CROPS)
WHITEBOX_SIZE = BOARD_FEATURES + SCALAR_SIZE


def whitebox_names():
    return board_feature_names() + scalar_names()


def encode_whitebox(obs, farm, private, opp_farm, opp_state, day, hour):
    """Board statistics + global scalars: the full white-box observation."""
    return (extract_board_features(farm, opp_farm, day)
            + encode_scalars(obs, farm, private, opp_farm, opp_state, day, hour))
OBS_SIZE = 2 * SPATIAL_SIZE + SCALAR_SIZE


def encode(obs, farm, private, opp_farm, opp_state, day, hour):
    """Full observation: our board, their board, then the scalar vector."""
    return (encode_board(farm, day)
            + encode_board(opp_farm, day)
            + encode_scalars(obs, farm, private, opp_farm, opp_state, day, hour))
