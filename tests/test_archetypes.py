"""Human-opponent archetypes (bet style x play tier) and the population built from them.

Figures quoted as "research" are from research/archetypes.md. Its population
moments (§6.2) came from a check simulation without bet noise, without the
awkward-all-in rounding and under double-on-any-two-cards rules, so the
tolerances here are wide and the known gaps are spelled out where they occur.
"""

import pickle
import random
import statistics
from collections import Counter
from dataclasses import replace

import numpy as np
import pytest

from rivals.agents import Agent
from rivals.agents.archetypes import (
    P1_SOLID,
    P2_CASUAL,
    P3_NOVICE,
    P3_SUBMODES,
    STYLES,
    TIERS,
    Archetype,
    Chaser,
    Closer,
    Erratic,
    FlatMid,
    FlatMin,
    FlatSmall,
    Hero,
    Presser,
    Protector,
    SideBetParams,
    SnapParams,
    Tactician,
    TimeoutParams,
)
from rivals.cards import ACE, RANK
from rivals.hand import Action
from rivals.match import play_match, play_player, simulate
from rivals.optimize import Population, default_population
from rivals.rules import DEFAULT_RULES
from rivals.shoe import match_shoes
from rivals.solver.basic import basic_chart, prime_charts

NO_TIMEOUT = TimeoutParams(p_timeout=0.0)
STYLE_IDS = [s.name for s in STYLES]


def play(agent, seed, rules=DEFAULT_RULES):
    """One player's match on the shoes of ``seed``, with its own random stream."""
    return play_player(agent, match_shoes(seed, rules), random.Random(f"{seed}:agent"), rules)


def matches(style, tier=P2_CASUAL, n=2000, **kwargs):
    """``n`` matches of one archetype with timeouts off."""
    agent = Archetype(style, tier, timeout=NO_TIMEOUT, **kwargs)
    return [play(agent, seed) for seed in range(n)]


def assert_chips(player, rules=DEFAULT_RULES):
    """Every wager is made of whole chips and fits the balance."""
    for r in player.rounds:
        assert r.bet % 5 == 0 and rules.min_bet <= r.bet <= r.balance_before
        for stake in (r.side_bets.perfect_pairs, r.side_bets.four_card_total):
            assert stake == 0 or (stake >= rules.side_bet_min and stake % 5 == 0)
        assert r.bet + r.side_bets.total <= r.balance_before


# --- legality ----------------------------------------------------------------------


@pytest.mark.parametrize("style", STYLES, ids=STYLE_IDS)
def test_every_style_and_tier_plays_legal_matches(style):
    # The engine raises on an illegal bet or action, so finishing is the test.
    seen = Counter()
    for tier in TIERS:
        agent = Archetype(style, tier)
        assert agent.label == style.name and agent.tier == tier.name
        assert agent.description == f"{style.name} x {tier.name}"
        for seed in range(220):
            player = play_match(agent, Agent(), seed).a
            assert_chips(player)
            seen["bankrupt"] += player.bankrupt
            for r in player.rounds:
                seen.update(action for _, action in r.result.actions)
                seen["insured"] += r.result.insurance_bet > 0
                seen["side"] += r.side_bets.total > 0
    assert seen[Action.DOUBLE] and seen[Action.SPLIT] and seen[Action.HIT] and seen[Action.STAND]
    assert seen["insured"] and seen["bankrupt"] and seen["side"]


@pytest.mark.parametrize("chips", [10, 15, 20, 25, 30, 40])
def test_short_stacks_stay_legal(chips):
    # Balances where side bets, doubles, splits and insurance are mostly
    # unaffordable. Habitual side-bettors stress the main-plus-side limit.
    rules = DEFAULT_RULES.with_(starting_chips=chips)
    prime_charts([replace(basic_chart(), rules=rules)])
    side_bet_rounds = 0
    for style in STYLES:
        keen = replace(style, side=replace(style.side, cls_probs=(0.0, 0.0, 1.0)))
        for tier in TIERS:
            for agent in (Archetype(style, tier), Archetype(keen, tier)):
                for seed in range(25):
                    player = play(agent, seed, rules)
                    assert_chips(player, rules)
                    side_bet_rounds += sum(r.side_bets.total > 0 for r in player.rounds)
                    if chips == 10:  # the first hand has no chips to spare
                        assert player.rounds[0].bet == 10
                        assert player.rounds[0].side_bets.total == 0
    assert side_bet_rounds > 0


