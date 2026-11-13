"""The optimisation pipeline and the strategy card."""

import pickle

import pytest

from rivals.agents import Agent
from rivals.agents.optimal import PolicyAgentFactory
from rivals.match import simulate
from rivals.optimize.bet_policy import BasicPlay, policy_trace
from rivals.optimize.pipeline import (
    actions_with_styles,
    default_styles,
    describe_opening,
    load_policy,
    optimize,
    save_policy,
)
from rivals.report.cheatsheet import bet_rules, coverage, render


class Flat(Agent):
    def __init__(self, amount):
        super().__init__()
        self.amount = amount
        self.name = f"flat-{amount}"

    def bet(self, state):
        return state.clamp_bet(self.amount)


class FlatMix:
    def __call__(self, rng):
        return Flat(rng.choice([10, 10, 25, 100, 250]))


@pytest.fixture(scope="module")
def result():
    return optimize(
        FlatMix(), matches=2500, holdout_matches=2500, histories=("count", "none"), log=lambda *_: None
    )


def test_actions_cover_every_style():
    styles = default_styles()
    actions = actions_with_styles(styles)
    assert {a.style for a in actions} == {0, 1, 2}
    assert len({a.label for a in actions}) == len(actions)
    # Side bets are only offered with basic play.
    assert all(a.style == 0 for a in actions if a.total or a.pairs or a.total_rest or a.pairs_rest)


def test_pipeline_picks_the_mode_that_holds_up_best(result):
    assert set(result.scores) == {"count", "none"}
    best_mode = max(result.scores, key=lambda m: result.scores[m][1])
    assert result.policy.history == best_mode
    fitted, held = result.scores[best_mode]
    assert fitted > 0.6 and held > 0.6  # far above the 0.556 of mirroring a flat-min player
    assert result.final_score > 0.6  # on matches that played no part in the choice
    assert len(result.policy.style_charts) == 3 and result.policy.style_charts[0] is None


def test_policy_with_play_styles_runs_through_the_real_engine(result):
    sim = simulate(PolicyAgentFactory(result.policy), FlatMix(), 800, seed=3_000_000)
    assert sim.total.score() > 0.6


def test_roll_forward_with_play_styles_matches_the_real_engine_exactly(result):
    import random

    from rivals.agents.optimal import PolicyAgent
    from rivals.match import play_player
    from rivals.optimize.bet_policy import policy_finals
    from rivals.shoe import match_shoes

    finals = policy_finals(result.holdout, result.policy)
    agent = PolicyAgent(result.policy)
    styles_used = set()
    for i in range(500):
        seed = int(result.holdout.seeds[i])
        real = play_player(agent, match_shoes(seed), random.Random(0))
        assert real.final_balance == finals[i], seed
    for table in result.policy.tables:
        styles_used |= {result.policy.actions[a].style for a in table.ravel()}
    assert styles_used >= {0, 1}  # the comparison really exercised a non-basic style


def test_policy_round_trips_through_a_file(result, tmp_path):
    path = save_policy(result.policy, tmp_path / "policy.pkl")
    loaded = load_policy(path)
    assert loaded.history == result.policy.history
    assert all((a == b).all() for a, b in zip(loaded.tables, result.policy.tables))
    assert "hand 1:" in describe_opening(loaded)


def test_trace_follows_every_match(result):
    trace = policy_trace(result.train, result.policy)
    assert len(trace) == 5
    assert trace[0]["alive"].all() and (trace[0]["balance"] == 1000).all()
    assert len(set(trace[0]["action"].tolist())) == 1  # one opening bet for everyone


def test_card_lists_reachable_situations_only(result):
    rules = bet_rules(result.train, result.policy, min_share=0.0)
    assert coverage(rules, 0) == pytest.approx(1.0)
    first = [r for r in rules if r.round_index == 0]
    assert len(first) == 1 and first[0].low <= 1000 <= first[0].high
    for r in range(1, 5):
        assert 0.9 < coverage(rules, r) <= 1.0 + 1e-9
    trimmed = bet_rules(result.train, result.policy, min_share=0.02)
    assert 0 < len(trimmed) < len(rules)


def test_card_ranges_never_hide_a_different_instruction(result):
    policy = result.policy
    rules = bet_rules(result.train, policy, min_share=0.0)
    by_situation = {}
    for rule in rules:
        by_situation.setdefault((rule.round_index, rule.history), []).append(rule)
    from rivals.optimize.bet_policy import describe_key, num_history_keys

    for (r, history), group in by_situation.items():
        group.sort(key=lambda x: x.low)
        for a, b in zip(group, group[1:]):
            assert a.high < b.low  # no overlap
        key = next(
            k for k in range(num_history_keys(r, policy.history))
            if describe_key(k, r, policy.history) == history
        )
        for rule in group:
            top = rule.high if rule.high != float("inf") else policy.grid[-1]
            for balance in policy.grid[(policy.grid >= rule.low) & (policy.grid <= top)]:
                assert policy.action(r, key, balance).label == rule.action


def test_card_renders_as_markdown(result):
    text = render(result.train, result.policy)
    assert text.startswith("# 21 Rivals strategy card")
    for hand in range(1, 6):
        assert f"## Hand {hand}" in text
    assert "| History | Balance | Do this | How often |" in text
    assert "Play basic strategy" in text and "Hard" in text
    assert '"play seek" changes these cells' in text
