"""Head-to-head matches on shared shoes."""

import random

import pytest

from rivals.agents import Agent, MatchState
from rivals.hand import Action
from rivals.match import Tally, play_match, play_player, simulate
from rivals.resolve import InvalidBetError
from rivals.rules import DEFAULT_RULES
from rivals.shoe import match_shoes
from rivals.side_bets import SideBets


class Flat(Agent):
    def __init__(self, amount):
        super().__init__()
        self.amount = amount
        self.name = f"flat-{amount}"

    def bet(self, state):
        return state.clamp_bet(self.amount)


class AllIn(Agent):
    def bet(self, state):
        return state.max_bet()


class Stander(Agent):
    """Stands on everything: plays differently from basic strategy."""

    def act(self, ctx, state):
        return Action.STAND


class Coin(Agent):
    """Random bet sizes: a stochastic agent."""

    def bet(self, state):
        return state.clamp_bet(self.rng.choice([10, 50, 100, 250]))


class SideBettor(Agent):
    def side_bets(self, state, bet):
        return SideBets(5, 5) if state.balance >= bet + 10 else SideBets()


def flat_min(rng):
    return Agent()


def flat_100(rng):
    return Flat(100)


def coin(rng):
    return Coin()


# --- single matches -----------------------------------------------------------


def test_mirror_match_always_ties():
    for seed in range(300):
        assert play_match(Agent(), Agent(), seed).outcome == 0
        result = play_match(Flat(250), Flat(250), seed)
        assert result.outcome == 0
        assert result.a == result.b


def test_same_cards_different_bets_scale_the_same_results():
    for seed in range(100):
        result = play_match(Flat(10), Flat(100), seed)
        if result.b.bankrupt or len(result.b.rounds) < 5:
            continue
        # Same decisions on the same shoes: every round's net is exactly 10x.
        if all(r.bet == 100 for r in result.b.rounds):
            assert [10 * n for n in result.a.nets] == list(result.b.nets)


def test_match_is_reproducible_and_depends_on_the_seed():
    a = play_match(Coin(), Coin(), 5)
    assert a == play_match(Coin(), Coin(), 5)
    assert any(play_match(Coin(), Coin(), s) != a for s in range(6, 12))


def test_two_copies_of_a_random_strategy_are_two_different_people():
    outcomes = {play_match(Coin(), Coin(), seed).outcome for seed in range(60)}
    assert outcomes == {-1, 0, 1} or outcomes == {-1, 1}
    # With the same random stream they mirror each other.
    for seed in range(60):
        assert play_match(Coin(), Coin(), seed, agent_seeds=(1, 1)).outcome == 0


def test_players_see_the_same_starting_cards_every_round():
    for seed in range(100):
        result = play_match(Agent(), Stander(), seed)
        for ra, rb in zip(result.a.rounds, result.b.rounds):
            assert ra.result.dealer_cards[:2] == rb.result.dealer_cards[:2]
            assert ra.result.hands[0].cards[0] == rb.result.hands[0].cards[0]


def test_balances_add_up():
    for seed in range(100):
        result = play_match(Coin(), SideBettor(), seed)
        for player in (result.a, result.b):
            assert player.final_balance == DEFAULT_RULES.starting_chips + sum(player.nets)
            balance = DEFAULT_RULES.starting_chips
            for record in player.rounds:
                assert record.balance_before == balance
                balance = record.balance_after


def test_bankrupt_player_stops_playing():
    seen = 0
    for seed in range(200):
        player = play_match(AllIn(), Agent(), seed).a
        if player.final_balance < DEFAULT_RULES.min_bet:
            seen += 1
            assert player.bankrupt
            assert len(player.rounds) < 5 or player.rounds[-1].net < 0
            assert player.rounds[-1].balance_after < DEFAULT_RULES.min_bet
        else:
            assert len(player.rounds) == 5 and not player.bankrupt
    assert seen > 100  # shoving five times in a row usually ends at zero


def test_leftover_chips_below_the_minimum_still_count():
    class Leaver(Agent):
        """Bets all but 5 chips, so a loss leaves 5."""

        def bet(self, state):
            return state.balance - 5

    for seed in range(200):
        result = play_match(Leaver(), AllIn(), seed)
        if result.a.final_balance == 5 and result.b.final_balance == 0:
            assert result.a.bankrupt and result.b.bankrupt
            assert result.outcome == 1  # 5 beats 0
            return
    pytest.fail("no match where both went bankrupt")


def test_state_given_to_the_agent():
    seen = []

    class Spy(Agent):
        def bet(self, state):
            seen.append(state)
            return 10

    play_match(Spy(), Agent(), 3)
    assert [s.round_index for s in seen] == [0, 1, 2, 3, 4]
    assert [s.rounds_left for s in seen] == [5, 4, 3, 2, 1]
    assert seen[0].balance == 1000 and seen[0].history == () and seen[0].last is None
    assert seen[-1].is_last_round and len(seen[-1].history) == 4
    assert seen[3].last.balance_after == seen[3].balance
    assert seen[3].profit == seen[3].balance - 1000
    assert isinstance(seen[0], MatchState)


def test_illegal_bets_are_errors_not_silently_fixed():
    class TooBig(Agent):
        def bet(self, state):
            return state.balance + 1

    with pytest.raises(InvalidBetError):
        play_match(TooBig(), Agent(), 1)


def test_play_player_uses_the_given_shoes():
    shoes = match_shoes(9)
    a = play_player(Flat(50), shoes, random.Random(1))
    b = play_player(Flat(50), shoes, random.Random(2))
    assert a == b


# --- many matches ---------------------------------------------------------------


def test_flat_min_against_flat_min_is_all_ties():
    result = simulate(flat_min, flat_min, 300)
    assert (result.total.wins, result.total.ties, result.total.losses) == (0, 300, 0)
    assert result.total.score() == pytest.approx(5 / 9)
    assert result.total.profit_per_entry() == 0


def test_a_strategy_against_itself_is_symmetric():
    result = simulate(coin, coin, 3000, seed=11)
    t = result.total
    assert t.matches == 3000
    assert abs(t.wins - t.losses) < 4 * (t.wins + t.losses) ** 0.5
    assert t.p_win + t.p_tie + t.p_loss == pytest.approx(1.0)


def test_simulation_is_reproducible_and_parallel_matches_serial():
    serial = simulate(flat_100, coin, 400, seed=5)
    again = simulate(flat_100, coin, 400, seed=5)
    parallel = simulate(flat_100, coin, 400, seed=5, processes=2)
    assert serial.total == again.total == parallel.total
    assert serial.by_opponent.keys() == parallel.by_opponent.keys() == {"Coin"}


def test_results_are_split_by_opponent():
    def mixed(rng):
        return Agent() if rng.random() < 0.5 else Flat(100)

    result = simulate(flat_100, mixed, 400)
    assert set(result.by_opponent) == {"Agent", "flat-100"}
    assert sum(t.matches for t in result.by_opponent.values()) == 400
    mirror = result.by_opponent["flat-100"]
    assert mirror.ties == mirror.matches


def test_tally_arithmetic():
    t = Tally(wins=60, ties=10, losses=30)
    assert t.matches == 100
    assert t.score() == pytest.approx(0.6 + 0.1 * 5 / 9)
    assert t.profit_per_entry() == pytest.approx(0.6 * 0.8 - 0.3)
    low, high = t.interval(t.p_win)
    assert low < 0.6 < high and high - low < 0.2
    assert t.score_stderr() == pytest.approx(
        ((0.6 + 0.1 * (5 / 9) ** 2 - t.score() ** 2) / 100) ** 0.5
    )
