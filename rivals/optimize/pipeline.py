"""End-to-end optimisation: record matches, search the bet schedule, check it, save it.

    python -m rivals.optimize.pipeline --matches 200000

writes ``tactics/optimized_policy.pkl`` and prints how the result scores on
matches it was not fitted to. ``tactics/optimized.py`` loads that file, so
the optimised strategy can be scored like any other tactic:

    python -m rivals.evaluate tactics/optimized.py
"""

from __future__ import annotations

import argparse
import os
import pickle
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from rivals.match import AgentFactory
from rivals.optimize.bet_policy import (
    BasicPlay,
    BetAction,
    BetPolicy,
    Scenarios,
    build_scenarios,
    default_actions,
    describe_key,
    policy_score,
    solve_bet_policy,
)
from rivals.optimize.play_policy import ChartPlay
from rivals.rules import DEFAULT_RULES, RulesConfig

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "tactics" / "optimized_policy.pkl"
#: Held-out matches use seeds far from the training ones.
HOLDOUT_OFFSET = 50_000_000


def default_styles(tolerance: float = 0.03) -> tuple:
    return (BasicPlay(), ChartPlay("seek", "seek", tolerance), ChartPlay("avoid", "avoid", tolerance))


def actions_with_styles(styles: tuple) -> list[BetAction]:
    """The default bets, plus every pure main bet again under each extra play style."""
    actions = default_actions()
    mains = [a for a in actions if not (a.pairs or a.total or a.pairs_rest or a.total_rest)]
    for index, style in enumerate(styles[1:], start=1):
        actions += [replace(a, style=index, label=f"{a.label}, play {style.name}") for a in mains]
    return actions


@dataclass
class Optimized:
    policy: BetPolicy
    #: Score by history mode: (on the matches it was solved from, on the selection half of the hold-out).
    scores: dict[str, tuple[float, float]]
    #: Score of the chosen policy on the half of the hold-out that played no part in choosing it.
    final_score: float
    train: Scenarios
    holdout: Scenarios


def optimize(
    opponents: AgentFactory | None = None,
    *,
    matches: int = 200_000,
    holdout_matches: int = 100_000,
    seed: int = 0,
    opponents_per_match: int = 2,
    processes: int = 1,
    rules: RulesConfig = DEFAULT_RULES,
    histories: tuple[str, ...] = ("pattern", "count", "none"),
    styles: tuple | None = None,
    log=print,
) -> Optimized:
    """Search for the best bet schedule against ``opponents`` (default: the archetype population).

    Each history mode is solved on the training matches. Half of the held-out
    matches pick the best mode; the other half, which influenced nothing,
    gives the score to quote (`final_score`).
    """
    if opponents is None:
        from rivals.optimize.population import default_population

        opponents = default_population(rules)
    styles = default_styles() if styles is None else styles
    for style in styles:
        style.policy(rules)  # solve charts here so worker processes receive them ready-made

    started = time.time()
    common = dict(opponents_per_match=opponents_per_match, rules=rules, processes=processes, styles=styles)
    train = build_scenarios(opponents, matches, seed=seed, **common)
    holdout = build_scenarios(opponents, holdout_matches, seed=seed + HOLDOUT_OFFSET, **common)
    log(f"recorded {matches:,} + {holdout_matches:,} matches in {time.time() - started:.0f}s")

    half = holdout.matches // 2
    select = holdout.subset(np.arange(half))
    untouched = holdout.subset(np.arange(half, holdout.matches))

    actions = actions_with_styles(styles)
    charts = tuple(getattr(style, "chart", lambda r: None)(rules) for style in styles)
    scores: dict[str, tuple[float, float]] = {}
    best: BetPolicy | None = None
    best_score = -1.0
    for mode in histories:
        started = time.time()
        policy = solve_bet_policy(train, actions=actions, history=mode)
        policy.style_charts = charts
        held = policy_score(select, policy)
        scores[mode] = (policy.expected_score, held)
        log(f"history={mode}: score {policy.expected_score:.4f} fitted, {held:.4f} held out "
            f"({time.time() - started:.0f}s)")
        if held > best_score:
            best, best_score = policy, held
    final = policy_score(untouched, best)
    log(f"chosen: history={best.history}, score {final:.4f} on {untouched.matches:,} untouched matches")
    return Optimized(best, scores, final, train, holdout)


def save_policy(policy: BetPolicy, path: Path = DEFAULT_POLICY_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(policy, f)
    return path


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> BetPolicy:
    with open(path, "rb") as f:
        return pickle.load(f)


def describe_opening(policy: BetPolicy, max_rows: int = 12) -> str:
    """The first two hands of the schedule in words."""
    start = policy.rules.starting_chips
    lines = [f"hand 1: {policy.action(0, 0, start).label}"]
    table = policy.tables[1]
    shown = 0
    for key in range(table.shape[0]):
        for balance in (800, 900, 1000, 1100, 1200, 1500):
            if shown >= max_rows:
                break
            label = policy.action(1, key, balance).label
            lines.append(f"hand 2, after {describe_key(key, 1, policy.history)}, balance {balance}: {label}")
            shown += 1
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rivals.optimize.pipeline")
    parser.add_argument("--matches", type=int, default=200_000)
    parser.add_argument("--holdout", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--processes", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--out", type=Path, default=DEFAULT_POLICY_PATH)
    args = parser.parse_args(argv)
    result = optimize(
        matches=args.matches, holdout_matches=args.holdout, seed=args.seed, processes=args.processes
    )
    path = save_policy(result.policy, args.out)
    print(f"\nbest history mode: {result.policy.history}")
    print(describe_opening(result.policy))
    print(f"\nsaved to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
