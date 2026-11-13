"""Both players in a match are dealt from the same shoe.

The dealer's cards must be the same for both whatever each player does, and
the player cards must be the same for as long as their decisions match.
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


def test_dealer_cards_are_identical_when_one_player_hits_and_the_other_stands():
    setup = dict(player_draws="2h 3s", dealer_draws="5d")
    stood, _ = play("Ts 6d", "9c 7h", [S], **setup)
    hit, _ = play("Ts 6d", "9c 7h", [H, S], **setup)
    hit_twice, _ = play("Ts 6d", "9c 7h", [H, H], **setup)
    assert stood.hands[0].cards != hit.hands[0].cards != hit_twice.hands[0].cards
    expected = tuple(parse_cards("9c 7h 5d"))
    assert stood.dealer_cards == hit.dealer_cards == hit_twice.dealer_cards == expected
    assert (stood.net, hit.net, hit_twice.net) == (-10, -10, 0)


def test_dealer_cards_are_identical_when_one_player_splits_and_doubles():
    setup = dict(player_draws="3d Kc Td 4s", dealer_draws="2d 9s")
    stood, _ = play("8s 8h", "5c 3h", [S], **setup)
    split, _ = play("8s 8h", "5c 3h", [P, D, H, S], **setup)
    assert len(split.hands) == 2
    assert stood.dealer_cards == split.dealer_cards == tuple(parse_cards("5c 3h 2d 9s"))


def test_sequential_shoe_would_let_player_draws_change_the_dealer_hand():
    # The alternative reading of the rules, kept behind a flag: here the card
    # one player takes is the card the other player's dealer gets.
    sequential = DEFAULT_RULES.with_(dealer_cards_independent=False)
    setup = dict(player_draws="2h", dealer_draws="5d", rules=sequential)
    stood, _ = play("Ts 6d", "9c 7h", [S], **setup)
    hit, _ = play("Ts 6d", "9c 7h", [H, S], **setup)
    assert stood.dealer_cards == tuple(parse_cards("9c 7h 2h"))
    assert hit.dealer_cards == tuple(parse_cards("9c 7h 5d"))


@pytest.mark.parametrize("num_decks", [1, 2, 6, 8])
def test_dealer_hand_depends_only_on_the_shoe(num_decks):
    rules = DEFAULT_RULES.with_(num_decks=num_decks)
    diverged = 0
    for seed in range(300):
        shoe = Shoe.from_seed(seed, num_decks)
        cursor = shoe.cursor()
        first, upcard, second, hole = (cursor.next() for _ in range(4))
        full_dealer_hand = tuple(play_dealer(cursor, upcard, hole, rules))

        a = play_round(shoe, RandomPolicy(seed), 10, rules=rules)
        b = play_round(shoe, RandomPolicy(seed + 10_000), 10, rules=rules)
        diverged += a.actions != b.actions

        for result in (a, b):
            assert result.hands[0].cards[0] == first
            assert result.dealer_cards[:2] == (upcard, hole)
            dealer_played = len(result.actions) > 0 and any(h.total <= 21 for h in result.hands)
            if dealer_played:
                assert result.dealer_cards == full_dealer_hand
            else:  # dealer or player blackjack, or every hand bust: no draws
                assert result.dealer_cards == (upcard, hole)
    assert diverged > 100  # the two players really did play differently


def test_identical_decisions_give_identical_rounds():
    for seed in range(200):
        shoe = Shoe.from_seed(seed)
        bets = SideBets(10, 10)
        a = play_round(shoe, RandomPolicy(seed), 50, bets, balance=1000)
        b = play_round(shoe, RandomPolicy(seed), 50, bets, balance=1000)
        assert a == b


def test_player_cards_match_until_decisions_diverge():
    for seed in range(200):
        shoe = Shoe.from_seed(seed)
        stand = play_round(shoe, ScriptedPolicy([S]), 10)
        hit = play_round(shoe, ScriptedPolicy([H, S]), 10)
        if not stand.actions:  # a blackjack ended the round
            assert stand == hit
            continue
        assert hit.hands[0].cards[:2] == stand.hands[0].cards
        assert hit.hands[0].cards[2] == shoe.cards[4]


def test_side_bets_resolve_identically_for_both_players():
    bets = SideBets(10, 10)
    for seed in range(200):
        shoe = Shoe.from_seed(seed)
        a = play_round(shoe, RandomPolicy(seed), 10, bets)
        b = play_round(shoe, RandomPolicy(seed + 10_000), 10, bets)
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
