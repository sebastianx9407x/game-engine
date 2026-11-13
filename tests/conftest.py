"""Shared test helpers."""

from __future__ import annotations

import random

import pytest

from rivals.hand import Action
from rivals.resolve import DecisionContext, ScriptedPolicy, play_round
from rivals.rules import DEFAULT_RULES
from rivals.shoe import Shoe


class RecordingPolicy(ScriptedPolicy):
    """A scripted policy that remembers the legal actions at each decision."""

    def __init__(self, actions=(), *, insurance=False):
        super().__init__(actions, insurance=insurance)
        self.legal_seen: list[tuple[Action, ...]] = []
        self.insurance_offers = 0

    def act(self, ctx: DecisionContext) -> Action:
        self.legal_seen.append(ctx.legal)
        return super().act(ctx)

    def take_insurance(self, ctx: DecisionContext) -> bool:
        self.insurance_offers += 1
        return super().take_insurance(ctx)


class RandomPolicy:
    """Picks uniformly among the legal actions."""

    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def act(self, ctx: DecisionContext) -> Action:
        return self._rng.choice(ctx.legal)

    def take_insurance(self, ctx: DecisionContext) -> bool:
        return self._rng.random() < 0.5


class NeverAsked:
    """Fails the test if the round asks for a play decision."""

    def act(self, ctx):
        raise AssertionError("policy should not have been asked to act")

    def take_insurance(self, ctx):
        return False


def play(
    player,
    dealer,
    actions=(),
    *,
    player_draws=(),
    dealer_draws=(),
    bet=10,
    insurance=False,
    rules=DEFAULT_RULES,
    **kwargs,
):
    """Play one round on a stacked shoe with a scripted policy."""
    shoe = Shoe.stacked(
        player,
        dealer,
        player_draws,
        dealer_draws,
        dealer_independent=rules.dealer_cards_independent,
    )
    policy = RecordingPolicy(actions, insurance=insurance)
    result = play_round(shoe, policy, bet, rules=rules, **kwargs)
    return result, policy


@pytest.fixture
def rules():
    return DEFAULT_RULES
