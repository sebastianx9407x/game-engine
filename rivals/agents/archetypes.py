"""Models of human opponents: a bet style crossed with a play-skill tier.

This is `research/archetypes.md` turned into code. An `Archetype` agent holds
one of ten bet styles (B1 Flat-min .. B10 Erratic), which decides how much to
wager, and one of three play tiers (P1 Solid, P2 Casual, P3 Novice), which
decides how the cards are played. Side bets, insurance and the reference
point ("am I ahead or behind?") are modules shared by all of them.

Every number from the research is a field of a frozen dataclass, with the
research's point estimate as its default. The comment on each field gives the
section it came from and the research's label: [S] taken from a source,
[D] derived, [A] assumption. A sensitivity sweep changes a number with
`dataclasses.replace` and never touches the logic.

Where the confirmed game rules (docs/DECISIONS.md) overtook the research:

* Doubling needs a total of 9, 10 or 11, so the "missed soft double" and
  "double a hard 8" rows of §4.2 cannot occur. They are still fields and come
  back to life under a rule set that allows those doubles.
* The dealer does not check under a ten, so basic strategy now hits 11 against
  a ten and does not split 8s against a ten. Players do not know that, so
  each tier keeps its textbook habit there: `double_11_vs_ten` and
  `split_8s_vs_ten` are set to one minus the research's miss rates for the
  textbook play (§4.2). This is a main source of divergence from a player
  who follows the correct chart.

Timeouts (§5.8). The engine has no clock and an agent cannot set its own
balance to 0, so a timeout is modelled as the agent's own behaviour: from the
hand where the clock would run out, it bets every chip and hits until it
busts, and does so again on any hand that is left. A hand ends on 0 unless
the cards make exactly 21, about one time in six, so roughly 89% of modelled
timeouts finish on 0 and the rest finish with a large stack, which a real
timeout never does. Set `TimeoutParams.p_timeout` to 0 to turn it off.

Conventions, where the research left room:

* "Hand 5" is the last round of the match and "hand 4" the one before it.
* "Behind" is judged against the player's own reference point R, never the
  opponent's balance, because the game is blind. Thresholds the research
  writes as chip counts (900, 1,100, 1,300, 1,500) are kept as distances from
  R, so they move with a pessimist's or a shared-outcome player's R.
* A round counts as a win or a loss by its main-hand net; side bets and
  insurance do not change how the player reacts.
* Reactions multiply the chips actually bet on the previous hand. A repeat, a
  return to the base bet and a PLAY 2x double are exact; everything else gets
  the noise and rounding of §3.0. An all-in is not noised.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from typing import Any

from rivals.agents.base import Agent, MatchState, RoundRecord
from rivals.cards import DECK_SIZE
from rivals.hand import Action, hand_value
from rivals.resolve import DecisionContext
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.side_bets import NO_SIDE_BETS, SideBets
from rivals.solver.basic import Chart, basic_chart
from rivals.solver.exact import ACE, NUM_VALUES, TEN, value_index

#: A discrete distribution: (value, probability) pairs whose probabilities sum to 1.
Dist = tuple[tuple[Any, float], ...]

#: Bet amount meaning "every chip".
ALL_IN = math.inf
#: In a distribution of multipliers or stack fractions: go back to the base bet.
BASE = -1.0
#: In a distribution of stack fractions: bet the table minimum.
MINIMUM = 0.0

_STAND, _HIT, _DOUBLE, _SPLIT = Action.STAND, Action.HIT, Action.DOUBLE, Action.SPLIT
_UP = tuple(value_index(card) for card in range(DECK_SIZE))
_EIGHT = 7  # value index of an eight
_SOFT_OFFSET = 220  # play tables are indexed by total * 10 + upcard, soft hands after hard


def draw(rng, dist: Dist):
    """One value from ``dist``."""
    x = rng.random()
    for value, p in dist:
        x -= p
        if x < 0:
            return value
    return dist[-1][0]


def _check_dists(obj) -> None:
    """Reject a parameter set whose distributions do not sum to 1."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if not isinstance(value, tuple) or not value:
            continue
        if isinstance(value[0], tuple):
            total = sum(p for _, p in value)
        elif f.name in ("tier_probs", "cls_probs"):
            total = sum(value)
        else:
            continue
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"{type(obj).__name__}.{f.name} sums to {total}, not 1")


# --- cross-cutting parameters ------------------------------------------------------


@dataclass(frozen=True)
class SnapParams:
    """How an intended bet becomes chips on the table (§3.0, §5.2)."""

    #: §1.2 [S: client] smallest chip; every bet is a multiple of it.
    chip: float = 5
    #: §3.0 [A] a bet within this many chips of the balance becomes all-in.
    all_in_margin: float = 5
    #: §3.0 [A] (bets below this, rounded to a multiple of this): 25s below
    #: 100, 50s below 250, 100s below 1,000, 500s above.
    grid: tuple[tuple[float, float], ...] = ((100, 25), (250, 50), (1000, 100), (math.inf, 500))
    #: §3.0 [A] chance the bet is an exact count, rounded to the chip instead.
    p_exact_count: float = 0.2
    #: §3.0 [A] an all-in that is not a multiple of this is "awkward" (the
    #: research's example is 1,135; "multiple of 100" is this code's reading).
    all_in_round_to: float = 100
    #: §3.0 [A] chance an awkward all-in is bet exactly, else rounded down.
    p_awkward_all_in_exact: float = 0.6
    #: §3.0 [A] sigma of the lognormal noise on bets above the minimum.
    noise_sigma: float = 0.15
    #: §5.2 [A] chance a doubled bet was made with the PLAY 2x button, which
    #: doubles it exactly and doubles carried side bets too.
    p_2x_button: float = 0.7


@dataclass(frozen=True)
class ReferenceParams:
    """How a player judges ahead or behind without seeing the opponent (§5.1).

    The rest of the probability, 0.85 by default, is the plain reference of
    the starting stack. The research gives 0.80 / 0.10 / 0.10 for the whole
    field with 0.05 shared-outcome players outside the Tacticians, so the
    three shares here are per style.
    """

    #: §5.1 [A] P(reference = start + U(pessimist_range)).
    p_pessimist: float = 0.10
    #: §5.1 [A] chips a pessimist adds to the starting stack.
    pessimist_range: tuple[float, float] = (50, 250)
    #: §5.1 [A] P(reference = estimate of the opponent from shared outcomes);
    #: 0.05 for every style but the Tactician.
    p_shared_estimate: float = 0.05
    #: §5.1 [A] bet the player assumes a typical opponent makes each hand.
    assumed_opponent_bet: float = 50
    #: §5.1 [A] behind means balance < reference - U(dead_zone), drawn once a match.
    dead_zone: tuple[float, float] = (0, 30)


