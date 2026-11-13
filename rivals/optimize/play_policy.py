"""Play styles that trade a little expected value for more or less variance.

Basic strategy maximises expected chips. A player who is behind may prefer a
bigger swing, and a player who is ahead a smaller one. A risk chart is built
like the basic-strategy chart, but in each cell it takes the most (or least)
volatile action among those whose EV is within a tolerance of the best.

Because the shoe is shared and sequential, playing a hand differently from
the opponent also changes the dealer's cards, so these styles add divergence
beyond what their own variance suggests. The bet-policy search measures that
directly, by replaying the recorded matches with each style.
"""

from __future__ import annotations

from rivals.hand import Action
from rivals.resolve import DecisionContext
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.solver.basic import Chart, derive_chart
from rivals.solver.exact import solver_for, value_index

MODES = ("seek", "avoid")


def risk_chart(rules: RulesConfig = DEFAULT_RULES, mode: str = "seek", tolerance: float = 0.05) -> Chart:
    """A chart that seeks or avoids variance at a cost of at most ``tolerance`` units of EV per decision."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")

    def select(options: dict[Action, tuple[float, float]]) -> Action:
        best = max(ev for ev, _ in options.values())
        close = {a: std for a, (ev, std) in options.items() if ev >= best - tolerance}
        pick = max if mode == "seek" else min
        # Ties in volatility go to the higher EV.
        return pick(close, key=lambda a: (close[a], options[a][0] if mode == "seek" else -options[a][0]))

    return derive_chart(solver_for(rules), select)


class ChartPolicy:
    """Plays any `Chart` through the round engine; never takes insurance."""

    def __init__(self, chart: Chart) -> None:
        self.chart = chart

    def act(self, ctx: DecisionContext) -> Action:
        hand = ctx.hand
        pair = value_index(hand.cards[0]) if Action.SPLIT in ctx.legal else None
        return self.chart.action(hand.total, hand.is_soft, pair, value_index(ctx.upcard), ctx.legal)

    def take_insurance(self, ctx: DecisionContext) -> bool:
        return False


class ChartPlay:
    """A play style for the bet-policy search: a risk chart, solved once and carried along when pickled."""

    def __init__(self, name: str, mode: str, tolerance: float = 0.05) -> None:
        self.name = name
        self.mode = mode
        self.tolerance = tolerance
        self._charts: dict[RulesConfig, Chart] = {}

    def chart(self, rules: RulesConfig) -> Chart:
        if rules not in self._charts:
            self._charts[rules] = risk_chart(rules, self.mode, self.tolerance)
        return self._charts[rules]

    def policy(self, rules: RulesConfig) -> ChartPolicy:
        return ChartPolicy(self.chart(rules))


class FixedChart:
    """A play style that uses a chart it was handed, e.g. one stored in a saved policy."""

    def __init__(self, name: str, chart: Chart) -> None:
        self.name = name
        self._chart = chart

    def chart(self, rules: RulesConfig) -> Chart:
        return self._chart

    def policy(self, rules: RulesConfig) -> ChartPolicy:
        return ChartPolicy(self._chart)


def styles_of(policy) -> tuple:
    """The play styles a saved `BetPolicy` was solved with, rebuilt from its own charts."""
    from rivals.optimize.bet_policy import BasicPlay

    styles: list = [BasicPlay()]
    for name, chart in list(zip(policy.style_names, policy.style_charts))[1:]:
        styles.append(FixedChart(name, chart))
    return tuple(styles)


def chart_differences(chart: Chart, baseline: Chart) -> list[str]:
    """Human-readable list of the cells where ``chart`` departs from ``baseline``."""
    from rivals.solver.basic import HARD_TOTALS, SOFT_TOTALS
    from rivals.solver.exact import ACE, NUM_VALUES, TEN, VALUE_NAMES

    order = list(range(1, NUM_VALUES)) + [ACE]
    out = []
    for name, totals, mine, theirs in (
        ("hard", HARD_TOTALS, chart.hard, baseline.hard),
        ("soft", SOFT_TOTALS, chart.soft, baseline.soft),
    ):
        for total in totals:
            changed: dict[str, list[str]] = {}
            for u in order:
                cell = str(mine[(total, u)])
                if cell != str(theirs[(total, u)]):
                    changed.setdefault(cell, []).append(VALUE_NAMES[u])
            for cell, ups in changed.items():
                out.append(f"{name} {total} vs {','.join(ups)}: {cell}")
    for pair in [ACE] + list(range(TEN, 0, -1)):
        split = [VALUE_NAMES[u] for u in order if chart.split[(pair, u)] and not baseline.split[(pair, u)]]
        keep = [VALUE_NAMES[u] for u in order if not chart.split[(pair, u)] and baseline.split[(pair, u)]]
        label = f"{VALUE_NAMES[pair]},{VALUE_NAMES[pair]}"
        if split:
            out.append(f"{label} vs {','.join(split)}: split")
        if keep:
            out.append(f"{label} vs {','.join(keep)}: do not split")
    return out
