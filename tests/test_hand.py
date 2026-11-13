import pytest

from rivals.cards import parse_card, parse_cards
from rivals.hand import Action, Hand, hand_value, insurance_available, legal_actions
from rivals.rules import DEFAULT_RULES

S, H, D, P, R = Action.STAND, Action.HIT, Action.DOUBLE, Action.SPLIT, Action.SURRENDER


def hand(text, bet=10, **kwargs):
    return Hand(parse_cards(text), bet, **kwargs)


@pytest.mark.parametrize(
    "text, total, soft",
    [
        ("Ts 7d", 17, False),
        ("As 6d", 17, True),
        ("As 6d Th", 17, False),
        ("As Ad", 12, True),
        ("As Ad Ah", 13, True),
        ("As Ad 9h", 21, True),
        ("As Ad 9h Tc", 21, False),
        ("As Kd", 21, True),
        ("Ts 6d 9h", 25, False),
        ("5s 5d As", 21, True),
    ],
)
def test_hand_value(text, total, soft):
    assert hand_value(parse_cards(text)) == (total, soft)


def test_first_decision_on_an_ordinary_hand():
    assert legal_actions(hand("Ts 6d"), DEFAULT_RULES) == (S, H, D)


def test_pairs_can_split():
    assert legal_actions(hand("8s 8d"), DEFAULT_RULES) == (S, H, D, P)


def test_no_double_or_split_after_a_hit():
    assert legal_actions(hand("2s 2d 2h"), DEFAULT_RULES) == (S, H)


def test_no_actions_on_21_or_bust():
    assert legal_actions(hand("5s 6d Th"), DEFAULT_RULES) == ()
    assert legal_actions(hand("Ts 6d Th"), DEFAULT_RULES) == ()


def test_only_one_split_by_default():
    split_hand = hand("8s 8d", from_split=True)
    assert P not in legal_actions(split_hand, DEFAULT_RULES, num_hands=2)
    assert P in legal_actions(split_hand, DEFAULT_RULES.with_(max_splits=3), num_hands=2)
    assert P not in legal_actions(hand("8s 8d"), DEFAULT_RULES.with_(max_splits=0))


def test_double_after_split_follows_the_rule():
    split_hand = hand("8s 3d", from_split=True)
    assert D in legal_actions(split_hand, DEFAULT_RULES, num_hands=2)
    no_das = DEFAULT_RULES.with_(double_after_split=False)
    assert D not in legal_actions(split_hand, no_das, num_hands=2)


def test_double_and_split_need_chips_to_cover():
    assert legal_actions(hand("8s 8d", bet=100), DEFAULT_RULES, bankroll=99) == (S, H)
    assert legal_actions(hand("8s 8d", bet=100), DEFAULT_RULES, bankroll=100) == (S, H, D, P)
    lenient = DEFAULT_RULES.with_(require_balance_for_extra_bets=False)
    assert legal_actions(hand("8s 8d", bet=100), lenient, bankroll=0) == (S, H, D, P)


def test_double_can_be_limited_to_certain_totals():
    restricted = DEFAULT_RULES.with_(double_totals=(9, 10, 11))
    for text in ["5s 4d", "6s 4d", "6s 5d"]:
        assert D in legal_actions(hand(text), restricted)
    for text in ["5s 3d", "7s 5d", "As 7d", "Ts 9d"]:  # 8, 12, soft 18, 19
        assert D in legal_actions(hand(text), DEFAULT_RULES)
        assert D not in legal_actions(hand(text), restricted)
    assert legal_actions(hand("5s 5d"), restricted) == (S, H, D, P)
    assert legal_actions(hand("8s 8d"), restricted) == (S, H, P)


def test_mixed_ten_value_cards_split_only_when_allowed():
    assert P in legal_actions(hand("Ks Qd"), DEFAULT_RULES)
    strict = DEFAULT_RULES.with_(split_by_value=False)
    assert P not in legal_actions(hand("Ks Qd"), strict)
    assert P in legal_actions(hand("Ks Kd"), strict)


def test_split_aces_can_be_hit_and_doubled_by_default():
    aces = hand("As 5d", from_split=True)
    assert legal_actions(aces, DEFAULT_RULES, num_hands=2) == (S, H, D)
    assert legal_actions(aces, DEFAULT_RULES.with_(hit_split_aces=False), num_hands=2) == ()


def test_surrender_is_off_by_default_and_first_decision_only():
    assert R not in legal_actions(hand("Ts 6d"), DEFAULT_RULES)
    with_surrender = DEFAULT_RULES.with_(surrender=True)
    assert R in legal_actions(hand("Ts 6d"), with_surrender)
    assert R not in legal_actions(hand("Ts 3d 3h"), with_surrender)
    assert R not in legal_actions(hand("Ts 6d", from_split=True), with_surrender, num_hands=2)


def test_blackjack_is_two_cards_and_not_from_a_split():
    assert hand("As Kd").is_blackjack(DEFAULT_RULES)
    assert not hand("5s 6d Th").is_blackjack(DEFAULT_RULES)
    assert not hand("As Kd", from_split=True).is_blackjack(DEFAULT_RULES)
    assert hand("As Kd", from_split=True).is_blackjack(
        DEFAULT_RULES.with_(split_21_is_blackjack=True)
    )


def test_insurance_is_offered_only_against_an_ace_and_when_affordable():
    ace, ten = parse_card("As"), parse_card("Ks")
    assert insurance_available(ace, 100, 50, DEFAULT_RULES)
    assert not insurance_available(ace, 100, 49, DEFAULT_RULES)
    assert not insurance_available(ten, 100, 1000, DEFAULT_RULES)
    assert not insurance_available(ace, 100, 1000, DEFAULT_RULES.with_(insurance_offered=False))