@dataclass(frozen=True)
class SideBetParams:
    """Side-bet habits (§5.9). The class shares differ by bet style (§6.1)."""

    #: §5.9, §6.1 [A/D] P(never / occasional / habitual); the field-wide mix.
    cls_probs: tuple[float, float, float] = (0.54, 0.31, 0.15)
    #: §5.9 [A] P(side bet on a hand) for the occasional class.
    p_hand_occasional: float = 0.25
    #: §5.9 [A] P(side bet on a hand) for the habitual class (REPLAY carries it).
    p_hand_habitual: float = 0.90
    #: §5.9 [A] which side bet; drawn once a match as the player's habit.
    which: Dist = (("pp", 0.40), ("4ct", 0.30), ("both", 0.30))
    #: §5.9 [A] usual stake in chips; drawn once a match. The research's last
    #: bucket is "100+" and is taken as 100.
    size: Dist = ((10, 0.45), (25, 0.35), (50, 0.10), (100, 0.10))
    #: §5.9 [A] P(a placed side bet is at least `big_frac` of the balance).
    p_big_frac: float = 0.02
    #: §5.9 [A] size of that big side bet; the research gives only the floor.
    big_frac: float = 0.25
    #: §3 B7 [A] share of an occasional side-bettor's side bets that land on
    #: the last hand (0.7 for Closers). None spreads them evenly.
    occasional_last_share: float | None = None

    def __post_init__(self) -> None:
        _check_dists(self)


@dataclass(frozen=True)
class TimeoutParams:
    """Running out the clock (§5.8). See the module docstring for how it is played."""

    #: §5.8 [A] P(timeout) per match; range 0.002-0.03.
    p_timeout: float = 0.01
    #: §5.8, §7.1 [A] hand (1-based) on which the clock runs out.
    hands: Dist = ((4, 0.4), (5, 0.6))

    def __post_init__(self) -> None:
        _check_dists(self)


# --- play tiers ----------------------------------------------------------------------


@dataclass(frozen=True)
class PlayTier:
    """Per-situation error probabilities for one skill tier (§4.2, §4.6).

    Each number is the chance, at every decision that fits the row, of taking
    the row's wrong action instead of basic strategy. Draws are independent.
    """

    name: str
    #: §4.2 stand on hard 12/13/14/15/16 against a ten (basic: hit).
    stand_stiff_hi: tuple[float, float, float, float, float]
    #: §4.2 [A] multiplier on the row above by upcard 7/8/9/T/A.
    stiff_hi_upcard: tuple[float, float, float, float, float]
    #: §4.2 stand on hard 12 against 2 / 3 (basic: hit).
    stand_12_lo: tuple[float, float]
    #: §4.2 hit hard 13 against 2/3/4/5/6 (basic: stand). Wagenaar anchors P3.
    hit_13_lo: tuple[float, float, float, float, float]
    #: §4.2 [A] hard 14 against 2-6: the 13 row times this.
    hit_14_scale: float
    #: §4.2 [A] hard 15-16 against 2-6: the 13 row times this.
    hit_15_16_scale: float
    #: §4.2 [A] hit hard 12 against 4/5/6 (basic: stand).
    hit_12_lo: tuple[float, float, float]
    #: §4.2 [A] hit hard 17-18.
    hit_17_18: float
    #: §4.2 [A] hit instead of doubling 11.
    fail_double_11: float
    #: §4.2 [A] multiplier on the row above against a 9 or ten.
    fail_double_11_hi_mult: float
    #: §4.2 [A] hit instead of doubling 10.
    fail_double_10: float
    #: §4.2 [A] hit instead of doubling 9.
    fail_double_9: float
    #: §4.2 [A] double 11 against an ace (basic: hit).
    over_double_11_ace: float
    #: §4.2 [A] double 10 against a ten or ace (basic: hit).
    over_double_10: float
    #: §4.2 [A] double 9 against a 2 or 7 and up (basic: hit).
    over_double_9: float
    #: §4.2 [A] double 8 against 5-6. Illegal under the confirmed rules (§4.7).
    over_double_8: float
    #: §4.2 fail to double a soft hand. No soft double is basic strategy under
    #: the confirmed rules (§4.7), so this row is idle.
    fail_soft_double: float
    #: §4.2 stand on soft 18 against 9/T/A (basic: hit).
    stand_soft18_hi: float
    #: §4.2 stand on soft 17 (basic: hit).
    stand_soft17: float
    #: §4.2 [A] stand on soft 13-16 (basic: hit).
    stand_soft_low: float
    #: §4.2 [A] fail to split aces.
    fail_split_aces: float
    #: §4.2 [A] fail to split 8s against 9/T/A, then play the 16.
    fail_split_8_hi: float
    #: §4.2 [A] fail to split 8s against 2-8.
    fail_split_8_lo: float
    #: §4.2 fail to make any other basic-strategy split.
    fail_split_other: float
    #: §4.2 [A] split tens.
    split_tens: float
    #: §4.6 [A] P(insurance) without a blackjack.
    p_insure: float
    #: §4.6 [A] multiplier on `p_insure` holding hard 19-20 / a hard 12-16.
    insure_hand_mult: tuple[float, float]
    #: §4.6 [A] P(insurance) holding a blackjack, i.e. even money.
    p_insure_blackjack: float
    #: [D] P(double 11 against a ten). The no-check rule makes hitting correct
    #: here, but players do not know that and keep their textbook habit, so the
    #: tiers set this to 1 - fail_double_11 * fail_double_11_hi_mult (§4.2).
    double_11_vs_ten: float = 0.0
    #: [D] P(split 8s against a ten), likewise 1 - fail_split_8_hi (§4.2).
    split_8s_vs_ten: float = 0.0
    #: §4.5 [A] optional pure-heuristic players within the tier: ("never_bust"
    #: or "mimic_dealer", share). Off by default, as in the research's schema.
    submodes: Dist = ()
    #: §4.5 [A] chance a sub-mode player decides by the tier's table instead.
    submode_noise: float = 0.05
    #: Multiplier on every play-error probability, for sweeps (§5.8 suggests
    #: 1.2 for "rushed" players). 0 gives exact basic strategy.
    error_scale: float = 1.0

    def scaled(self, factor: float) -> PlayTier:
        """This tier with every play-error probability multiplied by ``factor``."""
        return replace(self, error_scale=self.error_scale * factor)


P1_SOLID = PlayTier(
    name="P1 Solid",
    stand_stiff_hi=(0.01, 0.01, 0.02, 0.03, 0.06),
    stiff_hi_upcard=(0.6, 0.8, 1.0, 1.0, 1.0),
    stand_12_lo=(0.05, 0.03),
    hit_13_lo=(0.01, 0.01, 0.01, 0.01, 0.01),
    hit_14_scale=1.0,
    hit_15_16_scale=1.0,
    hit_12_lo=(0.02, 0.02, 0.02),
    hit_17_18=0.0,
    fail_double_11=0.01,
    fail_double_11_hi_mult=2.0,
    fail_double_10=0.02,
    fail_double_9=0.05,
    over_double_11_ace=0.50,
    over_double_10=0.02,
    over_double_9=0.02,
    over_double_8=0.0,
    fail_soft_double=0.08,
    stand_soft18_hi=0.08,
    stand_soft17=0.01,
    stand_soft_low=0.0,
    fail_split_aces=0.0,
    fail_split_8_hi=0.05,
    fail_split_8_lo=0.01,
    fail_split_other=0.08,
    double_11_vs_ten=0.98,
    split_8s_vs_ten=0.95,
    split_tens=0.005,
    p_insure=0.01,
    insure_hand_mult=(1.0, 1.0),
    p_insure_blackjack=0.10,
)

