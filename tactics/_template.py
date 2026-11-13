"""Copy this file, rename it, and change the three methods.

Score it with:   python -m rivals.evaluate tactics/your_file.py

`state` is what you know when a round starts:
    state.round_index    0 for hand 1 ... 4 for hand 5
    state.is_last_round  True on hand 5
    state.balance        your chips before betting
    state.profit         balance minus the 1,000 you started with
    state.last           your previous round (state.last.net is what it won or lost)
    state.history        all your previous rounds
You never see the opponent: the game is blind.
"""

from rivals.agents import Agent
from rivals.side_bets import SideBets


class Tactic(Agent):
    name = "template"

    def bet(self, state):
        """Main bet: at least 10, at most your balance."""
        if state.is_last_round and state.profit < 0:
            return state.clamp_bet(state.balance / 2)  # behind on the last hand: bet half
        return state.clamp_bet(50)

    def side_bets(self, state, bet):
        """Side bets (minimum 5 each). Main bet + side bets must fit in your balance."""
        return SideBets(perfect_pairs=0, four_card_total=0)

    def act(self, ctx, state):
        """Hit, stand, double or split. Must be one of ctx.legal."""
        return self.basic_action(ctx)  # basic strategy
