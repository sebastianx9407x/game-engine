import pytest

from rivals import cards
from rivals.rules import DEFAULT_RULES, RulesConfig


def test_every_card_round_trips_through_its_name():
    names = {cards.card_name(c) for c in range(52)}
    assert len(names) == 52
    for c in range(52):
        assert cards.parse_card(cards.card_name(c)) == c


def test_card_values():
    assert cards.value_of(cards.parse_card("As")) == 11
    assert [cards.value_of(cards.parse_card(r + "h")) for r in "23456789"] == list(range(2, 10))
    assert all(cards.value_of(cards.parse_card(r + "d")) == 10 for r in "TJQK")
    assert cards.parse_card("10h") == cards.parse_card("Th")


def test_colors():
    assert cards.color_of(cards.parse_card("As")) == cards.BLACK
    assert cards.color_of(cards.parse_card("Ac")) == cards.BLACK
    assert cards.color_of(cards.parse_card("Ah")) == cards.RED
    assert cards.color_of(cards.parse_card("Ad")) == cards.RED


@pytest.mark.parametrize("bad", ["", "A", "1s", "Ax", "AAs"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ValueError):
        cards.parse_card(bad)


def test_default_rules_match_the_published_game():
    r = DEFAULT_RULES
    assert (r.starting_chips, r.num_rounds, r.min_bet, r.max_bet) == (1000, 5, 10, None)
    assert r.num_decks == 6
    assert r.prize_multiple == 1.8
    assert r.tie_value == pytest.approx(5 / 9)  # a tie refunds the entry fee
    assert r.with_(prize_multiple=2.0).tie_value == 0.5
    assert r.with_(match_tie_value=0.4).tie_value == 0.4
    assert not r.dealer_hits_soft_17
    assert (r.blackjack_payout, r.insurance_payout) == (1.5, 2.0)
    assert r.max_splits == 1 and r.double_after_split and r.hit_split_aces
    assert r.double_totals == (9, 10, 11)
    assert r.dealer_peeks_on_ace and not r.dealer_peeks_on_ten
    assert r.split_deal_both_first and r.split_by_value and not r.split_21_is_blackjack
    assert r.side_bet_min == 5
    assert not r.surrender
    assert (r.perfect_pair_payout, r.colored_pair_payout, r.mixed_pair_payout) == (25, 12, 6)
    assert r.four_card_total_payouts == ((40, 10), (38, 8), (36, 2))


def test_rules_are_immutable_and_copyable():
    one_deck = DEFAULT_RULES.with_(num_decks=1)
    assert one_deck.num_decks == 1 and DEFAULT_RULES.num_decks == 6
    with pytest.raises(AttributeError):
        DEFAULT_RULES.num_decks = 2


@pytest.mark.parametrize(
    "bad",
    [
        {"num_decks": 0},
        {"num_rounds": 0},
        {"min_bet": 0},
        {"max_bet": 5},
        {"max_splits": -1},
        {"four_card_total_payouts": ((36, 2), (40, 10))},
    ],
)
def test_rules_reject_nonsense(bad):
    with pytest.raises(ValueError):
        RulesConfig(**bad)