def test_timeout_bets_everything_and_usually_ends_on_zero():
    agent = Archetype(FlatSmall(), P2_CASUAL, timeout=TimeoutParams(p_timeout=1.0))
    results = [play(agent, seed) for seed in range(1500)]
    for player in results:
        assert_chips(player)
        clock = next(r for r in player.rounds if r.bet == r.balance_before - r.balance_before % 5)
        assert clock.round_index in (3, 4) and clock.side_bets.total == 0
        assert all(a == Action.HIT for _, a in clock.result.actions)
    # Burning the stack fails when the cards make exactly 21 (see the module docstring).
    assert 0.82 < sum(p.final_balance < 10 for p in results) / len(results) < 0.95
    never = [play(Archetype(FlatSmall(), P2_CASUAL, timeout=NO_TIMEOUT), s) for s in range(300)]
    assert sum(p.bankrupt for p in never) < 30


# --- determinism ---------------------------------------------------------------------


@pytest.mark.parametrize("style", STYLES, ids=STYLE_IDS)
def test_same_seed_same_match_and_no_global_randomness(style):
    random.seed(99)
    np.random.seed(99)
    before = random.getstate(), np.random.get_state()[1].tolist()
    agent, twin = Archetype(style, P3_NOVICE), Archetype(style, P3_NOVICE)
    different = 0
    for seed in range(40):
        first = play(agent, seed)
        assert first == play(agent, seed) == play(twin, seed)
        other_stream = play_player(agent, match_shoes(seed), random.Random(f"{seed}:other"))
        different += other_stream != first
    assert different > 5
    assert (random.getstate(), np.random.get_state()[1].tolist()) == before


def test_two_copies_with_one_random_stream_mirror_each_other():
    # Research §7.5: catches decision randomness leaking into the cards.
    for style in (FlatMin(), Hero(), Erratic()):
        for seed in range(40):
            a, b = Archetype(style, P3_NOVICE), Archetype(style, P3_NOVICE)
            assert play_match(a, b, seed, agent_seeds=(7, 7)).outcome == 0
    # With their own streams, two copies are two different people.
    a, b = Archetype(Erratic(), P3_NOVICE), Archetype(Erratic(), P3_NOVICE)
    assert {play_match(a, b, seed).outcome for seed in range(40)} >= {-1, 1}


# --- population ------------------------------------------------------------------------


def test_population_samples_styles_and_tiers_at_the_configured_shares():
    pop = default_population()
    assert [label for label, _ in pop.entries] == STYLE_IDS
    assert sum(w for _, w in pop.entries) == pytest.approx(1.0)
    assert dict(pop.entries)["B4 Presser"] == pytest.approx(0.16)
    # Research §6.1 marginals: 16% / 50% / 34%.
    assert list(pop.tier_shares().values()) == pytest.approx([0.16, 0.50, 0.34], abs=0.01)

    n = 40_000
    rng = random.Random(3)
    agents = [pop(rng) for _ in range(n)]
    styles = Counter(a.label for a in agents)
    for label, weight in pop.entries:
        assert abs(styles[label] / n - weight) < 4 * (weight * (1 - weight) / n) ** 0.5
    tiers = Counter(a.tier for a in agents)
    for name, share in pop.tier_shares().items():
        assert abs(tiers[name] / n - share) < 4 * (share * (1 - share) / n) ** 0.5
    # The joint table: Tacticians are never novices, Heroes mostly are.
    joint = Counter((a.label, a.tier) for a in agents)
    assert joint[("B9 Tactician", "P3 Novice")] == 0
    assert joint[("B6 Hero", "P3 Novice")] / styles["B6 Hero"] == pytest.approx(0.55, abs=0.05)


