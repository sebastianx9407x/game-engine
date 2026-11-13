"""Play one round against a shoe and settle it.

`play_round` is the reference implementation of the 21 Rivals round: it is
written for clarity, and any faster kernel added later must reproduce its
results exactly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from rivals.cards import VALUE
from rivals.hand import Action, Hand, hand_value, insurance_available, is_natural, legal_actions
from rivals.rules import DEFAULT_RULES, RulesConfig
from rivals.shoe import Shoe, ShoeCursor
from rivals.side_bets import NO_SIDE_BETS, SideBets, settle_side_bets


class InvalidBetError(ValueError):
    """A wager breaks the table limits or exceeds the balance."""


class IllegalActionError(ValueError):
    """A policy chose an action that is not legal in the current state."""


class Outcome(Enum):
    BLACKJACK = "blackjack"
    WIN = "win"
    PUSH = "push"
    LOSE = "lose"
    BUST = "bust"
    SURRENDER = "surrender"


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """What a policy sees when asked to decide. Treat everything as read-only."""

    hand: Hand
    upcard: int
    #: Legal actions for `hand`. Empty when the question is insurance.
    legal: tuple[Action, ...]
    #: Position of `hand` among the player's hands this round.
    hand_index: int
    #: All of the player's hands this round (more than one after a split).
    hands: tuple[Hand, ...]
    #: Chips not yet wagered, available for doubles, splits and insurance.
    bankroll: float
    rules: RulesConfig


class Policy(Protocol):
    """Play decisions for one round."""

    def act(self, ctx: DecisionContext) -> Action: ...

    def take_insurance(self, ctx: DecisionContext) -> bool: ...


class ScriptedPolicy:
    """Plays a fixed list of actions in order, then stands. For tests and replays."""

    def __init__(self, actions: Iterable[Action] = (), *, insurance: bool = False) -> None:
        self._actions = list(actions)
        self._next = 0
        self._insurance = insurance

    def act(self, ctx: DecisionContext) -> Action:
        if self._next >= len(self._actions):
            return Action.STAND
        action = self._actions[self._next]
        self._next += 1
        return action

    def take_insurance(self, ctx: DecisionContext) -> bool:
        return self._insurance


@dataclass(frozen=True, slots=True)
class HandResult:
    cards: tuple[int, ...]
    #: Final wager on this hand (twice the starting bet if doubled).
    bet: float
    total: int
    outcome: Outcome
    net: float
    doubled: bool
    from_split: bool


@dataclass(frozen=True, slots=True)
class RoundResult:
    hands: tuple[HandResult, ...]
    #: Upcard, hole card, then any draws. The dealer only draws when the
    #: player still has a hand that can win.
    dealer_cards: tuple[int, ...]
    dealer_total: int
    dealer_blackjack: bool
    player_blackjack: bool
    #: (hand index, action) for every decision the policy made.
    actions: tuple[tuple[int, Action], ...]
    main_net: float
    insurance_bet: float
    insurance_net: float
    perfect_pairs_net: float
    four_card_total_net: float

    @property
    def side_net(self) -> float:
        return self.perfect_pairs_net + self.four_card_total_net

    @property
    def net(self) -> float:
        """Change in the player's balance from this round."""
        return self.main_net + self.insurance_net + self.side_net

    @property
    def upcard(self) -> int:
        return self.dealer_cards[0]

    @property
    def dealer_bust(self) -> bool:
        return self.dealer_total > 21


def validate_wagers(
    bet: float,
    side_bets: SideBets,
    balance: float | None,
    rules: RulesConfig,
) -> None:
    """Raise `InvalidBetError` unless the wagers are allowed. ``balance=None`` skips balance checks."""
    short_all_in = (
        rules.allow_short_all_in and balance is not None and 0 < bet == balance < rules.min_bet
    )
    if bet < rules.min_bet and not short_all_in:
        raise InvalidBetError(f"bet {bet} is below the minimum of {rules.min_bet}")
    if rules.max_bet is not None and bet > rules.max_bet:
        raise InvalidBetError(f"bet {bet} is above the maximum of {rules.max_bet}")
    for name, stake in (
        ("perfect pairs", side_bets.perfect_pairs),
        ("4-card total", side_bets.four_card_total),
    ):
        if stake == 0:
            continue
        if stake < rules.side_bet_min:
            raise InvalidBetError(f"{name} bet {stake} is below the minimum of {rules.side_bet_min}")
        if rules.side_bet_max is not None and stake > rules.side_bet_max:
            raise InvalidBetError(f"{name} bet {stake} is above the maximum of {rules.side_bet_max}")
    if balance is not None and bet + side_bets.total > balance:
        raise InvalidBetError(
            f"wagers of {bet + side_bets.total} exceed the balance of {balance}"
        )


def dealer_should_hit(total: int, soft: bool, rules: RulesConfig) -> bool:
    return total < 17 or (total == 17 and soft and rules.dealer_hits_soft_17)


def play_dealer(cursor: ShoeCursor, upcard: int, hole: int, rules: RulesConfig) -> list[int]:
    """Draw the dealer's hand out to completion."""
    cards = [upcard, hole]
    while dealer_should_hit(*hand_value(cards), rules):
        cards.append(cursor.next_dealer())
    return cards


