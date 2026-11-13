"""Rule set for 21 Rivals.

Every rule the engine depends on lives in `RulesConfig`. Fields marked
UNCONFIRMED are guesses about the real game that still need checking in the
app; they are flags so a wrong guess is a one-line change, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class RulesConfig:
    # --- match format ---
    starting_chips: float = 1000
    num_rounds: int = 5
    min_bet: float = 10
    #: None means the only cap is the player's balance.
    max_bet: float | None = None
    #: Confirmed in the app: a balance below `min_bet` is bankrupt and cannot
    #: be bet, so the match is over for that player. True would instead let
    #: them bet everything they have left.
    allow_short_all_in: bool = False
    #: Prize paid to the winner, as a multiple of the entry fee. Confirmed in
    #: the app: DraftKings keeps 10% of the pot ($1 entry pays $1.80, $5 pays $9).
    prize_multiple: float = 1.8
    #: Value of a match that ends with equal balances, on a scale where a
    #: loss is 0 and a win is 1. Confirmed in the app: a tie refunds the entry
    #: fee, which is worth 1 / prize_multiple = 5/9 of a win.
    match_tie_value: float = 1 / 1.8

    # --- shoe ---
    #: UNCONFIRMED (DraftKings says 6).
    num_decks: int = 6
    #: Confirmed by the user. False: one sequential shoe. The dealer's two starting
    #: cards are the same for both players, but the dealer draws after the
    #: player, so every card a player takes shifts what the dealer draws.
    #: True: the dealer's draws come from their own end of the shoe, so the
    #: dealer's whole hand never depends on what the player did.
    dealer_cards_independent: bool = False
    #: After a split, True deals a second card to both hands straight away;
    #: False deals the second hand's card when its turn starts. Confirmed in
    #: the app: both hands get their card straight away.
    split_deal_both_first: bool = True

    # --- dealer ---
    dealer_hits_soft_17: bool = False
    #: With an ace showing, the dealer checks for blackjack after the insurance
    #: decision, and a dealer blackjack ends the hand before the player acts.
    #: The user reports this is how the app behaves.
    dealer_peeks_on_ace: bool = True
    #: With a ten-value card showing, does the dealer check for an ace
    #: underneath before the player acts? Confirmed in the app: no. The player
    #: can still double and split, and a dealer blackjack then takes every bet
    #: on the table, doubles and splits included.
    dealer_peeks_on_ten: bool = False

    # --- main-bet payouts ---
    #: Confirmed in the app: paid exactly, so odd bets produce half chips.
    blackjack_payout: float = 1.5
    #: Confirmed in the app: insurance exists, costs half the stake, pays 2:1.
    insurance_offered: bool = True
    insurance_payout: float = 2.0

    # --- player options ---
    #: Number of splits allowed per round (1 means at most two hands).
    max_splits: int = 1
    #: True lets any two ten-value cards split (K-Q); False requires identical
    #: ranks. Confirmed in the app: 10, J, Q and K all split with each other.
    split_by_value: bool = True
    double_after_split: bool = True
    #: Hand totals that may double; None means any two cards. Confirmed in
    #: the app: "Double available when player shows 9, 10 or 11". Either
    #: total of a soft hand counts, so ace-8 (shown as 9/19) and ace-9
    #: (10/20) can double; the user doubled an ace-8 in the app.
    double_totals: tuple[int, ...] | None = (9, 10, 11)
    hit_split_aces: bool = True
    #: Does a two-card 21 on a split hand pay as a blackjack? Confirmed in the
    #: app: no, ace-ten after a split pays 1:1.
    split_21_is_blackjack: bool = False
    #: Late surrender (first decision only, lose half the bet). Confirmed in
    #: the app: 21 Rivals has no surrender.
    surrender: bool = False
    #: Doubles, splits and insurance need spare chips to cover. Confirmed in
    #: the app for double and split: both are greyed out after an all-in bet.
    require_balance_for_extra_bets: bool = True

    # --- side bets ---
    perfect_pair_payout: float = 25
    colored_pair_payout: float = 12
    mixed_pair_payout: float = 6
    #: (minimum total, payout) pairs, highest threshold first.
    four_card_total_payouts: tuple[tuple[int, float], ...] = ((40, 10), (38, 8), (36, 2))
    #: Smallest side bet. Confirmed in the app: 5.
    side_bet_min: float = 5
    #: Confirmed in the app: no cap besides the balance, and a side bet may be
    #: far larger than the main bet (600 on a side bet next to a 10 main bet).
    side_bet_max: float | None = None

    def __post_init__(self) -> None:
        if self.num_decks < 1:
            raise ValueError("num_decks must be at least 1")
        if self.num_rounds < 1:
            raise ValueError("num_rounds must be at least 1")
        if self.min_bet <= 0:
            raise ValueError("min_bet must be positive")
        if self.max_bet is not None and self.max_bet < self.min_bet:
            raise ValueError("max_bet must be at least min_bet")
        if self.max_splits < 0:
            raise ValueError("max_splits cannot be negative")
        thresholds = [t for t, _ in self.four_card_total_payouts]
        if thresholds != sorted(thresholds, reverse=True):
            raise ValueError("four_card_total_payouts must be sorted highest threshold first")

    def with_(self, **changes) -> RulesConfig:
        """Copy of these rules with some fields changed."""
        return replace(self, **changes)


DEFAULT_RULES = RulesConfig()
