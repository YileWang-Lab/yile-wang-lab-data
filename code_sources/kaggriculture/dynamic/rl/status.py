"""Is the RL run going up or down? Read-only, safe to run any time.

Per-iteration numbers cannot answer that question. Win rate is measured on 96
paired episodes, so its standard error is about 5 percentage points -- two
adjacent lines differing by 10pp is nothing. This blocks the history and
compares the recent block against the opening one with a standard error, so the
answer is a signal-to-noise ratio rather than an impression.

    python dynamic/rl/status.py           # summary
    python dynamic/rl/status.py 40        # blocks of 40 iterations
"""
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.path.join(ROOT, "logs", "rl", "train.out")

LINE = re.compile(
    r"^iter\s+(\d+)\s+winrate\s+([\d.]+)%\s+paired\s+([-+,\d]+)\s+"
    r"reward\s+([-+.\d]+)\s+p_id\s+([\d.]+)")


def parse():
    rows = []
    if not os.path.exists(LOG):
        return rows
    with open(LOG, errors="ignore") as fh:
        for ln in fh:
            m = LINE.match(ln.strip())
            if m:
                rows.append((int(m.group(1)), float(m.group(2)),
                             float(m.group(3).replace(",", "")),
                             float(m.group(4)), float(m.group(5))))
    return rows


def bar(v, lo, hi, width=28):
    if hi <= lo:
        return ""
    n = int(round(width * (v - lo) / (hi - lo)))
    return "#" * max(0, min(width, n))


def main():
    block = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    rows = parse()
    if not rows:
        print("no iterations logged yet -- check logs/rl/run.log")
        return
    print(f"{len(rows)} iterations logged, latest iter {rows[-1][0]}")
    print()

    # ---- blocked trend
    blocks = []
    for i in range(0, len(rows), block):
        chunk = rows[i:i + block]
        if len(chunk) < max(3, block // 3) and i > 0:
            break
        blocks.append((chunk[0][0], chunk[-1][0],
                       statistics.mean(c[1] for c in chunk),
                       statistics.mean(c[2] for c in chunk),
                       statistics.mean(c[4] for c in chunk),
                       len(chunk)))
    wrs = [b[2] for b in blocks]
    lo, hi = min(wrs), max(wrs)
    print(f"{'iters':>13}{'winrate':>9}{'paired':>11}{'p_id':>7}   trend")
    for a, b, wr, pm, pid, n in blocks:
        print(f"{a:>5}-{b:<7}{wr:>8.1f}%{pm:>11,.0f}{pid:>7.3f}   {bar(wr, lo, hi)}")

    # ---- is it up or down, with a standard error
    print()
    k = min(len(rows) // 3 or 1, 60)
    first, last = rows[:k], rows[-k:]
    for name, idx, unit in (("win rate", 1, "%"), ("paired margin", 2, "")):
        a = [r[idx] for r in first]
        b = [r[idx] for r in last]
        da = statistics.mean(b) - statistics.mean(a)
        sa = (statistics.pstdev(a) / len(a) ** 0.5) if len(a) > 1 else 0.0
        sb = (statistics.pstdev(b) / len(b) ** 0.5) if len(b) > 1 else 0.0
        se = (sa ** 2 + sb ** 2) ** 0.5
        t = da / se if se > 1e-9 else 0.0
        verdict = ("UP" if t > 2 else "DOWN" if t < -2 else "flat (within noise)")
        fmt = f"{da:+,.1f}{unit}" if idx == 1 else f"{da:+,.0f}"
        print(f"  {name:<15} first {k} vs last {k}: {fmt:>12}  "
              f"se {se:,.1f}  t {t:>+5.2f}   {verdict}")

    pid_now = rows[-1][4]
    print()
    print(f"  p_id now {pid_now:.3f} (starts 0.993)")
    if pid_now < 0.60:
        print("    -> policy has moved a long way off the scheduler. Fine IF win")
        print("       rate is UP; if win rate is DOWN the KL leash is too loose.")
    elif pid_now > 0.985 and len(rows) > 150:
        print("    -> barely moved in 150+ iterations: the leash is likely too")
        print("       tight to learn anything. Try --kl 0.02.")
    else:
        print("    -> drifting, which is what learning looks like.")


if __name__ == "__main__":
    main()
