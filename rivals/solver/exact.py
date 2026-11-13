"""Exact, composition-dependent values for every play decision.

For a player hand and a dealer upcard, `Solver.evaluate` gives each legal
action's expected value and its full distribution of net units (1 unit = the
starting bet). Suits do not matter here, so cards are reduced to ten values.

What is exact and what is not (see docs/DECISIONS.md):

* Stand, hit and double are exact for the shoe that is left after the cards
  on the table, including the effect of the dealer's blackjack check.
* A split is valued as two hands that each start from the pair card. The
  expected value ignores what one split hand learns from the other's cards,
  and the distribution of the two-hand total treats the hands as independent
  given the dealer's result. Both effects are tiny with several decks.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache, lru_cache

import numpy as np

from rivals.cards import VALUE, parse_card, parse_cards
from rivals.hand import Action
from rivals.rules import DEFAULT_RULES, RulesConfig

NUM_VALUES = 10
#: Value indices: 0 is an ace, 1..8 are two..nine, 9 is any ten-value card.
ACE, TEN = 0, 9
#: Points per value index with the ace counted as 1.
POINTS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
VALUE_NAMES = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "T")

Counts = tuple[int, ...]

# Dealer results: totals 17..21 are 0..4, then bust and blackjack.
D_BUST, D_BLACKJACK = 5, 6
NUM_DEALER_RESULTS = 7

# Where a finished player hand stands: bust, 16 or less, then 17..21.
F_BUST, F_STIFF = 0, 1
NUM_FINALS = 7


def value_index(card: int) -> int:
    """Value index (0..9) of an engine card id (0..51)."""
    value = VALUE[card]
    return ACE if value == 11 else value - 1


def counts_of(values: Iterable[int]) -> Counts:
    counts = [0] * NUM_VALUES
    for v in values:
        counts[v] += 1
    return tuple(counts)


def total_of(hand: Counts) -> tuple[int, bool]:
    """Best total and whether it is soft."""
    hard = 0
    for k, points in zip(hand, POINTS):
        hard += k * points
    if hand[ACE] and hard + 10 <= 21:
        return hard + 10, True
    return hard, False


def _add(hand: Counts, v: int) -> Counts:
    return hand[:v] + (hand[v] + 1,) + hand[v + 1 :]


def _final_of(total: int) -> int:
    if total > 21:
        return F_BUST
    return F_STIFF if total < 17 else total - 15


@lru_cache(maxsize=None)
def _dealer_table(upcard: int, hits_soft_17: bool, forbidden_hole: int | None):
    """Every way the dealer's hand can finish from ``upcard``.

    Returns arrays over the distinct sets of drawn cards (hole card included):
    how many of each value, how many draw orders lead there, the result, and
    the number of cards drawn. ``forbidden_hole`` is the hole-card value ruled
    out by the dealer's blackjack check, if there was one.
    """
    tally: dict[tuple[Counts, int], int] = {}
    drawn = [0] * NUM_VALUES

    def walk(hard: int, has_ace: bool, n: int) -> None:
        if n >= 1:
            total = hard + 10 if has_ace and hard + 10 <= 21 else hard
            soft = total != hard
            if n == 1 and total == 21:
                result = D_BLACKJACK
            elif total > 21:
                result = D_BUST
            elif total > 17 or (total == 17 and not (soft and hits_soft_17)):
                result = total - 17
            else:
                result = -1
            if result >= 0:
                key = (tuple(drawn), result)
                tally[key] = tally.get(key, 0) + 1
                return
        for v in range(NUM_VALUES):
            if n == 0 and v == forbidden_hole:
                continue
            drawn[v] += 1
            walk(hard + POINTS[v], has_ace or v == ACE, n + 1)
            drawn[v] -= 1

    walk(POINTS[upcard], upcard == ACE, 0)
    keys = list(tally)
    drawn_counts = np.array([k[0] for k in keys], dtype=np.int64)
    orders = np.array([tally[k] for k in keys], dtype=np.float64)
    results = np.array([k[1] for k in keys], dtype=np.int64)
    lengths = drawn_counts.sum(axis=1)

    # The chance of one set of drawn cards is
    #   orders * prod_v falling(n_v, k_v) / falling(size, length),
    # where falling(n, k) = n (n-1) ... (k factors). In logs that is a dot
    # product with a one-hot row, so all sets are done in one matrix product.
    rows = len(keys)
    depth = int(drawn_counts.max()) + 1
    longest = int(lengths.max())
    selector = np.zeros((rows, NUM_VALUES * depth + longest + 1))
    for v in range(NUM_VALUES):
        selector[np.arange(rows), v * depth + drawn_counts[:, v]] = 1.0
    selector[np.arange(rows), NUM_VALUES * depth + lengths] = -1.0
    by_result = np.zeros((NUM_DEALER_RESULTS, rows))
    by_result[results, np.arange(rows)] = orders
    return selector, by_result, depth, longest


_IMPOSSIBLE = -1e4  # log of a zero count; exp() of it underflows to exactly 0


def _dealer_probs(shoe: Counts, table, forbidden_hole: int | None) -> tuple[float, ...]:
    """Chance of each dealer result when the unseen cards are ``shoe``."""
    selector, by_result, depth, longest = table
    n = np.array(shoe, dtype=np.float64)
    size = n.sum()
    logs = np.empty(NUM_VALUES * depth + longest + 1)
    steps = n[:, None] - np.arange(depth - 1)[None, :]
    falling = logs[: NUM_VALUES * depth].reshape(NUM_VALUES, depth)
    falling[:, 0] = 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        np.cumsum(np.where(steps > 0, np.log(steps), _IMPOSSIBLE), axis=1, out=falling[:, 1:])
    denominators = logs[NUM_VALUES * depth :]
    denominators[0] = 0.0
    np.cumsum(np.log(size - np.arange(longest)), out=denominators[1:])
    probs = by_result @ np.exp(selector @ logs)
    if forbidden_hole is not None:
        probs = probs / (1.0 - shoe[forbidden_hole] / size)
    return tuple(probs.tolist())


@dataclass(frozen=True, slots=True)
class StrategyView:
    """What a fixed strategy is shown when the solver asks it for a decision."""

    total: int
    soft: bool
    #: Value index of the pair when the hand is two equal-value cards, else None.
    pair: int | None
    #: Dealer upcard as a value index.
    upcard: int
    num_cards: int
    from_split: bool
    legal: tuple[Action, ...]


Strategy = Callable[[StrategyView], Action]


@dataclass(frozen=True, slots=True)
class ActionValue:
    #: Expected net units.
    ev: float
    #: Net units -> probability.
    dist: dict[float, float]

    @property
    def std(self) -> float:
        """Standard deviation of net units, from `dist`."""
        mean = sum(x * p for x, p in self.dist.items())
        return sum((x - mean) ** 2 * p for x, p in self.dist.items()) ** 0.5


@dataclass(frozen=True, slots=True)
class HandEval:
    """Values of each legal action for one decision.

    Everything is conditional on the player getting to act: with a checked
    ace showing, the dealer is known not to have blackjack.
    """

    hand: Counts
    upcard: int
    total: int
    soft: bool
    actions: dict[Action, ActionValue]
    #: The highest-EV action, or the fixed strategy's choice if one was given.
    best: Action

    @property
    def ev(self) -> float:
        return self.actions[self.best].ev


@dataclass(frozen=True, slots=True)
class RoundValue:
    """A whole round from before the deal, per unit bet, with no side bets or insurance."""

    ev: float
    dist: dict[float, float]

    @property
    def house_edge(self) -> float:
        return -self.ev

    @property
    def std(self) -> float:
        mean = sum(x * p for x, p in self.dist.items())
        return sum((x - mean) ** 2 * p for x, p in self.dist.items()) ** 0.5


# A solved state: (ev, win, push, lose, finals). The first four are per unit
# staked. ``finals`` is the chance of each finishing position (see F_*), kept
# only for split hands, where it feeds the two-hand distribution.
_Value = tuple[float, float, float, float, tuple[float, ...] | None]

_LOSS: _Value = (-1.0, 0.0, 0.0, 1.0, None)
_ONE_HOT = tuple(tuple(1.0 if i == j else 0.0 for i in range(NUM_FINALS)) for j in range(NUM_FINALS))


def _mix(parts: list[tuple[float, _Value]], track_finals: bool) -> _Value:
    ev = win = push = lose = 0.0
    finals = [0.0] * NUM_FINALS if track_finals else None
    for p, (e, w, d, l, f) in parts:
        ev += p * e
        win += p * w
        push += p * d
        lose += p * l
        if finals is not None:
            for i in range(NUM_FINALS):
                finals[i] += p * f[i]
    return ev, win, push, lose, (tuple(finals) if finals is not None else None)


class _Context:
    """All hands against one upcard, either unsplit or as one hand of a split pair."""

    def __init__(self, solver: Solver, upcard: int, split_pair: int | None) -> None:
        rules = solver.rules
        self.solver = solver
        self.rules = rules
        self.upcard = upcard
        self.split_pair = split_pair
        self.is_split = split_pair is not None
        base = list(solver.full)
        base[upcard] -= 1
        if split_pair is not None:
            base[split_pair] -= 1  # the other hand's pair card
        self.base: Counts = tuple(base)
        if upcard == ACE and rules.dealer_peeks_on_ace:
            self.forbidden: int | None = TEN
        elif upcard == TEN and rules.dealer_peeks_on_ten:
            self.forbidden = ACE
        else:
            self.forbidden = None
        self.table = _dealer_table(upcard, rules.dealer_hits_soft_17, self.forbidden)
        self._stand: dict[Counts, _Value] = {}
        self._play: dict[Counts, _Value] = {}
        self._draws: dict[Counts, list[tuple[int, float]]] = {}

    # --- the shoe ---------------------------------------------------------

    def shoe(self, hand: Counts) -> Counts:
        return tuple(b - h for b, h in zip(self.base, hand))

    def possible(self, hand: Counts) -> bool:
        return min(self.shoe(hand)) >= 0

    def dealer_probs(self, hand: Counts) -> tuple[float, ...]:
        return _dealer_probs(self.shoe(hand), self.table, self.forbidden)

    def draws(self, hand: Counts) -> list[tuple[int, float]]:
        """(value, probability) of the player's next card."""
        cached = self._draws.get(hand)
        if cached is not None:
            return cached
        shoe = self.shoe(hand)
        size = sum(shoe)
        f = self.forbidden
        if f is None:
            weights = list(shoe)
        else:
            # The hole card is one of the unseen cards and is known not to be
            # value f, which makes f slightly likelier for everyone else.
            other = size - 1 - shoe[f]
            weights = [n * (other + (1 if v == f else 0)) for v, n in enumerate(shoe)]
        norm = sum(weights)
        out = [(v, w / norm) for v, w in enumerate(weights) if w > 0]
        self._draws[hand] = out
        return out

    # --- values -----------------------------------------------------------

    def stand(self, hand: Counts) -> _Value:
        cached = self._stand.get(hand)
        if cached is not None:
            return cached
        total = total_of(hand)[0]
        probs = self.dealer_probs(hand)
        if total < 17:
            win, push = probs[D_BUST], 0.0
        else:
            win = probs[D_BUST] + sum(probs[: total - 17])
            push = probs[total - 17]
        lose = 1.0 - win - push
        finals = _ONE_HOT[_final_of(total)] if self.is_split else None
        value = (win - lose, win, push, lose, finals)
        self._stand[hand] = value
        return value

    def _after_draw(self, hand: Counts, stand_only: bool) -> _Value:
        parts = []
        for v, p in self.draws(hand):
            nxt = _add(hand, v)
            if total_of(nxt)[0] > 21:
                value = (-1.0, 0.0, 0.0, 1.0, _ONE_HOT[F_BUST]) if self.is_split else _LOSS
            else:
                value = self.stand(nxt) if stand_only else self.play(nxt)
            parts.append((p, value))
        return _mix(parts, self.is_split)

    def hit(self, hand: Counts) -> _Value:
        return self._after_draw(hand, stand_only=False)

    def double(self, hand: Counts) -> _Value:
        """Per unit staked; the caller doubles the stake."""
        return self._after_draw(hand, stand_only=True)

    def play(self, hand: Counts) -> _Value:
        """Best of hit and stand from here on (no double or split)."""
        cached = self._play.get(hand)
        if cached is not None:
            return cached
        total, soft = total_of(hand)
        stand = self.stand(hand)
        if total == 21:
            value = stand
        else:
            hit = self.hit(hand)
            strategy = self.solver.strategy
            if strategy is None:
                value = hit if hit[0] > stand[0] else stand
            else:
                view = StrategyView(
                    total, soft, None, self.upcard, sum(hand), self.is_split,
                    (Action.STAND, Action.HIT),
                )
                value = hit if self.solver._ask(view) == Action.HIT else stand
        self._play[hand] = value
        return value

    def can_double(self, hand: Counts) -> bool:
        if sum(hand) != 2:
            return False
        if self.is_split and not self.rules.double_after_split:
            return False
        allowed = self.rules.double_totals
        if allowed is None:
            return True
        low = sum(k * points for k, points in zip(hand, POINTS))
        return total_of(hand)[0] in allowed or low in allowed

    def first_options(self, hand: Counts) -> dict[Action, _Value]:
        """Stand, hit and double (if allowed) for a hand's first decision, per unit staked."""
        options = {Action.STAND: self.stand(hand), Action.HIT: self.hit(hand)}
        if self.can_double(hand):
            options[Action.DOUBLE] = self.double(hand)
        return options


