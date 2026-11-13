"""The tactic evaluator."""

import pickle
import random
from pathlib import Path

import pytest

from rivals.agents import Agent
from rivals.evaluate import (
    BaselineFactory,
    TacticFactory,
    evaluate,
    format_report,
    load_tactic,
    main,
)

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = str(REPO / "tactics" / "_template.py")


def write_tactic(tmp_path, body, name="idea.py"):
    path = tmp_path / name
    path.write_text("from rivals.agents import Agent\n" + body)
    return str(path)


def test_template_is_a_working_tactic():
    cls = load_tactic(TEMPLATE)
    assert issubclass(cls, Agent) and cls().label == "template"


def test_load_tactic_finds_the_class(tmp_path):
    one = write_tactic(tmp_path, "class Shover(Agent):\n    def bet(self, state):\n        return state.max_bet()\n")
    assert load_tactic(one).__name__ == "Shover"
    two = write_tactic(tmp_path, "class A(Agent):\n    pass\nclass B(Agent):\n    pass\n", "two.py")
    with pytest.raises(ValueError):
        load_tactic(two)
    assert load_tactic(two + ":B").__name__ == "B"
    with pytest.raises(FileNotFoundError):
        load_tactic(str(tmp_path / "missing.py"))


def test_factory_is_picklable_and_builds_fresh_agents():
    factory = pickle.loads(pickle.dumps(TacticFactory(TEMPLATE)))
    a, b = factory(random.Random(1)), factory(random.Random(2))
    assert a is not b and a.label == factory.label == "template"


def test_baseline_against_itself_is_all_ties_with_zero_gain():
    report = evaluate(BaselineFactory(), BaselineFactory(), matches=200, opponent_label="itself")
    assert report.total.ties == 200
    assert report.comparisons[0].score_gain == 0
    assert not report.comparisons[0].significant


def test_paired_comparison_sees_a_real_difference(tmp_path):
    shover = TacticFactory(
        write_tactic(tmp_path, "class Shover(Agent):\n    def bet(self, state):\n        return state.max_bet()\n", "shove.py")
    )
    # Against a flat-min player, shoving every hand usually ends bankrupt.
    report = evaluate(shover, BaselineFactory(), matches=600, label="shover")
    assert report.total.p_loss > 0.6
    comparison = report.comparisons[0]
    assert comparison.baseline.ties == 600  # the baseline mirrors the opponent
    assert comparison.score_gain < 0 and comparison.significant
    text = format_report(report)
    assert "shover vs the field: 600 matches" in text
    assert "worse" in text and "profit per $1 entry" in text


def test_command_line_against_another_tactic(tmp_path, capsys):
    other = write_tactic(tmp_path, "class Hundred(Agent):\n    name = 'hundred'\n    def bet(self, state):\n        return state.clamp_bet(100)\n", "hundred.py")
    code = main([TEMPLATE, "--vs", other, "--matches", "300", "--processes", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "template vs hundred: 300 matches" in out
    assert "against flat-min basic strategy on the same matches" in out
