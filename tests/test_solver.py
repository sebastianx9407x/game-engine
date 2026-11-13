"""The exact solver and the basic strategy derived from it."""

import random
from fractions import Fraction

import numpy as np
import pytest

from rivals.cards import fresh_decks, parse_cards
from rivals.hand import Action
from rivals.resolve import play_round
from rivals.rules import DEFAULT_RULES
from rivals.shoe import Shoe
from rivals.solver import BasicStrategy, Solver, basic_chart, solver_for
from rivals.solver.exact import ACE, POINTS, TEN, counts_of, total_of, value_index

S, H, D, P = Action.STAND, Action.HIT, Action.DOUBLE, Action.SPLIT

# The textbook game: double any two cards, dealer checks under a ten, split
# aces get one card. Used to check the solver against the published chart.
PUBLISHED = DEFAULT_RULES.with_(double_totals=None, dealer_peeks_on_ten=True, hit_split_aces=False)
UPCARDS = [1, 2, 3, 4, 5, 6, 7, 8, TEN, ACE]  # 2..9, ten, ace as value indices


@pytest.fixture(scope="module")
def solver():
    return solver_for(DEFAULT_RULES)


@pytest.fixture(scope="module")
def published():
    return solver_for(PUBLISHED)


def hard_row(chart, total):
    return "".join(str(chart.hard[(total, u)])[0] for u in UPCARDS)


def soft_row(chart, total):
    return "".join(str(chart.soft[(total, u)])[0] for u in UPCARDS)


def pair_row(chart, pair):
    return "".join("P" if chart.split[(pair, u)] else "-" for u in UPCARDS)


# --- independent brute force ---------------------------------------------------


def brute_dealer(shoe, upcard, forbidden, h17=False):
    """Dealer result chances by plain enumeration with exact fractions."""
    out = {}

    def walk(cards, shoe, p):
        hard = sum(POINTS[c] for c in cards)
        total = hard + 10 if ACE in cards and hard + 10 <= 21 else hard
        if len(cards) == 2 and total == 21:
            key = "blackjack"
        elif total > 21:
            key = "bust"
        elif total > 17 or (total == 17 and not (total != hard and h17)):
            key = str(total)
        else:
            key = None
        if key is not None and len(cards) >= 2:
            out[key] = out.get(key, 0) + p
            return
        size = sum(shoe)
        blocked = shoe[forbidden] if (len(cards) == 1 and forbidden is not None) else 0
        for v in range(10):
            if shoe[v] == 0 or (len(cards) == 1 and v == forbidden):
                continue
            nxt = list(shoe)
            nxt[v] -= 1
            walk(cards + [v], nxt, p * Fraction(shoe[v], size - blocked))

    walk([upcard], list(shoe), Fraction(1))
    return out


def shoe_without(decks, *values):
    shoe = [4 * decks] * 9 + [16 * decks]
    for v in values:
        shoe[v] -= 1
    return shoe


@pytest.mark.parametrize(
    "cards, upcard, forbidden",
    [
        ("Ts 7d", "9c", None),
        ("Ts 6d", "Tc", None),  # no check under a ten: blackjack is a live result
        ("9s 8d", "Ac", TEN),  # checked ace: hole card is known not to be a ten
        ("5s 5d", "6c", None),
    ],
)
def test_dealer_chances_match_brute_force(cards, upcard, forbidden):
    rules = DEFAULT_RULES.with_(num_decks=1)
    values = [value_index(c) for c in parse_cards(cards)]
    up = value_index(parse_cards(upcard)[0])
    expected = brute_dealer(shoe_without(1, up, *values), up, forbidden)
    got = Solver(rules).dealer_probs(cards, upcard)
    assert sum(got.values()) == pytest.approx(1.0, abs=1e-12)
    for key, p in got.items():
        assert p == pytest.approx(float(expected.get(key, 0)), abs=1e-12), key
    if forbidden is None and up == TEN:
        assert got["blackjack"] > 0
    if forbidden is not None:
        assert got["blackjack"] == 0


