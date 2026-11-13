"""Seeded shoes.

A `Shoe` is an immutable card order. Both players in a match are dealt from
the same `Shoe`, each through their own `ShoeCursor`, so nothing one player
does can change what the other is dealt.

Dealing layout (see docs/DECISIONS.md):

* The initial deal comes off the front: player, dealer upcard, player, dealer
  hole card.
* Player draws continue from the front.
* Dealer draws come off the back when ``dealer_independent`` is True, which
  makes the dealer's whole hand a function of the shoe alone. When False they
  continue from the front, after whatever the player took.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from rivals.cards import DECK_SIZE, fresh_decks, parse_card, parse_cards
from rivals.rules import DEFAULT_RULES, RulesConfig


class ShoeExhausted(RuntimeError):
    """The shoe ran out of cards."""


class Shoe:
    """An immutable, ordered run of cards."""

    __slots__ = ("cards", "_seq")

    def __init__(self, cards: Iterable[int]) -> None:
        arr = np.array(cards, dtype=np.uint8)
        if arr.ndim != 1 or arr.size < 4:
            raise ValueError("a shoe needs at least four cards")
        if arr.max() >= DECK_SIZE:
            raise ValueError("card ids must be in 0..51")
        arr.setflags(write=False)
        #: Card order as a read-only uint8 array (for compiled code).
        self.cards = arr
        self._seq: tuple[int, ...] = tuple(arr.tolist())

    @classmethod
    def from_seed(cls, seed: int | Sequence[int], num_decks: int = DEFAULT_RULES.num_decks) -> Shoe:
        """Shuffle ``num_decks`` full decks. The same seed always gives the same order."""
        if num_decks < 1:
            raise ValueError("num_decks must be at least 1")
        rng = np.random.default_rng(seed)
        return cls(rng.permutation(fresh_decks(num_decks)))

    @classmethod
    def stacked(
        cls,
        player: str | Iterable[int | str],
        dealer: str | Iterable[int | str],
        player_draws: str | Iterable[int | str] = (),
        dealer_draws: str | Iterable[int | str] = (),
        *,
        dealer_independent: bool = True,
        size: int = DECK_SIZE,
        filler: int | str = "2c",
    ) -> Shoe:
        """A rigged shoe, for tests and for replaying logged hands.

        ``player`` is the player's two starting cards and ``dealer`` is
        (upcard, hole card). ``player_draws`` and ``dealer_draws`` are dealt in
        order. ``dealer_independent`` must match the rules the shoe is played
        under. Unspecified positions hold ``filler``.
        """
        p, d = parse_cards(player), parse_cards(dealer)
        if len(p) != 2 or len(d) != 2:
            raise ValueError("player and dealer each start with exactly two cards")
        p_draws, d_draws = parse_cards(player_draws), parse_cards(dealer_draws)
        front = [p[0], d[0], p[1], d[1], *p_draws]
        back: list[int] = []
        if dealer_independent:
            back = d_draws[::-1]
        else:
            front += d_draws
        fill = parse_card(filler) if isinstance(filler, str) else int(filler)
        padding = max(0, size - len(front) - len(back))
        return cls(front + [fill] * padding + back)

    def cursor(self, dealer_independent: bool = True) -> ShoeCursor:
        """A fresh dealing position at the top of this shoe."""
        return ShoeCursor(self, dealer_independent)

    def __len__(self) -> int:
        return len(self._seq)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Shoe) and self._seq == other._seq

    def __hash__(self) -> int:
        return hash(self._seq)

    def __repr__(self) -> str:
        return f"Shoe({len(self._seq)} cards)"


class ShoeCursor:
    """One player's dealing position in a `Shoe`."""

    __slots__ = ("_seq", "_front", "_back", "_independent")

    def __init__(self, shoe: Shoe, dealer_independent: bool = True) -> None:
        self._seq = shoe._seq
        self._front = 0
        self._back = len(self._seq) - 1
        self._independent = dealer_independent

    def next(self) -> int:
        """Next card off the front: the initial deal and all player draws."""
        if self._front > self._back:
            raise ShoeExhausted("shoe ran out of cards")
        card = self._seq[self._front]
        self._front += 1
        return card

    def next_dealer(self) -> int:
        """Next dealer draw (after the dealer's two starting cards)."""
        if not self._independent:
            return self.next()
        if self._front > self._back:
            raise ShoeExhausted("shoe ran out of cards")
        card = self._seq[self._back]
        self._back -= 1
        return card


def match_shoes(match_seed: int, rules: RulesConfig = DEFAULT_RULES) -> tuple[Shoe, ...]:
    """The shoes for one match: a fresh shuffle per round, all fixed by ``match_seed``."""
    return tuple(
        Shoe.from_seed([match_seed, round_idx], rules.num_decks)
        for round_idx in range(rules.num_rounds)
    )
