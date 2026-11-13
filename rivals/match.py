"""Head-to-head matches: two players on the same shoes.

Both players are dealt from identical shoes, so every difference in their
final balances comes from their own decisions. `simulate` plays many matches
and reports how often the first player finishes ahead.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from multiprocessing import get_context

from rivals.agents.base import Agent, MatchState, RoundRecord
from rivals.hand import Action
from rivals.resolve import DecisionContext, play_round
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.shoe import Shoe, match_shoes
from rivals.solver.basic import Chart, basic_chart, prime_charts


class _Seat:
    """Adapts an `Agent` plus its match state to the round engine's `Policy`."""

    __slots__ = ("agent", "state")

    def __init__(self, agent: Agent, state: MatchState) -> None:
        self.agent = agent
        self.state = state

    def act(self, ctx: DecisionContext) -> Action:
        return self.agent.act(ctx, self.state)

    def take_insurance(self, ctx: DecisionContext) -> bool:
        return self.agent.take_insurance(ctx, self.state)


@dataclass(frozen=True, slots=True)
class PlayerMatch:
    """One player's side of a match."""

    final_balance: float
    #: Rounds actually played; fewer than the full match if the player went bankrupt.
    rounds: tuple[RoundRecord, ...]
    bankrupt: bool

    @property
    def nets(self) -> tuple[float, ...]:
        """Net chips per round, as the MATCH STATS screen shows them."""
        return tuple(r.net for r in self.rounds)


@dataclass(frozen=True, slots=True)
class MatchResult:
    a: PlayerMatch
    b: PlayerMatch

    @property
    def outcome(self) -> int:
        """+1 if the first player finished ahead, -1 if behind, 0 for a tie."""
        diff = self.a.final_balance - self.b.final_balance
        return (diff > 0) - (diff < 0)


def play_player(
    agent: Agent,
    shoes: Sequence[Shoe],
    rng: random.Random,
    rules: RulesConfig = DEFAULT_RULES,
) -> PlayerMatch:
    """Play one player through a match's shoes."""
    agent.reset(rng, rules)
    balance = rules.starting_chips
    history: list[RoundRecord] = []
    bankrupt = False
    for index, shoe in enumerate(shoes):
        if balance < rules.min_bet and not (rules.allow_short_all_in and balance > 0):
            bankrupt = True
            break
        state = MatchState(index, balance, tuple(history), rules)
        bet = agent.bet(state)
        side = agent.side_bets(state, bet)
        result = play_round(shoe, _Seat(agent, state), bet, side, balance=balance, rules=rules)
        history.append(RoundRecord(index, balance, bet, side, result))
        balance += result.net
    return PlayerMatch(balance, tuple(history), bankrupt or balance < rules.min_bet)


def play_match(
    agent_a: Agent,
    agent_b: Agent,
    match_seed: int,
    rules: RulesConfig = DEFAULT_RULES,
    *,
    agent_seeds: tuple[int | str, int | str] | None = None,
) -> MatchResult:
    """Play both agents on the shoes of match ``match_seed``.

    Each agent gets its own random stream derived from the match seed, so two
    copies of the same random strategy behave like two different people. Pass
    ``agent_seeds`` to control the streams (equal seeds make them mirror).
    """
    shoes = match_shoes(match_seed, rules)
    seed_a, seed_b = agent_seeds or (f"{match_seed}:a", f"{match_seed}:b")
    a = play_player(agent_a, shoes, random.Random(seed_a), rules)
    b = play_player(agent_b, shoes, random.Random(seed_b), rules)
    return MatchResult(a, b)


# --- many matches ---------------------------------------------------------------

#: Builds the agent for one match. Called once per match with that match's
#: random stream, so a factory can pick a different opponent type each time.
AgentFactory = Callable[[random.Random], Agent]