P2_CASUAL = PlayTier(
    name="P2 Casual",
    stand_stiff_hi=(0.08, 0.12, 0.18, 0.26, 0.45),
    stiff_hi_upcard=(0.5, 0.65, 0.85, 1.0, 0.9),
    stand_12_lo=(0.45, 0.35),
    hit_13_lo=(0.30, 0.18, 0.10, 0.06, 0.05),
    hit_14_scale=0.6,
    hit_15_16_scale=0.4,
    hit_12_lo=(0.15, 0.10, 0.08),
    hit_17_18=0.005,
    fail_double_11=0.08,
    fail_double_11_hi_mult=1.8,
    fail_double_10=0.12,
    fail_double_9=0.45,
    over_double_11_ace=0.60,
    over_double_10=0.08,
    over_double_9=0.05,
    over_double_8=0.02,
    fail_soft_double=0.55,
    stand_soft18_hi=0.60,
    stand_soft17=0.15,
    stand_soft_low=0.02,
    fail_split_aces=0.03,
    fail_split_8_hi=0.25,
    fail_split_8_lo=0.06,
    fail_split_other=0.40,
    double_11_vs_ten=0.856,
    split_8s_vs_ten=0.75,
    split_tens=0.02,
    p_insure=0.06,
    insure_hand_mult=(2.0, 0.5),
    p_insure_blackjack=0.45,
)

P3_NOVICE = PlayTier(
    name="P3 Novice",
    stand_stiff_hi=(0.30, 0.40, 0.55, 0.65, 0.75),
    stiff_hi_upcard=(0.7, 0.8, 0.95, 1.0, 0.95),
    stand_12_lo=(0.70, 0.65),
    hit_13_lo=(0.50, 0.30, 0.18, 0.10, 0.08),
    hit_14_scale=0.7,
    hit_15_16_scale=0.5,
    hit_12_lo=(0.30, 0.22, 0.20),
    hit_17_18=0.02,
    fail_double_11=0.30,
    fail_double_11_hi_mult=1.5,
    fail_double_10=0.40,
    fail_double_9=0.85,
    over_double_11_ace=0.50,
    over_double_10=0.15,
    over_double_9=0.10,
    over_double_8=0.05,
    fail_soft_double=0.90,
    stand_soft18_hi=0.85,
    stand_soft17=0.45,
    stand_soft_low=0.10,
    fail_split_aces=0.15,
    fail_split_8_hi=0.55,
    fail_split_8_lo=0.30,
    fail_split_other=0.70,
    double_11_vs_ten=0.55,
    split_8s_vs_ten=0.45,
    split_tens=0.08,
    p_insure=0.15,
    insure_hand_mult=(2.0, 0.5),
    p_insure_blackjack=0.55,
)

TIERS: tuple[PlayTier, PlayTier, PlayTier] = (P1_SOLID, P2_CASUAL, P3_NOVICE)

#: §4.5 [A] the research's optional sub-modes for P3: 15% never-bust, 10%
#: mimic-the-dealer. Use ``replace(P3_NOVICE, submodes=P3_SUBMODES)``.
P3_SUBMODES: Dist = (("never_bust", 0.15), ("mimic_dealer", 0.10))


def _cell_error(tier: PlayTier, soft: bool, total: int, up: int, basic: Action, can_double: bool):
    """(probability, wrong action) for one chart cell. ``up`` is 2..10, 11 for an ace."""
    if soft:
        if basic == _DOUBLE:
            return tier.fail_soft_double, (_STAND if total == 18 else _HIT)
        if basic == _HIT:
            if total == 18 and up >= 9:
                return tier.stand_soft18_hi, _STAND
            if total == 17:
                return tier.stand_soft17, _STAND
            if 13 <= total <= 16:
                return tier.stand_soft_low, _STAND
        return 0.0, basic
    if basic == _DOUBLE:
        if total == 11:
            mult = tier.fail_double_11_hi_mult if up in (9, 10) else 1.0
            return tier.fail_double_11 * mult, _HIT
        if total == 10:
            return tier.fail_double_10, _HIT
        if total == 9:
            return tier.fail_double_9, _HIT
        return 0.0, basic
    if basic == _HIT:
        if can_double:
            if total == 11 and up == 11:
                return tier.over_double_11_ace, _DOUBLE
            if total == 11 and up == 10:
                return tier.double_11_vs_ten, _DOUBLE
            if total == 10 and up >= 10:
                return tier.over_double_10, _DOUBLE
            if total == 9 and (up == 2 or up >= 7):
                return tier.over_double_9, _DOUBLE
            if total == 8 and up in (5, 6):
                return tier.over_double_8, _DOUBLE
        if 12 <= total <= 16 and up >= 7:
            return tier.stand_stiff_hi[total - 12] * tier.stiff_hi_upcard[up - 7], _STAND
        if total == 12 and up <= 3:
            return tier.stand_12_lo[up - 2], _STAND
        return 0.0, basic
    if up <= 6:
        if total == 13:
            return tier.hit_13_lo[up - 2], _HIT
        if total == 14:
            return tier.hit_13_lo[up - 2] * tier.hit_14_scale, _HIT
        if total in (15, 16):
            return tier.hit_13_lo[up - 2] * tier.hit_15_16_scale, _HIT
        if total == 12 and up >= 4:
            return tier.hit_12_lo[up - 4], _HIT
    if total in (17, 18):
        return tier.hit_17_18, _HIT
    return 0.0, basic


