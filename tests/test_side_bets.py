from fractions import Fraction
from itertools import combinations

import pytest

from conftest import play
from rivals.cards import fresh_decks, parse_card, parse_cards
from rivals.hand import Action
from rivals.rules import DEFAULT_RULES
from rivals.side_bets import (
    PairType,
    SideBets,
    four_card_total,
    four_card_total_payout,
    pair_type,
    perfect_pairs_payout,
    settle,
    settle_side_bets,
)


@pytest.mark.parametrize(
    "a, b, kind, payout",
    [
        ("8h", "8h", PairType.PERFECT, 25),
        ("8h", "8d", PairType.COLORED, 12),
        ("8s", "8c", PairType.COLORED, 12),
        ("8h", "8s", PairType.MIXED, 6),
        ("8d", "8c", PairType.MIXED, 6),
        ("8h", "9h", PairType.NONE, 0),
        ("Kh", "Qh", PairType.NONE, 0),  # same value, different rank: not a pair
        ("Th", "Jh", PairType.NONE, 0),
    ],
)
def test_perfect_pairs_table(a, b, kind, payout):
    ca, cb = parse_card(a), parse_card(b)
    assert pair_type(ca, cb) is kind
    assert pair_type(cb, ca) is kind
    assert perfect_pairs_payout(ca, cb, DEFAULT_RULES) == payout


@pytest.mark.parametrize(
    "total, payout",
    [(20, 0), (35, 0), (36, 2), (37, 2), (38, 8), (39, 8), (40, 10), (41, 10), (44, 10)],
)
def test_four_card_total_table(total, payout):
    assert four_card_total_payout(total, DEFAULT_RULES) == payout


@pytest.mark.parametrize(
    "player, dealer, total",
    [
        ("As Ad", "Ah Ac", 44),  # aces always count 11
        ("Ks Qd", "Jh Tc", 40),
        ("As Kd", "9h 8c", 38),
        ("As 5d", "Th Tc", 36),
        ("9s 9d", "9h 8c", 35),
        ("2s 3d", "4h 5c", 14),
    ],
)
def test_four_card_total_sums_all_four_starting_cards(player, dealer, total):
    assert four_card_total(*parse_cards(player), *parse_cards(dealer)) == total


def test_settle_pays_odds_to_one_and_loses_the_stake():
    assert settle(20, 25) == 500
    assert settle(20, 0) == -20
    assert settle(0, 25) == 0
    assert settle(0, 0) == 0


def test_settle_side_bets_handles_each_bet_separately():
    cards = (*parse_cards("8h 8h"), *parse_cards("2s 3c"))
    assert settle_side_bets(SideBets(10, 20), *cards, DEFAULT_RULES) == (250, -20)
    assert settle_side_bets(SideBets(0, 20), *cards, DEFAULT_RULES) == (0, -20)
    cards = (*parse_cards("Ks Qd"), *parse_cards("Jh Tc"))
    assert settle_side_bets(SideBets(10, 20), *cards, DEFAULT_RULES) == (-10, 200)


def pair_odds(num_decks):
    deck = fresh_decks(num_decks).tolist()
    counts = {kind: 0 for kind in PairType}
    pairs = 0
    for a, b in combinations(deck, 2):
        counts[pair_type(a, b)] += 1
        pairs += 1
    return {kind: Fraction(n, pairs) for kind, n in counts.items()}


def test_pair_frequencies_in_six_decks():
    odds = pair_odds(6)
    assert odds[PairType.PERFECT] == Fraction(5, 311)
    assert odds[PairType.COLORED] == Fraction(6, 311)
    assert odds[PairType.MIXED] == Fraction(12, 311)


def test_single_deck_has_no_perfect_pairs():
    odds = pair_odds(1)
    assert odds[PairType.PERFECT] == 0
    assert odds[PairType.COLORED] == Fraction(1, 51)
    assert odds[PairType.MIXED] == Fraction(2, 51)


def test_side_bets_pay_even_when_the_main_hand_loses():
    # 8h 8h is a perfect pair; hitting 16 into a ten busts the main hand.
    result, _ = play(
        "8h 8h", "Tc 7d", [Action.HIT], player_draws="Ks", side_bets=SideBets(perfect_pairs=10)
    )
    assert result.main_net == -10
    assert result.perfect_pairs_net == 250
    assert result.net == 240


def test_side_bets_lose_even_when_the_main_hand_wins():
    result, _ = play("Ts 9d", "Tc 7d", side_bets=SideBets(10, 10))
    assert result.main_net == 10
    assert (result.perfect_pairs_net, result.four_card_total_net) == (-10, 20)  # total 36
    assert result.net == 20


def test_four_card_total_counts_the_hole_card_under_a_dealer_blackjack():
    result, _ = play("Ks Qd", "Ah Jc", side_bets=SideBets(four_card_total=10))
    assert result.dealer_blackjack
    assert result.main_net == -10
    assert result.four_card_total_net == 100  # 10 + 10 + 11 + 10 = 41


def test_side_bets_do_not_depend_on_how_the_hand_is_played():
    bets = SideBets(10, 10)
    stand, _ = play("8h 8d", "Tc Td", side_bets=bets)
    split, _ = play("8h 8d", "Tc Td", [Action.SPLIT], player_draws="Ts Th", side_bets=bets)
    assert stand.side_net == split.side_net == 120 + 20
