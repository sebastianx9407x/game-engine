"""Both players in a match are dealt from the same shoe.

Whatever each player does, both face the same dealer upcard and hole card,
and their own cards match for as long as their decisions match.

By default the shoe is sequential: the dealer draws after the player, so a
player who takes a different number of cards leaves the dealer different
draws. With ``dealer_cards_independent`` the dealer's whole hand is fixed.
"""

import numpy as np
import pytest

from conftest import RandomPolicy, play
from rivals.cards import parse_cards
from rivals.hand import Action
from rivals.resolve import ScriptedPolicy, play_dealer, play_round
from rivals.rules import DEFAULT_RULES
from rivals.shoe import Shoe, match_shoes
from rivals.side_bets import SideBets

S, H, D, P = Action.STAND, Action.HIT, Action.DOUBLE, Action.SPLIT
INDEPENDENT = DEFAULT_RULES.with_(dealer_cards_independent=True)
DECK_COUNTS = [1, 2, 6, 8]


# --- default: one sequential shoe -------------------------------------------


def test_a_card_one_player_takes_is_the_card_the_other_players_dealer_draws():
    shoe = Shoe(parse_cards("Ts 9c 6d 7h 2h 5d Kc 3s"))
    stood = play_round(shoe, ScriptedPolicy([S]), 10)
    hit = play_round(shoe, ScriptedPolicy([H, S]), 10)
    assert stood.dealer_cards[:2] == hit.dealer_cards[:2] == tuple(parse_cards("9c 7h"))
    assert stood.dealer_cards == tuple(parse_cards("9c 7h 2h"))  # 18 beats the 16
    assert hit.dealer_cards == tuple(parse_cards("9c 7h 5d"))  # 21 beats the 18
    assert (stood.net, hit.net) == (-10, -10)


def test_diverging_decisions_can_flip_the_dealer_from_bust_to_made_hand():
    # Standing lets the dealer take the king and bust; hitting takes the king
    # and busts, so that player loses without the dealer drawing.
    shoe = Shoe(parse_cards("Ts 9c 6d 7h Kc 5d 2s 2c"))
    stood = play_round(shoe, ScriptedPolicy([S]), 10)
    hit = play_round(shoe, ScriptedPolicy([H]), 10)
    assert stood.dealer_bust and stood.net == 10
    assert hit.net == -10 and hit.dealer_cards == tuple(parse_cards("9c 7h"))


@pytest.mark.parametrize("num_decks", DECK_COUNTS)
def test_starting_dealer_cards_never_depend_on_the_players(num_decks):
    rules = DEFAULT_RULES.with_(num_decks=num_decks)
    diverged = 0
    for seed in range(300):
        shoe = Shoe.from_seed(seed, num_decks)
        a = play_round(shoe, RandomPolicy(seed), 10, rules=rules)
        b = play_round(shoe, RandomPolicy(seed + 10_000), 10, rules=rules)
        diverged += a.actions != b.actions
        expected = (int(shoe.cards[1]), int(shoe.cards[3]))
        assert a.dealer_cards[:2] == b.dealer_cards[:2] == expected
        assert a.hands[0].cards[0] == b.hands[0].cards[0] == shoe.cards[0]
    assert diverged > 100  # the two players really did play differently


@pytest.mark.parametrize("num_decks", DECK_COUNTS)
def test_sequential_round_deals_the_shoe_in_order_with_the_dealer_last(num_decks):
    rules = DEFAULT_RULES.with_(num_decks=num_decks)
    for seed in range(300):
        shoe = Shoe.from_seed(seed, num_decks)
        result = play_round(shoe, RandomPolicy(seed), 10, rules=rules)
        player_cards = sum(len(h.cards) for h in result.hands)
        dealer_draws = result.dealer_cards[2:]
        drawn_by_player = player_cards - 2
        start = 4 + drawn_by_player
        assert list(dealer_draws) == shoe.cards[start : start + len(dealer_draws)].tolist()


# --- alternative: dealer hand fixed by the shoe alone ------------------------


def test_independent_dealer_cards_are_identical_when_one_player_hits_and_the_other_stands():
    setup = dict(player_draws="2h 3s", dealer_draws="5d", rules=INDEPENDENT)
    stood, _ = play("Ts 6d", "9c 7h", [S], **setup)
    hit, _ = play("Ts 6d", "9c 7h", [H, S], **setup)
    hit_twice, _ = play("Ts 6d", "9c 7h", [H, H], **setup)
    assert stood.hands[0].cards != hit.hands[0].cards != hit_twice.hands[0].cards
    expected = tuple(parse_cards("9c 7h 5d"))
    assert stood.dealer_cards == hit.dealer_cards == hit_twice.dealer_cards == expected
    assert (stood.net, hit.net, hit_twice.net) == (-10, -10, 0)


