"""The bet-schedule search."""

import pickle
import random

import numpy as np
import pytest

from rivals.agents import Agent
from rivals.agents.optimal import PolicyAgent, PolicyAgentFactory
from rivals.match import play_player, simulate
from rivals.optimize.bet_policy import (
    BetAction,
    build_scenarios,
    default_actions,
    default_grid,
    describe_key,
    history_keys,
    num_history_keys,
    policy_finals,
    policy_score,
    solve_bet_policy,
)
from rivals.rules import DEFAULT_RULES
from rivals.shoe import match_shoes


class Flat(Agent):
    def __init__(self, amount):
        super().__init__()
        self.amount = amount
        self.name = f"flat-{amount}"

    def bet(self, state):
        return state.clamp_bet(self.amount)


class FlatMix:
    """Opponents who bet a fixed amount every hand, picked at random per match."""

    def __call__(self, rng):
        return Flat(rng.choice([10, 10, 25, 100, 250]))


SMALL_ACTIONS = [
    BetAction(main=10, label="bet 10"),
    BetAction(main=50, label="bet 50"),
    BetAction(main=200, label="bet 200"),
    BetAction(main_fraction=0.5, label="bet half"),
    BetAction(main_fraction=1.0, label="all-in"),
    BetAction(main=10, total=100, label="bet 10 + 100 on 4-card total"),
]
SMALL_GRID = np.array([10, 50, 100, 250, 500, 750, 900, 1000, 1100, 1250, 1500, 2000, 3000], dtype=float)


@pytest.fixture(scope="module")
def train():
    return build_scenarios(FlatMix(), 4000, seed=0)


@pytest.fixture(scope="module")
def policy(train):
    return solve_bet_policy(train, actions=SMALL_ACTIONS, grid=SMALL_GRID, history="count")


# --- scenarios --------------------------------------------------------------------


def test_scenarios_record_unit_results_side_bets_and_opponents(train):
    assert train.units.shape == (1, 4000, 5, 4)
    assert train.pairs.shape == train.totals.shape == (4000, 5)
    assert train.opponents.shape == (4000, 2)
    # Without spare chips there is no double or split: one unit at most, 1.5 on a blackjack.
    assert set(np.unique(train.units[0, :, :, 0])) <= {-1.0, 0.0, 1.0, 1.5}
    assert train.units[0, :, :, 3].min() == -4.0 or train.units[0, :, :, 3].min() == -3.0
    # More spare chips never changes a hand that was not doubled or split.
    same = train.units[0, :, :, 0] == train.units[0, :, :, 3]
    assert 0.80 < same.mean() < 0.95
    assert set(np.unique(train.pairs)) <= {0.0, 6.0, 12.0, 25.0}
    assert set(np.unique(train.totals)) <= {0.0, 2.0, 8.0, 10.0}
    assert 0.06 < (train.pairs > 0).mean() < 0.09  # about 7.4% of hands are pairs
    assert abs(train.units[0, :, :, 3].mean() + 0.005) < 0.02


def test_scenarios_are_reproducible_and_parallel_matches_serial():
    a = build_scenarios(FlatMix(), 300, seed=50)
    b = build_scenarios(FlatMix(), 300, seed=50, processes=2)
    for name in ("units", "pairs", "totals", "opponents", "seeds"):
        assert np.array_equal(getattr(a, name), getattr(b, name)), name


def test_recorded_opponents_match_real_play():
    sc = build_scenarios(lambda rng: Flat(100), 50, seed=7, opponents_per_match=1)
    for i, seed in enumerate(sc.seeds):
        real = play_player(Flat(100), match_shoes(int(seed)), random.Random(0)).final_balance
        assert sc.opponents[i, 0] == real


# --- actions and keys -------------------------------------------------------------


