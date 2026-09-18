#!/usr/bin/env python3
"""Audit the reachable production bundle for the white-box contract.

This is a static dependency audit, not a gameplay score.  It follows the same
AST reachability used by ``package_whitebox.py`` and rejects replay/tape,
opponent-file, planner, and filesystem dependencies in the runtime closure.
Historical mining tools may still contain those words and imports; they are
outside the entry closure and are intentionally not audited as policy code.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.package_whitebox import reachable  # noqa: E402


FORBIDDEN_PARTS = (
    "replay", "tape", "opening", "schedule", "behavior", "weights",
    "ryo_targets", "opponents", "planner", "replays",
)
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__"}


def _forbidden_module(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in FORBIDDEN_PARTS)


def audit(entry: str, callable_name: str) -> dict[str, object]:
    sources = reachable(entry)
    errors: list[str] = []
    for name, source in sources.items():
        if _forbidden_module(name):
            errors.append(f"forbidden reachable module: {name}")
        if not source:
            continue
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                imported = []
            for imported_name in imported:
                if _forbidden_module(imported_name):
                    errors.append(
                        f"forbidden import in {name}: {imported_name}"
                    )
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in FORBIDDEN_CALLS):
                errors.append(
                    f"filesystem/dynamic call in {name}: {node.func.id}"
                )

    strategy_source = sources.get("whitebox.strategy", "")
    if strategy_source:
        strategy_tree = ast.parse(strategy_source, filename="whitebox.strategy")
        for node in ast.walk(strategy_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "decide":
                called = {
                    child.func.id for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                }
                if any(name in called for name in (
                        "_decide_from_replays", "_decide_from_schedule")):
                    errors.append(
                        "whitebox.strategy.decide calls a replay-derived branch"
                    )
                break

    return {
        "entry": entry,
        "callable": callable_name,
        "modules": tuple(sorted(sources)),
        "errors": tuple(dict.fromkeys(errors)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", required=True,
                        help="module path, e.g. whitebox.versions.v103_inserted_terminal_routes")
    parser.add_argument("--callable", required=True, dest="callable_name")
    args = parser.parse_args(argv)
    report = audit(args.entry, args.callable_name)
    print(f"entry: {report['entry']}")
    print(f"callable: {report['callable']}")
    print(f"reachable modules: {len(report['modules'])}")
    if report["errors"]:
        for error in report["errors"]:
            print(f"FAIL: {error}")
        return 1
    print("PASS: reachable runtime is white-box and filesystem-free")
    return 0


if __name__ == "__main__":
    sys.exit(main())
