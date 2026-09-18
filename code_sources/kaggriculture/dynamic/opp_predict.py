"""Opponent-aware supply prediction: a fitted g(obs; theta) for E[Q_opp_sales].

    theta* = argmin_theta  sum over (obs, Q) in D  L( Q, g(obs; theta) )

Every price term in this project consumes `N_them` -- the units the opponent can
still put on a book:

    MV       = P(q) + alpha * |P'(q)| * (N_them - N_us)
    P_realized(Q) = f(Q_ours + E[Q_opp])

and today `N_them` is the structural forecast from `dynamic/opp_state.py`. That
estimator is honest about its own failure: measured against their ACTUAL
remaining sales it predicts 72.8 strawberry against a true 192.7 -- biased low
by roughly 2.5x -- because it can only see tiles they have already planted and
is blind to replanting and to the FERTILIZE bonus. What it has is RANK
(correlation 0.66 to 0.82 on the five products that matter).

A scalar gain fixes a bias. It cannot fix the fact that the bias is not
constant: it grows through the season as the tiles they have not planted yet
come to dominate what is left to sell. That is a regression problem, and the
features for it are all public.

WHY LINEAR, AND WHY RIDGE
-------------------------
The training set is a few thousand rows of eight features. A behavioural-cloning
network on this project reached 92.8% action accuracy and produced an agent that
banked $288 (`planner/bc_play.py`), and the post-mortem was covariate shift, not
capacity. Here the target is a scalar the features genuinely determine, the
model has to run inside a stdlib-only submission, and every coefficient has to
be inspectable -- so ridge-regularised least squares, solved in closed form.

The estimator degrades gracefully: with `theta = None` it returns the structural
forecast unchanged, so the caller is never worse off than today.
"""

FEATURES = (
    "bias",
    "structural",      # the current forecast: held + tiles' remaining output
    "held",            # what the tracker says they are sitting on
    "harvest_rate",    # exact, from intra-day yield_units drops, x days left
    "sales_rate",      # exact, from the market-inventory identity, x days left
    "days_left",
    "n_tiles",         # their tiles producing this item
    "n_animals",       # whole herd: drives wheat demand and fertilizer supply
)

ANIMALS = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
SEASON_DAYS = 30


def feature_row(item, opp_farm, day, state, structural=None):
    """The public observation, as a feature vector. `state` is an
    `opp_state.OppState` that has been observed every turn."""
    days_left = float(max(0, SEASON_DAYS - day))
    n_tiles = 0
    n_animals = 0
    for row in (opp_farm or {}).get("tiles") or []:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal:
                n_animals += 1
                if ANIMALS.get(animal) == item:
                    n_tiles += 1
            elif tile.get("kind") == "PLANT" and tile.get("crop") == item:
                n_tiles += 1
    if structural is None:
        structural = state.forecast_production(opp_farm, item, day)
    return [
        1.0,
        float(structural),
        float(state.held(item)),
        float(state.harvest_rate(item)) * days_left,
        float(state.sold[item]) / max(1.0, float(day)) * days_left,
        days_left,
        float(n_tiles),
        float(n_animals),
    ]


# --------------------------------------------------------------- least squares

def _solve(a, b):
    """Gaussian elimination with partial pivoting. `a` is square, modified."""
    n = len(a)
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        inv = 1.0 / m[col][col]
        for j in range(col, n + 1):
            m[col][j] *= inv
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            if f:
                for j in range(col, n + 1):
                    m[r][j] -= f * m[col][j]
    return [m[i][n] for i in range(n)]


def fit(rows, ridge=1.0):
    """theta* by ridge-regularised least squares.

    `rows` are (x, y). The bias column is not penalised -- shrinking it would
    bias every prediction toward zero, which is the opposite of the correction
    this model exists to make.
    """
    if not rows:
        return None
    n = len(rows[0][0])
    ata = [[0.0] * n for _ in range(n)]
    atb = [0.0] * n
    for x, y in rows:
        for i in range(n):
            xi = x[i]
            if xi:
                atb[i] += xi * y
                for j in range(n):
                    ata[i][j] += xi * x[j]
    for i in range(1, n):
        ata[i][i] += ridge
    return _solve(ata, atb)


def predict(theta, x, floor=0.0):
    """g(obs; theta). Clamped at `floor`: a negative remaining supply is not a
    physical statement, and the term it feeds is signed."""
    if theta is None:
        # No model: fall back to the structural forecast, i.e. today's answer.
        return max(floor, x[1])
    return max(floor, sum(t * v for t, v in zip(theta, x)))


def score(theta, rows):
    """(bias, mean |err|, correlation) against held-out rows -- the same three
    numbers `dynamic/opp_state_test.py` reports, so the two are comparable."""
    if not rows:
        return 0.0, 0.0, 0.0
    pred = [predict(theta, x) for x, _ in rows]
    true = [y for _, y in rows]
    n = float(len(rows))
    mp = sum(pred) / n
    mt = sum(true) / n
    sp = (sum((p - mp) ** 2 for p in pred) / n) ** 0.5
    st = (sum((t - mt) ** 2 for t in true) / n) ** 0.5
    cov = sum((p - mp) * (t - mt) for p, t in zip(pred, true)) / n
    corr = cov / (sp * st) if sp > 1e-9 and st > 1e-9 else 0.0
    return mp - mt, sum(abs(p - t) for p, t in zip(pred, true)) / n, corr


# Fitted coefficients, keyed by item. Populated by dynamic/opp_predict_fit.py;
# empty means every caller transparently uses the structural forecast.
THETA = {}
