"""An agent that plays a solved `BetPolicy`."""

from __future__ import annotations

from rivals.agents.base import Agent, MatchState
from rivals.hand import Action
from rivals.resolve import DecisionContext
from rivals.side_bets import SideBets


class PolicyAgent(Agent):
    """Bets by a `BetPolicy` table and plays the style the table picks for each round."""

    def __init__(self, policy, name: str = "optimized", styles=None) -> None:
        super().__init__()
        self.policy = policy
        self.name = name
        #: Play policies by style index; None plays basic strategy for every style.
        self.styles = styles
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
        if self.styles is None or self._action.style == 0:
            return self.basic_action(ctx)
        return self.styles[self._action.style].act(ctx)


class PolicyAgentFactory:
    """Picklable factory for `simulate` and `evaluate`."""

    def __init__(self, policy, name: str = "optimized", styles=None) -> None:
        self.policy, self.label, self.styles = policy, name, styles

    def __call__(self, rng) -> PolicyAgent:
        return PolicyAgent(self.policy, self.label, self.styles)
