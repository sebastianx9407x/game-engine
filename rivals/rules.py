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
    #: Value of a match that ends with equal balances, on a scale where a
    #: loss is 0 and a win is 1. Confirmed in the app: a tie refunds the entry
    #: fee, so the exact value is entry fee / prize. That is 0.5 when the
    #: prize is twice the entry fee and higher when DraftKings keeps a cut.
    match_tie_value: float = 0.5

    # --- shoe ---
    #: UNCONFIRMED (DraftKings says 6).
    num_decks: int = 6
    #: UNCONFIRMED. False: one sequential shoe. The dealer's two starting
    #: cards are the same for both players, but the dealer draws after the
    #: player, so every card a player takes shifts what the dealer draws.
    #: True: the dealer's draws come from their own end of the shoe, so the
    #: dealer's whole hand never depends on what the player did.
    dealer_cards_independent: bool = False
    #: UNCONFIRMED. After a split, True deals a second card to both hands
    #: straight away; False deals the second hand's card when its turn starts.
    split_deal_both_first: bool = False

    # --- dealer ---
    dealer_hits_soft_17: bool = False
    #: UNCONFIRMED. Dealer checks for blackjack (ace or ten up) before the
    #: player acts. If False, a dealer blackjack takes every bet on the table,
    #: doubles and splits included.
    dealer_peeks: bool = True

    # --- main-bet payouts ---
    blackjack_payout: float = 1.5
    insurance_offered: bool = True
    insurance_payout: float = 2.0

    # --- player options ---
    #: Number of splits allowed per round (1 means at most two hands).
    max_splits: int = 1
    #: UNCONFIRMED. True lets any two ten-value cards split (K-Q); False
    #: requires identical ranks.
    split_by_value: bool = True
    double_after_split: bool = True
    hit_split_aces: bool = True
    #: UNCONFIRMED. Does a two-card 21 on a split hand pay as a blackjack?
    split_21_is_blackjack: bool = False
    #: Late surrender (first decision only, lose half the bet).
    surrender: bool = False
    #: UNCONFIRMED. Doubles, splits and insurance need spare chips to cover.
    require_balance_for_extra_bets: bool = True

    # --- side bets ---
    perfect_pair_payout: float = 25
    colored_pair_payout: float = 12
    mixed_pair_payout: float = 6
    #: (minimum total, payout) pairs, highest threshold first.
    four_card_total_payouts: tuple[tuple[int, float], ...] = ((40, 10), (38, 8), (36, 2))
    #: UNCONFIRMED. Smallest side bet.
    side_bet_min: float = 10
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