class PlayTable:
    """A tier's errors laid over the basic-strategy chart, as flat lookup lists.

    ``plain`` and ``doubling`` hold (basic action, error probability, wrong
    action) per hand, for decisions where doubling is not and is legal.
    ``split`` holds (chart splits, probability of doing the opposite) per pair.
    """

    __slots__ = ("plain", "doubling", "split", "never_bust", "mimic_dealer")

    def __init__(self, tier: PlayTier, chart: Chart) -> None:
        scale = tier.error_scale
        size = 2 * _SOFT_OFFSET
        self.plain: list = [(_STAND, 0.0, _STAND)] * size
        self.doubling: list = [(_STAND, 0.0, _STAND)] * size
        self.never_bust: list = [_STAND] * size
        self.mimic_dealer: list = [_STAND] * size
        for soft, cells in ((False, chart.hard), (True, chart.soft)):
            for (total, up_index), cell in cells.items():
                index = (_SOFT_OFFSET if soft else 0) + total * 10 + up_index
                up = 11 if up_index == ACE else up_index + 1
                for table, can_double in ((self.plain, False), (self.doubling, True)):
                    doubles = cell.first == _DOUBLE and can_double
                    basic = cell.first if doubles or cell.first != _DOUBLE else cell.fallback
                    p, wrong = _cell_error(tier, soft, total, up, basic, can_double)
                    table[index] = (basic, min(p * scale, 1.0), wrong)
                self.never_bust[index] = _HIT if total <= (17 if soft else 11) else _STAND
                self.mimic_dealer[index] = _HIT if total <= 16 else _STAND
        self.split: list = [(False, 0.0)] * (NUM_VALUES * 10)
        for (pair, up_index), splits in chart.split.items():
            up = 11 if up_index == ACE else up_index + 1
            if splits:
                if pair == ACE:
                    p = tier.fail_split_aces
                elif pair == _EIGHT:
                    p = tier.fail_split_8_hi if up >= 9 else tier.fail_split_8_lo
                else:
                    p = tier.fail_split_other
            elif pair == TEN:
                p = tier.split_tens
            elif pair == _EIGHT and up == 10:
                p = tier.split_8s_vs_ten
            else:
                p = 0.0
            self.split[pair * 10 + up_index] = (splits, min(p * scale, 1.0))


@lru_cache(maxsize=None)
def play_table(tier: PlayTier, rules: RulesConfig) -> PlayTable:
    """The lookup table for ``tier`` under ``rules`` (built once per process)."""
    return PlayTable(tier, basic_chart(rules))


# --- bet styles ------------------------------------------------------------------------


def _win_streak(history: tuple[RoundRecord, ...]) -> int:
    """Consecutive main-hand wins up to the latest round."""
    streak = 0
    for record in reversed(history):
        if record.result.main_net <= 0:
            break
        streak += 1
    return streak


def _stack_bet(ag: Archetype, frac: float, balance: float) -> tuple[float, bool]:
    """A bet given as a fraction of the stack; 1 is all-in, `MINIMUM` and `BASE` as named."""
    if frac >= 1.0:
        return ALL_IN, True
    if frac < 0:
        return ag.base, True
    return frac * balance, False


def _times(ag: Archetype, previous: float, mult: float) -> tuple[float, bool]:
    """The previous bet times ``mult``; an exact repeat or 2x-button double stays exact."""
    if mult == BASE:
        return ag.base, True
    if mult == 1.0:
        return previous, True
    if mult == 2.0 and ag.rng.random() < ag.snap.p_2x_button:
        ag.used_2x = True
        return 2 * previous, True
    return previous * mult, False


@dataclass(frozen=True)
class BetStyle:
    """Base for the ten bet styles: the parameters and the rule that uses them.

    A style is immutable and shared between agents. What it needs to remember
    within a match lives on the agent (`base`, `lock_at`, `locked_bet`).
    `propose` returns (chips, exact): ``exact`` bets skip the noise and
    rounding of §3.0, because they repeat or double chips already on the grid.
    """

    name: str = ""
    #: §0.1, §6.1 [A] share of the field.
    share: float = 0.0
    #: §6.1 [A] P(P1 / P2 / P3) given this style.
    tier_probs: tuple[float, float, float] = (0.16, 0.50, 0.34)
    side: SideBetParams = SideBetParams()
    reference: ReferenceParams = ReferenceParams()
    #: Base (or first) bet in chips; each style that has one sets its own.
    base_bet: Dist = ((10, 1.0),)
    #: §4.2 [A] chance of an extra double or split when behind on the last hand.
    p_variance_play: float = 0.0

    def __post_init__(self) -> None:
        _check_dists(self)

    def start(self, ag: Archetype) -> None:
        """Draw what the player fixes for the whole match."""
        ag.base = ag.settle(draw(ag.rng, self.base_bet), False, ag.rules.starting_chips)

    def propose(
        self, ag: Archetype, state: MatchState, ref: float, behind: bool
    ) -> tuple[float, bool]:
        raise NotImplementedError

    def side_bets(self, ag: Archetype, state: MatchState, bet: float) -> SideBets:
        """Side bets from the player's class and habit (§5.9)."""
        if not ag.side_class:
            return NO_SIDE_BETS
        spare = ag.whole_chips(state.balance - bet)
        if spare < ag.rules.side_bet_min:
            return NO_SIDE_BETS
        rng = ag.rng
        if rng.random() >= (ag.side_p_last if state.is_last_round else ag.side_p):
            return NO_SIDE_BETS
        both = ag.side_which == "both"
        total = ag.side_size * (2 if both else 1)
        if rng.random() < self.side.p_big_frac:
            total = max(total, ag.round_chips(self.side.big_frac * state.balance))
        elif ag.used_2x and state.last is not None and state.last.side_bets.total > 0:
            total *= 2
        return ag.place_side_bets(min(total, spare), ag.side_which)

    def insurance_prob(self, ag: Archetype, blackjack: bool, p: float) -> float:
        """Chance of taking insurance, given the play tier's chance ``p``."""
        return p


@dataclass(frozen=True)
class FlatStyle(BetStyle):
    """Shared by B1-B3: a steady bet, and sometimes a big one on the last hand (§5.6)."""

    #: §3 B2 [A] last hand, behind: P(big bet)...
    p_big_behind: float = 0.30
    #: §3 B1-B3 [A] ...and its size as a fraction of the stack.
    big_behind: Dist = ((1.0, 0.5), (0.5, 0.3), (0.25, 0.2))
    #: §3 B2 [A] last hand, ahead: P(big bet); the reference-independent effect...
    p_big_ahead: float = 0.10
    #: §3 B2 [A] ...and its size. The research gives sizes for B2 only; B1 and
    #: B3 use the same.
    big_ahead: Dist = ((1.0, 0.3), (0.5, 0.4), (0.25, 0.3))

    def last_hand_big(self, ag: Archetype, state: MatchState, behind: bool):
        """The last-hand big bet, or None when the player does not make one."""
        p, sizes = (
            (self.p_big_behind, self.big_behind) if behind else (self.p_big_ahead, self.big_ahead)
        )
        if ag.rng.random() < p:
            return _stack_bet(ag, draw(ag.rng, sizes), state.balance)
        return None


@dataclass(frozen=True)
class FlatMin(FlatStyle):
    """B1: bets the minimum every hand; a few shove on the last hand."""

    name: str = "B1 Flat-min"
    share: float = 0.12
    tier_probs: tuple[float, float, float] = (0.20, 0.50, 0.30)
    side: SideBetParams = SideBetParams(cls_probs=(0.75, 0.20, 0.05))
    #: §3 B1 [A] hand-1 bet.
    base_bet: Dist = ((10, 0.90), (25, 0.07), (50, 0.03))
    #: §3 B1 [A] P(same bet as hand 1) on each later hand; inertia per Chen et al.
    p_same: float = 0.90
    #: §3 B1 [A] the bet otherwise: 25 on 0.07 and 50 on 0.03 of later hands.
    other_bet: Dist = ((25, 0.7), (50, 0.3))
    #: §3 B1 [A] last hand, behind.
    p_big_behind: float = 0.15
    #: §3 B1 [A] last hand, ahead.
    p_big_ahead: float = 0.02

    def propose(self, ag, state, ref, behind):
        if not state.history:
            return ag.base, True
        if state.is_last_round:
            big = self.last_hand_big(ag, state, behind)
            if big is not None:
                return big
        if ag.rng.random() < self.p_same:
            return ag.base, True
        return draw(ag.rng, self.other_bet), False