def test_population_variants():
    pop = default_population()
    rng = random.Random(1)

    heroes = pop.only("B6 Hero")
    assert heroes.entries == [("B6 Hero", 1.0)]
    assert {heroes(rng).label for _ in range(200)} == {"B6 Hero"}
    assert {heroes(rng).tier for _ in range(400)} == {t.name for t in TIERS}

    more = pop.reweighted({"B6 Hero": 0.2, "B1 Flat-min": 0.0})
    shares = dict(more.entries)
    assert shares["B6 Hero"] == pytest.approx(0.2) and shares["B1 Flat-min"] == 0
    assert sum(shares.values()) == pytest.approx(1.0)
    # The untouched styles keep their proportions.
    assert shares["B4 Presser"] / shares["B5 Chaser"] == pytest.approx(0.16 / 0.08)
    drawn = Counter(more(rng).label for _ in range(20_000))
    assert drawn["B1 Flat-min"] == 0
    assert drawn["B6 Hero"] / 20_000 == pytest.approx(0.2, abs=0.012)

    tuned = pop.with_style(replace(pop.style("B6 Hero"), p_all_in_last_behind=0.1))
    assert tuned.style("B6 Hero").p_all_in_last_behind == 0.1
    assert pop.style("B6 Hero").p_all_in_last_behind == 0.8
    assert tuned.entries == pop.entries
    assert pop.with_modules(timeout=NO_TIMEOUT)(rng).timeout == NO_TIMEOUT

    custom = Population([Hero(), FlatMin()], [3, 1])
    assert custom.entries == [("B6 Hero", 0.75), ("B1 Flat-min", 0.25)]

    with pytest.raises(KeyError):
        pop.only("B11 Nobody")
    with pytest.raises(ValueError):
        pop.reweighted({"B6 Hero": 0.7, "B7 Closer": 0.6})
    with pytest.raises(ValueError):
        replace(Hero(), first_frac=((1.0, 0.5), (0.5, 0.4)))  # does not sum to 1


def test_population_pickles_and_works_as_a_simulation_factory():
    pop = default_population().reweighted({"B10 Erratic": 0.3})
    copy = pickle.loads(pickle.dumps(pop))
    assert copy.entries == pop.entries and copy.styles == pop.styles
    a, b = pop(random.Random(5)), copy(random.Random(5))
    assert a.description == b.description
    assert play(a, 1) == play(b, 1)

    serial = simulate(_flat_min, pop, 300, seed=2)
    parallel = simulate(_flat_min, pop, 300, seed=2, processes=2)
    assert serial.total == parallel.total
    assert set(serial.by_opponent) == set(parallel.by_opponent) <= set(STYLE_IDS)
    assert len(serial.by_opponent) >= 8


def _flat_min(rng):
    return Agent()


# --- bet styles: the trait that defines each one -----------------------------------------


def reactions(results):
    """Mean of (next bet / previous bet) on hands 2-4 after a win and after a loss."""
    after = {1: [], -1: []}
    for player in results:
        for prev, nxt in zip(player.rounds[:3], player.rounds[1:4]):
            net = prev.result.main_net
            if net:
                after[1 if net > 0 else -1].append(nxt.bet / prev.bet)
    return statistics.mean(after[1]), statistics.mean(after[-1])


def test_flat_min_bets_the_minimum():
    results = matches(FlatMin())
    early = [r.bet for p in results for r in p.rounds[:4]]
    # 0.90 start on 10 and stay there on 0.90 of later hands: 0.83 of bets.
    assert sum(b == 10 for b in early) / len(early) == pytest.approx(0.83, abs=0.04)
    assert max(early) <= 100 and statistics.mean(early) < 20
    last = [r.bet / r.balance_before for p in results for r in p.rounds[4:]]
    assert 0.01 < sum(f >= 0.25 for f in last) / len(last) < 0.15  # the rare last-hand shove


