"""Turn the text on a 21 Rivals screen into the state of the game.

The app prints everything the strategy needs: the balance, the round, each
hand's total in a small dark badge ("13", or "9/19" for a soft hand), the
dealer's total, the chips staked, and the four action buttons, which are lit
when available and grey when not. So no card recognition is needed to decide
what to do. Positions below are fractions of the phone screen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PIL import Image

from rivals.screen.capture import TextItem

_TOTAL = re.compile(r"^(\d{1,2})(?:/(\d{1,2}))?$")
_BUTTONS = ("DOUBLE", "HIT", "STAND", "SPLIT")

DEALER_BAND = (0.355, 0.400)  # y range of the dealer's total badge
PLAYER_BAND = (0.635, 0.675)  # y range of the player's total badges
HEADER_BAND = (0.190, 0.245)  # y range of the clock, balance and round values
STAKE_BAND = (0.815, 0.850)  # y range of the chip amounts under the bet spots
BUTTON_Y = 0.86  # the action buttons sit below this
LIT = 170  # a lit button has bright pixels; a grey one tops out near 100
#: Words printed on the felt, which are not messages.
_FELT = ("INSURANCE PAYS", "21 PA", "DEALER STANDS", "PERFECT", "PAIRS", "4-CARD", "TOTAL", "KINGS")


@dataclass(frozen=True, slots=True)
class HandTotal:
    """A total badge: ``total`` is the best total, ``low`` the other one on a soft hand."""

    text: str
    total: int
    soft: bool
    x: float
    #: After a split the app highlights the badge of the hand in play (an olive
    #: tint) and leaves the other dark. A lone hand is always the active one.
    active: bool = True

    @property
    def low(self) -> int:
        return self.total - 10 if self.soft else self.total


@dataclass(frozen=True, slots=True)
class ScreenState:
    #: "betting", "acting" (your move), "waiting" (cards on the table, not your move),
    #: "insurance", "over" (match finished) or "unknown".
    phase: str
    balance: float | None = None
    round: int | None = None
    rounds: int | None = None
    clock: str | None = None
    dealer: HandTotal | None = None
    hands: tuple[HandTotal, ...] = ()
    can_double: bool = False
    can_split: bool = False
    #: Chips shown under the main bet, Perfect Pairs and 4-Card Total spots.
    main_stake: float = 0
    pairs_stake: float = 0
    total_stake: float = 0
    messages: tuple[str, ...] = ()

    @property
    def active_hand(self) -> HandTotal | None:
        """The hand to act on, or None if it is unclear (two hands and neither highlighted)."""
        active = [hand for hand in self.hands if hand.active]
        return active[0] if len(active) == 1 else None


def _number(text: str) -> float | None:
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _region(image: Image.Image, item: TextItem, pad: float) -> np.ndarray:
    width, height = image.size
    box = (
        max(int((item.x - pad) * width), 0),
        max(int((item.y - pad / 2) * height), 0),
        min(int((item.x + item.w + pad) * width), width),
        min(int((item.y + item.h + pad / 2) * height), height),
    )
    return np.asarray(image.crop(box).convert("RGB"), dtype=np.float64)


def _is_lit(image: Image.Image, item: TextItem) -> bool:
    return float(np.percentile(_region(image, item, 0.012).max(axis=2), 95)) > LIT


def _badge(image: Image.Image, item: TextItem) -> tuple[bool, bool]:
    """(is a total badge, is highlighted). A badge is light text on a dark box; a card is the reverse."""
    pixels = _region(image, item, 0.006)
    red, green, blue = (float(pixels[..., c].mean()) for c in range(3))
    brightness = (red + green + blue) / 3
    if brightness > 140:  # white card face
        return False, False
    return True, red - blue > 25 and green - blue > 25  # olive tint


def _parse_total(text: str) -> tuple[int, bool] | None:
    match = _TOTAL.match(text.strip())
    if not match:
        return None
    first, second = int(match.group(1)), match.group(2)
    if second is None:
        return first, False
    return int(second), True


def _totals(image: Image.Image, items: list[TextItem], band: tuple[float, float]) -> list[HandTotal]:
    found = []
    for item in items:
        if not band[0] <= item.cy <= band[1]:
            continue
        parsed = _parse_total(item.text)
        if parsed is None or parsed[0] > 31:
            continue
        is_badge, highlighted = _badge(image, item)
        if is_badge:
            found.append(HandTotal(item.text.strip(), parsed[0], parsed[1], item.x, highlighted))
    found.sort(key=lambda h: h.x)
    if not any(h.active for h in found):  # nothing highlighted: a lone hand, or mid-animation
        found = [HandTotal(h.text, h.total, h.soft, h.x, True) for h in found]
    return found


def _below(items: list[TextItem], label: str) -> TextItem | None:
    """The text item printed just under a header label such as "Balance"."""
    head = next((i for i in items if i.text.strip().lower() == label), None)
    if head is None:
        return None
    under = [
        i for i in items
        if i is not head and 0 < i.cy - head.cy < 0.05 and abs(i.cx - head.cx) < 0.09
    ]
    return min(under, key=lambda i: i.cy, default=None)


def parse(items: list[TextItem], image: Image.Image) -> ScreenState:
    """The game state shown in one frame."""
    texts = {i.text.strip().upper() for i in items}
    balance_item, round_item, clock_item = (_below(items, k) for k in ("balance", "round", "time"))
    # On a blurry frame the small labels can be unreadable while the values
    # under them still are, so fall back to where the values sit.
    header = [i for i in items if HEADER_BAND[0] <= i.cy <= HEADER_BAND[1]]
    if balance_item is None:
        balance_item = next((i for i in header if 0.36 < i.cx < 0.64 and _number(i.text) is not None), None)
    if round_item is None:
        round_item = next((i for i in header if i.cx > 0.64 and "/" in i.text), None)
    if clock_item is None:
        clock_item = next((i for i in header if i.cx < 0.36 and ":" in i.text), None)
    balance = _number(balance_item.text) if balance_item else None
    round_now = rounds = None
    if round_item:
        match = re.match(r"^(\d)\s*/\s*(\d)$", round_item.text.strip())
        if match:
            round_now, rounds = int(match.group(1)), int(match.group(2))
    clock = clock_item.text.strip() if clock_item and ":" in clock_item.text else None

    if balance is None or round_now is None:
        over = bool(texts & {"FINISH", "MATCH STATS", "PLAY AGAIN FREE ENTRY"}) or any(
            t.startswith("PLAY AGAIN") for t in texts
        )
        return ScreenState("over" if over else "unknown")

    buttons = {i.text.strip().upper(): i for i in items if i.cy > BUTTON_Y and i.text.strip().upper() in _BUTTONS}
    lit = {name: _is_lit(image, item) for name, item in buttons.items()}
    dealer = _totals(image, items, DEALER_BAND)
    hands = _totals(image, items, PLAYER_BAND)

    stakes = {"main": 0.0, "pairs": 0.0, "total": 0.0}
    for item in items:
        if STAKE_BAND[0] <= item.cy <= STAKE_BAND[1] and (value := _number(item.text)) is not None:
            spot = "pairs" if item.cx < 0.42 else ("main" if item.cx < 0.57 else "total")
            stakes[spot] = value

    messages = tuple(
        i.text.strip() for i in items
        if 0.50 <= i.cy <= 0.62 and i.text.strip().isupper()
        and not i.text.strip().startswith(_FELT)
        and len(i.text.strip()) > 2
    )

    if "PLACE CHIPS" in texts or "DEAL" in texts:
        phase = "betting"
        stakes = {"main": 0.0, "pairs": 0.0, "total": 0.0}  # the chip tray sits in that band here
    elif any("INSURANCE" in t and "PAYS" not in t for t in texts) and {"YES", "NO"} & texts:
        phase = "insurance"
    elif lit.get("HIT") and hands:
        phase = "acting"
    elif hands or dealer:
        phase = "waiting"
    else:
        phase = "betting" if not buttons else "waiting"

    return ScreenState(
        phase, balance, round_now, rounds, clock,
        dealer[0] if dealer else None, tuple(hands),
        bool(lit.get("DOUBLE")), bool(lit.get("SPLIT")),
        stakes["main"], stakes["pairs"], stakes["total"], messages,
    )
