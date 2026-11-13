"""Basic strategy: the best action by hand total and dealer upcard.

The chart is derived from the exact solver, so it follows whatever rules are
configured. It is "total-dependent": it looks at the hand's total, whether it
is soft and whether it is a pair, not at the individual cards.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rivals.hand import Action
from rivals.resolve import DecisionContext
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.solver.exact import (
    ACE,
    NUM_VALUES,
    POINTS,
    TEN,
    VALUE_NAMES,
    Solver,
    StrategyView,
    solver_for,
    counts_of,
    total_of,
    value_index,
)

HARD_TOTALS = range(4, 21)
SOFT_TOTALS = range(12, 21)
_LETTER = {Action.STAND: "S", Action.HIT: "H", Action.DOUBLE: "D", Action.SPLIT: "P"}


@dataclass(frozen=True, slots=True)
class Cell:
    #: Best action on a two-card hand.
    first: Action
    #: Best of hit and stand, for when `first` is not available.
    fallback: Action

    def __str__(self) -> str:
        if self.first == Action.DOUBLE:
            return "D" + _LETTER[self.fallback].lower()
        return _LETTER[self.first]


@dataclass(frozen=True)
class Chart:
    """Basic strategy for one rule set. Upcards are value indices (0 = ace .. 9 = ten)."""

    rules: RulesConfig
    hard: dict[tuple[int, int], Cell]
    soft: dict[tuple[int, int], Cell]
    #: (pair value, upcard) -> True when splitting is the best play.
    split: dict[tuple[int, int], bool]

    def action(
        self,
        total: int,
        soft: bool,
        pair: int | None,
        upcard: int,
        legal: tuple[Action, ...],
    ) -> Action:
        """The chart's play, limited to the actions in ``legal``."""
        if pair is not None and Action.SPLIT in legal and self.split[(pair, upcard)]:
            return Action.SPLIT
        cell = (self.soft if soft else self.hard)[(total, upcard)]
        return cell.first if cell.first in legal else cell.fallback

    def __call__(self, view: StrategyView) -> Action:
        """Lets a chart be passed to `Solver` as a fixed strategy."""
        return self.action(view.total, view.soft, view.pair, view.upcard, view.legal)

    def render(self) -> str:
        """The chart as text. ``Dh``/``Ds`` mean double if allowed, else hit/stand."""
        order = list(range(1, NUM_VALUES)) + [ACE]  # 2..9, T, A
        lines = ["         " + "  ".join(f"{VALUE_NAMES[u]:>2}" for u in order)]

        def row(label: str, cells: list[str]) -> None:
            lines.append(f"{label:<9}" + "  ".join(f"{c:>2}" for c in cells))

        lines.append("Hard")
        for total in reversed(HARD_TOTALS):
            row(f"  {total}", [str(self.hard[(total, u)]) for u in order])
        lines.append("Soft")
        for total in reversed(SOFT_TOTALS):
            row(f"  A,{total - 11}" if total > 12 else "  A,A", [str(self.soft[(total, u)]) for u in order])
        lines.append("Pairs (P = split, - = play the total)")
        for pair in [ACE] + list(range(TEN, 0, -1)):
            name = VALUE_NAMES[pair]
            row(f"  {name},{name}", ["P" if self.split[(pair, u)] else "-" for u in order])
        return "\n".join(lines)


def _two_card_hands(total: int, soft: bool) -> list[tuple[int, int]]:
    """Two-card hands (as value indices) making this total, pairs last."""
    hands = []
    for a in range(NUM_VALUES):
        for b in range(a, NUM_VALUES):
            if total_of(counts_of([a, b])) == (total, soft):
                hands.append((a, b))
    non_pairs = [h for h in hands if h[0] != h[1]]
    return non_pairs or hands


#: Picks an action from {action: (ev, std)}.
Selector = Callable[[dict[Action, tuple[float, float]]], Action]


def _highest_ev(options: dict[Action, tuple[float, float]]) -> Action:
    return max(options, key=lambda a: options[a][0])


def derive_chart(solver: Solver, select: Selector = _highest_ev) -> Chart:
    """Build a chart from a solver that plays every decision optimally.

    ``select`` decides each cell from the EV and standard deviation of every
    action; the default takes the highest EV, which gives basic strategy.
    """
    if solver.strategy is not None:
        raise ValueError("derive the chart from a solver without a fixed strategy")
    full = solver.full
    hard: dict[tuple[int, int], Cell] = {}
    soft: dict[tuple[int, int], Cell] = {}
    split: dict[tuple[int, int], bool] = {}

    def summarise(hands: list[tuple[int, int]], up: int) -> dict[Action, tuple[float, float]]:
        """EV and std of each action, averaged over ``hands`` by how often each is dealt."""
        first: dict[Action, float] = {}
        second: dict[Action, float] = {}
        weight_sum = 0.0
        for a, b in hands:
            shoe = list(full)
            shoe[up] -= 1
            weight = shoe[a] * (shoe[b] - (a == b)) * (1 if a == b else 2)
            if weight <= 0:
                continue
            result = solver.evaluate_counts(counts_of([a, b]), up)
            weight_sum += weight
            for action, value in result.actions.items():
                first[action] = first.get(action, 0.0) + weight * value.ev
                moment = sum(x * x * p for x, p in value.dist.items())
                second[action] = second.get(action, 0.0) + weight * moment
        out = {}
        for action, total in first.items():
            ev = total / weight_sum
            out[action] = (ev, max(second[action] / weight_sum - ev * ev, 0.0) ** 0.5)
        return out

    for up in range(NUM_VALUES):
        for is_soft, totals, table in ((False, HARD_TOTALS, hard), (True, SOFT_TOTALS, soft)):
            for total in totals:
                options = summarise(_two_card_hands(total, is_soft), up)
                options.pop(Action.SPLIT, None)
                if not options:  # cannot be dealt from this shoe
                    table[(total, up)] = Cell(Action.STAND, Action.STAND)
                    continue
                fallback = select({a: options[a] for a in (Action.STAND, Action.HIT)})
                table[(total, up)] = Cell(select(options), fallback)
        for pair in range(NUM_VALUES):
            if full[pair] - (pair == up) < 2:
                split[(pair, up)] = False
                continue
            options = summarise([(pair, pair)], up)
            split[(pair, up)] = Action.SPLIT in options and select(options) == Action.SPLIT
    return Chart(solver.rules, hard, soft, split)


_CHARTS: dict[RulesConfig, Chart] = {}


def basic_chart(rules: RulesConfig = DEFAULT_RULES) -> Chart:
    """Basic strategy for ``rules`` (solved once per process, then cached)."""
    chart = _CHARTS.get(rules)
    if chart is None:
        chart = _CHARTS[rules] = derive_chart(solver_for(rules))
    return chart


def prime_charts(charts: list[Chart]) -> None:
    """Install charts solved elsewhere, so worker processes skip the several-second solve."""
    for chart in charts:
        _CHARTS[chart.rules] = chart


class BasicStrategy:
    """A `resolve.Policy` that plays the basic-strategy chart and never insures."""

    def __init__(self, rules: RulesConfig = DEFAULT_RULES) -> None:
        self.rules = rules
        self.chart = basic_chart(rules)

    def act(self, ctx: DecisionContext) -> Action:
        hand = ctx.hand
        pair = None
        if Action.SPLIT in ctx.legal:
            pair = value_index(hand.cards[0])
        return self.chart.action(
            hand.total, hand.is_soft, pair, value_index(ctx.upcard), ctx.legal
        )

    def take_insurance(self, ctx: DecisionContext) -> bool:
        return False