def test_double_value_matches_brute_force_including_the_hole_card_check():
    # One deck, 6-5 against a checked ace. Enumerate the hole card first (it
    # was dealt before the double card), then the double card, then the dealer.
    rules = DEFAULT_RULES.with_(num_decks=1)
    shoe = shoe_without(1, ACE, 5, 4)
    size = sum(shoe)
    ev = Fraction(0)
    for hole in range(10):
        if hole == TEN or shoe[hole] == 0:
            continue
        p_hole = Fraction(shoe[hole], size - shoe[TEN])
        after_hole = list(shoe)
        after_hole[hole] -= 1
        for card in range(10):
            if after_hole[card] == 0:
                continue
            p_card = Fraction(after_hole[card], size - 1)
            rest = list(after_hole)
            rest[card] -= 1
            player = 11 + POINTS[card] if card != ACE else 12
            # Dealer finishes from (ace, hole) drawing from `rest`.
            results = {}

            def walk(cards, shoe_now, p):
                hard = sum(POINTS[c] for c in cards)
                total = hard + 10 if hard + 10 <= 21 else hard
                if total >= 17:
                    results[total] = results.get(total, 0) + p
                    return
                n = sum(shoe_now)
                for v in range(10):
                    if shoe_now[v]:
                        nxt = list(shoe_now)
                        nxt[v] -= 1
                        walk(cards + [v], nxt, p * Fraction(shoe_now[v], n))

            walk([ACE, hole], rest, Fraction(1))
            for dealer_total, p in results.items():
                if dealer_total > 21 or player > dealer_total:
                    ev += p_hole * p_card * p * 2
                elif player < dealer_total:
                    ev -= p_hole * p_card * p * 2
    got = Solver(rules).evaluate("6s 5d", "Ac").actions[D].ev
    assert got == pytest.approx(float(ev), abs=1e-12)


# --- the textbook game ---------------------------------------------------------


def test_published_rules_reproduce_the_published_chart(published):
    chart = basic_chart(PUBLISHED)
    for total in (17, 18, 19, 20):
        assert hard_row(chart, total) == "SSSSSSSSSS"
    for total in (13, 14, 15, 16):
        assert hard_row(chart, total) == "SSSSSHHHHH"
    assert hard_row(chart, 12) == "HHSSSHHHHH"
    assert hard_row(chart, 11) == "DDDDDDDDDH"
    assert hard_row(chart, 10) == "DDDDDDDDHH"
    assert hard_row(chart, 9) == "HDDDDHHHHH"
    for total in (5, 6, 7, 8):
        assert hard_row(chart, total) == "HHHHHHHHHH"
    assert soft_row(chart, 20) == soft_row(chart, 19) == "SSSSSSSSSS"
    assert soft_row(chart, 18) == "SDDDDSSHHH"
    assert soft_row(chart, 17) == "HDDDDHHHHH"
    assert soft_row(chart, 16) == soft_row(chart, 15) == "HHDDDHHHHH"
    assert soft_row(chart, 14) == soft_row(chart, 13) == "HHHDDHHHHH"
    assert pair_row(chart, ACE) == "PPPPPPPPPP"
    assert pair_row(chart, TEN) == "----------"
    assert pair_row(chart, 8) == "PPPPP-PP--"  # nines
    assert pair_row(chart, 7) == "PPPPPPPPPP"  # eights
    assert pair_row(chart, 6) == "PPPPPP----"
    assert pair_row(chart, 5) == "PPPPP-----"
    assert pair_row(chart, 4) == "----------"
    assert pair_row(chart, 3) == "---PP-----"
    assert pair_row(chart, 2) == pair_row(chart, 1) == "PPPPPP----"


def test_published_rules_house_edge_is_in_the_known_range(published):
    # About 0.40% with resplitting; no resplit costs a few hundredths more.
    assert 0.0040 < published.round_value().house_edge < 0.0050


# --- 21 Rivals rules -------------------------------------------------------------


