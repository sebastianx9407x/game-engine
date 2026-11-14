"""Watch the game in a window and say what the strategy would do.

    python -m rivals.screen.live --window Discord          # live, from a window
    python -m rivals.screen.live --replay data/screens/match_02   # from saved frames

Reads the screen about once a second and prints a line whenever the advice
changes: the bet before each hand, the play during it. For free play and
analysis; check the operator's terms before using anything like this in a
paid contest.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from rivals.advise import advise_bet
from rivals.hand import Action
from rivals.optimize.bet_policy import BetPolicy
from rivals.screen.capture import find_window, grab, read_text
from rivals.screen.reader import HandTotal, ScreenState, parse
from rivals.solver.basic import basic_chart
from rivals.solver.exact import ACE, TEN


def upcard_index(dealer: HandTotal) -> int | None:
    """Value index of the dealer's upcard from the total shown while only one card is up."""
    if dealer.soft or dealer.total == 11:
        return ACE if dealer.low in (1, 11) or dealer.total == 11 else None
    if dealer.total == 1:
        return ACE
    if 2 <= dealer.total <= 9:
        return dealer.total - 1
    return TEN if dealer.total == 10 else None


def play_advice(state: ScreenState, policy: BetPolicy, style: str) -> Action | None:
    """The chart's play for the hand in play, or None if the screen is unclear."""
    hand = state.active_hand
    if hand is None or state.dealer is None or hand.total >= 21:
        return None
    up = upcard_index(state.dealer)
    if up is None:
        return None
    legal = [Action.STAND, Action.HIT]
    if state.can_double:
        legal.append(Action.DOUBLE)
    pair = None
    if state.can_split:
        legal.append(Action.SPLIT)
        # A splittable hand's total gives the pair away: 2/12 is aces, 16 is eights.
        pair = ACE if hand.soft else (TEN if hand.total == 20 else hand.total // 2 - 1)
    chart = basic_chart(policy.rules)
    if style in policy.style_names and policy.style_charts[policy.style_names.index(style)] is not None:
        chart = policy.style_charts[policy.style_names.index(style)]
    tables = chart.soft if hand.soft else chart.hard
    if (hand.total, up) not in tables:
        return None
    return chart.action(hand.total, hand.soft, pair, up, tuple(legal))


@dataclass
class Tracker:
    """Follows a match frame by frame and produces advice lines."""

    policy: BetPolicy
    results: str = ""
    round: int | None = None
    style: str = "basic"
    #: Balance before chips went down this round, and what the last finished round showed.
    start_balance: float | None = None
    final: ScreenState | None = None
    side_bets_seen: bool = False
    last_line: str = ""
    log: list[str] = field(default_factory=list)

    def _result_of_round(self, next_balance: float | None) -> str:
        """W, L or P for the main bet of the round that just ended."""
        if not self.side_bets_seen and self.start_balance is not None and next_balance is not None:
            delta = next_balance - self.start_balance
            return "W" if delta > 0 else ("L" if delta < 0 else "P")
        # Side bets cloud the balance, so judge from the final totals on the table.
        last = self.final
        if last is None or not last.hands:
            return "P"
        dealer = last.dealer.total if last.dealer else 0
        score = 0
        for hand in last.hands:
            if hand.total > 21:
                score -= 1
            elif dealer > 21 or dealer < 17 or hand.total > dealer:
                score += 1 if (dealer > 21 or hand.total > dealer or hand.total == 21) else 0
            elif hand.total < dealer:
                score -= 1
        return "W" if score > 0 else ("L" if score < 0 else "P")

    def _say(self, line: str, clock: str | None = None) -> str | None:
        """Report ``line`` once; the clock is shown but does not make a line new."""
        if line == self.last_line:
            return None
        self.last_line = line
        shown = f"[{clock}] {line}" if clock else line
        self.log.append(shown)
        return shown

    def update(self, state: ScreenState) -> str | None:
        """Feed one frame; returns a new advice line, or None if nothing changed."""
        if state.phase == "over":
            if self.round is not None:
                self.round = None
                self.results = ""
                return self._say("match over")
            return None
        if state.phase == "unknown" or state.round is None:
            return None

        if self.round is None or state.round < self.round:  # a new match
            self.round, self.results = state.round, ""
            self.start_balance, self.final, self.side_bets_seen = None, None, False
        elif state.round > self.round:  # the previous round finished
            missed = state.round - self.round - 1
            result = self._result_of_round(state.balance)
            if missed:
                # Hands went by unread (a blurry stream, usually). The balance
                # change across the gap is the best available guess for all of them.
                self.side_bets_seen = False
                result = self._result_of_round(state.balance) * (missed + 1)
                self.last_line = ""
                self.log.append(f"missed {missed} hand(s); history guessed from the balance")
            self.results += result
            self.round = state.round
            self.start_balance, self.final, self.side_bets_seen = None, None, False

        tag = f"hand {state.round}/{state.rounds}"
        clock = state.clock
        if state.phase == "betting":
            # The balance drops as chips are placed; the largest value seen is the starting one.
            if self.start_balance is None or state.balance > self.start_balance:
                self.start_balance = state.balance
            if len(self.results) != state.round - 1 or self.start_balance < self.policy.rules.min_bet:
                return None
            advice = advise_bet(self.policy, self.start_balance, self.results)
            self.style = advice.style
            history = self.results or "start"
            return self._say(f"{tag}, balance {self.start_balance:,.0f}, after {history}: {advice}", clock)

        if state.pairs_stake or state.total_stake:
            self.side_bets_seen = True
        if state.hands:
            self.final = state
        if state.phase == "insurance":
            return self._say(f"{tag}: insurance NO", clock)
        if state.phase == "acting":
            action = play_advice(state, self.policy, self.style)
            hand = state.active_hand
            if action is None or hand is None:
                return None
            which = ""
            if len(state.hands) > 1:
                which = " (left hand)" if hand is state.hands[0] else " (right hand)"
            return self._say(
                f"{tag}: you {hand.text}{which} vs dealer {state.dealer.text} -> {action.name}", clock
            )
        return None


def main(argv: list[str] | None = None) -> int:
    from rivals.optimize.pipeline import DEFAULT_POLICY_PATH, load_policy

    parser = argparse.ArgumentParser(prog="python -m rivals.screen.live")
    parser.add_argument("--window", default="Discord", help="app whose window shows the game")
    parser.add_argument("--replay", type=Path, help="folder of saved frames to run through instead")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--interval", type=float, default=0.3, help="pause between frames, seconds")
    parser.add_argument("--save", type=Path, help="also keep every frame in this folder")
    args = parser.parse_args(argv)

    tracker = Tracker(load_policy(args.policy))
    if args.replay:
        for path in sorted(args.replay.glob("*.png")):
            line = tracker.update(parse(read_text(path), Image.open(path)))
            if line:
                print(f"{path.name[2:6]}  {line}", flush=True)
        return 0

    window = find_window(args.window)
    if window is None:
        print(f"no on-screen window found for {args.window!r}")
        return 1
    print(f"watching {args.window} (window {window}); Ctrl-C to stop", flush=True)
    if args.save:
        args.save.mkdir(parents=True, exist_ok=True)
    frame = Path(tempfile.gettempdir()) / "rivals_live_frame.png"
    count = 0
    try:
        while True:
            count += 1
            target = args.save / f"f_{count:05d}.png" if args.save else frame
            if not grab(window, target):
                window = find_window(args.window) or window
                time.sleep(1)
                continue
            line = tracker.update(parse(read_text(target), Image.open(target)))
            if line:
                print(line, flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
