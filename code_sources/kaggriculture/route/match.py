"""Shared Kaggriculture match helpers.

This keeps the repeated boilerplate for:
- loading a fresh candidate module per episode,
- resolving opponent specs,
- running one seeded Kaggriculture episode,
- and reading the final money values.

The helper is intentionally tiny and deterministic so the existing batch,
tournament, and evaluator scripts can share it without changing policy logic.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

from kaggle_environments import make

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPISODE_STEPS = 720
BASE_OPPONENT = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")

_COUNTER = 0


@dataclass(frozen=True)
class MatchResult:
    me: float
    opp: float
    # Kaggle can still expose plausible final money after an agent error. Keep
    # statuses with the money so callers can exclude forfeits instead of
    # silently treating them as ordinary losses.
    status: tuple[str, ...] = ()

    @property
    def done(self) -> bool:
        return all(value == "DONE" for value in self.status)


def load_module(path: str, prefix: str = "cand", params: dict | None = None):
    global _COUNTER
    _COUNTER += 1
    spec = importlib.util.spec_from_file_location(f"{prefix}_{_COUNTER}_{os.getpid()}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for key, value in (params or {}).items():
        if key.startswith("_"):
            setattr(mod, key, value)
    return mod


def run_episode(candidate, opponent, seed: int, seat: int = 0) -> MatchResult:
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": EPISODE_STEPS, "seed": int(seed)},
        debug=False,
    )
    pair = [candidate, opponent] if seat == 0 else [opponent, candidate]
    env.run(pair)
    final = env.steps[-1]
    status = tuple(str(getattr(player, "status", "")) for player in final)
    return MatchResult(
        me=float(final[seat].observation["farms"][seat]["money"]),
        opp=float(final[1 - seat].observation["farms"][1 - seat]["money"]),
        status=status,
    )


def seat_pair(candidate, opponent, seat: int):
    return [candidate, opponent] if seat == 0 else [opponent, candidate]
