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

**D4. Dealer draws come off the back of the shoe.**
The plan's default is "dealer cards fixed regardless of player draws". To get that from one physical shoe (so the composition stays right for every deck count):
- initial deal off the front: player, dealer upcard, player, dealer hole card
- player draws continue from the front
- dealer draws come off the back

The dealer's whole hand is then a function of the shoe alone. `RulesConfig.dealer_cards_independent=False` switches to the other reading of DraftKings' wording (one sequential shoe, dealer draws after the player), where the two players' dealers can end up with different hands. Both are tested. Which one the real game uses is still unconfirmed and matters a lot for strategy, so it is worth checking in free play: play the same match as someone else, hit a different number of times, and compare the dealer's draws.

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
| `split_21_is_blackjack` | `False` | Ace-ten after a split pays 1:1. Standard. |
| `allow_short_all_in` | `False` | A balance below 10 cannot be bet. |
| `side_bet_min` | `10` | Same minimum as the main bet. |
| `require_balance_for_extra_bets` | `True` | From the plan. Also applies to insurance. |
| `dealer_peeks` | `True` | From the plan. With `False`, a dealer blackjack takes doubled and split bets too. |
| `surrender` | `False` | From the plan. When on, it is late surrender on the first decision. |

`side_bet_max` is no longer a guess. The user confirmed in the app (2026-11-13) that side bets have no cap besides the balance and need not be proportional to the main bet: 600 on a side bet next to a 10 main bet is accepted. Side bets are therefore a full-size variance tool, e.g. most of the stack on 4-Card Total at 10:1.

**D9. Total wagers are checked against the balance up front, and extras against what is left.**
Main bet plus side bets must fit in the balance. Doubles, splits and insurance must fit in what remains after everything already staked that round. So a player who bets everything cannot double or split, which is a real strategic cost of going all-in and is now modeled.

**D10. Round procedure details.**
- A hand that reaches 21 stands automatically.
- Insurance is half the main bet, offered only against an ace, and also covers "even money" on a player blackjack.
- The dealer peeks under both an ace and a ten.
- The dealer draws only if the player has a hand that can still win. If the player busts everything, `dealer_cards` is just the two starting cards. Players who diverged can therefore see different amounts of the dealer's hand, but never different cards.
- The upcard is the first dealer card dealt, the hole card the second.

**D11. Shuffles are numpy PCG64 seeded with `[match_seed, round_index]`.**
`match_shoes(seed, rules)` gives the shoes for a match. A test pins the first cards of one shuffle so a numpy upgrade cannot silently change what a seed means. These shuffles are our own; they cannot reproduce DraftKings' shuffle for a real match ID.

### Sanity check
600,000 seeded rounds of approximate basic strategy at 6 decks came out at −0.39% ± 0.15% per unit bet, in line with the expected house edge for these rules. 150,000 rounds at 1 deck came out at +0.12% ± 0.30%, also plausible. The exact figure comes from the Phase 2 solver.
