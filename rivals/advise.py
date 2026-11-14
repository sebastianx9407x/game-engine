"""What to do right now, given what is on the table.

This is the strategy card as a lookup: describe the situation and get the
bet for the round or the play for the hand. It is the decision half of any
tool that reads the game screen; the screen reading itself lives elsewhere.

    python -m rivals.advise bet --balance 850 --history L
    python -m rivals.advise play --cards "6s 5d" --up Tc --style seek
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from rivals.cards import parse_card, parse_cards
from rivals.hand import Action, Hand, legal_actions
from rivals.optimize.bet_policy import BetPolicy
from rivals.rules import RulesConfig
from rivals.solver.basic import basic_chart
from rivals.solver.exact import value_index

_RESULTS = {"L": 0, "P": 1, "W": 2}


@dataclass(frozen=True)
class BetAdvice:
    main: float
    perfect_pairs: float
    four_card_total: float
    #: How to play the hand that follows: "basic", "seek" or "avoid".
    style: str
    label: str

    def __str__(self) -> str:
        parts = [f"bet {self.main:g}"]
        if self.perfect_pairs:
            parts.append(f"{self.perfect_pairs:g} on Perfect Pairs")
        if self.four_card_total:
            parts.append(f"{self.four_card_total:g} on 4-Card Total")
        text = " + ".join(parts)
        return text if self.style == "basic" else f"{text}, then play the {self.style} chart"


def history_key(policy: BetPolicy, results: str) -> int:
    """The policy's history key for main-bet results so far, e.g. ``"WLP"``."""
    cats = [_RESULTS[c] for c in results.upper()]
    r = len(cats)
    if policy.history == "none" or r == 0:
        return 0
    if policy.history == "pattern":
        return sum(c * 3**i for i, c in enumerate(cats))
    return cats.count(2) * (r + 1) + cats.count(0)


def advise_bet(policy: BetPolicy, balance: float, results: str = "") -> BetAdvice:
    """The bet for the next hand.

    ``results`` is one letter per hand already played: W, L or P for how the
    main bet ended (ignore side bets). ``balance`` is the chips held now.
    """
    rules = policy.rules
    round_index = len(results)
    if round_index >= rules.num_rounds:
        raise ValueError("the match is over")
    if balance < rules.min_bet:
        raise ValueError("bankrupt: the balance is below the minimum bet")
    action = policy.action(round_index, history_key(policy, results), balance)
    main, pairs, total = (float(x) for x in action.amounts(balance))
    return BetAdvice(main, pairs, total, policy.style_names[action.style], action.label)


def advise_play(
    cards,
    upcard,
    *,
    rules: RulesConfig,
    style: str = "basic",
    policy: BetPolicy | None = None,
    after_split: bool = False,
    can_afford_more: bool = True,
) -> Action:
    """The play for a hand: hit, stand, double or split.

    ``cards`` are the hand's cards and ``upcard`` the dealer's, as text such as
    ``"8s 8h"`` or card ids. ``after_split`` marks a hand that came from a
    split. ``can_afford_more`` is False when there are not enough spare chips
    to double or split (after an all-in, for example).
    """
    hand = Hand(parse_cards(cards), rules.min_bet, from_split=after_split)
    up = parse_card(upcard) if isinstance(upcard, str) else upcard
    legal = legal_actions(
        hand,
        rules,
        num_hands=2 if after_split else 1,
        bankroll=float("inf") if can_afford_more else 0.0,
    )
    if not legal:
        return Action.STAND
    chart = basic_chart(rules)
    if style != "basic":
        if policy is None or style not in policy.style_names:
            raise ValueError(f"no chart for play style {style!r}")
        chart = policy.style_charts[policy.style_names.index(style)]
    pair = value_index(hand.cards[0]) if Action.SPLIT in legal else None
    return chart.action(hand.total, hand.is_soft, pair, value_index(up), legal)


def main(argv: list[str] | None = None) -> int:
    from rivals.optimize.pipeline import DEFAULT_POLICY_PATH, load_policy

    parser = argparse.ArgumentParser(prog="python -m rivals.advise")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    bet = sub.add_parser("bet", help="the bet for the next hand")
    bet.add_argument("--balance", type=float, required=True)
    bet.add_argument("--history", default="", help="main-bet results so far, e.g. WLP")
    play = sub.add_parser("play", help="the play for a hand")
    play.add_argument("--cards", required=True, help='your cards, e.g. "6s 5d"')
    play.add_argument("--up", required=True, help="dealer upcard, e.g. Tc")
    play.add_argument("--style", default="basic")
    play.add_argument("--after-split", action="store_true")
    play.add_argument("--all-in", action="store_true", help="no chips left to double or split")
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    if args.command == "bet":
        print(advise_bet(policy, args.balance, args.history))
    else:
        action = advise_play(
            args.cards, args.up, rules=policy.rules, style=args.style, policy=policy,
            after_split=args.after_split, can_afford_more=not args.all_in,
        )
        print(action.name.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