def test_rivals_chart_differs_from_the_textbook_where_the_rules_do(solver):
    chart = basic_chart(DEFAULT_RULES)
    assert hard_row(chart, 11) == "DDDDDDDDHH"  # no double into a possible hidden blackjack
    assert hard_row(chart, 10) == "DDDDDDDDHH"
    assert hard_row(chart, 9) == "HDDDDHHHHH"
    assert hard_row(chart, 16) == "SSSSSHHHHH"
    assert hard_row(chart, 12) == "HHSSSHHHHH"
    # Soft hands below ace-8 cannot double at all.
    assert soft_row(chart, 18) == "SSSSSSSHHH"
    for total in (13, 14, 15, 16, 17):
        assert soft_row(chart, total) == "HHHHHHHHHH"
    assert soft_row(chart, 20) == soft_row(chart, 19) == "SSSSSSSSSS"
    assert pair_row(chart, ACE) == "PPPPPPPPPP"
    assert pair_row(chart, 7) == "PPPPPPPP-P"  # eights: no split against a ten
    assert pair_row(chart, 8) == "PPPPP-PP--"
    assert pair_row(chart, TEN) == pair_row(chart, 4) == "----------"


def test_rivals_house_edge(solver):
    edge = solver.round_value().house_edge
    assert 0.0040 < edge < 0.0055
    assert sum(solver.round_value().dist.values()) == pytest.approx(1.0, abs=1e-12)


def test_round_distribution_mean_is_close_to_the_ev(solver):
    value = solver.round_value()
    mean = sum(x * p for x, p in value.dist.items())
    # Not identical: split totals come from an independence approximation.
    assert mean == pytest.approx(value.ev, abs=2e-4)
    assert 1.05 < value.std < 1.20
    assert value.dist[1.5] == pytest.approx(0.0453, abs=5e-4)  # a paid blackjack


def test_chart_costs_almost_nothing_against_perfect_play(solver):
    chart_value = Solver(DEFAULT_RULES, strategy=basic_chart(DEFAULT_RULES)).round_value()
    best = solver.round_value()
    assert chart_value.ev <= best.ev + 1e-12
    assert best.ev - chart_value.ev < 2e-4


def test_fewer_decks_are_better_for_the_player(solver):
    one_deck = Solver(DEFAULT_RULES.with_(num_decks=1)).round_value()
    assert one_deck.ev > solver.round_value().ev + 0.003


# --- single decisions --------------------------------------------------------------


def test_action_values_are_proper_distributions(solver):
    for cards, up in [("Ts 6d", "Tc"), ("6s 5d", "6c"), ("As 7d", "9c"), ("8s 8d", "6c"), ("As Ad", "Tc")]:
        result = solver.evaluate(cards, up)
        for action, value in result.actions.items():
            assert sum(value.dist.values()) == pytest.approx(1.0, abs=1e-9), (cards, action)
            mean = sum(x * p for x, p in value.dist.items())
            tolerance = 0.01 if action == P else 1e-9
            assert mean == pytest.approx(value.ev, abs=tolerance), (cards, action)
        assert result.best == max(result.actions, key=lambda a: result.actions[a].ev)


def test_double_stakes_two_units_and_split_up_to_four(solver):
    result = solver.evaluate("6s 5d", "6c")
    assert set(result.actions[D].dist) == {-2.0, 0.0, 2.0}
    assert set(result.actions[S].dist) <= {-1.0, 0.0, 1.0}
    split = solver.evaluate("8s 8d", "6c").actions[P]
    assert min(split.dist) == -4.0 and max(split.dist) == 4.0
    assert split.std > solver.evaluate("8s 8d", "6c").actions[S].std


def test_well_known_decisions(solver):
    assert solver.evaluate("Ts Td", "6c").best == S
    assert solver.evaluate("Ts 6d", "Tc").best == H
    assert solver.evaluate("Ts 6d", "6c").best == S
    assert solver.evaluate("6s 5d", "6c").best == D
    assert solver.evaluate("8s 8d", "6c").best == P
    assert solver.evaluate("As Ad", "6c").best == P
    assert solver.evaluate("Ts 6d", "Tc").ev < 0 < solver.evaluate("Ts Td", "6c").ev


def test_legal_actions_follow_the_rules(solver, published):
    assert D not in solver.evaluate("As 7d", "6c").actions  # 8/18 cannot double
    assert D in solver.evaluate("As 8d", "6c").actions  # 9/19 can
    assert D in published.evaluate("As 7d", "6c").actions
    assert P in solver.evaluate("Ks Qd", "6c").actions
    assert set(solver.evaluate("5s 4d 3h", "6c").actions) == {S, H}
    assert D in solver.evaluate("8s 3d", "6c", after_split=True).actions
    assert P not in solver.evaluate("8s 8d", "6c", after_split=True).actions


