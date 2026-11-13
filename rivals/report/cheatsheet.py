"""Turn a solved bet policy into a strategy card a person can follow.

The policy table covers every balance and history, most of which never
happen. The card keeps only situations the policy actually reaches on the
recorded matches, merges neighbouring balances that get the same instruction,
and lists them most common first.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rivals.optimize.bet_policy import BetPolicy, Scenarios, describe_key, policy_trace
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
        if self.low == self.high:
            return f"{self.low:,.0f}"
        return f"{self.low:,.0f}-{self.high:,.0f}"


def bet_rules(sc: Scenarios, policy: BetPolicy, min_share: float = 0.002) -> list[Rule]:
    """The policy's reachable situations as rules, dropping those rarer than ``min_share``."""
    trace = policy_trace(sc, policy)
    rules: list[Rule] = []
    for r, step in enumerate(trace):
        alive = step["alive"]
        for key in np.unique(step["key"][alive]):
            mask = alive & (step["key"] == key)
            balances, actions = step["balance"][mask], step["action"][mask]
            order = np.argsort(balances, kind="stable")
            balances, actions = balances[order], actions[order]
            # Runs of consecutive balances (in sorted order) sharing an action.
            breaks = np.flatnonzero(np.diff(actions)) + 1
            for chunk_b, chunk_a in zip(np.split(balances, breaks), np.split(actions, breaks)):
                share = len(chunk_b) / sc.matches
                if share < min_share:
                    continue
                rules.append(
                    Rule(
                        r,
                        describe_key(int(key), r, policy.history),
                        float(chunk_b[0]),
                        float(chunk_b[-1]),
                        policy.actions[int(chunk_a[0])].label,
                        share,
                    )
                )
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
        f"Estimated score {policy.expected_score:.1%} (win + {policy.rules.tie_value:.3f} x tie) "
        f"on the {sc.matches:,} simulated matches it was fitted to.",
        "",
        f"History = {legend}, judged by your main bet only. "
        "Balance ranges are what the strategy itself reaches; rare situations are left out.",
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
