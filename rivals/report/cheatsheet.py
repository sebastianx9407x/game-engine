"""Turn a solved bet policy into a strategy card a person can follow.

The policy table covers every balance and history, most of which never
happen. The card keeps only situations the policy actually reaches on the
recorded matches, merges neighbouring balances that get the same instruction,
and lists them most common first.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rivals.optimize.bet_policy import (
    BetPolicy,
    Scenarios,
    describe_key,
    policy_score,
    policy_trace,
)
from rivals.optimize.play_policy import chart_differences
from rivals.solver.basic import basic_chart


@dataclass(frozen=True)
class Rule:
    """One line of the card: in this situation, bet this."""

    round_index: int
    history: str
    low: float
    high: float
    action: str
    #: Share of all matches that reach this line.
    share: float

    @property
    def balance(self) -> str:
        if self.high == float("inf"):
            return f"{self.low:,.0f} or more"
        if self.low == self.high:
            return f"{self.low:,.0f}"
        return f"{self.low:,.0f}-{self.high:,.0f}"


def bet_rules(sc: Scenarios, policy: BetPolicy, min_share: float = 0.002) -> list[Rule]:
    """The policy's reachable situations as rules, dropping those rarer than ``min_share``.

    Balance ranges follow the policy's own balance levels: neighbouring levels
    are merged only when the policy gives them the same instruction, so a
    range never hides a different one. ``low``-``high`` covers every balance
    from ``low`` up to, but not including, the next range.
    """
    trace = policy_trace(sc, policy)
    grid = policy.grid
    rules: list[Rule] = []
    for r, step in enumerate(trace):
        alive = step["alive"]
        table = policy.tables[r]
        for key in np.unique(step["key"][alive]):
            mask = alive & (step["key"] == key)
            counts = np.bincount(step["level"][mask], minlength=len(grid))
            reached = np.flatnonzero(counts)
            start = int(reached[0])
            while start <= reached[-1]:
                end = start
                while end + 1 < len(grid) and table[key, end + 1] == table[key, start]:
                    end += 1
                share = counts[start : end + 1].sum() / sc.matches
                if share >= min_share:
                    top = grid[end + 1] - 5 if end + 1 < len(grid) else float("inf")
                    rules.append(
                        Rule(
                            r,
                            describe_key(int(key), r, policy.history),
                            float(grid[start]),
                            float(top),
                            policy.actions[int(table[key, start])].label,
                            float(share),
                        )
                    )
                start = end + 1
    return rules


def coverage(rules: list[Rule], round_index: int) -> float:
    """Share of matches whose situation in this round appears on the card."""
    return sum(rule.share for rule in rules if rule.round_index == round_index)


def render(sc: Scenarios, policy: BetPolicy, min_share: float = 0.005, title: str = "21 Rivals strategy card") -> str:
    """The strategy card as Markdown."""
    rules = bet_rules(sc, policy, min_share)
    legend = {"pattern": "results so far in order (W win, L loss, P push)",
              "count": "wins and losses so far", "none": "ignored"}[policy.history]
    lines = [
        f"# {title}",
        "",
        f"Scores {policy_score(sc, policy):.1%} (win + {policy.rules.tie_value:.3f} x tie) "
        f"on {sc.matches:,} simulated matches against the modelled field.",
        "",
        f"History = {legend}, judged by your main bet only. "
        "Only situations the strategy actually reaches are listed; rare ones are left out. "
        "If your balance falls between two lines, use the line below it.",
    ]
    for r in range(sc.rounds):
        chosen = sorted((x for x in rules if x.round_index == r), key=lambda x: -x.share)
        lines += ["", f"## Hand {r + 1}", "", "| History | Balance | Do this | How often |", "|---|---|---|---|"]
        for rule in chosen:
            lines.append(f"| {rule.history} | {rule.balance} | {rule.action} | {rule.share:.1%} |")
        lines.append("")
        lines.append(f"Covers {coverage(rules, r):.0%} of matches at this hand.")
    basic = basic_chart(policy.rules)
    lines += ["", "## Play", "", "Play basic strategy unless the bet line says otherwise:", "", "```", basic.render(), "```"]
    for name, chart in zip(policy.style_names, policy.style_charts):
        if chart is None:
            continue
        lines += ["", f"\"play {name}\" changes these cells:", ""]
        lines += [f"- {line}" for line in chart_differences(chart, basic)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the strategy card for the saved policy, measured on freshly recorded matches."""
    import argparse
    import os
    from pathlib import Path

    from rivals.optimize.bet_policy import build_scenarios
    from rivals.optimize.pipeline import DEFAULT_POLICY_PATH, load_policy
    from rivals.optimize.play_policy import styles_of
    from rivals.optimize.population import default_population

    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(prog="python -m rivals.report.cheatsheet")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--matches", type=int, default=60_000)
    parser.add_argument("--seed", type=int, default=90_000_000)
    parser.add_argument("--processes", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--min-share", type=float, default=0.005)
    parser.add_argument("--out", type=Path, default=repo / "docs" / "STRATEGY_CARD.md")
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    styles = styles_of(policy)  # the charts the policy was solved with, not today's defaults
    sc = build_scenarios(
        default_population(policy.rules), args.matches, seed=args.seed,
        rules=policy.rules, processes=args.processes, styles=styles,
    )
    args.out.write_text(render(sc, policy, args.min_share))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
