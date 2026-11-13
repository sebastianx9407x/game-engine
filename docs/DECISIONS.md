# Decisions

Changes to `docs/PLAN.md` and design choices the plan left open, with the reason for each. Newest phase last.

## Phase 1 (rules, cards, shoe, hand, resolve, side bets)

### Departures from the plan

**D1. Python 3.13 for development, `requires-python >= 3.12`.**
The plan says Python 3.12. This machine has only 3.13 and 3.14, so the virtualenv is built on 3.13. Nothing in the code needs more than 3.12. 3.13 was picked over 3.14 because numba support for it is established, and Phase 2 needs numba.

**D1a. The virtualenv lives at `~/.venvs/blackjack-engine`; `.venv` in the repo is a symlink to it.**
`~/Documents` is synced by iCloud, which flags everything inside a dot-folder as hidden. Python 3.13 ignores hidden `.pth` files, so an editable install inside the repo stopped importing `rivals` a few minutes after it was created. Keeping the environment outside the synced folder avoids that. Pytest also gets `pythonpath = ["."]` so the tests run from the repo with any interpreter. To rebuild: `python3.13 -m venv ~/.venvs/blackjack-engine && .venv/bin/pip install -e ".[dev]"`.

**D2. numba is not a dependency yet.**
Phase 1 has no hot loop. It gets added in the phase that first uses it, so the install stays light and a numba/Python version problem can't block the rules engine.

**D3. A `Shoe` is immutable; each player deals through their own `ShoeCursor`.**
The plan describes `shoe.py` as "deterministic dealer vs player card streams". Rather than a shoe object that tracks its own position, the shoe is a frozen card order and `play_round` opens a fresh cursor on it. Both players in a match are handed the same `Shoe` object, and one player's round cannot disturb the other's. `shoe.cards` is a read-only `uint8` array, ready for a compiled kernel later.

**D4. One sequential shoe by default; the dealer draws after the player.** *(default flipped 2026-11-13)*
The plan's default was "dealer cards fixed regardless of player draws". The default is now the opposite:
- initial deal off the front of the shoe: player, dealer upcard, player, dealer hole card
- player draws continue from the front
- dealer draws continue from the front, after whatever the player took

Both players always face the same upcard and hole card. But a player who hits, doubles or splits uses up cards, so the dealer's draws can differ between the two players, and the dealer can bust for one and make a hand for the other.

