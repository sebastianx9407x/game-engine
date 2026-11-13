"""An agent that plays a solved `BetPolicy`."""

from __future__ import annotations

from rivals.agents.base import Agent, MatchState
from rivals.hand import Action
from rivals.resolve import DecisionContext
from rivals.side_bets import SideBets
from rivals.solver.exact import value_index


class PolicyAgent(Agent):
    """Bets by a `BetPolicy` table and plays the style the table picks for each round."""

    def __init__(self, policy, name: str = "optimized") -> None:
        super().__init__()
        self.policy = policy
        self.name = name
        self._action = None

    def history_key(self, state: MatchState) -> int:
        """The shared-history key, from the sign of our own main-bet results."""
        mode = self.policy.history
        r = state.round_index
        if mode == "none" or r == 0:
            return 0
        cats = [(rec.result.main_net > 0) - (rec.result.main_net < 0) + 1 for rec in state.history]
        if mode == "pattern":
            return sum(c * 3**i for i, c in enumerate(cats))
        wins, losses = cats.count(2), cats.count(0)
        return wins * (r + 1) + losses

    def bet(self, state: MatchState) -> float:
        self._action = self.policy.action(state.round_index, self.history_key(state), state.balance)
        main, _, _ = self._action.amounts(state.balance)
        return float(main)

    def side_bets(self, state: MatchState, bet: float) -> SideBets:
        _, pairs, total = self._action.amounts(state.balance)
        return SideBets(float(pairs), float(total))

    def act(self, ctx: DecisionContext, state: MatchState) -> Action:
        style = self._action.style
        if style == 0:
            return self.basic_action(ctx)
        charts = self.policy.style_charts
        if style >= len(charts) or charts[style] is None:
            raise ValueError(
                f"the policy uses play style {style} but carries no chart for it; "
                "set policy.style_charts (optimize() does this)"
            )
        chart = charts[style]
        hand = ctx.hand
        pair = value_index(hand.cards[0]) if Action.SPLIT in ctx.legal else None
        return chart.action(hand.total, hand.is_soft, pair, value_index(ctx.upcard), ctx.legal)


class PolicyAgentFactory:
    """Picklable factory for `simulate` and `evaluate`."""

    def __init__(self, policy, name: str = "optimized") -> None:
        self.policy, self.label = policy, name

    def __call__(self, rng) -> PolicyAgent:
        return PolicyAgent(self.policy, self.label)
