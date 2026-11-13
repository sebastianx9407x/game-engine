import pytest

from conftest import play
from rivals.cards import parse_cards
from rivals.hand import Action
from rivals.resolve import IllegalActionError, Outcome
from rivals.rules import DEFAULT_RULES

S, H, D, P = Action.STAND, Action.HIT, Action.DOUBLE, Action.SPLIT


def cards_of(result):
    return [h.cards for h in result.hands]


def hands(*texts):
    return [tuple(parse_cards(t)) for t in texts]


# --- double -----------------------------------------------------------------


def test_double_wins_twice_the_bet_and_takes_exactly_one_card():
    result, policy = play("6s 5d", "Tc 8h", [D, H], player_draws="9h 2c", bet=10)
    assert result.hands[0].cards == tuple(parse_cards("6s 5d 9h"))
    assert result.hands[0].doubled and result.hands[0].bet == 20
    assert result.net == 20
    assert len(policy.legal_seen) == 1  # no decision after doubling


def test_double_loses_twice_the_bet():
    result, _ = play("6s 5d", "Tc 8h", [D], player_draws="2h", bet=10)
    assert result.net == -20


def test_double_push_returns_everything():
    result, _ = play("6s 5d", "Tc 8h", [D], player_draws="7h", bet=10)
    assert result.net == 0


def test_double_is_only_offered_on_nine_ten_or_eleven():
    for player in ["5s 4d", "6s 4d", "6s 5d", "5s 5d"]:
        _, policy = play(player, "Tc 8h", [S])
        assert D in policy.legal_seen[0]
    for player in ["2s 3d", "5s 3d", "7s 5d", "As 7d", "7s 7d"]:
        _, policy = play(player, "Tc 8h", [S])
        assert D not in policy.legal_seen[0]
    with pytest.raises(IllegalActionError):
        play("As 7d", "Tc 8h", [D], player_draws="2h")


def test_double_on_any_two_cards_when_configured():
    any_two = DEFAULT_RULES.with_(double_totals=None)
    for player in ["2s 3d", "Ts 9d", "As 7d", "7s 7d"]:
        _, policy = play(player, "Tc 8h", [S], rules=any_two)
        assert D in policy.legal_seen[0]
    result, _ = play("As 7d", "Tc 8h", [D], player_draws="2h", rules=any_two)
    assert result.net == 20  # soft 18 + 2 = 20 beats 18


def test_double_is_not_allowed_after_a_hit():
    with pytest.raises(IllegalActionError):
        play("2s 3d", "Tc 8h", [H, D], player_draws="4h 5c")


def test_double_needs_chips_to_cover():
    with pytest.raises(IllegalActionError):
        play("6s 5d", "Tc 8h", [D], player_draws="9h", bet=100, balance=199)
    result, _ = play("6s 5d", "Tc 8h", [D], player_draws="9h", bet=100, balance=200)
    assert result.net == 200


def test_side_bets_and_insurance_reduce_what_is_left_to_double_with():
    # 100 main + 5 insurance leaves 95 of 200: not enough to double.
    with pytest.raises(IllegalActionError):
        play("6s 5d", "Ac 8h", [D], player_draws="9h", bet=100, balance=200, insurance=True)


# --- split ------------------------------------------------------------------


def test_split_plays_two_hands_with_the_original_bet_each():
    result, _ = play("8s 8h", "Tc 7h", [P, S, H], player_draws="Td 3c Ts", bet=10)
    assert cards_of(result) == hands("8s Td", "8h 3c Ts")
    assert [h.bet for h in result.hands] == [10, 10]
    assert [h.outcome for h in result.hands] == [Outcome.WIN, Outcome.WIN]
    assert result.net == 20


def test_split_hands_settle_separately():
    # First hand busts, second beats the dealer's 17.
    result, _ = play("8s 8h", "Tc 7h", [P, H, S], player_draws="5d Kc Ts")
    assert cards_of(result) == hands("8s 5d Kc", "8h Ts")
    assert [h.outcome for h in result.hands] == [Outcome.BUST, Outcome.WIN]
    assert result.net == 0


def test_second_split_hand_gets_its_card_when_its_turn_starts():
    result, _ = play("8s 8h", "Tc 7h", [P, H, S, S], player_draws="2d 3c Ts")
    assert cards_of(result) == hands("8s 2d 3c", "8h Ts")


def test_both_split_hands_can_be_dealt_up_front():
    both_first = DEFAULT_RULES.with_(split_deal_both_first=True)
    result, _ = play("8s 8h", "Tc 7h", [P, H, S, S], player_draws="2d 3c Ts", rules=both_first)
    assert cards_of(result) == hands("8s 2d Ts", "8h 3c")


def test_only_one_split_is_allowed():
    _, policy = play("8s 8h", "Tc 7h", [P, S, S], player_draws="8d 8c")
    first, left, right = policy.legal_seen
    assert P in first
    assert P not in left and P not in right  # both are pairs of eights again
    with pytest.raises(IllegalActionError):
        play("8s 8h", "Tc 7h", [P, P], player_draws="8d 8c")


