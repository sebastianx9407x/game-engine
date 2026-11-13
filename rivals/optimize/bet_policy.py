"""Search for the bet schedule that wins the most matches.

The game is blind and both players get the same cards, so an opponent's
result on a given set of shoes does not depend on anything we do. That makes
the search cheap:

1. `build_scenarios` plays many matches' worth of shoes once. For each match
   it records what one unit bet would have won us in every round, what each
   side bet would have paid, and where sampled opponents finished.
2. `solve_bet_policy` works backwards from the last hand. For every
   situation (hand number, our balance, what the shared cards have done so
   far) it tries each bet on every recorded match in that situation, plays
   the rest of the match with the choices already made for later hands, and
   keeps the bet with the best average score.

The score is P(win) + tie value x P(tie), the project's objective.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from multiprocessing import get_context

import numpy as np

from rivals.agents.base import Agent
from rivals.match import AgentFactory, play_player
from rivals.resolve import play_round
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.shoe import match_shoes
from rivals.side_bets import four_card_total, four_card_total_payout, perfect_pairs_payout
from rivals.solver.basic import BasicStrategy, basic_chart, prime_charts

#: A main bet may be backed by up to this many times itself in spare chips
#: (split, then double both hands). Unit results are recorded for 1..MAX_COVER.
MAX_COVER = 4
CHIP = 5  # bets are built from chips, so they are multiples of 5


class BasicPlay:
    """Play style 0: the basic-strategy chart."""

    name = "basic"

    def policy(self, rules: RulesConfig):
        return BasicStrategy(rules)


@dataclass(frozen=True)
class Scenarios:
    """What happened on a set of recorded matches, independent of how we bet."""

    rules: RulesConfig
    seeds: np.ndarray
    #: units[style, match, round, cover-1]: our main-bet result per unit staked when
    #: we can afford ``cover`` times the bet in total (1 = no double or split).
    units: np.ndarray
    #: Side-bet payout odds per match and round; 0 means the bet lost.
    pairs: np.ndarray
    totals: np.ndarray
    #: Final balances of the sampled opponents, per match.
    opponents: np.ndarray
    style_names: tuple[str, ...] = ("basic",)

    @property
    def matches(self) -> int:
        return len(self.seeds)

    @property
    def rounds(self) -> int:
        return self.units.shape[2]

    def categories(self) -> np.ndarray:
        """Per match and round: 0 loss, 1 push, 2 win for a basic-strategy player."""
        return (np.sign(self.units[0, :, :, MAX_COVER - 1]) + 1).astype(np.int64)

    def subset(self, index: np.ndarray) -> Scenarios:
        return Scenarios(
            self.rules, self.seeds[index], self.units[:, index], self.pairs[index],
            self.totals[index], self.opponents[index], self.style_names,
        )


def _scenario_block(args):
    seeds, make_opponent, per_match, rules, styles = args
    policies = [style.policy(rules) for style in styles]
    n, rounds = len(seeds), rules.num_rounds
    units = np.zeros((len(styles), n, rounds, MAX_COVER))
    pairs = np.zeros((n, rounds))
    totals = np.zeros((n, rounds))
    opponents = np.zeros((n, per_match))
    bet = rules.min_bet
    for i, seed in enumerate(seeds):
        shoes = match_shoes(seed, rules)
        for r, shoe in enumerate(shoes):
            first, up, second, hole = (int(c) for c in shoe.cards[:4])
            pairs[i, r] = perfect_pairs_payout(first, second, rules)
            totals[i, r] = four_card_total_payout(four_card_total(first, second, up, hole), rules)
            for s, policy in enumerate(policies):
                for cover in range(1, MAX_COVER + 1):
                    result = play_round(shoe, policy, bet, balance=bet * cover, rules=rules)
                    units[s, i, r, cover - 1] = result.main_net / bet
        for k in range(per_match):
            opponent = make_opponent(random.Random(f"{seed}:make-opp:{k}"))
            played = play_player(opponent, shoes, random.Random(f"{seed}:opp:{k}"), rules)
            opponents[i, k] = played.final_balance
    return units, pairs, totals, opponents


def build_scenarios(
    make_opponent: AgentFactory,
    matches: int,
    *,
    seed: int = 0,
    opponents_per_match: int = 2,
    rules: RulesConfig = DEFAULT_RULES,
    processes: int = 1,
    styles: Sequence = (BasicPlay(),),
) -> Scenarios:
    """Record ``matches`` matches (seeds ``seed`` onwards) for the policy search."""
    seeds = np.arange(seed, seed + matches)
    if processes <= 1:
        parts = [_scenario_block((seeds.tolist(), make_opponent, opponents_per_match, rules, styles))]
    else:
        block = math.ceil(matches / (processes * 4))
        jobs = [
            (seeds[i : i + block].tolist(), make_opponent, opponents_per_match, rules, styles)
            for i in range(0, matches, block)
        ]
        charts = [basic_chart(rules)]
        with get_context("spawn").Pool(processes, initializer=prime_charts, initargs=(charts,)) as pool:
            parts = pool.map(_scenario_block, jobs)
    return Scenarios(
        rules,
        seeds,
        np.concatenate([p[0] for p in parts], axis=1),
        np.concatenate([p[1] for p in parts]),
        np.concatenate([p[2] for p in parts]),
        np.concatenate([p[3] for p in parts]),
        tuple(style.name for style in styles),
    )


# --- actions -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BetAction:
    """One way to bet a round. Amounts are chips; fractions are of the current balance."""

    #: Main bet as a fixed amount, or 0 to use `main_fraction`.
    main: float = 0
    main_fraction: float = 0
    #: Side stakes: a fixed amount plus a fraction of what is left after the main bet.
    pairs: float = 0
    total: float = 0
    pairs_rest: float = 0
    total_rest: float = 0
    #: Index of the play style to use for the round.
    style: int = 0
    label: str = ""

    def amounts(self, balance):
        """(main, pairs, total) stakes for a balance; works on numbers and arrays."""
        if self.main:
            main = self.main + 0 * balance
        else:
            main = np.floor(self.main_fraction * balance / CHIP) * CHIP
        rest = np.maximum(balance - main, 0)
        pairs = self.pairs + np.floor(self.pairs_rest * rest / CHIP) * CHIP
        total = self.total + np.floor(self.total_rest * rest / CHIP) * CHIP
        return main, pairs, total

    def valid(self, balance: float, rules: RulesConfig) -> bool:
        main, pairs, total = (float(x) for x in self.amounts(balance))
        if main < rules.min_bet or main + pairs + total > balance:
            return False
        return all(x == 0 or x >= rules.side_bet_min for x in (pairs, total))


def default_actions() -> list[BetAction]:
    """The search space: a ladder of main bets, plus side bets next to a minimum main bet."""
    actions = [BetAction(main=m, label=f"bet {m}") for m in (10, 25, 50, 100, 150, 200, 300, 400, 500, 750, 1000)]
    actions += [
        BetAction(main_fraction=0.5, label="bet half"),
        BetAction(main_fraction=1.0, label="all-in"),
    ]
    for stake in (50, 100, 200, 400):
        actions.append(BetAction(main=10, total=stake, label=f"bet 10 + {stake} on 4-card total"))
        actions.append(BetAction(main=10, pairs=stake, label=f"bet 10 + {stake} on pairs"))
    actions += [
        BetAction(main=10, total_rest=1.0, label="bet 10 + the rest on 4-card total"),
        BetAction(main=10, pairs_rest=1.0, label="bet 10 + the rest on pairs"),
        BetAction(main=10, total_rest=0.5, label="bet 10 + half the rest on 4-card total"),
        BetAction(main=10, pairs_rest=0.5, label="bet 10 + half the rest on pairs"),
    ]
    return actions


def default_grid() -> np.ndarray:
    """Balance levels the policy distinguishes; a balance uses the level at or below it."""
    levels = (
        list(range(10, 100, 10))
        + list(range(100, 2000, 50))
        + list(range(2000, 4000, 250))
        + [4000, 5000, 6000, 8000, 12000]
    )
    return np.array(levels, dtype=np.float64)


# --- shared-history keys -------------------------------------------------------------

HISTORY_MODES = ("pattern", "count", "none")


def history_keys(categories: np.ndarray, round_index: int, mode: str) -> np.ndarray:
    """Key for what the shared cards did in rounds before ``round_index``.

    ``categories`` is (matches, rounds) of 0 loss / 1 push / 2 win. "pattern"
    keeps the full sequence, "count" only how many wins and losses, "none"
    ignores history.
    """
    past = categories[:, :round_index]
    if mode == "none" or round_index == 0:
        return np.zeros(len(categories), dtype=np.int64)
    if mode == "pattern":
        return (past * 3 ** np.arange(round_index)).sum(axis=1)
    if mode == "count":
        wins, losses = (past == 2).sum(axis=1), (past == 0).sum(axis=1)
        return wins * (round_index + 1) + losses
    raise ValueError(f"unknown history mode {mode!r}")


def num_history_keys(round_index: int, mode: str) -> int:
    if mode == "none" or round_index == 0:
        return 1
    return 3**round_index if mode == "pattern" else (round_index + 1) ** 2


def describe_key(key: int, round_index: int, mode: str) -> str:
    if mode == "none" or round_index == 0:
        return "any"
    if mode == "pattern":
        return "".join("LPW"[(key // 3**r) % 3] for r in range(round_index))
    wins, losses = divmod(key, round_index + 1)
    return f"{wins}W {losses}L"


# --- the policy ----------------------------------------------------------------------


@dataclass
class BetPolicy:
    """Which `BetAction` to use in every situation."""

    rules: RulesConfig
    actions: list[BetAction]
    grid: np.ndarray
    history: str
    #: tables[round][history key, balance level] -> index into `actions`.
    tables: list[np.ndarray]
    #: Estimated score from each situation, same shape as `tables`.
    values: list[np.ndarray] = field(default_factory=list)
    style_names: tuple[str, ...] = ("basic",)
    #: Play chart for each style index; None means basic strategy.
    style_charts: tuple = (None,)

    def level(self, balance: float) -> int:
        return max(int(np.searchsorted(self.grid, balance, side="right")) - 1, 0)

    def action(self, round_index: int, key: int, balance: float) -> BetAction:
        return self.actions[int(self.tables[round_index][key, self.level(balance)])]

    @property
    def expected_score(self) -> float:
        """Estimated score at the start of a match, on the matches it was solved from."""
        start = self.level(self.rules.starting_chips)
        return float(self.values[0][0, start])


class _Arrays:
    """Action parameters as arrays, so a vector of action indices can be applied at once."""

    def __init__(self, actions: Sequence[BetAction]) -> None:
        get = lambda name: np.array([getattr(a, name) for a in actions], dtype=np.float64)
        self.main, self.main_fraction = get("main"), get("main_fraction")
        self.pairs, self.total = get("pairs"), get("total")
        self.pairs_rest, self.total_rest = get("pairs_rest"), get("total_rest")
        self.style = np.array([a.style for a in actions], dtype=np.int64)


def _play(sc: Scenarios, arr: _Arrays, rows: np.ndarray, r: int, balance: np.ndarray, act):
    """Bet action(s) ``act`` in round ``r`` on matches ``rows``.

    Returns the new balances and what the player saw happen to the main bet
    (0 loss, 1 push, 2 win), which is what later history keys are built from.
    """
    fixed = arr.main[act]
    fraction = arr.main_fraction[act]
    main = np.where(fixed > 0, fixed, np.floor(fraction * balance / CHIP) * CHIP)
    rest = np.maximum(balance - main, 0)
    pairs = arr.pairs[act] + np.floor(arr.pairs_rest[act] * rest / CHIP) * CHIP
    total = arr.total[act] + np.floor(arr.total_rest[act] * rest / CHIP) * CHIP
    cover = np.clip((balance - pairs - total) // np.maximum(main, 1), 1, MAX_COVER).astype(np.int64)
    unit = sc.units[arr.style[act], rows, r, cover - 1]
    pay_pairs, pay_total = sc.pairs[rows, r], sc.totals[rows, r]
    net = main * unit
    net = net + np.where(pay_pairs > 0, pairs * pay_pairs, -pairs)
    net = net + np.where(pay_total > 0, total * pay_total, -total)
    return balance + net, (np.sign(unit) + 1).astype(np.int64)


def _finish(
    sc: Scenarios, arr: _Arrays, policy: BetPolicy, seen: np.ndarray,
    rows: np.ndarray, start_round: int, balance: np.ndarray,
) -> np.ndarray:
    """Final balances after playing rounds ``start_round`` onwards with ``policy``.

    ``seen`` is (len(rows), rounds): the main-bet result the player observed
    in each earlier round. It is filled in as the rounds are played, so every
    later bet is keyed on what the player would really have seen, whatever
    play style and chip cover produced it.
    """
    min_bet = sc.rules.min_bet
    for r in range(start_round, sc.rounds):
        alive = balance >= min_bet
        level = np.maximum(np.searchsorted(policy.grid, balance, side="right") - 1, 0)
        act = policy.tables[r][history_keys(seen, r, policy.history), level]
        played, category = _play(sc, arr, rows, r, balance, act)
        seen[:, r] = category
        balance = np.where(alive, played, balance)
    return balance


def _score(final: np.ndarray, opponents: np.ndarray, tie_value: float) -> float:
    diff = final[:, None] - opponents
    return float((diff > 0).mean() + tie_value * (diff == 0).mean())


def solve_bet_policy(
    sc: Scenarios,
    *,
    actions: Sequence[BetAction] | None = None,
    grid: np.ndarray | None = None,
    history: str = "pattern",
    min_matches: int = 300,
) -> BetPolicy:
    """Best bet for every (hand, shared history, balance), by backward induction.

    A history seen in fewer than ``min_matches`` recorded matches falls back
    to the choice made without looking at history, to avoid fitting noise.
    """
    actions = list(actions) if actions is not None else default_actions()
    grid = default_grid() if grid is None else np.asarray(grid, dtype=np.float64)
    rules = sc.rules
    tie = rules.tie_value
    arr = _Arrays(actions)
    cats = sc.categories()
    rounds = sc.rounds
    keys = [history_keys(cats, r, history) for r in range(rounds)]
    policy = BetPolicy(
        rules, actions, grid, history,
        [np.zeros((num_history_keys(r, history), len(grid)), dtype=np.int64) for r in range(rounds)],
        [np.zeros((num_history_keys(r, history), len(grid))) for r in range(rounds)],
        sc.style_names,
    )
    valid = np.array([[a.valid(b, rules) for a in actions] for b in grid])
    everyone = np.arange(sc.matches)

    def best_for(rows: np.ndarray, r: int, level: int) -> tuple[int, float]:
        balance = np.full(len(rows), grid[level])
        opponents = sc.opponents[rows]
        best, best_value = 0, -1.0
        for a in np.flatnonzero(valid[level]):
            seen = cats[rows]
            after, seen[:, r] = _play(sc, arr, rows, r, balance, int(a))
            final = _finish(sc, arr, policy, seen, rows, r + 1, after)
            value = _score(final, opponents, tie)
            if value > best_value + 1e-12:
                best, best_value = int(a), value
        return best, best_value

    start_level = policy.level(rules.starting_chips)
    for r in range(rounds - 1, -1, -1):
        levels = [start_level] if r == 0 else range(len(grid))
        fallback: dict[int, tuple[int, float]] = {}

        def without_history(lvl: int) -> tuple[int, float]:
            if lvl not in fallback:
                fallback[lvl] = best_for(everyone, r, lvl)
            return fallback[lvl]

        for key in range(num_history_keys(r, history)):
            rows = np.flatnonzero(keys[r] == key)
            for lvl in levels:
                if len(rows) >= min_matches:
                    choice, value = best_for(rows, r, lvl)
                elif len(rows):
                    choice = without_history(lvl)[0]
                    balance = np.full(len(rows), grid[lvl])
                    seen = cats[rows]
                    after, seen[:, r] = _play(sc, arr, rows, r, balance, choice)
                    final = _finish(sc, arr, policy, seen, rows, r + 1, after)
                    value = _score(final, sc.opponents[rows], tie)
                else:
                    choice, value = without_history(lvl)
                policy.tables[r][key, lvl] = choice
                policy.values[r][key, lvl] = value
    return policy


def policy_finals(sc: Scenarios, policy: BetPolicy) -> np.ndarray:
    """Final balance on each recorded match when betting ``policy``.

    This replays exactly what `PolicyAgent` does in the real engine.
    """
    arr = _Arrays(policy.actions)
    seen = np.ones((sc.matches, sc.rounds), dtype=np.int64)
    start = np.full(sc.matches, sc.rules.starting_chips, dtype=np.float64)
    return _finish(sc, arr, policy, seen, np.arange(sc.matches), 0, start)


def policy_score(sc: Scenarios, policy: BetPolicy) -> float:
    """Score of ``policy`` on recorded matches (use ones it was not solved from)."""
    return _score(policy_finals(sc, policy), sc.opponents, sc.rules.tie_value)


def policy_trace(sc: Scenarios, policy: BetPolicy) -> list[dict[str, np.ndarray]]:
    """What the policy did on each recorded match, round by round.

    One dict per round with, per match: ``alive`` (still had the minimum
    bet), ``key`` (shared-history key), ``balance`` before betting, and the
    ``action`` index chosen.
    """
    arr = _Arrays(policy.actions)
    rows = np.arange(sc.matches)
    seen = np.ones((sc.matches, sc.rounds), dtype=np.int64)
    balance = np.full(sc.matches, sc.rules.starting_chips, dtype=np.float64)
    trace = []
    for r in range(sc.rounds):
        key = history_keys(seen, r, policy.history)
        alive = balance >= sc.rules.min_bet
        level = np.maximum(np.searchsorted(policy.grid, balance, side="right") - 1, 0)
        act = policy.tables[r][key, level]
        trace.append({"alive": alive, "key": key, "balance": balance.copy(), "action": act, "level": level})
        played, seen[:, r] = _play(sc, arr, rows, r, balance, act)
        balance = np.where(alive, played, balance)
    return trace
