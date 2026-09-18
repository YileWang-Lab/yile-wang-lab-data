"""Live terminal dashboard for the RL run. Read-only; safe at any time.

    python dynamic/rl/dash.py            # refreshes every 20s
    python dynamic/rl/dash.py 60         # every 60s
    python dynamic/rl/dash.py 0          # print once and exit

WHY IT SPLITS SELF-PLAY FROM POOL. A blended win rate is unreadable here. A
policy frozen at the scheduler identity scores 0.6*50% + 0.4*0% = 30% overall,
and the self-play share of a 96-episode batch varies by about +-5 episodes
(sd = sqrt(96*0.6*0.4) = 4.8), so the blend alone swings several points. That
produced a spurious "win rate UP, t=+3.94" reading over 150 iterations in which
nothing was learned at all.

Split apart the question is direct:

    SELF   is the policy beating a frozen snapshot of itself? 50% means no.
    POOL   is it beating the reference agents? 0% is where it starts.
    p_id   how much probability still sits on "do what the scheduler would do".

The verdict line uses a t statistic, never an eyeball: one iteration's win rate
is 96 paired episodes, se about 5pp, so adjacent lines differing by 10pp are
noise.
"""
import os
import re
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:] = [q for q in sys.path
               if os.path.abspath(q or ".") != os.path.dirname(
                   os.path.abspath(__file__))]
sys.path.insert(0, ROOT)
LOGDIR = os.path.join(ROOT, "logs", "rl")
LOG = os.path.join(LOGDIR, "train.out")
LOG2 = os.path.join(LOGDIR, "train.log")

LINE = re.compile(
    r"^iter\s+(\d+)\s+winrate\s+([\d.]+)%\s+paired\s+([-+,\d]+)\s+"
    r"reward\s+([-+.\d]+)\s+"
    r"(?:selfwr\s+([\d.nan]+)%\s+poolwr\s+([\d.nan]+)%\s+)?"
    r"(?:rung\s+(\d+)\s+)?"
    r"p_id\s+([\d.]+)")

C = {"r": "\033[0m", "b": "\033[1m", "dim": "\033[2m", "g": "\033[32m",
     "y": "\033[33m", "red": "\033[31m", "cy": "\033[36m"}


def _latest_run(rows):
    """Keep only the CURRENT run.

    train.py opens train.log in APPEND mode, so the file accumulates every
    restart -- and tonight's restarts changed the reward, the policy class and
    the curriculum. Concatenating them draws one curve through several
    incompatible configurations: the tell was a rung sparkline that went
    5-3-1-3-5-8 (non-monotone, so not one run's promotions) and a POOL wr that
    stepped from a flat floor to 70% at the moment the curriculum was added.

    A restart shows up as the iteration counter going BACKWARDS, so the last
    non-decreasing suffix is the run in progress.
    """
    if not rows:
        return rows
    start = 0
    for i in range(1, len(rows)):
        if rows[i]["it"] <= rows[i - 1]["it"]:
            start = i
    return rows[start:]


def parse(all_runs=False):
    rows = []
    src = LOG if os.path.exists(LOG) else LOG2
    if not os.path.exists(src):
        return rows
    with open(src, errors="ignore") as fh:
        for ln in fh:
            m = LINE.match(ln.strip())
            if not m:
                continue
            f = lambda s: float(s) if s and s != "nan" else float("nan")  # noqa: E731
            rows.append({"it": int(m.group(1)), "wr": float(m.group(2)),
                         "paired": float(m.group(3).replace(",", "")),
                         "reward": float(m.group(4)),
                         "self": f(m.group(5)), "pool": f(m.group(6)),
                         "rung": int(m.group(7)) if m.group(7) else 0,
                         "pid": float(m.group(8))})
    return rows if all_runs else _latest_run(rows)


def spark(vals, lo=None, hi=None, width=48):
    if not vals:
        return ""
    ch = "▁▂▃▄▅▆▇█"
    v = vals[-width:]
    lo = min(v) if lo is None else lo
    hi = max(v) if hi is None else hi
    if hi - lo < 1e-9:
        return ch[3] * len(v)
    return "".join(ch[min(7, int(7 * (x - lo) / (hi - lo)))] for x in v)


