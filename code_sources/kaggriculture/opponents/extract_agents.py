"""Extract the agent source out of the uploaded reference notebooks.

Deliberately does NOT run the notebooks' own bootstrap cells (they write
main.py / build submission tarballs / shell out to pip). Instead it pulls the
payload *string literal* out with `ast`, decodes it here, and writes plain .py
files we can then read before anything executes.
"""
import ast
import base64
import glob
import json
import os
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def literal_assignments(src):
    """{name: value} for every top-level assignment whose RHS is a pure literal
    expression (string concat / "".join((...)) etc). Anything involving a call
    to something other than str.join, or any import/exec, is skipped."""
    out = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        try:
            out[tgt.id] = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            # handle "".join((...)) which literal_eval rejects
            v = node.value
            if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                    and v.func.attr == "join" and isinstance(v.func.value, ast.Constant)):
                try:
                    parts = ast.literal_eval(v.args[0])
                    out[tgt.id] = v.func.value.value.join(parts)
                except Exception:
                    pass
    return out


def decode_payload(name, value):
    """Try the two packings used by these notebooks."""
    if not isinstance(value, str) or len(value) < 5000:
        return None
    for label, fn in (("b85+zlib", lambda s: zlib.decompress(base64.b85decode(s))),
                      ("b64", lambda s: base64.b64decode(s))):
        try:
            raw = fn(value)
            text = raw.decode("utf-8")
            if "def agent" in text:
                return label, text
        except Exception:
            continue
    return None


def extract(nb_path):
    nb = json.load(open(nb_path, encoding="utf-8"))
    cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
    for idx, cell in enumerate(cells):
        src = "".join(cell.get("source", []))
        for name, value in literal_assignments(src).items():
            got = decode_payload(name, value)
            if got:
                label, text = got
                stem = os.path.basename(nb_path).replace(".ipynb", "")
                out = os.path.join(HERE, f"{stem}.py")
                with open(out, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"{os.path.basename(nb_path):<50} cell{idx} {name} [{label}] -> "
                      f"{os.path.basename(out)} ({len(text):,} chars)")
                return out
    # A `%%writefile main.py` cell IS the agent: its body is written verbatim
    # as the submission. Prefer it over concatenating every cell, which mixes
    # in plotting/validation code and IPython magics that will not parse.
    for idx, cell in enumerate(cells):
        src = "".join(cell.get("source", []))
        first = src.lstrip().split("\n", 1)
        if first and first[0].startswith("%%writefile") and len(first) > 1:
            body = first[1]
            if "def agent" in body:
                stem = os.path.basename(nb_path).replace(".ipynb", "")
                out = os.path.join(HERE, f"{stem}.py")
                with open(out, "w", encoding="utf-8") as f:
                    f.write(body)
                print(f"{os.path.basename(nb_path):<50} cell{idx} %%writefile -> "
                      f"{os.path.basename(out)} ({len(body):,} chars)")
                return out

    # no packed payload: maybe the notebook defines `agent` in plain source
    joined = "\n\n".join("".join(c.get("source", [])) for c in cells)
    if "def agent" in joined:
        stem = os.path.basename(nb_path).replace(".ipynb", "")
        out = os.path.join(HERE, f"{stem}.py")
        with open(out, "w", encoding="utf-8") as f:
            f.write(joined)
        print(f"{os.path.basename(nb_path):<50} plain source -> {os.path.basename(out)} ({len(joined):,} chars)")
        return out
    print(f"{os.path.basename(nb_path):<50} no agent payload found")
    return None


if __name__ == "__main__":
    for nb in sorted(glob.glob(os.path.join(HERE, "*.ipynb"))):
        extract(nb)
