"""Append the flat route layer to an EXISTING agent file, changing nothing else.

Same contract as `pbt/treeify.py`, which this replaces for new work -- read that
file's docstring for why baking is wrong here (v3's market layer came from an
older `pbt/intervene.py` and `route.bake` would silently swap it) and for the
`get_last_callable` hazard. The short version:

  COPY, DON'T BAKE     the source file is copied byte-for-byte and one block is
                       appended. `head -c <n> out.py | cmp - in.py` is silent.
  FIT TO THE TARGET    `flatroute_src` re-reads the ten arrays out of the file
                       being flattened, so the tape and the array cannot drift.
  ENTRY POINT          Kaggle walks the namespace in INSERTION order, so the
                       last *newly defined* callable wins -- `_flatroute_entry`,
                       which takes one argument and delegates to `agent`, same
                       as the stub it displaces. `--check` verifies rather than
                       assumes.

    python pbt/flatify.py <in.py> <out.py> [--check]
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from pbt.treeify import last_callable  # noqa: E402  same resolution rule


def flatify(src, dst):
    from pbt.flatroute import flatroute_src
    if os.path.abspath(src) == os.path.abspath(dst):
        raise SystemExit("refusing to flatify a file onto itself")
    block = flatroute_src(src)                   # fit to THIS file's tables
    shutil.copyfile(src, dst)                    # byte-for-byte, then append
    with open(dst, "a") as f:
        f.write(block)
    return dst


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[-1].strip())
    src, dst = sys.argv[1], sys.argv[2]
    before = last_callable(src)
    out = flatify(src, dst)
    print("%s (%d bytes)" % (src, os.path.getsize(src)))
    print("  -> %s (%d bytes, +%d)"
          % (out, os.path.getsize(out), os.path.getsize(out) - os.path.getsize(src)))
    print("  Kaggle entry before: %s" % (before[0] if before else None))
    if "--check" in sys.argv[3:]:
        after = last_callable(out)
        print("  Kaggle entry after:  %s" % (after[0] if after else None))
        if after is None:
            raise SystemExit("no callable found -- the file would not load")
        import inspect
        try:
            n = len([p for p in inspect.signature(after[1]).parameters.values()
                     if p.default is inspect.Parameter.empty
                     and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        except (TypeError, ValueError):
            n = -1
        print("  required positional args: %d  (must be 1)" % n)
        if n != 1:
            raise SystemExit("the entry point Kaggle would pick is not agent(obs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
