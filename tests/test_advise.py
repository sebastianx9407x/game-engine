"""The situation -> recommendation lookup."""

import random

import pytest

from rivals.advise import advise_bet, advise_play, history_key, main
from rivals.agents.optimal import PolicyAgent
from rivals.hand import Action
from rivals.match import play_player
from rivals.optimize.pipeline import DEFAULT_POLICY_PATH, load_policy
from rivals.rules import DEFAULT_RULES
from rivals.shoe import match_shoes


@pytest.fixture(scope="module")
def policy():
    return load_policy(DEFAULT_POLICY_PATH)


def test_opening_bet_is_legal_and_described(policy):
    advice = advise_bet(policy, 1000)
    assert 10 <= advice.main <= 1000
    assert advice.main + advice.perfect_pairs + advice.four_card_total <= 1000
    assert str(advice).startswith(f"bet {advice.main:g}")
    assert advice.style in policy.style_names


def test_advice_matches_what_the_optimized_agent_does(policy):
    agent = PolicyAgent(policy)
    letters = {-1: "L", 0: "P", 1: "W"}
    for seed in range(150):
        played = play_player(agent, match_shoes(seed), random.Random(0))
        results = ""
        for record in played.rounds:
            advice = advise_bet(policy, record.balance_before, results)
            assert advice.main == record.bet
            assert advice.perfect_pairs == record.side_bets.perfect_pairs
            assert advice.four_card_total == record.side_bets.four_card_total
            net = record.result.main_net
            results += letters[(net > 0) - (net < 0)]


def test_history_key_reads_letters(policy):
    assert history_key(policy, "") == 0
    assert history_key(policy, "wl") == history_key(policy, "WL")
    with pytest.raises(KeyError):
        history_key(policy, "X")


def test_bet_advice_refuses_impossible_situations(policy):
    with pytest.raises(ValueError):
        advise_bet(policy, 5)
    with pytest.raises(ValueError):
        advise_bet(policy, 1000, "WLWLW")


def test_play_advice_follows_the_real_rules(policy):
    rules = DEFAULT_RULES
    assert advise_play("6s 5d", "6c", rules=rules) == Action.DOUBLE
    assert advise_play("6s 5d", "Tc", rules=rules) == Action.HIT  # hidden blackjack risk
    assert advise_play("6s 5d", "Tc", rules=rules, style="seek", policy=policy) == Action.DOUBLE
    assert advise_play("6s 5d", "6c", rules=rules, can_afford_more=False) == Action.HIT
    assert advise_play("8s 8h", "6c", rules=rules) == Action.SPLIT
    assert advise_play("8s 8h", "Tc", rules=rules) == Action.HIT
    assert advise_play("8s 8h", "6c", rules=rules, after_split=True) == Action.STAND
    assert advise_play("Ts 6d", "7c", rules=rules) == Action.HIT
    assert advise_play("Ts 6d 2h", "7c", rules=rules) == Action.STAND
    assert advise_play("5s 6d Th", "7c", rules=rules) == Action.STAND  # 21: nothing to do
    with pytest.raises(ValueError):
        advise_play("6s 5d", "Tc", rules=rules, style="wild", policy=policy)


def test_command_line(capsys):
    assert main(["bet", "--balance", "1000"]) == 0
    assert capsys.readouterr().out.startswith("bet ")
    assert main(["play", "--cards", "6s 5d", "--up", "6c"]) == 0
    assert capsys.readouterr().out.strip() == "double"
