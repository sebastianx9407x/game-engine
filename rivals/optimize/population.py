"""The field of opponents: a weighted mix of archetypes.

A `Population` is the opponent factory for `rivals.match.simulate`: called
with a random stream, it picks a bet style by its share, then a play tier
from that style's row of the joint table (research §6.1), and returns the
agent. It holds only frozen parameter objects, so it pickles and can be sent
to worker processes.

Every share is a low-confidence prior (research §0). The methods here derive
variants for sensitivity analysis without touching the defaults.
"""

from __future__ import annotations

import random
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from itertools import accumulate

from rivals.agents.archetypes import (
    STYLES,
    TIERS,
    Archetype,
    BetStyle,
    PlayTier,
    SnapParams,
    TimeoutParams,
)
from rivals.rules import DEFAULT_RULES, RulesConfig


class Population:
    """Bet styles with weights, plus the modules every opponent shares."""

    def __init__(
        self,
        styles: Sequence[BetStyle] = STYLES,
        weights: Iterable[float] | None = None,
        *,
        tiers: tuple[PlayTier, PlayTier, PlayTier] = TIERS,
        snap: SnapParams = SnapParams(),
        timeout: TimeoutParams = TimeoutParams(),
        rules: RulesConfig = DEFAULT_RULES,
    ) -> None:
        self.styles = tuple(styles)
        raw = [s.share for s in self.styles] if weights is None else list(weights)
        total = sum(raw)
        if len(raw) != len(self.styles) or min(raw, default=0) < 0 or total <= 0:
            raise ValueError("need one non-negative weight per style, not all zero")
        if len({s.name for s in self.styles}) != len(self.styles):
            raise ValueError("style names must be unique")
        #: Shares of the field, summing to 1, in the order of `styles`.
        self.weights = tuple(w / total for w in raw)
        self.tiers = tiers
        self.snap = snap
        self.timeout = timeout
        self.rules = rules
        self._cumulative = tuple(accumulate(self.weights))

    def __call__(self, rng: random.Random) -> Archetype:
        """One opponent drawn from the field."""
        index = min(bisect_right(self._cumulative, rng.random()), len(self.styles) - 1)
        style = self.styles[index]
        p1, p2, _ = style.tier_probs
        x = rng.random()
        tier = self.tiers[0 if x < p1 else 1 if x < p1 + p2 else 2]
        return Archetype(style, tier, snap=self.snap, timeout=self.timeout, rules=self.rules)

    def __repr__(self) -> str:
        parts = ", ".join(f"{label} {weight:.1%}" for label, weight in self.entries if weight)
        return f"Population({parts})"

    # --- reading ------------------------------------------------------------

    @property
    def entries(self) -> list[tuple[str, float]]:
        """(bet-style label, share of the field) for every style."""
        return [(s.name, w) for s, w in zip(self.styles, self.weights)]

    def style(self, label: str) -> BetStyle:
        """The parameters of the style called ``label``."""
        for style in self.styles:
            if style.name == label:
                return style
        raise KeyError(f"no bet style called {label!r}; have {[s.name for s in self.styles]}")

    def tier_shares(self) -> dict[str, float]:
        """Share of the field in each play tier, summed over the bet styles."""
        shares = {tier.name: 0.0 for tier in self.tiers}
        for style, weight in zip(self.styles, self.weights):
            for tier, p in zip(self.tiers, style.tier_probs):
                shares[tier.name] += weight * p
        return shares

    # --- variants -----------------------------------------------------------

    def _with(self, styles: Sequence[BetStyle], weights: Iterable[float]) -> Population:
        return Population(
            styles, weights, tiers=self.tiers, snap=self.snap, timeout=self.timeout, rules=self.rules
        )

    def reweighted(self, shares: Mapping[str, float]) -> Population:
        """The field with the named styles at exactly the given shares.

        The other styles keep their proportions to each other and fill what is
        left, so ``reweighted({"B6 Hero": 0.2})`` has 20% Heroes.
        """
        for label in shares:
            self.style(label)
        fixed = sum(shares.values())
        if fixed > 1 + 1e-12 or min(shares.values(), default=0) < 0:
            raise ValueError("shares must be non-negative and sum to at most 1")
        rest = sum(w for (label, w) in self.entries if label not in shares)
        scale = (1 - fixed) / rest if rest else 0.0
        return self._with(
            self.styles,
            [shares[label] if label in shares else w * scale for label, w in self.entries],
        )

    def only(self, label: str) -> Population:
        """A field made of one bet style, with its usual mix of play tiers."""
        return self._with([self.style(label)], [1.0])

    def with_style(self, style: BetStyle) -> Population:
        """The field with the style of the same name replaced, e.g. by a `replace` copy."""
        self.style(style.name)
        return self._with([style if s.name == style.name else s for s in self.styles], self.weights)

    def with_modules(
        self,
        *,
        tiers: tuple[PlayTier, PlayTier, PlayTier] | None = None,
        snap: SnapParams | None = None,
        timeout: TimeoutParams | None = None,
    ) -> Population:
        """The field with different play tiers, chip rounding or timeout parameters."""
        return Population(
            self.styles,
            self.weights,
            tiers=tiers or self.tiers,
            snap=snap or self.snap,
            timeout=timeout or self.timeout,
            rules=self.rules,
        )


def default_population(rules: RulesConfig = DEFAULT_RULES) -> Population:
    """The DraftKings field at the research's point estimates (§6.1)."""
    return Population(rules=rules)
