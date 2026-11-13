"""Variance-seeking and variance-avoiding play charts."""

import pickle

import pytest

from rivals.hand import Action
from rivals.optimize.play_policy import ChartPlay, ChartPolicy, chart_differences, risk_chart
from rivals.resolve import play_round
from rivals.rules import DEFAULT_RULES
from rivals.shoe import Shoe
from rivals.solver import Solver, basic_chart


@pytest.fixture(scope="module")
def charts():
    return {
        "basic": basic_chart(DEFAULT_RULES),
        "seek": risk_chart(DEFAULT_RULES, "seek", 0.03),
        "avoid": risk_chart(DEFAULT_RULES, "avoid", 0.03),
    }


def test_zero_tolerance_is_basic_strategy(charts):
    for mode in ("seek", "avoid"):
        assert chart_differences(risk_chart(DEFAULT_RULES, mode, 0.0), charts["basic"]) == []


def test_risk_charts_move_variance_the_right_way_at_a_small_cost(charts):
    value = {name: Solver(DEFAULT_RULES, strategy=chart).round_value() for name, chart in charts.items()}
    assert value["seek"].std > value["basic"].std > value["avoid"].std
    for name in ("seek", "avoid"):
        cost = value["basic"].ev - value[name].ev
        assert 0 < cost < 0.002  # under 0.2% of a bet per round


def test_seeking_doubles_and_splits_more_and_avoiding_less(charts):
    def count(chart):
        doubles = sum(c.first == Action.DOUBLE for c in list(chart.hard.values()) + list(chart.soft.values()))
        return doubles + sum(chart.split.values())

    assert count(charts["seek"]) > count(charts["basic"]) > count(charts["avoid"])


def test_differences_are_described(charts):
    lines = chart_differences(charts["seek"], charts["basic"])
    assert "hard 11 vs T,A: Dh" in lines
    assert any(line.endswith(": split") for line in lines)
    assert any("do not split" in line for line in chart_differences(charts["avoid"], charts["basic"]))


def test_chart_policy_plays_legal_rounds(charts):
    for name in ("seek", "avoid"):
        policy = ChartPolicy(charts[name])
        for seed in range(300):
            play_round(Shoe.from_seed(seed), policy, 10, balance=1000)
            play_round(Shoe.from_seed(seed), policy, 10, balance=10)  # nothing spare


def test_chart_play_carries_its_chart_when_pickled():
    style = ChartPlay("seek", "seek", 0.03)
    chart = style.chart(DEFAULT_RULES)
    clone = pickle.loads(pickle.dumps(style))
    assert clone.name == "seek" and clone._charts[DEFAULT_RULES].hard == chart.hard
    assert isinstance(clone.policy(DEFAULT_RULES), ChartPolicy)


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        risk_chart(DEFAULT_RULES, "wild")
