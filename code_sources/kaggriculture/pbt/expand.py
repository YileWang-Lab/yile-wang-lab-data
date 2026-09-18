"""Expand every compressed blob in an agent file into readable literal source.

The v3 lineage ships twelve `json.loads(zlib.decompress(base64.b85decode(...)))`
one-liners: the ten route tables and the two market tapes `_V17_R5_MARKETS` and
`_V17_MD_MARKETS`. Each is a 10 KB wall of b85 that no one can read, diff or
edit. This rewrites them as plain Python literals, one row per line with its
step number, and changes nothing else in the file.

    python pbt/expand.py <in.py> <out.py> [--check]

FOUND BY AST, NOT BY REGEX. Blob assignments are located with `ast`: any
module-level assignment whose value contains a `b85decode`/`b64decode` call,
whatever it is named and however many source lines it spans (the route tables
are one line each, the market tapes are three). A regex over `_ACTIONS_` would
have silently skipped the market pair, which is precisely the thing the user
asked for and precisely the thing a name-based match loses.

VALUES COME FROM EXECUTING THE FILE, so what gets written is what the file
actually produced -- not a re-derivation, not a snapshot from `logs/`. If the
blob and the expansion could disagree, the expansion would be a behaviour change
wearing a formatting diff.

THE LITERALS ARE JSON, WHICH IS ALSO PYTHON here. These structures are lists,
dicts, strings and ints only; JSON's spelling of those is Python's spelling.
`_render` asserts that -- if a `True`/`False`/`None` ever appears it falls back
to `repr`, because `true`/`false`/`null` are not Python and would fail at
import rather than quietly.

COST. Expanded, the file goes from ~155 KB to ~1.5 MB and the import stops being
a zlib decode and starts being a parse of 1.5 MB of source. A Kaggle agent has an
init budget, so `--check` MEASURES import time both ways instead of assuming the
trade is free. Read the number before shipping an expanded file; the compact one
is not worse, it is just unreadable.
"""
import ast
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

DECODERS = ("b85decode", "b64decode", "a85decode", "decompress")
_loads = [0]


def _load(path):
    _loads[0] += 1
    spec = importlib.util.spec_from_file_location(
        "expand_%d_%d" % (os.getpid(), _loads[0]), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def find_blobs(src):
    """[(name, first_line, last_line)] for every module-level blob assignment.

    1-indexed and inclusive, matching `ast`'s own convention so the caller can
    slice source lines without off-by-one arithmetic.
    """
    out = []
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        for sub in ast.walk(node.value):
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in DECODERS):
                out.append((target.id, node.lineno, node.end_lineno))
                break
    return out


def _literal(obj):
    """A Python literal for `obj`, preferring JSON's spelling where it is legal."""
    def clean(o):
        if isinstance(o, bool) or o is None:
            return False
        if isinstance(o, dict):
            return all(clean(k) and clean(v) for k, v in o.items())
        if isinstance(o, (list, tuple)):
            return all(clean(v) for v in o)
        return isinstance(o, (str, int, float))
    return json.dumps(obj, separators=(", ", ": ")) if clean(obj) else repr(obj)


def _render(name, value):
    """`name = <literal>` as source lines. Long row-lists get one row per line."""
    if isinstance(value, list) and len(value) > 32:
        rows = ["%s = [" % name]
        width = len(str(len(value) - 1))
        for i, row in enumerate(value):
            rows.append("    %s,%s# %*d"
                        % (_literal(row), " " * 2, width, i))
        rows.append("]")
        return rows
    return ["%s = %s" % (name, _literal(value))]


def expand(src_path, dst_path):
    if os.path.abspath(src_path) == os.path.abspath(dst_path):
        raise SystemExit("refusing to expand a file onto itself")
    src = open(src_path).read()
    module = _load(src_path)                     # values as the file produces them
    blobs = find_blobs(src)
    if not blobs:
        raise SystemExit("no blobs found in %s" % src_path)

    lines = src.splitlines()
    out, cursor, done = [], 0, []
    for name, lo, hi in sorted(blobs, key=lambda b: b[1]):
        out.extend(lines[cursor:lo - 1])         # untouched source before the blob
        value = getattr(module, name)
        out.extend(_render(name, value))
        cursor = hi
        done.append((name, type(value).__name__, len(value)))
    out.extend(lines[cursor:])

    with open(dst_path, "w") as f:
        f.write("\n".join(out) + "\n")
    return done


def _import_seconds(path, n=5):
    """Median COLD import wall time -- fresh directory, no bytecode cache.

    Measured cold on purpose. A warm `__pycache__` makes the expanded file look
    73% FASTER than the compact one, because the 1.5 MB parse is cached to .pyc
    while the compact file's zlib+json decode has to run at every import. That
    number is an artifact: Kaggle writes the submission and imports it, so the
    parse is paid. Cold, expansion costs ~8x. Never quote the warm figure.
    """
    import shutil
    import tempfile
    import time
    times = []
    for i in range(n):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "cold_%d.py" % i)
            shutil.copyfile(path, p)
            t0 = time.time()
            spec = importlib.util.spec_from_file_location("cold_%d_%d" % (os.getpid(), i), p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            times.append(time.time() - t0)
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return sorted(times)[len(times) // 2]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[4].strip())
    src, dst = sys.argv[1], sys.argv[2]
    done = expand(src, dst)
    print("%s (%d bytes)" % (src, os.path.getsize(src)))
    print("  -> %s (%d bytes, x%.1f)"
          % (dst, os.path.getsize(dst),
             os.path.getsize(dst) / float(os.path.getsize(src))))
    print("  expanded %d blobs:" % len(done))
    for name, kind, n in done:
        print("    %-38s %-5s %d rows" % (name, kind, n))

    if "--check" in sys.argv[3:]:
        before, after = _load(src), _load(dst)
        bad = []
        for name, _kind, _n in done:
            a = json.dumps(getattr(before, name), sort_keys=True)
            b = json.dumps(getattr(after, name), sort_keys=True)
            if a != b:
                bad.append(name)
        print("  values identical: %d/%d%s"
              % (len(done) - len(bad), len(done),
                 "" if not bad else "   MISMATCH: " + ", ".join(bad)))
        t_src, t_dst = _import_seconds(src), _import_seconds(dst)
        print("  COLD import   compact %.3fs   expanded %.3fs   (%+.1f%%, x%.1f)"
              % (t_src, t_dst, 100.0 * (t_dst - t_src) / max(t_src, 1e-9),
                 t_dst / max(t_src, 1e-9)))
        if bad:
            raise SystemExit("expansion changed a value -- do not use this file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
