import pytest

from conftest import NeverAsked, play
from rivals.cards import parse_cards
from rivals.hand import Action
from rivals.resolve import IllegalActionError, InvalidBetError, Outcome, play_round
from rivals.rules import DEFAULT_RULES
from rivals.shoe import Shoe
from rivals.side_bets import SideBets

S, H, D, P, R = Action.STAND, Action.HIT, Action.DOUBLE, Action.SPLIT, Action.SURRENDER


# --- main bet ---------------------------------------------------------------


@pytest.mark.parametrize("bet, net", [(10, 15), (25, 37.5), (100, 150), (1000, 1500)])
def test_blackjack_pays_three_to_two(bet, net):
    result, policy = play("As Kd", "9c 7h", bet=bet)
    assert result.net == net
    assert result.player_blackjack
    assert result.hands[0].outcome is Outcome.BLACKJACK
    assert policy.legal_seen == []  # the round ends without a decision


def test_win_pays_even_money():
    result, _ = play("Ts 9d", "Tc 8h", bet=50)
    assert result.net == 50
    assert result.hands[0].outcome is Outcome.WIN


def test_loss_costs_the_bet():
    result, _ = play("Ts 7d", "Tc 9h", bet=50)
    assert result.net == -50
    assert result.hands[0].outcome is Outcome.LOSE


def test_push_returns_the_bet():
    result, _ = play("Ts 8d", "Tc 8h", bet=50)
    assert result.net == 0
    assert result.hands[0].outcome is Outcome.PUSH


def test_bust_loses_and_the_dealer_does_not_draw():
    result, _ = play("Ts 6d", "9c 7h", [H], player_draws="Kh", dealer_draws="5d")
    assert result.net == -10
    assert result.hands[0].outcome is Outcome.BUST
    assert result.dealer_cards == tuple(parse_cards("9c 7h"))


def test_dealer_bust_pays_any_standing_hand():
    result, _ = play("Ts 2d", "6c Th", dealer_draws="Kd")
    assert result.dealer_bust and result.dealer_total == 26
    assert result.net == 10


def test_dealer_draws_to_17_and_stops():
    result, _ = play("Ts 9d", "2c 3h", dealer_draws="4d 5s 3c 9h")
    assert result.dealer_cards == tuple(parse_cards("2c 3h 4d 5s 3c"))
    assert result.dealer_total == 17
    assert result.net == 10


def test_dealer_stands_on_soft_17():
    result, _ = play("Ts 8d", "As 6d", dealer_draws="4c")
    assert result.dealer_cards == tuple(parse_cards("As 6d"))
    assert result.net == 10


def test_dealer_hits_soft_17_when_configured():
    h17 = DEFAULT_RULES.with_(dealer_hits_soft_17=True)
    result, _ = play("Ts 8d", "As 6d", dealer_draws="4c", rules=h17)
    assert result.dealer_cards == tuple(parse_cards("As 6d 4c"))
    assert result.net == -10


def test_multi_card_21_is_not_a_blackjack():
    result, _ = play("5s 6d", "Tc 8h", [H], player_draws="Th", bet=10)
    assert result.hands[0].total == 21
    assert result.hands[0].outcome is Outcome.WIN
    assert result.net == 10


def test_21_stands_automatically():
    result, policy = play("5s 6d", "Tc 8h", [H, H], player_draws="Th 2c")
    assert len(policy.legal_seen) == 1
    assert result.hands[0].cards == tuple(parse_cards("5s 6d Th"))


def test_blackjack_payout_is_configurable():
    six_to_five = DEFAULT_RULES.with_(blackjack_payout=1.2)
    result, _ = play("As Kd", "9c 7h", bet=100, rules=six_to_five)
    assert result.net == 120


# --- dealer blackjack and insurance -----------------------------------------


def test_dealer_blackjack_under_an_ace_ends_the_round_before_the_player_acts():
    shoe = Shoe.stacked("Ts 9d", "Ac Kh")
    result = play_round(shoe, NeverAsked(), 10)
    assert result.dealer_blackjack
    assert result.net == -10
    assert result.actions == ()


def test_dealer_blackjack_under_a_ten_is_not_revealed_until_the_player_has_acted():
    result, policy = play("Ts 9d", "Kc Ah", [S])
    assert len(policy.legal_seen) == 1  # the player got to act
    assert result.dealer_blackjack
    assert result.dealer_cards == tuple(parse_cards("Kc Ah"))
    assert result.net == -10


def test_dealer_blackjack_under_a_ten_takes_doubled_bets():
    result, _ = play("6s 5d", "Kc Ah", [D], player_draws="Th", bet=10)
    assert result.hands[0].total == 21
    assert result.net == -20


def test_dealer_blackjack_under_a_ten_takes_both_split_bets():
    result, _ = play("8s 8h", "Kc Ah", [P, S, S], player_draws="Td 9c", bet=10)
    assert [h.outcome for h in result.hands] == [Outcome.LOSE, Outcome.LOSE]
    assert result.net == -20


def test_ace_ten_after_a_split_still_loses_to_a_dealer_blackjack_under_a_ten():
    result, _ = play("As Ad", "Kc Ah", [P, S, S], player_draws="Td 9c", bet=10)
    assert result.hands[0].total == 21
    assert [h.outcome for h in result.hands] == [Outcome.LOSE, Outcome.LOSE]
    assert result.net == -20