def test_flat_small_and_flat_mid_repeat_their_bet():
    for style, typical, low, high in ((FlatSmall(), 25, 20, 75), (FlatMid(), 100, 50, 250)):
        results = matches(style)
        first = [p.rounds[0].bet for p in results]
        assert statistics.median(first) == typical
        assert sum(low <= b <= high for b in first) / len(first) > 0.9
        pairs = [(a.bet, b.bet) for p in results for a, b in zip(p.rounds[:3], p.rounds[1:4])]
        assert sum(a == b for a, b in pairs) / len(pairs) > 0.6
        win, loss = reactions(results)
        assert win > loss  # the flat styles lean toward pressing (§5.4)
    # Last hand: 0.35 of those behind go big and half of those shove; 0.10 and 0.3 when ahead.
    last = [r for p in matches(FlatMid()) for r in p.rounds[4:]]
    behind = [r.bet >= 0.8 * r.balance_before for r in last if r.balance_before < 950]
    ahead = [r.bet >= 0.8 * r.balance_before for r in last if r.balance_before >= 1000]
    assert sum(behind) / len(behind) == pytest.approx(0.175, abs=0.07)
    assert sum(ahead) / len(ahead) == pytest.approx(0.03, abs=0.03)


def test_presser_raises_after_a_win_and_chaser_after_a_loss():
    press_win, press_loss = reactions(matches(Presser()))
    assert press_win > 1.4 and press_loss < 1.0  # research: mean x1.6 after a win
    chase_win, chase_loss = reactions(matches(Chaser()))
    assert chase_loss > 1.6 and chase_win < 1.05
    assert press_win > chase_win and chase_loss > press_loss


def test_chaser_bets_to_get_back_to_even_late():
    late = [
        r
        for p in matches(Chaser(), n=4000)
        for r in p.rounds[3:]
        if r.balance_before < 900 and r.balance_before >= 400
    ]
    # About half aim at (1,000 - balance) + base or more; a flat base bet would not.
    assert sum(r.bet >= 1000 - r.balance_before for r in late) / len(late) > 0.4


def test_hero_bets_half_the_stack_or_more_on_the_first_hand():
    results = matches(Hero())
    first = [p.rounds[0].bet for p in results]
    assert sum(b == 1000 for b in first) / len(first) == pytest.approx(0.45, abs=0.04)
    assert sum(b >= 500 for b in first) / len(first) > 0.6  # 0.75 intend it; noise trims some
    assert sum(p.bankrupt for p in results) / len(results) == pytest.approx(0.44, abs=0.08)
    # Up big, half of them drop to the minimum.
    rich = [r.bet for p in results for r in p.rounds[1:4] if r.balance_before >= 1600]
    assert sum(b == 10 for b in rich) / len(rich) == pytest.approx(0.5, abs=0.08)


def test_closer_saves_it_for_the_last_hand():
    results = matches(Closer())
    early = [r.bet / r.balance_before for p in results for r in p.rounds[:4]]
    assert statistics.mean(early) < 0.06
    last = [r for p in results for r in p.rounds[4:]]
    behind = [r.bet / r.balance_before for r in last if r.balance_before < 950]
    ahead = [r.bet / r.balance_before for r in last if r.balance_before >= 1000]
    assert len(behind) > 300 and len(ahead) > 300
    assert statistics.mean(behind) > 10 * statistics.mean(early)
    # Research: all-in 0.65 plus 0.6 of the stack 0.20 when behind.
    assert sum(f >= 0.5 for f in behind) / len(behind) == pytest.approx(0.82, abs=0.1)
    assert sum(f >= 0.9 for f in ahead) / len(ahead) == pytest.approx(0.25, abs=0.08)
    assert statistics.mean(behind) > statistics.mean(ahead)


def test_protector_drops_to_the_minimum_once_ahead_by_its_threshold():
    agent = Archetype(Protector(), P2_CASUAL, timeout=NO_TIMEOUT)
    locked_rounds = unlocked_rounds = 0
    for seed in range(2000):
        player = play(agent, seed)
        if agent._ref_shared:
            continue
        locked = None
        for r in player.rounds:
            if locked is None and r.balance_before >= agent._ref + agent.lock_at:
                locked = r.bet
                assert locked in (10, 25)
            if locked is not None:
                locked_rounds += 1
                assert r.bet == locked  # sticky for the rest of the match
            else:
                unlocked_rounds += 1
                assert r.bet >= 25 or r.bet > r.balance_before - 5
    assert locked_rounds > 1000 and unlocked_rounds > 1000


