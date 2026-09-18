#!/usr/bin/env python3
"""Build a self-contained Kaggle file from a modular white-box version.

The output embeds the exact reachable Python sources without minification,
learned parameters, replay data, or opponent files.  A tiny import hook exposes
those sources under their original module names so the submitted program runs
the same code that the local arena validates.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = ("whitebox", "route")


def _module_path(name: str) -> Path | None:
    path = ROOT.joinpath(*name.split("."))
    package = path / "__init__.py"
    if package.is_file():
        return package
    module = path.with_suffix(".py")
    return module if module.is_file() else None


def _local_name(name: str) -> bool:
    return any(name == package or name.startswith(package + ".")
               for package in LOCAL_PACKAGES)


def _resolve_from(current: str, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    parts = current.split(".")
    current_path = _module_path(current)
    if current_path is not None and current_path.name != "__init__.py":
        parts = parts[:-1]
    keep = max(0, len(parts) - (node.level - 1))
    base = parts[:keep]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _dependencies(name: str, source: str) -> set[str]:
    deps: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=str(_module_path(name)))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _local_name(alias.name) and _module_path(alias.name):
                    deps.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(name, node)
            if _local_name(base) and _module_path(base):
                deps.add(base)
            for alias in node.names:
                child = base + "." + alias.name if base else alias.name
                if _local_name(child) and _module_path(child):
                    deps.add(child)
    return deps


def reachable(entry: str) -> dict[str, str]:
    todo = [entry]
    sources: dict[str, str] = {}
    while todo:
        name = todo.pop()
        if name in sources:
            continue
        path = _module_path(name)
        if path is None:
            raise ValueError(f"local module not found: {name}")
        source = path.read_text(encoding="utf-8")
        sources[name] = source
        todo.extend(sorted(_dependencies(name, source) - sources.keys(),
                           reverse=True))

        # Queue real parent packages even when the entry imports a leaf.
        pieces = name.split(".")
        for cut in range(1, len(pieces)):
            parent = ".".join(pieces[:cut])
            if parent not in sources and _module_path(parent):
                todo.append(parent)
    # ``whitebox.versions`` is deliberately a namespace directory with no
    # __init__.py. A standalone bundle still needs a synthetic package so
    # importlib can reach its embedded version leaf.
    for name in list(sources):
        pieces = name.split(".")
        for cut in range(1, len(pieces)):
            sources.setdefault(".".join(pieces[:cut]), "")
    return dict(sorted(sources.items()))


def render(entry: str, callable_name: str, sources: dict[str, str]) -> str:
    package_names = sorted(
        name for name in sources
        if any(other.startswith(name + ".") for other in sources)
    )
    lines = [
        f'"""Generated transparent Kaggriculture bundle for {entry}."""',
        "# This file contains only reachable whitebox/ and route/ production source.",
        "# It contains no tape, replay, identity lookup, fitted weights, or opponent code.",
        "import importlib.abc as _bundle_abc",
        "import importlib.util as _bundle_util",
        "import sys as _bundle_sys",
        "",
        f"_BUNDLE_PACKAGES = {set(package_names)!r}",
        "_BUNDLE_SOURCES = {}",
    ]
    for name, source in sources.items():
        lines.append(f"_BUNDLE_SOURCES[{name!r}] = {source!r}")
    lines.extend([
        "",
        "class _WhiteboxBundleLoader(_bundle_abc.Loader):",
        "    def create_module(self, spec):",
        "        return None",
        "",
        "    def exec_module(self, module):",
        "        name = module.__spec__.name",
        "        filename = '<whitebox-bundle>/' + name.replace('.', '/') + '.py'",
        "        module.__file__ = filename",
        "        exec(compile(_BUNDLE_SOURCES[name], filename, 'exec'), module.__dict__)",
        "",
        "",
        "class _WhiteboxBundleFinder(_bundle_abc.MetaPathFinder):",
        "    def find_spec(self, fullname, path=None, target=None):",
        "        if fullname not in _BUNDLE_SOURCES:",
        "            return None",
        "        return _bundle_util.spec_from_loader(",
        "            fullname, _WhiteboxBundleLoader(),",
        "            is_package=fullname in _BUNDLE_PACKAGES)",
        "",
        "",
        "_bundle_sys.meta_path.insert(0, _WhiteboxBundleFinder())",
        f"from {entry} import {callable_name} as _WHITEBOX_ENTRY",
        "",
        "",
        "def kaggriculture_agent(observation, configuration=None):",
        "    # The modular white-box API depends only on the live observation.",
        "    return _WHITEBOX_ENTRY(observation)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", required=True,
                        help="entry module, e.g. whitebox.versions.v199_spatial_route_multistart")
    parser.add_argument("--callable", required=True, dest="callable_name")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sources = reachable(args.entry)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.entry, args.callable_name, sources),
                      encoding="utf-8")
    total = sum(len(source.encode("utf-8")) for source in sources.values())
    print(f"wrote {output} with {len(sources)} modules / {total} source bytes")
    for name in sources:
        print(name)


if __name__ == "__main__":
    main()