def test_peek_under_a_ten_when_configured():
    peeking = DEFAULT_RULES.with_(dealer_peeks_on_ten=True)
    shoe = Shoe.stacked("6s 5d", "Kc Ah")
    result = play_round(shoe, NeverAsked(), 10, rules=peeking)
    assert result.net == -10


@pytest.mark.parametrize("dealer", ["Kc Ah", "Ac Kh"])
def test_blackjack_against_dealer_blackjack_pushes(dealer):
    result, _ = play("As Kd", dealer)
    assert result.net == 0
    assert result.hands[0].outcome is Outcome.PUSH


def test_insurance_pays_two_to_one_against_a_dealer_blackjack():
    result, _ = play("Ts 9d", "Ac Kh", insurance=True, bet=10)
    assert result.insurance_bet == 5
    assert result.insurance_net == 10
    assert result.main_net == -10
    assert result.net == 0


def test_insurance_loses_when_the_dealer_has_no_blackjack():
    result, _ = play("Ts 9d", "Ac 9h", insurance=True, bet=10)
    assert result.insurance_net == -5
    assert result.main_net == -10  # 19 against 20
    assert result.net == -15


def test_insured_blackjack_is_even_money_either_way():
    no_bj, _ = play("As Kd", "Ac 9h", insurance=True, bet=10)
    dealer_bj, _ = play("As Kd", "Ac Kh", insurance=True, bet=10)
    assert no_bj.net == dealer_bj.net == 10


def test_insurance_is_not_offered_against_a_ten():
    result, policy = play("Ts 9d", "Kc Ah", insurance=True)
    assert policy.insurance_offers == 0
    assert result.insurance_bet == 0
    assert result.net == -10


def test_insurance_needs_spare_chips():
    result, policy = play("Ts 9d", "Ac Kh", insurance=True, bet=100, balance=140)
    assert policy.insurance_offers == 0 and result.net == -100
    result, policy = play("Ts 9d", "Ac Kh", insurance=True, bet=100, balance=150)
    assert policy.insurance_offers == 1 and result.net == 0


def test_declining_insurance_costs_nothing():
    result, policy = play("Ts 9d", "Ac 7h")
    assert policy.insurance_offers == 1
    assert result.insurance_bet == 0 and result.net == 10


def test_without_a_peek_under_an_ace_the_dealer_blackjack_takes_doubles_too():
    no_peek = DEFAULT_RULES.with_(dealer_peeks_on_ace=False)
    result, policy = play("6s 5d", "Ac Kh", [D], player_draws="Th", rules=no_peek)
    assert len(policy.legal_seen) == 1  # the player got to act
    assert result.net == -20
    insured, _ = play("6s 5d", "Ac Kh", [D], player_draws="Th", insurance=True, rules=no_peek)
    assert insured.net == -20 + 10
    blackjack, _ = play("As Kd", "Ac Kh", rules=no_peek)
    assert blackjack.net == 0


# --- surrender --------------------------------------------------------------


def test_surrender_is_illegal_by_default():
    with pytest.raises(IllegalActionError):
        play("Ts 6d", "Tc 9h", [R])


def test_surrender_loses_half_when_enabled():
    result, _ = play("Ts 6d", "Tc 9h", [R], rules=DEFAULT_RULES.with_(surrender=True))
    assert result.net == -5
    assert result.hands[0].outcome is Outcome.SURRENDER


# --- wager limits -----------------------------------------------------------


def test_bet_below_the_minimum_is_rejected():
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", bet=9)


def test_bet_can_be_the_whole_balance_but_no_more():
    result, _ = play("Ts 9d", "Tc 8h", bet=1000, balance=1000)
    assert result.net == 1000
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", bet=1001, balance=1000)


def test_side_bets_count_against_the_balance():
    play("Ts 9d", "Tc 8h", bet=980, balance=1000, side_bets=SideBets(10, 10))
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", bet=990, balance=1000, side_bets=SideBets(10, 10))


def test_side_bet_limits():
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", side_bets=SideBets(perfect_pairs=4))
    result, _ = play("Ts 9d", "Tc 8h", side_bets=SideBets(perfect_pairs=5))
    assert result.perfect_pairs_net == -5
    capped = DEFAULT_RULES.with_(side_bet_max=100)
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", side_bets=SideBets(four_card_total=101), rules=capped)


def test_max_bet_when_configured():
    capped = DEFAULT_RULES.with_(max_bet=500)
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", bet=501, rules=capped)


def test_short_stack_all_in_follows_the_rule():
    with pytest.raises(InvalidBetError):
        play("Ts 9d", "Tc 8h", bet=5, balance=5)
    lenient = DEFAULT_RULES.with_(allow_short_all_in=True)
    result, _ = play("Ts 9d", "Tc 8h", bet=5, balance=5, rules=lenient)
    assert result.net == 5
    with pytest.raises(InvalidBetError):  # still must be the whole stack
        play("Ts 9d", "Tc 8h", bet=5, balance=8, rules=lenient)


def test_illegal_action_is_rejected():
    with pytest.raises(IllegalActionError):
        play("Ts 9d", "Tc 8h", [P])