def test_independent_dealer_cards_are_identical_when_one_player_splits_and_doubles():
    setup = dict(player_draws="3d Kc Td 4s", dealer_draws="2d 9s", rules=INDEPENDENT)
    stood, _ = play("8s 8h", "5c 3h", [S], **setup)
    split, _ = play("8s 8h", "5c 3h", [P, D, H, S], **setup)
    assert len(split.hands) == 2
    assert stood.dealer_cards == split.dealer_cards == tuple(parse_cards("5c 3h 2d 9s"))


@pytest.mark.parametrize("num_decks", DECK_COUNTS)
def test_independent_dealer_hand_depends_only_on_the_shoe(num_decks):
    rules = INDEPENDENT.with_(num_decks=num_decks)
    diverged = 0
    for seed in range(300):
        shoe = Shoe.from_seed(seed, num_decks)
        cursor = shoe.cursor(dealer_independent=True)
        first, upcard, second, hole = (cursor.next() for _ in range(4))
        full_dealer_hand = tuple(play_dealer(cursor, upcard, hole, rules))

        a = play_round(shoe, RandomPolicy(seed), 10, rules=rules)
        b = play_round(shoe, RandomPolicy(seed + 10_000), 10, rules=rules)
        diverged += a.actions != b.actions

        for result in (a, b):
            assert result.dealer_cards[:2] == (upcard, hole)
            dealer_played = len(result.actions) > 0 and any(h.total <= 21 for h in result.hands)
            if dealer_played:
                assert result.dealer_cards == full_dealer_hand
            else:  # dealer or player blackjack, or every hand bust: no draws
                assert result.dealer_cards == (upcard, hole)
    assert diverged > 100


# --- true under both shoe models --------------------------------------------


@pytest.mark.parametrize("rules", [DEFAULT_RULES, INDEPENDENT], ids=["sequential", "independent"])
def test_identical_decisions_give_identical_rounds(rules):
    bets = SideBets(10, 10)
    for seed in range(200):
        shoe = Shoe.from_seed(seed)
        a = play_round(shoe, RandomPolicy(seed), 50, bets, balance=1000, rules=rules)
        b = play_round(shoe, RandomPolicy(seed), 50, bets, balance=1000, rules=rules)
        assert a == b


@pytest.mark.parametrize("rules", [DEFAULT_RULES, INDEPENDENT], ids=["sequential", "independent"])
def test_player_cards_match_until_decisions_diverge(rules):
    for seed in range(200):
        shoe = Shoe.from_seed(seed)
        stand = play_round(shoe, ScriptedPolicy([S]), 10, rules=rules)
        hit = play_round(shoe, ScriptedPolicy([H, S]), 10, rules=rules)
        if not stand.actions:  # a blackjack ended the round
            assert stand == hit
            continue
        assert hit.hands[0].cards[:2] == stand.hands[0].cards
        assert hit.hands[0].cards[2] == shoe.cards[4]


@pytest.mark.parametrize("rules", [DEFAULT_RULES, INDEPENDENT], ids=["sequential", "independent"])
def test_side_bets_resolve_identically_for_both_players(rules):
    bets = SideBets(10, 10)
    for seed in range(200):
        shoe = Shoe.from_seed(seed)
        a = play_round(shoe, RandomPolicy(seed), 10, bets, rules=rules)
        b = play_round(shoe, RandomPolicy(seed + 10_000), 10, bets, rules=rules)
        assert a.side_net == b.side_net


def test_playing_a_round_leaves_the_shoe_untouched():
    shoe = Shoe.from_seed(5)
    before = shoe.cards.copy()
    for seed in range(20):
        play_round(shoe, RandomPolicy(seed), 10)
    assert np.array_equal(shoe.cards, before)


def test_a_whole_match_is_reproducible_from_its_seed():
    def run(match_seed):
        return [
            play_round(shoe, RandomPolicy(i), 100, balance=1000)
            for i, shoe in enumerate(match_shoes(match_seed))
        ]

    assert run(77) == run(77)
    assert [r.dealer_cards for r in run(77)] != [r.dealer_cards for r in run(78)]
