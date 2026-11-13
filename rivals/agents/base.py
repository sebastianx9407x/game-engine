"""The interface every player implements.

An `Agent` makes three kinds of decision each round: how much to bet, which
side bets to add, and how to play the cards. It sees only its own match so
far, never the opponent: 21 Rivals is played blind.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from rivals.hand import Action
from rivals.resolve import DecisionContext, RoundResult
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.side_bets import NO_SIDE_BETS, SideBets
from rivals.solver.basic import basic_chart
from rivals.solver.exact import value_index


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """One finished round, as the player who played it saw it."""

    round_index: int
    balance_before: float
    bet: float
    side_bets: SideBets
    result: RoundResult

    @property
    def net(self) -> float:
        return self.result.net

    @property
    def balance_after(self) -> float:
        return self.balance_before + self.result.net


@dataclass(frozen=True, slots=True)
class MatchState:
    """What a player knows when a round starts."""

    #: 0 for the first round.
    round_index: int
    #: Chips available before betting this round.
    balance: float
    #: The player's own earlier rounds, oldest first.
    history: tuple[RoundRecord, ...]
    rules: RulesConfig

    @property
    def rounds_left(self) -> int:
        """Rounds still to play, this one included."""
        return self.rules.num_rounds - self.round_index

    @property
    def is_last_round(self) -> bool:
        return self.rounds_left == 1

    @property
    def profit(self) -> float:
        """Chips up or down on the starting stack."""
        return self.balance - self.rules.starting_chips

    @property
    def last(self) -> RoundRecord | None:
        return self.history[-1] if self.history else None

    def max_bet(self) -> float:
        """Largest main bet allowed right now."""
        cap = self.rules.max_bet
        return self.balance if cap is None else min(self.balance, cap)

    def clamp_bet(self, amount: float) -> float:
        """``amount`` pulled into the legal range for the main bet."""
        return max(self.rules.min_bet, min(amount, self.max_bet()))


class Agent:
    """Base player: bets the minimum, takes no side bets, plays basic strategy.

    Subclasses override whichever decisions they want to change. `reset` is
    called at the start of every match; an agent with random behaviour must
    draw all its randomness from ``self.rng`` so matches are reproducible.
    """

    #: Label used in reports. Defaults to the class name.
    name: str = ""

    def __init__(self) -> None:
        self.rng = random.Random(0)
        self.rules = DEFAULT_RULES
        self._chart = None

    @property
    def label(self) -> str:
        return self.name or type(self).__name__

    def reset(self, rng: random.Random, rules: RulesConfig) -> None:
        """Start a new match."""
        self.rng = rng
        if rules != self.rules or self._chart is None:
            self._chart = None
        self.rules = rules

    # --- decisions --------------------------------------------------------

    def bet(self, state: MatchState) -> float:
        """Main bet for this round, between the minimum and `state.max_bet()`."""
        return self.rules.min_bet

    def side_bets(self, state: MatchState, bet: float) -> SideBets:
        """Side bets for this round. Main bet plus side bets must fit in the balance."""
        return NO_SIDE_BETS

    def act(self, ctx: DecisionContext, state: MatchState) -> Action:
        """Play decision. ``ctx.legal`` lists what is allowed."""
        return self.basic_action(ctx)

    def take_insurance(self, ctx: DecisionContext, state: MatchState) -> bool:
        return False

    # --- helpers ----------------------------------------------------------

    def basic_action(self, ctx: DecisionContext) -> Action:
        """The basic-strategy play for this decision."""
        if self._chart is None:
            self._chart = basic_chart(self.rules)
        hand = ctx.hand
        pair = value_index(hand.cards[0]) if Action.SPLIT in ctx.legal else None
        return self._chart.action(
            hand.total, hand.is_soft, pair, value_index(ctx.upcard), ctx.legal
        )
