"""Append the CART route layer to an EXISTING agent file, changing nothing else.

WHY NOT `route.bake`. Baking copies a base and re-generates every layer from the
current generators. The v3 submission's market layer was emitted by an older
`pbt/intervene.py` -- it has no `_IV_STRUCT`, `_IV_MIN_PRICE` or `_IV_STAGED` --
so re-baking it would silently swap in a different market layer and the result
would no longer be "the same agent with a tree instead of an array". This tool
copies the file BYTE FOR BYTE and appends one block.

THE TREE IS FITTED TO THE FILE BEING TREEIFIED, never to `logs/tape/tables.json`
and never to kawa. `treeroute_src` re-reads the ten arrays out of the target
module itself, so the tape and the tree cannot drift apart.

ENTRY-POINT HAZARD, and why this is safe (HANDOFF rule 3). Kaggle resolves a
file agent with `get_last_callable`, which walks the namespace in INSERTION
order, so rebinding a name does not move it. A file that already ends in
`_submission_entry` keeps that name's ORIGINAL position, and the last *newly*
defined callable becomes `_treeroute_entry` from the appended block. That is
fine only because `_treeroute_entry(obs)` takes one argument and delegates to
`agent`, exactly like the stub it displaces -- kaggle_environments passes one
argument to a one-argument callable. It is checked, not assumed: `--check`
reports which callable Kaggle would pick.

    python pbt/treeify.py <in.py> <out.py> [--check]
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)


def last_callable(path):
    """What `get_last_callable` would pick: the last callable by insertion order."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("treeify_probe", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    picked = None
    for name, value in vars(m).items():          # dicts preserve insertion order
        if callable(value) and not name.startswith("__"):
            picked = (name, value)
    return picked


def treeify(src, dst):
    from pbt.treeroute import treeroute_src
    if os.path.abspath(src) == os.path.abspath(dst):
        raise SystemExit("refusing to treeify a file onto itself")
    block = treeroute_src(src)                   # fit to THIS file's tables
    shutil.copyfile(src, dst)                    # byte-for-byte, then append
    with open(dst, "a") as f:
        f.write(block)
    return dst


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[-1].strip())
    src, dst = sys.argv[1], sys.argv[2]
    before = last_callable(src)
    out = treeify(src, dst)
    print(f"{src} ({os.path.getsize(src):,} bytes)")
    print(f"  -> {out} ({os.path.getsize(out):,} bytes)")
    print(f"  Kaggle entry before: {before[0] if before else None}")
    if "--check" in sys.argv[3:]:
        after = last_callable(out)
        print(f"  Kaggle entry after:  {after[0] if after else None}")
        if after is None:
            raise SystemExit("no callable found -- the file would not load")
        import inspect
        try:
            n = len([p for p in inspect.signature(after[1]).parameters.values()
                     if p.default is inspect.Parameter.empty
                     and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        except (TypeError, ValueError):
            n = -1
        print(f"  required positional args: {n}  (must be 1)")
        if n != 1:
            raise SystemExit("the entry point Kaggle would pick is not agent(obs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
