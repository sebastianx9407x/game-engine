"""Side bets: Perfect Pairs and 4-Card Total.

Both resolve on the starting cards alone, independently of the main hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from rivals.cards import COLOR, RANK, SUIT, VALUE
from rivals.rules import RulesConfig


@dataclass(frozen=True, slots=True)
class SideBets:
    """Chips staked on each side bet for one round (0 = not played)."""

    perfect_pairs: float = 0
    four_card_total: float = 0

    @property
    def total(self) -> float:
        return self.perfect_pairs + self.four_card_total


NO_SIDE_BETS = SideBets()


class PairType(IntEnum):
    NONE = 0
    MIXED = 1  # same rank, different color
    COLORED = 2  # same rank and color, different suit
    PERFECT = 3  # same rank and suit


def pair_type(card_a: int, card_b: int) -> PairType:
    if RANK[card_a] != RANK[card_b]:
        return PairType.NONE
    if SUIT[card_a] == SUIT[card_b]:
        return PairType.PERFECT
    if COLOR[card_a] == COLOR[card_b]:
        return PairType.COLORED
    return PairType.MIXED


def perfect_pairs_payout(card_a: int, card_b: int, rules: RulesConfig) -> float:
    """Payout odds (x:1) for the player's two starting cards; 0 if the bet loses."""
    kind = pair_type(card_a, card_b)
    if kind is PairType.PERFECT:
        return rules.perfect_pair_payout
    if kind is PairType.COLORED:
        return rules.colored_pair_payout
    if kind is PairType.MIXED:
        return rules.mixed_pair_payout
    return 0


def four_card_total(player_a: int, player_b: int, upcard: int, hole: int) -> int:
    """Sum of the player's two cards and both dealer cards, every ace as 11."""
    return VALUE[player_a] + VALUE[player_b] + VALUE[upcard] + VALUE[hole]


def four_card_total_payout(total: int, rules: RulesConfig) -> float:
    """Payout odds (x:1) for a 4-card total; 0 if the bet loses."""
    for threshold, payout in rules.four_card_total_payouts:
        if total >= threshold:
            return payout
    return 0


def settle(bet: float, payout: float) -> float:
    """Net chips for a side bet: ``bet * payout`` on a win, ``-bet`` on a loss."""
    if not bet:
        return 0
    return bet * payout if payout else -bet


def settle_side_bets(
    bets: SideBets,
    player_a: int,
    player_b: int,
    upcard: int,
    hole: int,
    rules: RulesConfig,
) -> tuple[float, float]:
    """Net chips for (Perfect Pairs, 4-Card Total)."""
    pairs_net = settle(bets.perfect_pairs, perfect_pairs_payout(player_a, player_b, rules))
    total_net = settle(
        bets.four_card_total,
        four_card_total_payout(four_card_total(player_a, player_b, upcard, hole), rules),
    )
    return pairs_net, total_net
