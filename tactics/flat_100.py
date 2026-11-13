"""Bet 100 every hand, basic strategy, no side bets. A simple reference point."""

from rivals.agents import Agent


class Tactic(Agent):
    name = "flat-100"

    def bet(self, state):
        return state.clamp_bet(100)