def play_round(
    shoe: Shoe,
    policy: Policy,
    bet: float,
    side_bets: SideBets = NO_SIDE_BETS,
    *,
    balance: float | None = None,
    rules: RulesConfig = DEFAULT_RULES,
) -> RoundResult:
    """Play one round from the top of ``shoe`` and return what happened.

    ``balance`` is the player's chips before betting. It caps the wagers and
    decides whether doubles, splits and insurance are affordable; ``None``
    means an unlimited bankroll.
    """
    validate_wagers(bet, side_bets, balance, rules)
    bankroll = (float("inf") if balance is None else balance) - bet - side_bets.total

    cursor = shoe.cursor(rules.dealer_cards_independent)
    first, upcard, second, hole = cursor.next(), cursor.next(), cursor.next(), cursor.next()
    start = Hand([first, second], bet)
    hands = [start]
    actions: list[tuple[int, Action]] = []

    pairs_net, total_net = settle_side_bets(side_bets, first, second, upcard, hole, rules)
    dealer_blackjack = is_natural(upcard, hole)
    player_blackjack = start.total == 21

    insurance_bet = 0.0
    if insurance_available(upcard, bet, bankroll, rules):
        ctx = DecisionContext(start, upcard, (), 0, (start,), bankroll, rules)
        if policy.take_insurance(ctx):
            insurance_bet = bet / 2
            bankroll -= insurance_bet
    if dealer_blackjack:
        insurance_net = insurance_bet * rules.insurance_payout
    else:
        insurance_net = -insurance_bet

    dealer_cards = [upcard, hole]
    round_over = player_blackjack or (dealer_blackjack and rules.dealer_peeks)

    if not round_over:
        bankroll = _play_player_hands(hands, upcard, cursor, policy, bankroll, rules, actions)
        can_still_win = any(not h.is_bust and not h.surrendered for h in hands)
        if can_still_win and not dealer_blackjack:
            dealer_cards = play_dealer(cursor, upcard, hole, rules)

    dealer_total = hand_value(dealer_cards)[0]
    results = tuple(_settle_hand(h, dealer_total, dealer_blackjack, rules) for h in hands)

    return RoundResult(
        hands=results,
        dealer_cards=tuple(dealer_cards),
        dealer_total=dealer_total,
        dealer_blackjack=dealer_blackjack,
        player_blackjack=player_blackjack,
        actions=tuple(actions),
        main_net=sum(r.net for r in results),
        insurance_bet=insurance_bet,
        insurance_net=insurance_net,
        perfect_pairs_net=pairs_net,
        four_card_total_net=total_net,
    )


def _play_player_hands(
    hands: list[Hand],
    upcard: int,
    cursor: ShoeCursor,
    policy: Policy,
    bankroll: float,
    rules: RulesConfig,
    actions: list[tuple[int, Action]],
) -> float:
    """Play every player hand left to right, in place. Returns the remaining bankroll."""
    index = 0
    while index < len(hands):
        hand = hands[index]
        if len(hand.cards) == 1:  # split hand still waiting for its second card
            hand.cards.append(cursor.next())
        while not hand.done:
            legal = legal_actions(hand, rules, num_hands=len(hands), bankroll=bankroll)
            if not legal:  # 21, bust, or split aces that may not be hit
                hand.done = True
                break
            ctx = DecisionContext(hand, upcard, legal, index, tuple(hands), bankroll, rules)
            action = policy.act(ctx)
            if action not in legal:
                raise IllegalActionError(f"{action!r} is not legal for {hand!r}; legal: {legal}")
            actions.append((index, Action(action)))

            if action == Action.STAND:
                hand.done = True
            elif action == Action.HIT:
                hand.cards.append(cursor.next())
            elif action == Action.DOUBLE:
                bankroll -= hand.bet
                hand.bet *= 2
                hand.doubled = True
                hand.cards.append(cursor.next())
                hand.done = True
            elif action == Action.SURRENDER:
                hand.surrendered = True
                hand.done = True
            else:  # SPLIT
                bankroll -= hand.bet
                left = Hand([hand.cards[0]], hand.bet, from_split=True)
                right = Hand([hand.cards[1]], hand.bet, from_split=True)
                hands[index : index + 1] = [left, right]
                left.cards.append(cursor.next())
                if rules.split_deal_both_first:
                    right.cards.append(cursor.next())
                hand = left
        index += 1
    return bankroll


def _settle_hand(
    hand: Hand,
    dealer_total: int,
    dealer_blackjack: bool,
    rules: RulesConfig,
) -> HandResult:
    total = hand.total
    blackjack = hand.is_blackjack(rules)
    if hand.surrendered:
        outcome, net = Outcome.SURRENDER, -hand.bet / 2
    elif total > 21:
        outcome, net = Outcome.BUST, -hand.bet
    elif dealer_blackjack:
        # Reached with a peek only when the player never acted, and without a
        # peek after they did; either way only a player blackjack survives.
        outcome, net = (Outcome.PUSH, 0.0) if blackjack else (Outcome.LOSE, -hand.bet)
    elif blackjack:
        outcome, net = Outcome.BLACKJACK, hand.bet * rules.blackjack_payout
    elif dealer_total > 21 or total > dealer_total:
        outcome, net = Outcome.WIN, hand.bet
    elif total == dealer_total:
        outcome, net = Outcome.PUSH, 0.0
    else:
        outcome, net = Outcome.LOSE, -hand.bet
    return HandResult(
        cards=tuple(hand.cards),
        bet=hand.bet,
        total=total,
        outcome=outcome,
        net=net,
        doubled=hand.doubled,
        from_split=hand.from_split,
    )