@dataclass(frozen=True)
class FlatSmall(FlatStyle):
    """B2: bets the one-tap default and repeats it, with occasional adjustments."""

    name: str = "B2 Flat-small"
    share: float = 0.17
    tier_probs: tuple[float, float, float] = (0.10, 0.50, 0.40)
    side: SideBetParams = SideBetParams(cls_probs=(0.55, 0.30, 0.15))
    #: §3 B2 [A] hand-1 bet, anchored on the default 25 chip.
    base_bet: Dist = ((25, 0.55), (50, 0.30), (75, 0.10), (20, 0.05))
    #: §3 B2 [A] after a win: P(change), else repeat with REPLAY.
    p_change_win: float = 0.35
    #: §3 B2 [A] the change after a win, as a multiple of the previous bet.
    on_win: Dist = ((2.0, 0.55), (1.5, 0.35), (0.5, 0.10))
    #: §3 B2 [A] after a loss: P(change), else repeat.
    p_change_loss: float = 0.30
    #: §3 B2 [A] the change after a loss.
    on_loss: Dist = ((0.5, 0.60), (2.0, 0.25), (1.5, 0.15))
    #: §5.7 [A] P(halve the next bet) after losing to a dealer blackjack.
    p_cold_halve: float = 0.15
    #: §5.11 [S: client] profit that triggers a win celebration.
    celebration_profit: float = 100
    #: §5.11 [A] optional: raise on the next bet after a celebrated win. The
    #: research suggests 0.10 and calls it unvalidated; off by default.
    celebration_bonus: float = 0.0

    def react(self, ag: Archetype, last: RoundRecord) -> tuple[float, bool]:
        """Next bet from the last round's result: repeat, or change by a multiple."""
        rng = ag.rng
        net = last.result.main_net
        if net > 0:
            if rng.random() >= self.p_change_win:
                amount, exact = last.bet, True
            else:
                amount, exact = _times(ag, last.bet, draw(rng, self.on_win))
            if self.celebration_bonus and net >= self.celebration_profit:
                return amount * (1 + self.celebration_bonus), False
            return amount, exact
        if net < 0:
            if last.result.dealer_blackjack and rng.random() < self.p_cold_halve:
                return last.bet * 0.5, False
            if rng.random() >= self.p_change_loss:
                return last.bet, True
            return _times(ag, last.bet, draw(rng, self.on_loss))
        return last.bet, True

    def propose(self, ag, state, ref, behind):
        if not state.history:
            return ag.base, True
        if state.is_last_round:
            big = self.last_hand_big(ag, state, behind)
            if big is not None:
                return big
        return self.react(ag, state.history[-1])


@dataclass(frozen=True)
class FlatMid(FlatSmall):
    """B3: a flat unit of 100-200, adjusting like B2."""

    name: str = "B3 Flat-mid"
    share: float = 0.11
    tier_probs: tuple[float, float, float] = (0.15, 0.55, 0.30)
    #: §3 B3 [A] hand-1 bet.
    base_bet: Dist = ((100, 0.55), (200, 0.20), (50, 0.15), (150, 0.05), (250, 0.05))
    #: §3 B3 [A] last hand, behind.
    p_big_behind: float = 0.35


@dataclass(frozen=True)
class Presser(BetStyle):
    """B4: raises after a win, returns to base after a loss, bets house money."""

    name: str = "B4 Presser"
    share: float = 0.16
    tier_probs: tuple[float, float, float] = (0.15, 0.55, 0.30)
    side: SideBetParams = SideBetParams(cls_probs=(0.45, 0.35, 0.20))
    #: §3 B4 [A] base bet.
    base_bet: Dist = ((25, 0.25), (50, 0.35), (100, 0.30), (200, 0.10))
    #: §3 B4 [A] after a win, multiple of the previous bet; scaled to Zhang 2008.
    on_win: Dist = ((2.0, 0.45), (1.5, 0.30), (1.0, 0.20), (BASE, 0.05))
    #: §3 B4 [S: Bennis 2004, qualitative] wins in a row that prompt a reset.
    streak_len: int = 3
    #: §3 B4 [A] P(reset to base) after that streak.
    p_streak_reset: float = 0.40
    #: §3 B4 [A] after a loss.
    on_loss: Dist = ((BASE, 0.70), (0.5, 0.15), (1.0, 0.15))
    #: §3 B4 [S: Zhang 2008] extra chips bet per chip above the reference.
    house_money_slope: float = 0.08
    #: §3 B4 [A] a bet above this fraction of the stack is cut back to it...
    soft_cap_frac: float = 0.5
    #: §3 B4 [A] ...with this probability.
    p_soft_cap: float = 0.8
    #: §3 B4 [A] last hand, behind: P(all-in).
    p_all_in_last_behind: float = 0.40
    #: §3 B4 [A] last hand, ahead: P(switch to base), else keep pressing.
    p_base_last_ahead: float = 0.40
    #: §5.7 [A] P(halve the next bet) after losing to a dealer blackjack.
    p_cold_halve: float = 0.15
    #: §5.11 [S: client] / [A]: see `FlatSmall`.
    celebration_profit: float = 100
    celebration_bonus: float = 0.0

    def propose(self, ag, state, ref, behind):
        rng = ag.rng
        balance = state.balance
        if not state.history:
            amount, exact = ag.base, True
        else:
            if state.is_last_round:
                if behind:
                    if rng.random() < self.p_all_in_last_behind:
                        return ALL_IN, True
                elif rng.random() < self.p_base_last_ahead:
                    return ag.base, True
            last = state.history[-1]
            net = last.result.main_net
            if net > 0:
                streak = _win_streak(state.history) == self.streak_len
                if streak and rng.random() < self.p_streak_reset:
                    amount, exact = ag.base, True
                else:
                    amount, exact = _times(ag, last.bet, draw(rng, self.on_win))
                if self.celebration_bonus and net >= self.celebration_profit:
                    amount, exact = amount * (1 + self.celebration_bonus), False
            elif net < 0:
                if last.result.dealer_blackjack and rng.random() < self.p_cold_halve:
                    amount, exact = last.bet * 0.5, False
                else:
                    amount, exact = _times(ag, last.bet, draw(rng, self.on_loss))
            else:
                amount, exact = last.bet, True
        if balance > ref and self.house_money_slope:
            amount, exact = amount + self.house_money_slope * (balance - ref), False
        if amount > self.soft_cap_frac * balance and rng.random() < self.p_soft_cap:
            amount, exact = self.soft_cap_frac * balance, False
        return amount, exact


