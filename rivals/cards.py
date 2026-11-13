"""Card encoding.

A card is an int in 0..51: ``card = rank * 4 + suit``.

* rank: 0 = ace, 1..8 = two..nine, 9 = ten, 10 = jack, 11 = queen, 12 = king
* suit: 0 = spades, 1 = clubs, 2 = hearts, 3 = diamonds, so ``suit >> 1`` is
  the color (0 = black, 1 = red)

Text form is rank then suit, e.g. ``"As"``, ``"Td"``, ``"7h"``.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

RANKS = "A23456789TJQK"
SUITS = "schd"
NUM_RANKS = 13
NUM_SUITS = 4
DECK_SIZE = 52

ACE = 0
BLACK, RED = 0, 1

# Blackjack value per rank; an ace is 11 here and softened in hand totals.
RANK_VALUES = (11, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10)

# Per-card lookup tables. Tuples are for the pure-Python engine, the numpy
# arrays are for vectorized and compiled code.
RANK = tuple(c // NUM_SUITS for c in range(DECK_SIZE))
SUIT = tuple(c % NUM_SUITS for c in range(DECK_SIZE))
COLOR = tuple(s >> 1 for s in SUIT)
VALUE = tuple(RANK_VALUES[r] for r in RANK)

CARD_RANK = np.array(RANK, dtype=np.uint8)
CARD_SUIT = np.array(SUIT, dtype=np.uint8)
CARD_COLOR = np.array(COLOR, dtype=np.uint8)
CARD_VALUE = np.array(VALUE, dtype=np.uint8)


def make_card(rank: int, suit: int) -> int:
    return rank * NUM_SUITS + suit


def rank_of(card: int) -> int:
    return RANK[card]


def suit_of(card: int) -> int:
    return SUIT[card]


def color_of(card: int) -> int:
    return COLOR[card]


def value_of(card: int) -> int:
    """Blackjack value, with an ace counted as 11."""
    return VALUE[card]


def is_ace(card: int) -> bool:
    return RANK[card] == ACE


def is_ten_value(card: int) -> bool:
    return VALUE[card] == 10


def parse_card(text: str) -> int:
    """``"As"`` -> 0. ``"10"`` is accepted for the ten, and case is ignored."""
    text = text.strip()
    rank_text, suit_text = text[:-1].upper(), text[-1:].lower()
    if rank_text == "10":
        rank_text = "T"
    if len(rank_text) != 1 or rank_text not in RANKS or suit_text not in SUITS or not suit_text:
        raise ValueError(f"not a card: {text!r}")
    return make_card(RANKS.index(rank_text), SUITS.index(suit_text))


def parse_cards(cards: str | Iterable[int | str]) -> list[int]:
    """Accepts ``"As Kd"`` or any mix of card ints and card strings."""
    if isinstance(cards, str):
        cards = cards.replace(",", " ").split()
    return [parse_card(c) if isinstance(c, str) else int(c) for c in cards]


def card_name(card: int) -> str:
    return RANKS[RANK[card]] + SUITS[SUIT[card]]


def cards_str(cards: Iterable[int]) -> str:
    return " ".join(card_name(c) for c in cards)


def fresh_decks(num_decks: int) -> np.ndarray:
    """Unshuffled cards of ``num_decks`` full decks."""
    return np.tile(np.arange(DECK_SIZE, dtype=np.uint8), num_decks)