def test_tactician_sizes_the_last_bet_to_its_estimate_of_the_field():
    agent = Archetype(Tactician(), P1_SOLID, timeout=NO_TIMEOUT)
    early, safe, close = [], [], []
    for seed in range(2500):
        player = play(agent, seed)
        early += [r.bet / r.balance_before for r in player.rounds[:4]]
        assert all(r.side_bets.total == 0 for r in player.rounds[:4])
        if len(player.rounds) == 5 and not agent._ref_shared:
            last = player.rounds[4]
            if last.balance_before >= agent._ref + 300:
                safe.append(last.bet / last.balance_before)
            elif last.balance_before < agent._ref + 100:
                close.append(last.bet / last.balance_before)
    assert 0.07 < statistics.median(early) < 0.13 and max(early) < 0.4
    assert safe and all(f < 0.02 for f in safe)
    assert len(close) > 100 and min(close) > 0.3


def test_erratic_bets_all_over_the_place():
    results = matches(Erratic())
    fractions = [r.bet / r.balance_before for p in results for r in p.rounds]
    assert sum(f > 0.99 for f in fractions) / len(fractions) == pytest.approx(0.11, abs=0.04)
    assert sum(f < 0.05 for f in fractions) / len(fractions) > 0.2
    assert sum(0.2 < f < 0.9 for f in fractions) / len(fractions) > 0.2
    assert statistics.pstdev(fractions) > 0.25


def test_bets_cluster_on_round_numbers():
    # Research §5.2: about 80% of hand-1 bets on these values.
    round_values = {10, 25, 50, 75, 100, 150, 200, 250, 500, 1000}
    pop = default_population()
    first = [play(pop(random.Random(seed)), seed).rounds[0].bet for seed in range(3000)]
    assert sum(b in round_values for b in first) / len(first) == pytest.approx(0.82, abs=0.06)
    # With noise and exact counts off, every first bet is one of the research's values.
    plain = pop.with_modules(snap=SnapParams(noise_sigma=0.0, p_exact_count=0.0))
    first = [play(plain(random.Random(seed)), seed).rounds[0].bet for seed in range(1500)]
    assert sum(b in round_values | {300} for b in first) / len(first) > 0.94


def test_side_bet_classes():
    def side_rate(style, cls_probs):
        keen = replace(style, side=replace(style.side, cls_probs=cls_probs))
        rounds = [r for p in matches(keen, n=600) for r in p.rounds]
        return rounds, sum(r.side_bets.total > 0 for r in rounds) / len(rounds)

    assert side_rate(FlatSmall(), (1.0, 0.0, 0.0))[1] == 0
    assert side_rate(FlatSmall(), (0.0, 1.0, 0.0))[1] == pytest.approx(0.25, abs=0.04)
    rounds, rate = side_rate(FlatSmall(), (0.0, 0.0, 1.0))
    assert rate == pytest.approx(0.90, abs=0.03)
    stakes = Counter(max(r.side_bets.perfect_pairs, r.side_bets.four_card_total) for r in rounds)
    assert stakes[10] > stakes[25] > stakes[50] > 0
    # Closers who side-bet occasionally do it mostly on the last hand.
    rounds, _ = side_rate(Closer(), (0.0, 1.0, 0.0))
    placed = [r.round_index for r in rounds if r.side_bets.total > 0]
    assert sum(i == 4 for i in placed) / len(placed) == pytest.approx(0.7, abs=0.08)


# --- play tiers ----------------------------------------------------------------------------

