"""Pull every public Kaggriculture kernel and turn the usable ones into agents.

The training pool is six reference agents we beat 0.7% of the time, which is a
pool with no rungs: it teaches nothing and measures nothing. Widening it is the
cheapest way to get a curriculum, and the competition has hundreds of public
notebooks spanning getting-started tutorials to near-top builds.

Two things make this messier than "download and run":

  NOT EVERY NOTEBOOK IS AN AGENT. Many are analysis, leaderboard scrapers, or
  write-ups; the handoff already recorded four that extract to analysis code
  rather than a callable. Each candidate is therefore imported in a subprocess
  and required to survive one real game before it is kept.

  DUPLICATES ARE EVERYWHERE. Notebooks get forked and re-published, and the pool
  already found "V20-Adaptive-R1 is kawa itself". Files are deduplicated by the
  sha256 of their extracted source, so a fork does not become a second rung.

    python dynamic/rl/fetch_external.py [pages] [per_page]

Writes opponents/external/*.py and a manifest at opponents/external/INDEX.json.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTDIR = os.path.join(ROOT, "opponents", "external")
KAGGLE = "/home/yilewang/kagg-env/bin/kaggle"
PY = "/home/yilewang/kagg-env/bin/python"
SORTS = ["voteCount", "hotness", "scoreDescending", "dateRun"]


def list_kernels(pages, per_page):
    refs = {}
    for sort in SORTS:
        for page in range(1, pages + 1):
            cmd = [KAGGLE, "kernels", "list", "--competition", "kaggriculture",
                   "--page-size", str(per_page), "--page", str(page),
                   "--sort-by", sort]
            try:
                out = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=180).stdout
            except subprocess.TimeoutExpired:
                continue
            got = 0
            for ln in out.splitlines()[2:]:
                m = re.match(r"^(\S+/\S+)\s{2,}(.+?)\s{2,}", ln)
                if m:
                    refs.setdefault(m.group(1), m.group(2).strip())
                    got += 1
            if got == 0:
                break
    return refs


def _strip_magics(src):
    """Comment out shell escapes and IPython magics.

    Notebook cells carry `!pip install ...` and `%matplotlib ...`, which are not
    Python, so the whole extracted file is a SyntaxError and the candidate is
    rejected for its first line rather than for its agent. This recovered a
    large share of the pool.
    """
    out = []
    for ln in src.split("\n"):
        t = ln.lstrip()
        if t[:1] in ("!", "%", "?") and not t.startswith("#"):
            out.append("# " + ln)
        else:
            out.append(ln)
    return "\n".join(out)


def extract_source(path):
    """Return python source from a .py or .ipynb kernel file."""
    if path.endswith(".py"):
        return _strip_magics(open(path, errors="ignore").read())
    try:
        nb = json.load(open(path, errors="ignore"))
    except Exception:
        return ""
    parts = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        parts.append("".join(cell.get("source", [])))
    return _strip_magics("\n\n".join(parts))


PROBE = r'''
import sys, os, importlib.util
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.abspath("dynamic")]
sys.path.insert(0, %r)
from planner.simulate import Simulator
spec = importlib.util.spec_from_file_location("cand", %r)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
fn = getattr(m, "_submission_entry", None) or getattr(m, "agent", None)
assert callable(fn), "no agent callable"
ospec = importlib.util.spec_from_file_location("opp", %r)
om = importlib.util.module_from_spec(ospec); ospec.loader.exec_module(om)
ofn = getattr(om, "_submission_entry", None) or om.agent
sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=1009)
a, b = sim.run_episode(fn, ofn)
print("OK", int(a), int(b))
'''


def probe(path, tape):
    """Does this file actually play a full game? Subprocess, so a crash or a
    hang in someone else's notebook cannot take the harness with it."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(PROBE % (ROOT, path, tape))
        probe_path = fh.name
    try:
        r = subprocess.run([PY, probe_path], capture_output=True, text=True,
                           timeout=180, cwd=ROOT)
        line = [l for l in r.stdout.splitlines() if l.startswith("OK")]
        if line:
            _, a, b = line[0].split()
            return int(a), int(b), None
        err = (r.stderr.strip().splitlines() or ["no output"])[-1]
        return None, None, err[:110]
    except subprocess.TimeoutExpired:
        return None, None, "timeout"
    finally:
        os.unlink(probe_path)


def main():
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    per_page = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    os.makedirs(OUTDIR, exist_ok=True)
    tape = os.path.join(ROOT, "opponents",
                        "kaggriculture-multi-route-farming-agent.py")

    refs = list_kernels(pages, per_page)
    print(f"{len(refs)} distinct public kernels listed", flush=True)

    seen_hash = set()
    for p in os.listdir(OUTDIR):
        if p.endswith(".py"):
            seen_hash.add(hashlib.sha256(
                open(os.path.join(OUTDIR, p), "rb").read()).hexdigest())

    index, kept, skipped = [], 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (ref, title) in enumerate(sorted(refs.items()), 1):
            slug = ref.replace("/", "__")
            d = os.path.join(tmp, slug)
            os.makedirs(d, exist_ok=True)
            try:
                subprocess.run([KAGGLE, "kernels", "pull", ref, "-p", d],
                               capture_output=True, text=True, timeout=180)
            except subprocess.TimeoutExpired:
                skipped += 1
                continue
            files = [os.path.join(d, f) for f in os.listdir(d)
                     if f.endswith((".py", ".ipynb"))]
            if not files:
                skipped += 1
                continue
            src = max((extract_source(f) for f in files), key=len)
            if len(src) < 2000 or "def agent" not in src:
                skipped += 1
                continue
            h = hashlib.sha256(src.encode()).hexdigest()
            if h in seen_hash:
                skipped += 1
                continue
            seen_hash.add(h)
            dest = os.path.join(OUTDIR, slug + ".py")
            open(dest, "w").write(src)
            a, b, err = probe(dest, tape)
            if err:
                os.unlink(dest)
                skipped += 1
                status = f"unusable ({err})"
            else:
                kept += 1
                index.append({"ref": ref, "title": title, "file": slug + ".py",
                              "vs_tape": [a, b]})
                status = f"OK  {a:,} v {b:,}"
            print(f"  [{i}/{len(refs)}] {ref[:52]:<52} {status}", flush=True)

    json.dump(index, open(os.path.join(OUTDIR, "INDEX.json"), "w"), indent=1)
    print(f"\nkept {kept} playable agents, skipped {skipped}")
    print(f"wrote {OUTDIR}")


if __name__ == "__main__":
    main()