@dataclass
class Tally:
    """Win/tie/loss counts for the first player, with the money attached."""

    wins: int = 0
    ties: int = 0
    losses: int = 0
    #: Sums for averages: own final balance, opponent's final balance.
    balance_sum: float = 0.0
    opponent_balance_sum: float = 0.0

    @property
    def matches(self) -> int:
        return self.wins + self.ties + self.losses

    def add(self, result: MatchResult) -> None:
        outcome = result.outcome
        if outcome > 0:
            self.wins += 1
        elif outcome < 0:
            self.losses += 1
        else:
            self.ties += 1
        self.balance_sum += result.a.final_balance
        self.opponent_balance_sum += result.b.final_balance

    def merge(self, other: Tally) -> None:
        self.wins += other.wins
        self.ties += other.ties
        self.losses += other.losses
        self.balance_sum += other.balance_sum
        self.opponent_balance_sum += other.opponent_balance_sum

    # --- rates ------------------------------------------------------------

    @property
    def p_win(self) -> float:
        return self.wins / self.matches

    @property
    def p_tie(self) -> float:
        return self.ties / self.matches

    @property
    def p_loss(self) -> float:
        return self.losses / self.matches

    def score(self, rules: RulesConfig = DEFAULT_RULES) -> float:
        """The objective: P(win) + tie value x P(tie)."""
        return self.p_win + rules.tie_value * self.p_tie

    def score_stderr(self, rules: RulesConfig = DEFAULT_RULES) -> float:
        tie = rules.tie_value
        mean = self.score(rules)
        second_moment = self.p_win + tie * tie * self.p_tie
        return math.sqrt(max(second_moment - mean * mean, 0.0) / self.matches)

    def profit_per_entry(self, rules: RulesConfig = DEFAULT_RULES) -> float:
        """Average money won per 1 of entry fee: a win pays the prize, a tie refunds."""
        return self.p_win * (rules.prize_multiple - 1) - self.p_loss

    def interval(self, rate: float, z: float = 1.96) -> tuple[float, float]:
        """Wilson confidence interval for a rate observed over these matches."""
        n = self.matches
        centre = (rate + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return centre - half, centre + half


@dataclass
class SimulationResult:
    total: Tally = field(default_factory=Tally)
    #: The same counts split by the opponent's label.
    by_opponent: dict[str, Tally] = field(default_factory=dict)
    #: Outcome of every match in seed order (+1 win, 0 tie, -1 loss), if kept.
    outcomes: list[int] = field(default_factory=list)

    def add(self, opponent_label: str, result: MatchResult, keep_outcome: bool = False) -> None:
        self.total.add(result)
        self.by_opponent.setdefault(opponent_label, Tally()).add(result)
        if keep_outcome:
            self.outcomes.append(result.outcome)

    def merge(self, other: SimulationResult) -> None:
        self.total.merge(other.total)
        for label, tally in other.by_opponent.items():
            self.by_opponent.setdefault(label, Tally()).merge(tally)
        self.outcomes.extend(other.outcomes)


def _run_block(args) -> SimulationResult:
    make_agent, make_opponent, seeds, rules, keep_outcomes = args
    out = SimulationResult()
    for seed in seeds:
        agent = make_agent(random.Random(f"{seed}:make-a"))
        opponent = make_opponent(random.Random(f"{seed}:make-b"))
        out.add(opponent.label, play_match(agent, opponent, seed, rules), keep_outcomes)
    return out


def simulate(
    make_agent: AgentFactory,
    make_opponent: AgentFactory,
    matches: int,
    *,
    seed: int = 0,
    rules: RulesConfig = DEFAULT_RULES,
    processes: int = 1,
    keep_outcomes: bool = False,
) -> SimulationResult:
    """Play ``matches`` matches of ``make_agent`` against ``make_opponent``.

    Match ``i`` uses match seed ``seed + i``, so two strategies simulated with
    the same seed face the same cards and the same opponents' random streams,
    which makes their results directly comparable; ``keep_outcomes`` records
    each match's outcome in seed order for such paired comparisons. With
    ``processes > 1`` the factories must be picklable (module-level functions
    or classes).
    """
    seeds = range(seed, seed + matches)
    if processes <= 1:
        return _run_block((make_agent, make_opponent, seeds, rules, keep_outcomes))
    block = math.ceil(matches / (processes * 4))
    blocks = [seeds[i : i + block] for i in range(0, matches, block)]
    out = SimulationResult()
    charts: list[Chart] = [basic_chart(rules)]
    with get_context("spawn").Pool(processes, initializer=prime_charts, initargs=(charts,)) as pool:
        jobs = [(make_agent, make_opponent, b, rules, keep_outcomes) for b in blocks]
        for part in pool.map(_run_block, jobs):
            out.merge(part)
    return out