#: A 10-chip flat bettor with no side bets: every double and split is affordable.
PLAIN_BETS = FlatMin(
    base_bet=((10, 1.0),), p_same=1.0, p_big_behind=0.0, p_big_ahead=0.0,
    side=SideBetParams(cls_probs=(1.0, 0.0, 0.0)),
)
_RANK = {Action.STAND: 0, Action.HIT: 1, Action.DOUBLE: 2, Action.SPLIT: 2}


class Audited(Archetype):
    """Records each decision next to the basic-strategy play."""

    def reset(self, rng, rules):
        super().reset(rng, rules)
        self.decisions = []

    def act(self, ctx, state):
        action = super().act(ctx, state)
        self.decisions.append((state.round_index, action, self.basic_action(ctx)))
        return action


def audit(tier, n_matches):
    """Error statistics for ``tier`` over ``n_matches`` matches of flat 10-chip bets."""
    agent = Audited(PLAIN_BETS, tier, timeout=NO_TIMEOUT)
    hands = error_hands = decisions = errors = passive = 0
    insurance = {True: [0, 0], False: [0, 0]}
    for seed in range(n_matches):
        player = play(agent, seed)
        hands += len(player.rounds)
        decisions += len(agent.decisions)
        wrong = [(i, a, b) for i, a, b in agent.decisions if a != b]
        errors += len(wrong)
        error_hands += len({i for i, _, _ in wrong})
        passive += sum(_RANK[a] < _RANK[b] for _, a, b in wrong)
        for r in player.rounds:
            if RANK[r.result.upcard] == ACE:
                offered = insurance[r.result.player_blackjack]
                offered[0] += 1
                offered[1] += r.result.insurance_bet > 0
    return {
        "hands": error_hands / hands,
        "decisions": errors / decisions,
        "passive": passive / max(errors, 1),
        "insure": insurance[False][1] / insurance[False][0],
        "even_money": insurance[True][1] / max(insurance[True][0], 1),
    }


def without_textbook_habits(tier):
    return replace(tier, double_11_vs_ten=0.0, split_8s_vs_ten=0.0)


@pytest.fixture(scope="module")
def tier_audits():
    # The research counts errors against the textbook chart. Doubling 11 or
    # splitting 8s against a ten is the textbook play, so those habits are
    # switched off here; they have their own test below.
    return {tier.name: audit(without_textbook_habits(tier), 7000) for tier in TIERS}


def test_tier_error_rates_match_the_research(tier_audits):
    # Research §4.1, share of HANDS with at least one error: 1.8% / 12.6% / 28.3%,
    # under double-any-two-cards rules. With doubling limited to 9-11 the soft
    # double rows vanish (§4.7 expects about -1 point for P2); measured over
    # 200,000 hands: 1.76% / 12.0% / 27.5%.
    assert tier_audits["P1 Solid"]["hands"] == pytest.approx(0.018, abs=0.006)
    assert tier_audits["P2 Casual"]["hands"] == pytest.approx(0.126, abs=0.02)
    assert tier_audits["P3 Novice"]["hands"] == pytest.approx(0.283, abs=0.03)
    for stats in tier_audits.values():
        # A hand has about 1.35 decisions, so the per-decision rate is lower.
        assert 0.6 * stats["hands"] < stats["decisions"] < 0.9 * stats["hands"]


def test_errors_are_mostly_passive(tier_audits):
    # Research §4.1: 76% / 83% / 84% of errors are failing to hit, double or split.
    assert tier_audits["P1 Solid"]["passive"] == pytest.approx(0.76, abs=0.12)
    assert tier_audits["P2 Casual"]["passive"] == pytest.approx(0.83, abs=0.06)
    assert tier_audits["P3 Novice"]["passive"] == pytest.approx(0.84, abs=0.06)


def test_insurance_rates_by_tier(tier_audits):
    # Research §4.6: 1% / 6% / 15% without a blackjack (before the hand
    # multipliers), 10% / 45% / 55% with one.
    assert tier_audits["P1 Solid"]["insure"] == pytest.approx(0.01, abs=0.01)
    assert tier_audits["P2 Casual"]["insure"] == pytest.approx(0.06, abs=0.025)
    assert tier_audits["P3 Novice"]["insure"] == pytest.approx(0.15, abs=0.04)
    assert tier_audits["P1 Solid"]["even_money"] < 0.25
    assert tier_audits["P2 Casual"]["even_money"] == pytest.approx(0.45, abs=0.17)
    assert tier_audits["P3 Novice"]["even_money"] == pytest.approx(0.55, abs=0.17)