def _unit_ev(action: Action, value: _Value) -> float:
    return 2 * value[0] if action == Action.DOUBLE else value[0]


class Solver:
    """Exact decision values under one rule set.

    With ``strategy=None`` every decision is the highest-EV one. With a
    strategy, decisions follow it instead, so the same machinery gives the
    exact value of any fixed way of playing (a basic-strategy chart, a
    mistake-prone human).
    """

    def __init__(self, rules: RulesConfig = DEFAULT_RULES, strategy: Strategy | None = None) -> None:
        if rules.surrender or rules.split_21_is_blackjack or rules.max_splits > 1:
            raise NotImplementedError(
                "the solver does not model surrender, blackjack after a split, or resplitting"
            )
        self.rules = rules
        self.strategy = strategy
        per_value = 4 * rules.num_decks
        self.full: Counts = (per_value,) * 9 + (4 * per_value,)
        self._contexts: dict[tuple[int, int | None], _Context] = {}
        self._split_cache: dict[tuple[int, int], tuple[float, dict[float, float]]] = {}
        self._round: RoundValue | None = None

    # --- plumbing ---------------------------------------------------------

    def _context(self, upcard: int, split_pair: int | None = None) -> _Context:
        key = (upcard, split_pair)
        ctx = self._contexts.get(key)
        if ctx is None:
            ctx = self._contexts[key] = _Context(self, upcard, split_pair)
        return ctx

    def _ask(self, view: StrategyView) -> Action:
        action = self.strategy(view)
        if action not in view.legal:
            raise ValueError(f"strategy chose {action!r}, which is not legal in {view}")
        return action

    def _choose(self, ctx: _Context, hand: Counts, evs: dict[Action, float]) -> Action:
        if self.strategy is None:
            return max(evs, key=evs.get)
        total, soft = total_of(hand)
        values = [v for v, k in enumerate(hand) if k]
        pair = values[0] if sum(hand) == 2 and len(values) == 1 else None
        view = StrategyView(total, soft, pair, ctx.upcard, sum(hand), ctx.is_split, tuple(evs))
        return self._ask(view)

    # --- splits -----------------------------------------------------------

    def _split(self, pair: int, upcard: int) -> tuple[float, dict[float, float]]:
        """EV and net distribution (both hands together) of splitting a pair."""
        key = (pair, upcard)
        cached = self._split_cache.get(key)
        if cached is not None:
            return cached
        ctx = self._context(upcard, pair)
        start = counts_of([pair])
        one_card_only = pair == ACE and not self.rules.hit_split_aces
        ev = 0.0
        # Chance of each finishing position, at single and at doubled stakes.
        finals = [[0.0] * NUM_FINALS, [0.0] * NUM_FINALS]
        for v, p in ctx.draws(start):
            hand = _add(start, v)
            if one_card_only or total_of(hand)[0] == 21:
                action, value = Action.STAND, ctx.stand(hand)
            else:
                options = ctx.first_options(hand)
                action = self._choose(ctx, hand, {a: _unit_ev(a, x) for a, x in options.items()})
                value = options[action]
            stake = 1 if action == Action.DOUBLE else 0
            ev += p * _unit_ev(action, value)
            for i in range(NUM_FINALS):
                finals[stake][i] += p * value[4][i]

        dealer = ctx.dealer_probs(start)
        dist = [0.0] * 9  # nets -4..4
        for result, p_dealer in enumerate(dealer):
            if p_dealer <= 0:
                continue
            one = [0.0] * 5  # nets -2..2 for one hand
            for stake_index, stake in ((0, 1), (1, 2)):
                for final, p in enumerate(finals[stake_index]):
                    if p <= 0:
                        continue
                    if final == F_BUST or result == D_BLACKJACK:
                        net = -stake
                    elif result == D_BUST:
                        net = stake
                    else:
                        player = final - 2  # stiff is below every dealer total
                        net = stake if player > result else (0 if player == result else -stake)
                    one[net + 2] += p
            for i, a in enumerate(one):
                if a:
                    for j, b in enumerate(one):
                        dist[i + j] += p_dealer * a * b
        out = (2 * ev, {float(net - 4): p for net, p in enumerate(dist) if p > 0})
        self._split_cache[key] = out
        return out

    # --- public API -------------------------------------------------------

    def evaluate_counts(self, hand: Counts, upcard: int, *, after_split: bool = False) -> HandEval:
        """`evaluate` for a hand given as value counts and an upcard value index."""
        num_cards = sum(hand)
        if num_cards < 2:
            raise ValueError("a decision needs at least two cards")
        total, soft = total_of(hand)
        if total >= 21:
            raise ValueError("no decision to make on 21 or a bust")
        values = [v for v, k in enumerate(hand) if k]
        if after_split:
            if num_cards == 2 and len(values) == 1:
                ctx = self._context(upcard, values[0])
            else:
                raise ValueError("after_split needs the split hand's pair card; use evaluate()")
        else:
            ctx = self._context(upcard)
        return self._evaluate(ctx, hand)

    def _evaluate(self, ctx: _Context, hand: Counts) -> HandEval:
        if not ctx.possible(hand):
            raise ValueError("those cards are not all in the shoe")
        total, soft = total_of(hand)
        num_cards = sum(hand)
        actions: dict[Action, ActionValue] = {}

        def add(action: Action, value: _Value, stake: int) -> None:
            _, win, push, lose, _ = value
            dist = {float(stake): win, 0.0: push, float(-stake): lose}
            actions[action] = ActionValue(stake * value[0], {x: p for x, p in dist.items() if p > 0})

        if num_cards == 2:
            if ctx.split_pair == ACE and not self.rules.hit_split_aces:
                raise ValueError("split aces get one card each and cannot act")
            for action, value in ctx.first_options(hand).items():
                add(action, value, 2 if action == Action.DOUBLE else 1)
            values = [v for v, k in enumerate(hand) if k]
            if not ctx.is_split and len(values) == 1 and self.rules.max_splits >= 1:
                ev, dist = self._split(values[0], ctx.upcard)
                actions[Action.SPLIT] = ActionValue(ev, dist)
        else:
            add(Action.STAND, ctx.stand(hand), 1)
            add(Action.HIT, ctx.hit(hand), 1)
        best = self._choose(ctx, hand, {a: v.ev for a, v in actions.items()})
        return HandEval(hand, ctx.upcard, total, soft, actions, best)

    def evaluate(
        self,
        cards: str | Iterable[int | str],
        upcard: int | str,
        *,
        after_split: bool = False,
    ) -> HandEval:
        """Value of every legal action for these player cards against ``upcard``.

        Cards are engine card ids or text such as ``"8s 8h"``. With
        ``after_split=True`` the cards are one hand of a split pair, first
        card first, and the other hand's pair card is taken out of the shoe.
        """
        values = [value_index(c) for c in parse_cards(cards)]
        up = value_index(parse_card(upcard) if isinstance(upcard, str) else upcard)
        hand = counts_of(values)
        if after_split:
            return self._evaluate(self._context(up, values[0]), hand)
        return self.evaluate_counts(hand, up)

    def dealer_probs(self, cards: str | Iterable[int | str], upcard: int | str) -> dict[str, float]:
        """Dealer's finishing chances given the player's cards, after any blackjack check."""
        up = value_index(parse_card(upcard) if isinstance(upcard, str) else upcard)
        hand = counts_of(value_index(c) for c in parse_cards(cards))
        probs = self._context(up).dealer_probs(hand)
        names = ("17", "18", "19", "20", "21", "bust", "blackjack")
        return dict(zip(names, probs))

    def insurance_ev(self, cards: str | Iterable[int | str]) -> float:
        """EV of insurance per unit of the main bet, knowing the player's cards and the ace up."""
        hand = counts_of(value_index(c) for c in parse_cards(cards))
        shoe = [n - k for n, k in zip(self.full, hand)]
        shoe[ACE] -= 1
        p_ten = shoe[TEN] / sum(shoe)
        return 0.5 * (self.rules.insurance_payout * p_ten - (1 - p_ten))

    def round_value(self) -> RoundValue:
        """Value of a round from before the deal, per unit bet."""
        if self._round is not None:
            return self._round
        rules = self.rules
        full = self.full
        size = sum(full)
        ev = 0.0
        dist: dict[float, float] = {}

        def spread(p: float, part: dict[float, float]) -> None:
            for net, q in part.items():
                dist[net] = dist.get(net, 0.0) + p * q

        for a in range(NUM_VALUES):
            for b in range(a, NUM_VALUES):
                p_hand = full[a] * (full[b] - (a == b)) / (size * (size - 1)) * (1 if a == b else 2)
                if p_hand <= 0:
                    continue
                hand = counts_of([a, b])
                for up in range(NUM_VALUES):
                    left = full[up] - hand[up]
                    if left <= 0:
                        continue
                    p = p_hand * left / (size - 2)
                    ctx = self._context(up)
                    shoe = ctx.shoe(hand)
                    unseen = size - 3
                    # Dealer blackjack that is found before the player acts.
                    p_checked = shoe[ctx.forbidden] / unseen if ctx.forbidden is not None else 0.0
                    if a == ACE and b == TEN:
                        if up == ACE:
                            p_dealer_bj = shoe[TEN] / unseen
                        elif up == TEN:
                            p_dealer_bj = shoe[ACE] / unseen
                        else:
                            p_dealer_bj = 0.0
                        ev += p * (1 - p_dealer_bj) * rules.blackjack_payout
                        spread(p * (1 - p_dealer_bj), {float(rules.blackjack_payout): 1.0})
                        spread(p * p_dealer_bj, {0.0: 1.0})
                        continue
                    result = self._evaluate(ctx, hand)
                    best = result.actions[result.best]
                    ev += p * (-p_checked + (1 - p_checked) * best.ev)
                    spread(p * p_checked, {-1.0: 1.0})
                    spread(p * (1 - p_checked), best.dist)
        self._round = RoundValue(ev, dict(sorted(dist.items())))
        return self._round


@cache
def solver_for(rules: RulesConfig = DEFAULT_RULES) -> Solver:
    """A shared optimal-play solver for ``rules``; its results are cached across callers."""
    return Solver(rules)