def trend(rows, key):
    """(delta, se, t) comparing the opening third against the closing third."""
    vals = [r[key] for r in rows if r[key] == r[key]]
    if len(vals) < 12:
        return None
    k = min(len(vals) // 3, 80)
    a, b = vals[:k], vals[-k:]
    d = statistics.mean(b) - statistics.mean(a)
    se = ((statistics.pstdev(a) / len(a) ** 0.5) ** 2
          + (statistics.pstdev(b) / len(b) ** 0.5) ** 2) ** 0.5
    return d, se, (d / se if se > 1e-9 else 0.0)


def verdict(t):
    if t is None:
        return f"{C['dim']}not enough data{C['r']}"
    d, se, tv = t
    if tv > 2:
        return f"{C['g']}UP   {d:+8.1f}  t {tv:+5.2f}{C['r']}"
    if tv < -2:
        return f"{C['red']}DOWN {d:+8.1f}  t {tv:+5.2f}{C['r']}"
    return f"{C['y']}flat {d:+8.1f}  t {tv:+5.2f}{C['r']}"


def chart(series, height=14, width=64, lo=None, hi=None, hline=None,
          hlabel=""):
    """Overlaid line chart for the terminal.

    `series` is [(label, marker, colour, values)]. History is bucketed into
    `width` columns and each bucket is MEANED rather than sampled -- a single
    iteration is 96 paired episodes with se ~5pp, so plotting raw points draws
    the noise instead of the trend.
    """
    live = [(l, m, c, v) for l, m, c, v in series if v]
    if not live:
        return f"    {C['dim']}(no data yet){C['r']}"
    allv = [x for _l, _m, _c, v in live for x in v]
    lo = min(allv) if lo is None else lo
    hi = max(allv) if hi is None else hi
    if hi - lo < 1e-9:
        hi = lo + 1.0
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    grid = [[" "] * width for _ in range(height)]
    colour = [[""] * width for _ in range(height)]

    def row_of(val):
        f = (val - lo) / (hi - lo)
        return max(0, min(height - 1, int(round((1 - f) * (height - 1)))))

    if hline is not None and lo <= hline <= hi:
        r = row_of(hline)
        for c in range(width):
            grid[r][c] = "-"
            colour[r][c] = C["dim"]

    for _label, marker, col, vals in live:
        n = len(vals)
        for c in range(width):
            a = int(c * n / width)
            b = max(a + 1, int((c + 1) * n / width))
            chunk = vals[a:b]
            if not chunk:
                continue
            r = row_of(statistics.mean(chunk))
            grid[r][c] = marker
            colour[r][c] = col

    out = []
    for r in range(height):
        val = hi - (hi - lo) * r / (height - 1)
        body = "".join((colour[r][c] + grid[r][c] + C["r"]) if grid[r][c] != " "
                       else " " for c in range(width))
        out.append(f"   {val:>6.1f} |{body}")
    out.append(f"   {'':>6} +{'-' * width}")
    key = "  ".join(f"{col}{mk}{C['r']} {lb}" for lb, mk, col, _v in live)
    n = max(len(v) for _l, _m, _c, v in live)
    out.append(f"   {'':>6}  0{' ' * max(0, width - 12)}iter {n}")
    if hline is not None:
        key += f"   {C['dim']}- {hlabel}{C['r']}"
    out.append(f"   {'':>6}  {key}")
    return "\n".join(out)


def _rules_block(max_lines=14):
    """Read the live checkpoint and print the policy as text.

    This is what a white-box run buys: the coefficients ARE the strategy, so
    training can be watched as rules appearing rather than as a loss curve.
    """
    ck = os.path.join(LOGDIR, "latest.pt")
    if not os.path.exists(ck):
        return f"    {C['dim']}(no checkpoint yet){C['r']}"
    try:
        import torch
        from dynamic.rl.linear_policy import (DEFAULT_INTERACTIONS,
                                              LinearDailyNet, LinearSellNet)
        d = torch.load(ck, map_location="cpu", weights_only=False)
        dn, sn = LinearDailyNet(), LinearSellNet(interactions=DEFAULT_INTERACTIONS)
        dn.load_state_dict(d["daily"])
        sn.load_state_dict(d["sell"])
    except Exception as e:                       # an MLP checkpoint, or mid-write
        return f"    {C['dim']}(not a white-box checkpoint: {type(e).__name__}){C['r']}"
    txt = (dn.explain("crop_pref", top=3, min_abs=0.02) + "\n"
           + dn.explain("crew_delta", top=2, min_abs=0.02) + "\n"
           + sn.rules(top=2, min_abs=0.08))
    lines = [l for l in txt.split("\n") if l.strip()][:max_lines]
    if not lines:
        return f"    {C['dim']}(still at the scheduler identity -- nothing learned yet){C['r']}"
    return "\n".join("  " + l for l in lines)


def render():
    rows = parse()
    out = []
    A = out.append
    A(f"{C['b']}RL training — Kaggriculture{C['r']}    "
      f"{C['dim']}{time.strftime('%Y-%m-%d %H:%M:%S')}{C['r']}")
    A("")
    alive = subprocess.run(["pgrep", "-f", "dynamic.rl.tr" + "ain"],
                           capture_output=True, text=True).stdout.split()
    state = (f"{C['g']}RUNNING{C['r']} ({len(alive)} procs)" if alive
             else f"{C['red']}NOT RUNNING{C['r']}")
    A(f"  status   {state}")
    if not rows:
        A(f"  {C['dim']}no iterations logged yet{C['r']}")
        return "\n".join(out)

    last = rows[-1]
    n_all = len(parse(all_runs=True))
    extra = (f"   {C['dim']}({n_all - len(rows)} earlier rows from previous "
             f"runs hidden){C['r']}" if n_all > len(rows) else "")
    A(f"  iters    {len(rows)} in this run   latest {last['it']}{extra}")
    A("")
    # 'now' is ONE iteration -- 96 paired episodes, se ~5pp on a win rate. It
    # swung 12% to 100% on consecutive iterations while the 50-iteration mean
    # sat near 50, and reading the single value as the state of the run is
    # exactly the mistake this dashboard exists to prevent. mean50 is the column
    # to read; 'now' is kept only to show the run is alive.
    A(f"  {C['b']}{'':<10}{C['dim']}{'now*':>8}{C['r']}{C['b']}{'mean50':>9}   "
      f"last 48 iterations{C['r']}")

    def line(label, key, fmt="{:.1f}%"):
        vals = [r[key] for r in rows if r[key] == r[key]]
        if not vals:
            return
        m50 = statistics.mean(vals[-50:])
        A(f"  {label:<10}{C['dim']}{fmt.format(vals[-1]):>8}{C['r']}"
          f"{fmt.format(m50):>9}   {C['cy']}{spark(vals)}{C['r']}")

    line("SELF wr", "self")
    line("POOL wr", "pool")
    line("paired", "paired", "{:+,.0f}")
    line("p_id", "pid", "{:.3f}")
    line("rung", "rung", "{:.0f}")
    A("")
    A(f"  {C['b']}win rate over training{C['r']}")
    A(chart([("SELF (vs frozen self)", "o", C["g"],
              [r["self"] for r in rows if r["self"] == r["self"]]),
             ("POOL (vs opponents)", "*", C["cy"],
              [r["pool"] for r in rows if r["pool"] == r["pool"]])],
            hline=50.0, hlabel="50% = no better than its own snapshot"))
    A("")
    A(f"  {C['b']}paired margin{C['r']}")
    A(chart([("paired", ".", C["y"], [r["paired"] for r in rows])],
            height=8, hline=0.0, hlabel="0 = level with the opponent"))
    A("")
    A(f"  {C['b']}trend (first third vs last third){C['r']}")
    for label, key in (("self-play wr", "self"), ("pool wr", "pool"),
                       ("paired margin", "paired")):
        A(f"    {label:<16}{verdict(trend(rows, key))}")
    A("")

    # --- the two failure modes, stated plainly
    pid = last["pid"]
    sw = [r["self"] for r in rows if r["self"] == r["self"]]
    A(f"  {C['b']}diagnosis{C['r']}")
    if pid > 0.985 and len(rows) > 120:
        A(f"    {C['y']}p_id {pid:.3f} after {len(rows)} iters: the policy has not "
          f"moved.{C['r']}")
        A(f"    {C['dim']}The KL leash is holding it at the scheduler identity. "
          f"Nothing is being learned.{C['r']}")
    elif sw and statistics.mean(sw[-30:]) < 45:
        A(f"    {C['red']}self-play win rate {statistics.mean(sw[-30:]):.1f}% — the "
          f"policy is LOSING to a frozen copy of itself.{C['r']}")
        A(f"    {C['dim']}It is moving in a harmful direction: the leash is too "
          f"loose, or the advantage is noise.{C['r']}")
    elif sw and statistics.mean(sw[-30:]) > 55:
        A(f"    {C['g']}self-play win rate {statistics.mean(sw[-30:]):.1f}% — "
          f"beating its own snapshot. This is real improvement.{C['r']}")
    else:
        A(f"    {C['dim']}self-play near 50% and p_id {pid:.3f}: drifting without a "
          f"clear direction yet.{C['r']}")
    A("")
    # --- the policy as rules, which is the point of a white-box run
    A(f"  {C['b']}rules the policy has learned{C['r']}   "
      f"{C['dim']}(from logs/rl/latest.pt){C['r']}")
    A(_rules_block())
    A("")
    A(f"  {C['dim']}* 'now' is a single 96-episode iteration (se ~5pp) -- read "
      f"mean50, not now.{C['r']}")
    A(f"  {C['dim']}baseline to beat: SHIPPED tape+market is +80,210 paired above "
      f"the RL start point.{C['r']}")
    A(f"  {C['dim']}final scores land in logs/rl/RESULTS.md when the run ends.{C['r']}")
    return "\n".join(out)


def main():
    if "--plain" in sys.argv:
        for k in C:
            C[k] = ""
        sys.argv = [a for a in sys.argv if a != "--plain"]
    every = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    if every <= 0:
        print(render())
        return
    try:
        while True:
            sys.stdout.write("\033[H\033[J" + render() + "\n")
            sys.stdout.flush()
            time.sleep(every)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
