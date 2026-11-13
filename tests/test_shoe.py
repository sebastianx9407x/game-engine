import numpy as np
import pytest

from rivals.cards import fresh_decks, parse_cards
from rivals.rules import DEFAULT_RULES
from rivals.shoe import Shoe, ShoeExhausted, match_shoes


def test_same_seed_gives_same_shoe():
    assert Shoe.from_seed(42) == Shoe.from_seed(42)
    assert np.array_equal(Shoe.from_seed(42).cards, Shoe.from_seed(42).cards)


def test_different_seeds_give_different_shoes():
    assert Shoe.from_seed(1) != Shoe.from_seed(2)


def test_shuffle_is_pinned():
    # Guards against the shuffle changing silently (numpy upgrade, refactor).
    # If this fails, old match seeds no longer reproduce the same matches.
    assert Shoe.from_seed(0, 1).cards[:8].tolist() == [38, 11, 18, 10, 23, 28, 4, 36]


@pytest.mark.parametrize("num_decks", [1, 2, 6, 8])
def test_shoe_holds_exactly_the_configured_decks(num_decks):
    shoe = Shoe.from_seed(7, num_decks)
    assert len(shoe) == 52 * num_decks
    assert np.array_equal(np.sort(shoe.cards), np.sort(fresh_decks(num_decks)))
    assert np.bincount(shoe.cards, minlength=52).tolist() == [num_decks] * 52


def test_from_seed_rejects_zero_decks():
    with pytest.raises(ValueError):
        Shoe.from_seed(1, 0)


def test_shoe_is_immutable():
    shoe = Shoe.from_seed(3)
    with pytest.raises(ValueError):
        shoe.cards[0] = 0


def test_match_shoes_are_deterministic_and_distinct_per_round():
    a, b = match_shoes(123), match_shoes(123)
    assert a == b
    assert len(a) == DEFAULT_RULES.num_rounds
    assert len(set(a)) == len(a)
    assert match_shoes(124) != a


def test_match_shoes_follow_the_configured_deck_count_and_round_count():
    shoes = match_shoes(5, DEFAULT_RULES.with_(num_decks=2, num_rounds=3))
    assert [len(s) for s in shoes] == [104, 104, 104]


def test_independent_cursors_do_not_interfere():
    shoe = Shoe.from_seed(9)
    a, b = shoe.cursor(), shoe.cursor()
    first = [a.next() for _ in range(10)]
    assert [b.next() for _ in range(10)] == first == shoe.cards[:10].tolist()


def test_dealer_draws_come_from_the_back_when_independent():
    shoe = Shoe.from_seed(9)
    cur = shoe.cursor(dealer_independent=True)
    [cur.next() for _ in range(6)]
    assert [cur.next_dealer(), cur.next_dealer()] == shoe.cards[::-1][:2].tolist()


def test_dealer_draws_follow_the_player_when_sequential():
    shoe = Shoe.from_seed(9)
    cur = shoe.cursor(dealer_independent=False)
    [cur.next() for _ in range(6)]
    assert [cur.next_dealer(), cur.next_dealer()] == shoe.cards[6:8].tolist()


def test_cursor_never_deals_a_card_twice():
    shoe = Shoe(parse_cards("As Kd 5h 7c 9s"))
    cur = shoe.cursor(dealer_independent=True)
    dealt = [cur.next(), cur.next(), cur.next_dealer(), cur.next(), cur.next_dealer()]
    assert sorted(dealt) == sorted(shoe.cards.tolist())
    with pytest.raises(ShoeExhausted):
        cur.next()
    with pytest.raises(ShoeExhausted):
        cur.next_dealer()


def test_stacked_layout():
    sequential = Shoe.stacked("As Kd", "9c 7h", "2s 3s", "4d 5d")
    assert sequential.cards[:8].tolist() == parse_cards("As 9c Kd 7h 2s 3s 4d 5d")
    shoe = Shoe.stacked("As Kd", "9c 7h", "2s 3s", "4d 5d", dealer_independent=True)
    assert shoe.cards[:6].tolist() == parse_cards("As 9c Kd 7h 2s 3s")
    assert shoe.cards[-2:].tolist() == parse_cards("5d 4d")