def test_resplit_when_configured():
    resplit = DEFAULT_RULES.with_(max_splits=2)
    result, _ = play("8s 8h", "Tc 7h", [P, P, S, S, S], player_draws="8d Ts Th Td", rules=resplit)
    assert cards_of(result) == hands("8s Ts", "8d Th", "8h Td")
    assert result.net == 30


def test_only_pairs_can_split():
    _, policy = play("8s 9h", "Tc 7h", [S])
    assert P not in policy.legal_seen[0]
    with pytest.raises(IllegalActionError):
        play("8s 9h", "Tc 7h", [P])


def test_ten_value_cards_split_by_value_unless_configured_otherwise():
    result, _ = play("Ks Qh", "Tc 7h", [P, S, S], player_draws="9d 9c")
    assert cards_of(result) == hands("Ks 9d", "Qh 9c")
    with pytest.raises(IllegalActionError):
        play("Ks Qh", "Tc 7h", [P], rules=DEFAULT_RULES.with_(split_by_value=False))


def test_split_needs_chips_to_cover():
    with pytest.raises(IllegalActionError):
        play("8s 8h", "Tc 7h", [P], player_draws="Td Ts", bet=100, balance=199)
    result, _ = play("8s 8h", "Tc 7h", [P, S, S], player_draws="Td Ts", bet=100, balance=200)
    assert result.net == 200


def test_double_after_split():
    result, policy = play("8s 8h", "Tc 7h", [P, D, S], player_draws="3d Kc 2d", bet=10)
    assert cards_of(result) == hands("8s 3d Kc", "8h 2d")
    assert [h.bet for h in result.hands] == [20, 10]
    assert [h.doubled for h in result.hands] == [True, False]
    assert result.net == 10  # doubled 21 wins 20, the 10 loses to 17
    assert D in policy.legal_seen[1] and D in policy.legal_seen[2]


def test_double_after_split_can_be_switched_off():
    no_das = DEFAULT_RULES.with_(double_after_split=False)
    with pytest.raises(IllegalActionError):
        play("8s 8h", "Tc 7h", [P, D], player_draws="3d Kc Td", rules=no_das)


def test_chips_run_out_across_split_and_double():
    # 30 chips: 10 bet, 10 to split, 10 to double the first hand, none for the second.
    _, policy = play(
        "8s 8h", "Tc 7h", [P, D, S], player_draws="3d Kc 3c", bet=10, balance=30
    )
    assert D in policy.legal_seen[1]
    assert D not in policy.legal_seen[2]


def test_split_aces_can_be_hit():
    result, policy = play("As Ah", "Tc 7h", [P, H, S, S], player_draws="5d 4c 6s")
    assert cards_of(result) == hands("As 5d 4c", "Ah 6s")
    assert H in policy.legal_seen[1]
    assert [h.total for h in result.hands] == [20, 17]
    assert result.net == 10  # win and push


def test_split_aces_get_one_card_each_when_hitting_is_off():
    one_card = DEFAULT_RULES.with_(hit_split_aces=False)
    result, policy = play("As Ah", "Tc 7h", [P, H, H], player_draws="5d Kc", rules=one_card)
    assert cards_of(result) == hands("As 5d", "Ah Kc")
    assert len(policy.legal_seen) == 1  # only the split itself
    assert result.net == 0  # 16 loses, 21 wins


def test_21_after_a_split_pays_even_money():
    result, policy = play("As Ah", "Tc 7h", [P, S], player_draws="Kd 9c", bet=10)
    assert result.hands[0].total == 21
    assert result.hands[0].outcome is Outcome.WIN
    assert result.hands[0].net == 10
    assert not result.player_blackjack
    assert len(policy.legal_seen) == 2  # the 21 stood on its own


def test_21_after_a_split_can_pay_as_blackjack_when_configured():
    generous = DEFAULT_RULES.with_(split_21_is_blackjack=True)
    result, _ = play("As Ah", "Tc 7h", [P, S], player_draws="Kd 9c", bet=10, rules=generous)
    assert result.hands[0].outcome is Outcome.BLACKJACK
    assert result.hands[0].net == 15


def test_dealer_still_draws_when_one_split_hand_survives():
    result, _ = play(
        "8s 8h", "Tc 6h", [P, H, S], player_draws="5d Kc Ts", dealer_draws="Kd"
    )
    assert result.dealer_cards == tuple(parse_cards("Tc 6h Kd"))
    assert cards_of(result) == hands("8s 5d Kc", "8h Ts")
    assert [h.outcome for h in result.hands] == [Outcome.BUST, Outcome.WIN]


def test_dealer_does_not_draw_when_every_split_hand_busts():
    result, _ = play(
        "8s 8h", "Tc 6h", [P, H, H], player_draws="5d Kc 6s Ks", dealer_draws="Kd"
    )
    assert result.dealer_cards == tuple(parse_cards("Tc 6h"))
    assert cards_of(result) == hands("8s 5d Kc", "8h 6s Ks")
    assert result.net == -20