def test_a_tier_with_no_errors_plays_basic_strategy():
    stats = audit(P3_NOVICE.scaled(0.0), 1500)
    assert stats["decisions"] == 0
    rushed = audit(P2_CASUAL.scaled(1.2), 3000)["hands"]
    assert 0.126 < rushed < 0.18


def test_novice_sub_modes_never_double_or_split():
    never_bust = replace(P3_NOVICE, submodes=(("never_bust", 1.0),), submode_noise=0.0)
    agent = Audited(PLAIN_BETS, never_bust, timeout=NO_TIMEOUT)
    for seed in range(300):
        player = play(agent, seed)
        for r in player.rounds:
            assert all(a in (Action.HIT, Action.STAND) for _, a in r.result.actions)
            assert all(h.total <= 21 for h in r.result.hands)  # it never busts
    mixed = audit(replace(P3_NOVICE, submodes=P3_SUBMODES), 3000)
    assert mixed["hands"] > 0.26


def test_players_keep_their_textbook_habits_against_a_ten():
    # 11 against a ten and 8s against a ten: basic strategy changed when the
    # no-check-under-a-ten rule was confirmed, but players do not know that.
    # Each tier doubles and splits there as often as the research says it
    # makes the textbook play.
    assert (P1_SOLID.double_11_vs_ten, P1_SOLID.split_8s_vs_ten) == (0.98, 0.95)
    assert (P2_CASUAL.double_11_vs_ten, P2_CASUAL.split_8s_vs_ten) == (0.856, 0.75)
    assert (P3_NOVICE.double_11_vs_ten, P3_NOVICE.split_8s_vs_ten) == (0.55, 0.45)

    def count(tier):
        agent = Audited(PLAIN_BETS, tier, timeout=NO_TIMEOUT)
        seen = Counter()
        for seed in range(2500):
            play(agent, seed)
            seen.update((a, b) for _, a, b in agent.decisions if a != b)
        return seen

    off = count(without_textbook_habits(P1_SOLID))
    on = count(P1_SOLID)
    # (played, basic): splitting where basic strategy hits happens only with 8s against a ten.
    assert off[(Action.SPLIT, Action.HIT)] == 0 and on[(Action.SPLIT, Action.HIT)] > 5
    assert on[(Action.DOUBLE, Action.HIT)] > 3 * off[(Action.DOUBLE, Action.HIT)] > 0


# --- the whole field against the research's implied moments (§0.4, §6.2) --------------------


@pytest.fixture(scope="module")
def field():
    pop = default_population()
    return [play(pop(random.Random(f"{seed}:make")), seed) for seed in range(16_000)]


def test_field_first_hand_bets(field):
    first = [p.rounds[0].bet for p in field]
    n = len(first)
    # Research: 15.5% bet 10, 44.6% 11-50, 28.5% 51-200, 6.2% 201-999, 5.1% all-in.
    # Measured (60,000 players): 15.7 / 41.8 / 29.1 / 8.4 / 5.0. The shift from
    # 11-50 into 201-999 is the bet noise the research's check left out: with
    # noise off this code gives 15.6 / 44.3 / 28.6 / 6.6 / 4.9.
    assert sum(b == 1000 for b in first) / n == pytest.approx(0.051, abs=0.015)
    assert sum(b == 10 for b in first) / n == pytest.approx(0.155, abs=0.03)
    assert sum(10 < b <= 50 for b in first) / n == pytest.approx(0.446, abs=0.05)
    assert sum(50 < b <= 200 for b in first) / n == pytest.approx(0.285, abs=0.04)
    assert sum(200 < b < 1000 for b in first) / n == pytest.approx(0.062, abs=0.04)
    # §5.5: the average first bet is "about 8-12%" of the stack; measured 13%.
    assert 0.09 < statistics.mean(first) / 1000 < 0.15