def test_hidden_blackjack_under_a_ten_makes_doubling_eleven_wrong(solver, published):
    assert solver.evaluate("6s 5d", "Tc").best == H
    assert published.evaluate("6s 5d", "Tc").best == D
    # The loss side of the double includes the dealer's blackjack.
    assert solver.dealer_probs("6s 5d", "Tc")["blackjack"] == pytest.approx(24 / 309)
    assert published.dealer_probs("6s 5d", "Tc")["blackjack"] == 0


def test_insurance_is_a_losing_bet_without_card_information(solver):
    assert solver.insurance_ev("9s 8d") == pytest.approx(0.5 * (3 * 96 / 309 - 1))
    assert solver.insurance_ev("Ts Kd") < solver.insurance_ev("9s 8d") < 0


def test_unsupported_rules_are_refused():
    for change in ({"surrender": True}, {"split_21_is_blackjack": True}, {"max_splits": 2}):
        with pytest.raises(NotImplementedError):
            Solver(DEFAULT_RULES.with_(**change))


def test_fixed_strategy_must_stay_legal():
    always_double = Solver(DEFAULT_RULES, strategy=lambda view: D)
    with pytest.raises(ValueError):
        always_double.evaluate("Ts 6d", "Tc")


# --- against the round engine --------------------------------------------------------


def simulate_start(cards, upcard, rounds, seed, policy):
    """Average net of real rounds that start with these cards, by simulation."""
    player = parse_cards(cards)
    up = parse_cards(upcard)[0]
    rest = fresh_decks(DEFAULT_RULES.num_decks).tolist()
    for c in (*player, up):
        rest.remove(c)
    rng = random.Random(seed)
    nets = []
    for _ in range(rounds):
        rng.shuffle(rest)
        shoe = Shoe([player[0], up, player[1], *rest])
        nets.append(play_round(shoe, policy, 10).net / 10)
    nets = np.array(nets)
    return nets.mean(), nets.std() / np.sqrt(rounds), nets


@pytest.mark.parametrize(
    "cards, upcard",
    [
        ("8s 8d", "6c"),  # split with doubles after
        ("As Ad", "Tc"),  # split into a possible hidden blackjack
        ("6s 5d", "5c"),  # double
        ("Ts 6d", "Tc"),  # hit a stiff against a ten that may hide an ace
    ],
)
def test_solver_agrees_with_simulated_rounds(solver, cards, upcard):
    policy = BasicStrategy(DEFAULT_RULES)
    mean, stderr, nets = simulate_start(cards, upcard, 20_000, 7, policy)
    exact = solver.evaluate(cards, upcard)
    assert mean == pytest.approx(exact.ev, abs=4 * stderr + 0.003)
    # The whole distribution, not just the mean.
    for net, p in exact.actions[exact.best].dist.items():
        observed = float((nets == net).mean())
        assert observed == pytest.approx(p, abs=4 * (p * (1 - p) / len(nets)) ** 0.5 + 0.004), net


def test_basic_strategy_policy_plays_the_chart():
    policy = BasicStrategy(DEFAULT_RULES)
    chart = policy.chart
    rng = random.Random(3)
    for seed in range(300):
        result = play_round(Shoe.from_seed(seed), policy, 10, balance=1000)
        assert result.insurance_bet == 0
        if not result.actions:
            continue
        # The first decision matches the chart for the starting hand.
        start = [value_index(c) for c in (result.hands[0].cards[0], Shoe.from_seed(seed).cards[2])]
        total, soft = total_of(counts_of(start))
        pair = start[0] if start[0] == start[1] else None
        legal = (S, H, D, P)
        expected = chart.action(total, soft, pair, value_index(result.upcard), legal)
        if expected == D and not (total in (9, 10, 11) or (soft and total in (19, 20))):
            continue
        assert result.actions[0][1] == expected


def test_chart_renders_as_text():
    text = basic_chart(DEFAULT_RULES).render()
    assert "Hard" in text and "Soft" in text and "Pairs" in text
    assert len(text.splitlines()) == 1 + 1 + 17 + 1 + 9 + 1 + 10