@dataclass(frozen=True)
class Chaser(BetStyle):
    """B5: doubles after a loss, returns to base after a win, bets to get back to even."""

    name: str = "B5 Chaser"
    share: float = 0.08
    tier_probs: tuple[float, float, float] = (0.10, 0.50, 0.40)
    side: SideBetParams = SideBetParams(cls_probs=(0.55, 0.30, 0.15))
    #: §3 B5 [A] base bet.
    base_bet: Dist = ((25, 0.30), (50, 0.35), (100, 0.30), (10, 0.05))
    #: §3 B5 [A] after a loss, multiple of the previous bet.
    on_loss: Dist = ((2.0, 0.65), (1.5, 0.15), (3.0, 0.05), (1.0, 0.15))
    #: §3 B5 [A] if the raised bet exceeds the stack: P(all-in), else repeat.
    p_all_in_if_over: float = 0.6
    #: §3 B5 [A] after a win.
    on_win: Dist = ((BASE, 0.8), (1.0, 0.2))
    #: §3 B5 [A] break-even targeting starts with this many hands left (hand 4).
    target_from_hands_left: int = 2
    #: §3 B5 [A] P(bet the deficit plus base) when behind, before the last hand.
    p_target: float = 0.5
    #: §3 B5 [A] last hand, behind: P(act), split between target and all-in.
    p_last_behind: float = 0.6
    #: §3 B5 [A] share of those that bet the break-even target, else all-in.
    last_target_share: float = 0.5

    def propose(self, ag, state, ref, behind):
        if not state.history:
            return ag.base, True
        rng = ag.rng
        balance = state.balance
        if behind and state.rounds_left <= self.target_from_hands_left:
            target = (ref - balance) + ag.base
            if state.is_last_round:
                if rng.random() < self.p_last_behind:
                    if rng.random() < self.last_target_share:
                        return target, False
                    return ALL_IN, True
            elif rng.random() < self.p_target:
                return target, False
        last = state.history[-1]
        net = last.result.main_net
        if net < 0:
            amount, exact = _times(ag, last.bet, draw(rng, self.on_loss))
            if amount > balance:
                ag.used_2x = False
                if rng.random() < self.p_all_in_if_over:
                    return ALL_IN, True
                return last.bet, True
            return amount, exact
        if net > 0:
            return _times(ag, last.bet, draw(rng, self.on_win))
        return last.bet, True


@dataclass(frozen=True)
class Hero(BetStyle):
    """B6: bets half to all of the stack early, then protects or keeps swinging."""

    name: str = "B6 Hero"
    share: float = 0.10
    tier_probs: tuple[float, float, float] = (0.05, 0.40, 0.55)
    #: §3 B6 [A] side-bet classes, and P(side bet >= 25% of the stack) of 0.10.
    side: SideBetParams = SideBetParams(cls_probs=(0.35, 0.35, 0.30), p_big_frac=0.10)
    #: §3 B6 [A] hand-1 bet as a fraction of the stack; Haghani & Dewey prevalence.
    first_frac: Dist = ((1.0, 0.45), (0.5, 0.30), (0.3, 0.15), (0.15, 0.10))
    #: §3 B6 [A] chips above the reference at which the Hero is "up big" (1,500).
    up_big_margin: float = 500
    #: §3 B6 [A] up big, redrawn each hand: minimum, half the stack, or 15% of it.
    up_big_frac: Dist = ((MINIMUM, 0.5), (0.5, 0.3), (0.15, 0.2))
    #: §3 B6 [A] behind: fraction of the stack.
    behind_frac: Dist = ((1.0, 0.35), (0.5, 0.25), (0.2, 0.40))
    #: §3 B6 [A] at or above the reference but not up big.
    middle_frac: float = 0.2
    #: §3 B6 [A] last hand, behind: P(all-in).
    p_all_in_last_behind: float = 0.8

    def start(self, ag):
        ag.base = ag.rules.min_bet

    def propose(self, ag, state, ref, behind):
        rng = ag.rng
        balance = state.balance
        if not state.history:
            return _stack_bet(ag, draw(rng, self.first_frac), balance)
        if behind:
            if state.is_last_round and rng.random() < self.p_all_in_last_behind:
                return ALL_IN, True
            return _stack_bet(ag, draw(rng, self.behind_frac), balance)
        if balance >= ref + self.up_big_margin:
            return _stack_bet(ag, draw(rng, self.up_big_frac), balance)
        return self.middle_frac * balance, False


@dataclass(frozen=True)
class Closer(BetStyle):
    """B7: small and flat until the last hand, then large or all-in."""

    name: str = "B7 Closer"
    share: float = 0.12
    tier_probs: tuple[float, float, float] = (0.20, 0.55, 0.25)
    #: §3 B7 [A] side-bet classes; occasional bettors favour the last hand.
    side: SideBetParams = SideBetParams(cls_probs=(0.55, 0.35, 0.10), occasional_last_share=0.7)
    #: §3 B7 [A] base bet for hands 1-4.
    base_bet: Dist = ((10, 0.35), (25, 0.40), (50, 0.25))
    #: §3 B7 [A] hands 2-4 after a win: P(bet `press_mult` x base), else base.
    p_press: float = 0.35
    press_mult: float = 2.0
    #: §3 B7 [A] hand 4: chips below the reference that trigger a pre-shove (S < 900)...
    hand4_deficit: float = 100
    #: §3 B7 [A] ...with this probability...
    p_hand4: float = 0.25
    #: §3 B7 [A] ...of this fraction of the stack.
    hand4_frac: float = 0.5
    #: §3 B7 [A] last hand, behind: fraction of the stack, or the base bet.
    last_behind: Dist = ((1.0, 0.65), (0.6, 0.20), (BASE, 0.15))
    #: §3 B7 [A] last hand, ahead; McKenzie's reference-independent effect.
    last_ahead: Dist = ((1.0, 0.25), (MINIMUM, 0.50), (0.25, 0.25))

    def propose(self, ag, state, ref, behind):
        if not state.history:
            return ag.base, True
        rng = ag.rng
        balance = state.balance
        if state.is_last_round:
            sizes = self.last_behind if behind else self.last_ahead
            return _stack_bet(ag, draw(rng, sizes), balance)
        if state.rounds_left == 2 and balance < ref - self.hand4_deficit:
            if rng.random() < self.p_hand4:
                return self.hand4_frac * balance, False
        if state.history[-1].result.main_net > 0 and rng.random() < self.p_press:
            return _times(ag, ag.base, self.press_mult)
        return ag.base, True