def test_field_last_hand(field):
    alive = [p.rounds[4] for p in field if len(p.rounds) == 5]
    assert len(alive) / len(field) == pytest.approx(0.948, abs=0.02)
    big = [r for r in alive if r.bet >= 0.5 * r.balance_before]
    # Research: 24.6% of those alive bet at least half the stack; measured 26.2%.
    assert len(big) / len(alive) == pytest.approx(0.246, abs=0.04)
    # Research: 84% of them are behind 1,000; measured 78%.
    assert sum(r.balance_before < 1000 for r in big) / len(big) == pytest.approx(0.84, abs=0.1)
    # Research: 18.6% go all-in. Measured 14.2% to the last chip. KNOWN GAP: the
    # research's check lacked the §3.0 rule that 40% of awkward all-ins are
    # rounded down to a multiple of 100. Counting those shoves gives 20.2%, and
    # with the rule switched off this code gives 20.0%.
    all_in = sum(r.bet > r.balance_before - 5 for r in alive) / len(alive)
    assert all_in == pytest.approx(0.142, abs=0.03)
    shoves = sum(r.bet >= r.balance_before - r.balance_before % 100 for r in big) / len(alive)
    assert shoves == pytest.approx(0.186, abs=0.04)


def test_field_final_balances(field):
    finals = sorted(p.final_balance for p in field)
    n = len(finals)
    # Research: 13.9% bankrupt; measured 12.5%. Same cause as the all-in gap:
    # a shove rounded down to a multiple of 100 leaves chips behind (15.0% with
    # that rule off). The 1% of modelled timeouts adds about 0.9 points.
    assert sum(p.bankrupt for p in field) / n == pytest.approx(0.139, abs=0.035)
    # Research: 46.9% finish above 1,000; measured 45.0%.
    assert sum(f > 1000 for f in finals) / n == pytest.approx(0.469, abs=0.04)
    # Research quantiles 10/25/50/75/90: 0 / 800 / 1,000 / 1,170 / 1,700, mean 995.
    # Measured: 0 / 700 / 990 / 1,175 / 1,715, mean 969. The lower mean is the
    # house edge, play errors and side bets, which the research's check left out.
    assert finals[n // 10] < 10
    assert 600 <= finals[n // 4] <= 850
    assert 960 <= finals[n // 2] <= 1000
    assert 1100 <= finals[3 * n // 4] <= 1250
    assert 1500 <= finals[9 * n // 10] <= 1950
    assert 940 < statistics.mean(finals) < 1000
    # Research: 32.5% make a bet of 500 or more at some point; measured 34.0%.
    big_bettors = sum(any(r.bet >= 500 for r in p.rounds) for p in field)
    assert big_bettors / n == pytest.approx(0.325, abs=0.04)


def test_field_habits(field):
    pairs = [(a, b) for p in field for a, b in zip(p.rounds, p.rounds[1:])]
    # Research §5.3: P(next bet = previous bet) = 54%; measured 54.2%.
    assert sum(a.bet == b.bet for a, b in pairs) / len(pairs) == pytest.approx(0.54, abs=0.05)
    rounds = [r for p in field for r in p.rounds]
    # Research §5.9: about 21% of hands carry a side bet; measured 19.1%.
    assert sum(r.side_bets.total > 0 for r in rounds) / len(rounds) == pytest.approx(0.21, abs=0.04)
    # Research §5.4: the bet after a win is +0.10 median-bet units above the
    # bet after a non-win on hands 2-4; measured +0.11 to +0.13.
    after_win, after_other = [], []
    for p in field:
        if len(p.rounds) < 2:
            continue
        unit = statistics.median(r.bet for r in p.rounds)
        for prev, nxt in zip(p.rounds[:3], p.rounds[1:4]):
            (after_win if prev.result.main_net > 0 else after_other).append(nxt.bet / unit)
    assert 0.0 < statistics.mean(after_win) - statistics.mean(after_other) < 0.3
