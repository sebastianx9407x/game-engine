"""Hand state and the actions legal from it."""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum

from rivals.cards import ACE, RANK, VALUE, cards_str
from rivals.rules import RulesConfig


class Action(IntEnum):
    STAND = 0
    HIT = 1
    DOUBLE = 2
    SPLIT = 3
    SURRENDER = 4


def hand_value(cards: Iterable[int]) -> tuple[int, bool]:
    """Best total and whether it is soft (an ace still counted as 11)."""
    total = 0
    aces = 0
    for card in cards:
        value = VALUE[card]
        total += value
        if value == 11:
            aces += 1
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_natural(card_a: int, card_b: int) -> bool:
    """Two cards making 21."""
    return VALUE[card_a] + VALUE[card_b] == 21


class Hand:
    """One player hand in play. Mutable; `resolve.play_round` owns the mutation."""

    __slots__ = ("cards", "bet", "from_split", "doubled", "surrendered", "done")

    def __init__(self, cards: Iterable[int], bet: float, *, from_split: bool = False) -> None:
        self.cards: list[int] = list(cards)
        self.bet = bet
        self.from_split = from_split
        self.doubled = False
        self.surrendered = False
        self.done = False

    @property
    def total(self) -> int:
        return hand_value(self.cards)[0]

    @property
    def is_soft(self) -> bool:
        return hand_value(self.cards)[1]

    @property
    def is_bust(self) -> bool:
        return self.total > 21

    @property
    def is_split_aces(self) -> bool:
        return self.from_split and RANK[self.cards[0]] == ACE

    def is_blackjack(self, rules: RulesConfig) -> bool:
        """Two-card 21 that pays as a blackjack under ``rules``."""
        if len(self.cards) != 2 or self.total != 21:
            return False
        return not self.from_split or rules.split_21_is_blackjack

    def __repr__(self) -> str:
        return f"Hand({cards_str(self.cards)} = {self.total}, bet={self.bet})"


def is_pair(hand: Hand, rules: RulesConfig) -> bool:
    """Two cards that may be split under ``rules`` (ignoring split count and chips)."""
    if len(hand.cards) != 2:
        return False
    a, b = hand.cards
    if RANK[a] == RANK[b]:
        return True
    return rules.split_by_value and VALUE[a] == VALUE[b]


def legal_actions(
    hand: Hand,
    rules: RulesConfig,
    *,
    num_hands: int = 1,
    bankroll: float = float("inf"),
) -> tuple[Action, ...]:
    """Actions open to ``hand`` right now.

    ``num_hands`` is how many hands the player holds this round and
    ``bankroll`` is the chips they have left that are not already wagered.
    """
    if hand.done or hand.total >= 21:
        return ()
    if hand.is_split_aces and not rules.hit_split_aces:
        return ()
    actions = [Action.STAND, Action.HIT]
    if len(hand.cards) == 2:
        can_cover = bankroll >= hand.bet or not rules.require_balance_for_extra_bets
        total_allowed = rules.double_totals is None or hand.total in rules.double_totals
        if can_cover and total_allowed and (not hand.from_split or rules.double_after_split):
            actions.append(Action.DOUBLE)
        if can_cover and num_hands - 1 < rules.max_splits and is_pair(hand, rules):
            actions.append(Action.SPLIT)
        if rules.surrender and num_hands == 1 and not hand.from_split:
            actions.append(Action.SURRENDER)
    return tuple(actions)


def insurance_available(upcard: int, bet: float, bankroll: float, rules: RulesConfig) -> bool:
    """Insurance costs half the main bet and is offered against an ace."""
    if not rules.insurance_offered or RANK[upcard] != ACE:
        return False
    return bankroll >= bet / 2 or not rules.require_balance_for_extra_bets