def test_bet_action_amounts_and_validity():
    rules = DEFAULT_RULES
    assert BetAction(main=100).amounts(1000) == (100, 0, 0)
    assert BetAction(main_fraction=0.5).amounts(1015)[0] == 505  # whole chips of 5
    assert BetAction(main_fraction=1.0).amounts(1037.5)[0] == 1035
    main, pairs, total = BetAction(main=10, total_rest=1.0).amounts(1000)
    assert (main, pairs, total) == (10, 0, 990)
    assert BetAction(main=100).valid(100, rules) and not BetAction(main=100).valid(95, rules)
    assert not BetAction(main_fraction=0.5).valid(15, rules)  # half of 15 is under the minimum
    assert not BetAction(main=10, total=100).valid(105, rules)
    assert BetAction(main=10, total=100).valid(110, rules)
    # With 2 chips left over the side stake rounds down to nothing: a plain 10 bet.
    assert BetAction(main=10, total_rest=1.0).amounts(12) == (10, 0, 0)
    assert BetAction(main=10, total_rest=1.0).valid(12, rules)
    for action in default_actions():
        assert action.valid(1000, rules), action.label
    assert all(np.diff(default_grid()) > 0)


def test_history_keys():
    cats = np.array([[2, 0, 1, 2, 0], [0, 0, 0, 0, 0]])
    assert history_keys(cats, 0, "pattern").tolist() == [0, 0]
    assert history_keys(cats, 3, "pattern").tolist() == [2 + 0 * 3 + 1 * 9, 0]
    assert describe_key(11, 3, "pattern") == "WLP"
    assert history_keys(cats, 4, "count").tolist() == [2 * 5 + 1, 0 * 5 + 4]
    assert describe_key(11, 4, "count") == "2W 1L"
    assert history_keys(cats, 4, "none").tolist() == [0, 0]
    assert num_history_keys(4, "pattern") == 81 and num_history_keys(4, "count") == 25
    assert num_history_keys(0, "pattern") == 1


# --- solving ----------------------------------------------------------------------


def test_solved_policy_beats_mirroring_the_minimum(train, policy):
    always_min = solve_bet_policy(train, actions=SMALL_ACTIONS[:1], grid=SMALL_GRID, history="none")
    assert policy.expected_score == pytest.approx(policy_score(train, policy))
    assert policy.expected_score > always_min.expected_score + 0.05
    assert 0 <= always_min.expected_score <= 1


def test_policy_holds_up_on_matches_it_was_not_solved_from(policy):
    fresh = build_scenarios(FlatMix(), 4000, seed=500_000)
    assert policy_score(fresh, policy) > policy.expected_score - 0.04


def test_every_table_entry_is_a_legal_bet(policy):
    rules = DEFAULT_RULES
    for r, table in enumerate(policy.tables):
        for key in range(table.shape[0]):
            for level, balance in enumerate(policy.grid):
                assert policy.actions[table[key, level]].valid(balance, rules), (r, key, balance)


def test_policy_agent_reproduces_the_search_roll_forward(train, policy):
    finals = policy_finals(train, policy)
    agent = PolicyAgent(policy)
    same = 0
    for i in range(400):
        real = play_player(agent, match_shoes(int(train.seeds[i])), random.Random(1)).final_balance
        same += real == finals[i]
    # They differ only when a hand the agent could not afford to double or
    # split would have ended the other side of zero.
    assert same >= 0.97 * 400


def test_policy_agent_plays_legally_and_scores_like_the_estimate(policy):
    factory = PolicyAgentFactory(policy)
    assert pickle.loads(pickle.dumps(factory)).label == "optimized"
    result = simulate(factory, FlatMix(), 1500, seed=900_000)
    assert result.total.matches == 1500
    assert result.total.score() > policy.expected_score - 0.06


def test_fixed_bet_policy_is_just_that_bet(train):
    only_fifty = solve_bet_policy(train, actions=[BetAction(main=50, label="bet 50"), BetAction(main=10, label="bet 10")], grid=np.array([10.0, 50.0]), history="none")
    assert only_fifty.action(0, 0, 1000).label in ("bet 50", "bet 10")
    assert only_fifty.action(2, 0, 30).label == "bet 10"  # 50 is unaffordable at 30