@dataclass(frozen=True)
class Protector(BetStyle):
    """B8: medium bets until up by a threshold, then the minimum for the rest."""

    name: str = "B8 Protector"
    share: float = 0.05
    tier_probs: tuple[float, float, float] = (0.25, 0.55, 0.20)
    side: SideBetParams = SideBetParams(cls_probs=(0.75, 0.20, 0.05))
    #: §3 B8 [A] base bet while not locked.
    base_bet: Dist = ((100, 0.4), (200, 0.3), (50, 0.2), (300, 0.1))
    #: §3 B8 [A] lock once the balance is this far above the reference; round numbers.
    lock_threshold: Dist = ((50, 0.2), (100, 0.4), (200, 0.3), (300, 0.1))
    #: §3 B8 [A] the bet once locked, kept for the rest of the match.
    locked_bet: Dist = ((10, 0.8), (25, 0.2))
    #: §3 B8 [A] behind: P(bet the deficit plus base), else base.
    p_target_behind: float = 0.4
    #: §3 B8 [A] last hand, behind: P(all-in).
    p_all_in_last_behind: float = 0.5

    def start(self, ag):
        super().start(ag)
        ag.lock_at = draw(ag.rng, self.lock_threshold)
        ag.locked_bet = None

    def propose(self, ag, state, ref, behind):
        rng = ag.rng
        balance = state.balance
        if ag.locked_bet is None and balance >= ref + ag.lock_at:
            ag.locked_bet = draw(rng, self.locked_bet)
        if ag.locked_bet is not None:
            return ag.locked_bet, True
        if behind:
            if state.is_last_round and rng.random() < self.p_all_in_last_behind:
                return ALL_IN, True
            if rng.random() < self.p_target_behind:
                return (ref - balance) + ag.base, False
        return ag.base, True


@dataclass(frozen=True)
class Tactician(BetStyle):
    """B9: sizes bets against an estimate of the opponent; a stand-in for a sharp human."""

    name: str = "B9 Tactician"
    share: float = 0.04
    tier_probs: tuple[float, float, float] = (0.70, 0.30, 0.00)
    #: §3 B9: side bets are state-dependent, so the class mechanism is off.
    side: SideBetParams = SideBetParams(cls_probs=(1.0, 0.0, 0.0))
    #: §3 B9, §5.1 [A] 80% estimate the opponent from shared outcomes. The rest
    #: keep the field's 8:1 split between the plain and pessimist references.
    reference: ReferenceParams = ReferenceParams(p_pessimist=0.022, p_shared_estimate=0.80)
    #: §3 B9 [A] hands 1-4: fraction of the stack; drawn once a match.
    early_frac: Dist = ((0.05, 0.3), (0.10, 0.4), (0.15, 0.3))
    #: §3 B9 [A] last hand: below reference + this (S < 1,100) the bet is `last_close_frac`.
    close_margin: float = 100
    last_close_frac: Dist = ((1.0, 0.5), (0.6, 0.5))
    #: §3 B9 [A] last hand: at or above reference + this (S >= 1,300) the bet is the minimum.
    safe_margin: float = 300
    #: §3 B9 [A] last hand, in between.
    last_middle_frac: float = 0.35
    #: §3 B9, §4.2 [A] extra doubles and splits when behind on the last hand.
    #: Needs spare chips equal to the bet, which `last_close_frac` never leaves.
    p_variance_play: float = 0.5
    #: §3 B9 says only "buys variance when behind, sheds it when ahead". The
    #: four numbers below are this code's reading of that, all [A]:
    #: P(side bet) when behind on the last hand with chips to spare...
    p_side_when_behind: float = 0.5
    #: ...and its size as a fraction of the stack.
    side_frac_when_behind: float = 0.25
    #: P(insurance) when behind: declining keeps the variance.
    p_insure_behind: float = 0.0
    #: P(even money on a blackjack) when not behind: taking it sheds variance.
    p_even_money_ahead: float = 1.0

    def start(self, ag):
        ag.base = draw(ag.rng, self.early_frac)

    def propose(self, ag, state, ref, behind):
        balance = state.balance
        if not state.is_last_round:
            return ag.base * balance, False
        if balance < ref + self.close_margin:
            return _stack_bet(ag, draw(ag.rng, self.last_close_frac), balance)
        if balance >= ref + self.safe_margin:
            return MINIMUM, True
        return self.last_middle_frac * balance, False

    def side_bets(self, ag, state, bet):
        if not (state.is_last_round and ag.behind):
            return NO_SIDE_BETS
        spare = ag.whole_chips(state.balance - bet)
        if spare < ag.rules.side_bet_min or ag.rng.random() >= self.p_side_when_behind:
            return NO_SIDE_BETS
        stake = ag.round_chips(self.side_frac_when_behind * state.balance)
        return ag.place_side_bets(min(stake, spare), draw(ag.rng, self.side.which))

    def insurance_prob(self, ag, blackjack, p):
        if ag.behind:
            return self.p_insure_behind
        return self.p_even_money_ahead if blackjack else p


@dataclass(frozen=True)
class Erratic(BetStyle):
    """B10: bet sizes with no rule, from 1% of the stack to all of it."""

    name: str = "B10 Erratic"
    share: float = 0.05
    tier_probs: tuple[float, float, float] = (0.05, 0.40, 0.55)
    #: §3 B10, §5.9 [A] side-bet classes, and P(side bet >= 25% of the stack) of 0.05.
    side: SideBetParams = SideBetParams(cls_probs=(0.35, 0.35, 0.30), p_big_frac=0.05)
    #: §3 B10 [A] P(all-in) on each hand.
    p_all_in: float = 0.10
    #: §3 B10 [A] otherwise the fraction of the stack is log-uniform on this range.
    frac_range: tuple[float, float] = (0.01, 1.0)

    def start(self, ag):
        ag.base = ag.rules.min_bet

    def propose(self, ag, state, ref, behind):
        rng = ag.rng
        if rng.random() < self.p_all_in:
            return ALL_IN, True
        low, high = self.frac_range
        return state.balance * math.exp(rng.uniform(math.log(low), math.log(high))), False


#: The ten bet styles at the research's point estimates, in order B1..B10.
STYLES: tuple[BetStyle, ...] = (
    FlatMin(),
    FlatSmall(),
    FlatMid(),
    Presser(),
    Chaser(),
    Hero(),
    Closer(),
    Protector(),
    Tactician(),
    Erratic(),
)


# --- the agent ---------------------------------------------------------------------------