Why it changed: the user confirmed on 2026-11-13 that this is how the game deals. The card order is the same for both players however many cards each takes; what differs is who gets each card. If one player stands earlier than the other, their dealer draws a card that the other player drew. (An online answer the user found earlier said the same, and it is the literal reading of DraftKings' "same six-deck shoe order".)

`RulesConfig.dealer_cards_independent=True` keeps the plan's original model available, where dealer draws come off the back of the shoe and the dealer's whole hand is a function of the shoe alone. Both models are tested, but only the sequential one needs to be reported from here on.

What this means for later phases:
- Phase 2 (solver): nothing. The EV and outcome distribution of a single player's decision are identical under both models.
- Phase 3–4 (matches, optimizer): it matters. Playing a hand differently from the opponent also re-rolls the dealer's result, so play deviations create more divergence than the plan assumed. In particular, taking one card more or fewer than the opponent hands the dealer a different card, even when the player's own result is unchanged.

**D5. `resolve.py` defines a small `Policy` protocol (`act`, `take_insurance`), not the full `Agent`.**
The plan's `Agent` (`bet`, `side_bets`, `act`) belongs to Phase 3 with `match.py`. A round only needs play decisions, so `play_round(shoe, policy, bet, side_bets, balance=, rules=)` takes the wagers as arguments. A Phase 3 `Agent` satisfies `Policy` by having those two methods. Policies receive a `DecisionContext` (hand, upcard, legal actions, hand index, all hands, spare chips, rules). `ScriptedPolicy` ships in the package because replaying logged hands needs it too.

**D6. `play_round` is a readable pure-Python reference, about 28 µs per round.**
That is roughly 35k rounds per second per core: fine for tests and notebooks, too slow for the millions of matches in Phase 3–4. The numba kernel planned there must be cross-checked against `play_round` on the same shoes, round for round.

### Choices the plan left open

**D7. Chips are plain numbers and may be fractional.**
Blackjack at 3:2 on an odd bet and insurance at half the bet both produce half chips (bet 25 pays 37.5). Amounts are not rounded, and bets are not forced to a chip denomination. Every value that can arise is a multiple of a power of two, which floats hold exactly, so "who has more chips" comparisons stay exact. If the app turns out to round payouts or restrict bet sizes, add a rounding rule or a bet increment to `RulesConfig`.

**D8. Extra rule flags for things nobody has confirmed.** All are in `RulesConfig`, marked UNCONFIRMED:

| Flag | Default | Why this default |
|---|---|---|
| `split_by_value` | `True` | K-Q can split. Usual for online blackjack. |
| `split_deal_both_first` | `False` | Second split hand gets its card when its turn starts (casino procedure). Changes which card lands where, not the odds. |
| `double_totals` | `None` (any two cards) | The user reported doubling on any first two cards. The rules text in a development build of the game client says "Double available when player shows 9, 10 or 11" (see `research/archetypes.md` §1.2). The flag was added so either can be modeled; set it to `(9, 10, 11)` if a soft or hard-8 double is refused in the app. |
| `split_21_is_blackjack` | `False` | Ace-ten after a split pays 1:1. Standard. |
| `side_bet_min` | `10` | Same minimum as the main bet. |
| `require_balance_for_extra_bets` | `True` | No longer a guess for double and split: the user confirmed (2026-11-13) both are greyed out after betting the whole balance. Assumed to apply to insurance too. |
| `dealer_peeks` | `True` | From the plan. With `False`, a dealer blackjack takes doubled and split bets too. |
| `surrender` | `False` | From the plan. When on, it is late surrender on the first decision. |

`side_bet_max` is no longer a guess. The user confirmed in the app (2026-11-13) that side bets have no cap besides the balance and need not be proportional to the main bet: 600 on a side bet next to a 10 main bet is accepted. Side bets are therefore a full-size variance tool, e.g. most of the stack on 4-Card Total at 10:1.

**D9. Total wagers are checked against the balance up front, and extras against what is left.**
Main bet plus side bets must fit in the balance. Doubles, splits and insurance must fit in what remains after everything already staked that round. So a player who bets everything cannot double or split, which is a real strategic cost of going all-in and is now modeled.

**D10. Round procedure details.**
- A hand that reaches 21 stands automatically.
- Insurance is half the main bet, offered only against an ace, and also covers "even money" on a player blackjack.
- The dealer peeks under both an ace and a ten.
- The dealer draws only if the player has a hand that can still win. If the player busts everything, `dealer_cards` is just the two starting cards. Under the sequential shoe (D4) players who diverged can also see different dealer draws.
- The upcard is the first dealer card dealt, the hole card the second.

**D10a. Side bets give the player no information during the hand.** *(confirmed 2026-11-13)*
The user checked in free play: the 4-Card Total result appears only after the hand ends, once the hole card is face up. So it cannot be used to read the dealer's hole card before acting. This matches the engine, where a policy's `DecisionContext` carries no side-bet results. Side bets stay a pure variance tool.

**D10b. A player with fewer than 10 chips is bankrupt; their match ends there.** *(confirmed 2026-11-13)*
The user checked both cases in free play: the match ends at 0, and a balance under the 10 minimum also counts as bankrupt and cannot be bet. That confirms `allow_short_all_in=False`, and `play_round` already refuses such a bet. `match.py` (Phase 3) must stop dealing to a player once their balance is below `min_bet`. Still open: whether a bankrupt player's leftover chips (say 5) count as their final balance or as 0, which only matters when both players go bankrupt.

**D10c. A tied match refunds the entry fee, and the winner gets 1.8× the entry fee.** *(confirmed by the user 2026-11-13)*
DraftKings keeps 10% of the pot: a $1 entry pays $1.80, a $5 entry pays $9, and so on. A tie returns the entry fee. `RulesConfig` now has `prize_multiple = 1.8`, and `match_tie_value` changed from the plan's 0.5 to 1/1.8 = 5/9 ≈ 0.556, which is what a refund is worth on the optimizer's scale (loss = 0, win = 1).

Consequences:
- The objective is P(win) + (5/9)·P(tie), not P(win) + 0.5·P(tie). Tying is worth slightly more than a coin flip, so mirroring the typical opponent is a slightly better fallback than the plan assumed.
- Break-even: in entry-fee units a win is +0.8, a loss is −1 and a tie is 0. A strategy makes money only if it wins more than 5/9 = 55.6% of the matches that don't tie.

For the record, a web search the same day found no written source for the tie rule. The launch post's "A tie is a push, and your play comes back to you" is about one hand tying the dealer, not the match.

**D11. Shuffles are numpy PCG64 seeded with `[match_seed, round_index]`.**
`match_shoes(seed, rules)` gives the shoes for a match. A test pins the first cards of one shuffle so a numpy upgrade cannot silently change what a seed means. These shuffles are our own; they cannot reproduce DraftKings' shuffle for a real match ID.

### Sanity check
600,000 seeded rounds of approximate basic strategy at 6 decks came out at −0.39% ± 0.15% per unit bet, in line with the expected house edge for these rules. 150,000 rounds at 1 deck came out at +0.12% ± 0.30%, also plausible. The exact figure comes from the Phase 2 solver.

## Research delivered (2026-11-13)

`research/archetypes.md` is in. It models each opponent as a bet style × a play-skill tier, not the plan's single list of eight archetypes, because casino data show play errors are roughly independent of bet size. Phase 3 should build `agents/archetypes.py` on that two-dimensional structure. Every population share in it is a low-confidence prior: the game launched on 2026-11-10 and there is no player data yet.

The research also found a public development build of the game client. It is a dev build, so each item needs confirming in the app, but two already match what the user saw (bankruptcy under 10 chips, one split):
- **Doubling may be limited to 9, 10 or 11.** Conflicts with the user's report; now behind `double_totals` (D8).
- **A timeout leaves a balance of 0**, so running out the clock is the same as going bankrupt.
- **Chip denominations are 5, 10, 25, 100, 500, 1000, with 25 selected by default.** Bets are built by tapping chips, so bets are multiples of 5, and odd multiples of 5 produce half chips on a blackjack (D7).
- **REPLAY** repeats the last round's bets and **PLAY 2x** doubles them, which makes flat betting and doubling-up the lowest-effort choices.
