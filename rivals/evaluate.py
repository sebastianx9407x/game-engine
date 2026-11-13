"""Score a tactic against the field.

    python -m rivals.evaluate tactics/my_idea.py
    python -m rivals.evaluate tactics/my_idea.py --matches 200000 --baseline tactics/other.py
    python -m rivals.evaluate tactics/my_idea.py --vs tactics/other.py

A tactic file is a Python file defining an `Agent` subclass (see
tactics/_template.py). The report gives the chance of winning, tying and
losing against the simulated DraftKings field, the same split by opponent
type, and a paired comparison with a baseline tactic on identical matches.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from rivals.agents.base import Agent
from rivals.match import AgentFactory, SimulationResult, Tally, simulate
from rivals.rules import DEFAULT_RULES, RulesConfig

_LOADED: dict[str, type[Agent]] = {}


def load_tactic(spec: str) -> type[Agent]:
    """The `Agent` subclass in a tactic file.

    ``spec`` is a path, optionally followed by ``:ClassName``. Without a class
    name the file must define a class called ``Tactic`` or exactly one
    `Agent` subclass.
    """
    cached = _LOADED.get(spec)
    if cached is not None:
        return cached
    path_text, _, class_name = spec.partition(":")
    path = Path(path_text).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"no tactic file at {path}")
    module_name = f"rivals_tactic_{abs(hash(str(path)))}"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    if class_name:
        cls = getattr(module, class_name)
    elif hasattr(module, "Tactic"):
        cls = module.Tactic
    else:
        found = [
            obj
            for obj in vars(module).values()
            if isinstance(obj, type) and issubclass(obj, Agent) and obj.__module__ == module_name
        ]
        if len(found) != 1:
            raise ValueError(
                f"{path.name} defines {len(found)} Agent subclasses; name one as path:ClassName "
                "or call it Tactic"
            )
        cls = found[0]
    if not (isinstance(cls, type) and issubclass(cls, Agent)):
        raise TypeError(f"{spec} is not an Agent subclass")
    _LOADED[spec] = cls
    return cls


class TacticFactory:
    """Builds a tactic from its file; picklable, so it works across processes."""

    def __init__(self, spec: str) -> None:
        self.spec = spec

    def __call__(self, rng: random.Random) -> Agent:
        return load_tactic(self.spec)()

    @property
    def label(self) -> str:
        return load_tactic(self.spec)().label


class BaselineFactory:
    """The reference player: minimum bet every hand, basic strategy, no side bets."""

    label = "flat-min basic strategy"

    def __call__(self, rng: random.Random) -> Agent:
        return Agent()


@dataclass
class Comparison:
    """Tactic minus baseline on the same matches."""

    baseline_label: str
    baseline: Tally
    score_gain: float
    score_gain_stderr: float

    @property
    def significant(self) -> bool:
        return abs(self.score_gain) > 1.96 * self.score_gain_stderr


@dataclass
class Report:
    label: str
    opponent_label: str
    rules: RulesConfig
    result: SimulationResult
    comparisons: list[Comparison]

    @property
    def total(self) -> Tally:
        return self.result.total


def _paired_gain(a: list[int], b: list[int], tie_value: float) -> tuple[float, float]:
    def score(outcome: int) -> float:
        return 1.0 if outcome > 0 else (tie_value if outcome == 0 else 0.0)

    diffs = [score(x) - score(y) for x, y in zip(a, b)]
    n = len(diffs)
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / max(n - 1, 1)
    return mean, math.sqrt(var / n)


def evaluate(
    tactic: AgentFactory,
    opponents: AgentFactory | None = None,
    *,
    matches: int = 20_000,
    seed: int = 0,
    processes: int = 1,
    rules: RulesConfig = DEFAULT_RULES,
    baselines: list[AgentFactory] | None = None,
    label: str | None = None,
    opponent_label: str = "the field",
) -> Report:
    """Simulate ``tactic`` against ``opponents`` (default: the archetype population).

    Each baseline plays the very same matches (same cards, same opponents with
    the same random streams), so the reported gain over a baseline is far
    less noisy than comparing two separate runs.
    """
    if opponents is None:
        from rivals.optimize.population import default_population

        opponents = default_population(rules)
    if baselines is None:
        baselines = [BaselineFactory()]
    kwargs = dict(seed=seed, rules=rules, processes=processes, keep_outcomes=True)
    result = simulate(tactic, opponents, matches, **kwargs)
    comparisons = []
    for baseline in baselines:
        base = simulate(baseline, opponents, matches, **kwargs)
        gain, stderr = _paired_gain(result.outcomes, base.outcomes, rules.tie_value)
        comparisons.append(
            Comparison(getattr(baseline, "label", "baseline"), base.total, gain, stderr)
        )
    name = label or getattr(tactic, "label", None) or "tactic"
    return Report(name, opponent_label, rules, result, comparisons)


# --- text report ------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def _rate(tally: Tally, rate: float) -> str:
    low, high = tally.interval(rate)
    return f"{_pct(rate)}  ({100 * low:.1f}-{100 * high:.1f})"


def format_report(report: Report) -> str:
    rules = report.rules
    t = report.total
    lines = [
        f"{report.label} vs {report.opponent_label}: {t.matches:,} matches",
        "",
        f"  win   {_rate(t, t.p_win)}",
        f"  tie   {_rate(t, t.p_tie)}",
        f"  loss  {_rate(t, t.p_loss)}",
        "",
        f"  score (win + {rules.tie_value:.3f} x tie)   {_pct(t.score(rules))}  "
        f"+- {100 * 1.96 * t.score_stderr(rules):.1f}",
        f"  profit per $1 entry           {t.profit_per_entry(rules):+.3f}",
        f"  average final balance         {t.balance_sum / t.matches:,.0f}"
        f"   (opponents {t.opponent_balance_sum / t.matches:,.0f})",
    ]
    if len(report.result.by_opponent) > 1:
        lines += ["", "  by opponent type           share    win    tie   loss   score"]
        rows = sorted(report.result.by_opponent.items(), key=lambda kv: -kv[1].matches)
        for name, tally in rows:
            lines.append(
                f"    {name:<24} {_pct(tally.matches / t.matches)} {_pct(tally.p_win)} "
                f"{_pct(tally.p_tie)} {_pct(tally.p_loss)}  {_pct(tally.score(rules))}"
            )
    for comp in report.comparisons:
        verdict = "better" if comp.score_gain > 0 else "worse"
        if not comp.significant:
            verdict = "no clear difference"
        lines += [
            "",
            f"  against {comp.baseline_label} on the same matches:",
            f"    its score {_pct(comp.baseline.score(rules))}, "
            f"profit per $1 {comp.baseline.profit_per_entry(rules):+.3f}",
            f"    gain {100 * comp.score_gain:+.2f} points "
            f"+- {100 * 1.96 * comp.score_gain_stderr:.2f}  ->  {verdict}",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rivals.evaluate", description="Score a tactic file against the field."
    )
    parser.add_argument("tactic", help="path to a tactic file, optionally path.py:ClassName")
    parser.add_argument("--matches", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--processes", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1))
    )
    parser.add_argument("--vs", help="play against this tactic file instead of the field")
    parser.add_argument(
        "--baseline",
        action="append",
        default=[],
        help="tactic file to compare with on the same matches (repeatable); "
        "the flat-min basic-strategy player is always included",
    )
    parser.add_argument("--decks", type=int, help="override the number of decks")
    args = parser.parse_args(argv)

    rules = DEFAULT_RULES if args.decks is None else DEFAULT_RULES.with_(num_decks=args.decks)
    tactic = TacticFactory(args.tactic)
    opponents = TacticFactory(args.vs) if args.vs else None
    baselines: list[AgentFactory] = [BaselineFactory()] + [TacticFactory(b) for b in args.baseline]
    report = evaluate(
        tactic,
        opponents,
        matches=args.matches,
        seed=args.seed,
        processes=args.processes,
        rules=rules,
        baselines=baselines,
        label=tactic.label,
        opponent_label=opponents.label if opponents else "the field",
    )
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