class Archetype(Agent):
    """A human opponent: one bet style, one play tier, and the shared modules.

    `label` is the bet style's name, so simulation results split by style;
    `tier` is the play tier's name and `description` joins the two. The agent
    can be reused: `reset` redraws everything a player fixes once per match.
    """

    def __init__(
        self,
        style: BetStyle,
        tier: PlayTier,
        *,
        snap: SnapParams = SnapParams(),
        timeout: TimeoutParams = TimeoutParams(),
        rules: RulesConfig = DEFAULT_RULES,
    ) -> None:
        super().__init__()
        self.rules = rules
        self.style = style
        self.skill = tier
        self.snap = snap
        self.timeout = timeout
        self.name = style.name
        self.tier = tier.name
        self._table: PlayTable | None = None
        self._submode: list | None = None
        # Per-match state; `reset` fills it in.
        self.base: float = rules.min_bet
        self.lock_at: float = 0.0
        self.locked_bet: float | None = None
        self.behind = False
        self.used_2x = False
        self.side_class = 0
        self.side_which = "pp"
        self.side_size: float = 0
        self.side_p = 0.0
        self.side_p_last = 0.0
        self._ref: float = rules.starting_chips
        self._ref_shared = False
        self._dead_zone = 0.0
        self._timeout_round = rules.num_rounds
        self._burning = False
        self._variance_p = 0.0

    @property
    def description(self) -> str:
        return f"{self.name} x {self.tier}"

    def __repr__(self) -> str:
        return f"Archetype({self.description})"

    def reset(self, rng, rules: RulesConfig) -> None:
        super().reset(rng, rules)
        self._table = play_table(self.skill, rules)
        self._submode = None
        if self.skill.submodes:
            x = rng.random()
            for mode, share in self.skill.submodes:
                x -= share
                if x < 0:
                    self._submode = getattr(self._table, mode)
                    break

        ref = self.style.reference
        x = rng.random()
        self._ref = rules.starting_chips
        self._ref_shared = x < ref.p_shared_estimate
        if not self._ref_shared and x < ref.p_shared_estimate + ref.p_pessimist:
            self._ref += rng.uniform(*ref.pessimist_range)
        self._dead_zone = rng.uniform(*ref.dead_zone)

        side = self.style.side
        x = rng.random()
        self.side_class = 0 if x < side.cls_probs[0] else 1 if x < sum(side.cls_probs[:2]) else 2
        if self.side_class:
            self.side_which = draw(rng, side.which)
            self.side_size = draw(rng, side.size)
            self.side_p = self.side_p_last = side.p_hand_habitual
            if self.side_class == 1:
                self.side_p = self.side_p_last = p = side.p_hand_occasional
                share, n = side.occasional_last_share, rules.num_rounds
                if share is not None and n > 1:
                    self.side_p_last = min(1.0, share * n * p)
                    self.side_p = (1 - share) * n * p / (n - 1)

        self._timeout_round = rules.num_rounds
        if rng.random() < self.timeout.p_timeout:
            self._timeout_round = draw(rng, self.timeout.hands) - 1
        self._burning = False
        self.behind = False
        self.used_2x = False
        self._variance_p = 0.0
        self.style.start(self)

    # --- reference point (§5.1) ---------------------------------------------

    def reference(self, state: MatchState) -> float:
        """The balance this player thinks they need to beat."""
        if not self._ref_shared:
            return self._ref
        unit = self.style.reference.assumed_opponent_bet
        return self._ref + unit * sum(r.result.main_net / r.bet for r in state.history)

    # --- chips (§3.0) -------------------------------------------------------

    def whole_chips(self, amount: float) -> float:
        """``amount`` rounded down to what the smallest chip can make."""
        return amount - amount % self.snap.chip

    def round_chips(self, amount: float) -> float:
        """``amount`` rounded to the round number a player would tap out."""
        for below, step in self.snap.grid:
            if amount < below:
                break
        return step * round(amount / step)

    def max_bet(self, balance: float) -> float:
        """The largest main bet the chips allow: all-in."""
        rules = self.rules
        limit = balance if rules.max_bet is None else min(balance, rules.max_bet)
        return max(self.whole_chips(limit), rules.min_bet)

    def settle(self, amount: float, exact: bool, balance: float) -> float:
        """Turn an intended bet into a legal one: noise, rounding, then limits."""
        snap = self.snap
        low = self.rules.min_bet
        cap = self.max_bet(balance)
        if amount == ALL_IN:
            step = snap.all_in_round_to
            rounded = cap - cap % step
            if low <= rounded < cap and self.rng.random() >= snap.p_awkward_all_in_exact:
                return rounded
            return cap
        if amount <= low:
            return low
        if not exact:
            if snap.noise_sigma:
                amount *= self.rng.lognormvariate(0.0, snap.noise_sigma)
            if amount >= balance - snap.all_in_margin:
                return cap
            if self.rng.random() < snap.p_exact_count:
                amount = snap.chip * round(amount / snap.chip)
            else:
                amount = self.round_chips(amount)
        return min(max(amount, low), cap)

    def place_side_bets(self, total: float, which: str) -> SideBets:
        """Put ``total`` chips on the named side bet, split evenly for "both"."""
        low = self.rules.side_bet_min
        if which == "both":
            half = self.whole_chips(total / 2)
            if half >= low:
                return SideBets(half, half)
            which = "pp"
        stake = self.whole_chips(total)
        if stake < low:
            return NO_SIDE_BETS
        return SideBets(stake, 0) if which == "pp" else SideBets(0, stake)

    # --- decisions ------------------------------------------------------------

    def bet(self, state: MatchState) -> float:
        self.used_2x = False
        self._burning = state.round_index >= self._timeout_round
        if self._burning:
            self._variance_p = 0.0
            return self.max_bet(state.balance)
        ref = self.reference(state)
        self.behind = state.balance < ref - self._dead_zone
        style = self.style
        self._variance_p = (
            style.p_variance_play if self.behind and state.is_last_round else 0.0
        )
        amount, exact = style.propose(self, state, ref, self.behind)
        return self.settle(amount, exact, state.balance)

    def side_bets(self, state: MatchState, bet: float) -> SideBets:
        if self._burning:
            return NO_SIDE_BETS
        return self.style.side_bets(self, state, bet)

    def take_insurance(self, ctx: DecisionContext, state: MatchState) -> bool:
        if self._burning:
            return False
        skill = self.skill
        total, soft = hand_value(ctx.hand.cards)
        blackjack = total == 21
        if blackjack:
            p = skill.p_insure_blackjack
        elif soft:
            p = skill.p_insure
        elif total >= 19:
            p = skill.p_insure * skill.insure_hand_mult[0]
        elif 12 <= total <= 16:
            p = skill.p_insure * skill.insure_hand_mult[1]
        else:
            p = skill.p_insure
        return self.rng.random() < self.style.insurance_prob(self, blackjack, p)

    def act(self, ctx: DecisionContext, state: MatchState) -> Action:
        if self._burning:
            return _HIT
        legal = ctx.legal
        cards = ctx.hand.cards
        total, soft = hand_value(cards)
        up = _UP[ctx.upcard]
        index = (_SOFT_OFFSET if soft else 0) + total * 10 + up
        random = self.rng.random
        table = self._table
        if self._submode is not None and random() >= self.skill.submode_noise:
            return self._submode[index]
        cells = table.plain
        if len(legal) > 2:
            if _SPLIT in legal:
                splits, p = table.split[_UP[cards[0]] * 10 + up]
                if p and random() < p:
                    splits = not splits
                if splits:
                    return _SPLIT
            if _DOUBLE in legal:
                cells = table.doubling
        action, p, wrong = cells[index]
        if p and random() < p:
            action = wrong
        if self._variance_p and action == _HIT and len(legal) > 2:
            if random() < self._variance_p:
                return _DOUBLE if _DOUBLE in legal else _SPLIT if _SPLIT in legal else _HIT
        return action
