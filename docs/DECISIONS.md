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
Blackjack at 3:2 on an odd bet and insurance at half the bet both produce half chips (bet 25 pays 37.5). Amounts are not rounded, and bets are not forced to a chip denomination. Every value that can arise is a multiple of a power of two, which floats hold exactly, so "who has more chips" comparisons stay exact. The user confirmed (2026-11-13) that the app pays fractional chips, so no rounding rule is needed.

**D8. Extra rule flags for things nobody has confirmed.** All are in `RulesConfig`, marked UNCONFIRMED:

| Flag | Default | Why this default |
|---|---|---|
| `split_by_value` | `True` | No longer a guess: the user confirmed (2026-11-13) that 10, J, Q and K all split with each other. |
| `split_deal_both_first` | `True` | No longer a guess: the user confirmed (2026-11-13) that after a split both hands get their second card straight away. The first default (`False`, casino procedure) was wrong. Changes which card lands where, not the odds. |
| `double_totals` | `(9, 10, 11)` | No longer a guess: the user read the rule in the app (2026-11-13), "Double available when player shows 9, 10 or 11". Either total of a soft hand counts: the user doubled an ace-8 (shown as 9/19), so ace-8 and ace-9 can double. The plan's "double on any first two cards" was wrong. |
| `split_21_is_blackjack` | `False` | No longer a guess: the user confirmed (2026-11-13) that ace-ten after a split pays 1:1. |
| `side_bet_min` | `5` | No longer a guess: the user confirmed (2026-11-13) the smallest side bet is 5. |
| `require_balance_for_extra_bets` | `True` | No longer a guess for double and split: the user confirmed (2026-11-13) both are greyed out after betting the whole balance. Assumed to apply to insurance too. |
| `dealer_peeks_on_ace` / `dealer_peeks_on_ten` | `True` / `False` | Replaces the plan's single "dealer peeks: yes". See "The dealer does not check under a ten" below. |
| `surrender` | `False` | No longer a guess: the user confirmed (2026-11-13) there is no surrender. |

`side_bet_max` is no longer a guess. The user confirmed in the app (2026-11-13) that side bets have no cap besides the balance and need not be proportional to the main bet: 600 on a side bet next to a 10 main bet is accepted. Side bets are therefore a full-size variance tool, e.g. most of the stack on 4-Card Total at 10:1.

**D9. Total wagers are checked against the balance up front, and extras against what is left.**
Main bet plus side bets must fit in the balance. Doubles, splits and insurance must fit in what remains after everything already staked that round. So a player who bets everything cannot double or split, which is a real strategic cost of going all-in and is now modeled.

**D10. Round procedure details.**
- A hand that reaches 21 stands automatically.
- Insurance is half the main bet, offered only against an ace, and also covers "even money" on a player blackjack.
- The dealer peeks under an ace only (see "The dealer does not check under a ten" below).
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

## Rules read from the app by the user (2026-11-13)

These match the engine defaults and are no longer guesses: insurance is offered, costs half the stake and pays 2:1; there is no surrender; a 21 on the first two cards pays 3:2; Perfect Pairs is on the player's first two cards and pays 6:1 mixed, 12:1 same color, 25:1 perfect; 4-Card Total is the player's first two cards plus the dealer's first two cards, paying 2:1 on 36–37 and 8:1 on 38–39. A total of 40 or more pays 10:1 (the user confirmed this after first typing "1 to 1").

## Doubling is limited to 9, 10 or 11 (2026-11-13)

The user read it in the app's rules, along with "Maximum one split per hand" (already the default). `double_totals` now defaults to `(9, 10, 11)`; `None` restores any-two-cards. Effects:
- The only soft doubles are ace-8 and ace-9 (their low totals are 9 and 10), and there is no doubling 8 or less, so the Phase 2 basic strategy chart will differ from the published 6D S17 DAS chart in the soft-hand rows, and the house edge is a little higher than the plan's 0.4–0.5% reference. Validate the solver against the published chart with `double_totals=None`, then report the restricted chart.
- Double after split still applies when the split hand totals 9, 10 or 11.
- The research's "missed soft double" errors no longer exist (`research/archetypes.md` §4.7).

## The results screen shows the opponent's net result on every hand (2026-11-13)

The user sent a screenshot of the MATCH STATS screen. It shows both final balances, a timeline of both balances, and for each of the five hands the net chips won or lost by each player. That is far more than a final balance: it is the opponent's whole bet path.

What a per-hand net tells us about the opponent's bet:
- a loss of X means a bet of X, or X/2 doubled or split
- a win of X means a bet of X, or X/1.5 on a blackjack, or X/2 doubled
- a 0 is a push and hides the bet
- side bets are folded into the same number

Because the first two player cards and the dealer's first two are shared, the user's own hand usually tells which case applies (a blackjack, a push, a dealer blackjack).

First logged match: the user went +100, −100, 0, −100, −25 and finished on 875; the opponent went +250, −250, 0, −250, −700 and finished on 50. Read plainly, the opponent bet 250 flat, then put 700 of their remaining 750 on the last hand. That is the "Closer" pattern from `research/archetypes.md` on top of a flat-mid base. One match is an anecdote, not evidence.

`data/hand_log.csv` is the log (one row per hand, format in `data/README.md`), created now instead of in Phase 5 so real matches are captured from the start. No usernames go in it, since the repo is on GitHub. The research's calibration method (§8) assumed only final balances; with per-hand nets, calibration can score each archetype against the opponent's full five-hand path. Phase 3's archetype models should therefore be able to report the likelihood of an observed sequence of per-hand nets, given the shared cards where they were logged.

## The dealer does not check under a ten (2026-11-13)

The user confirmed in the app: when the dealer shows a ten-value card with an ace underneath, the hand does not end at once. The player can still double and split, and then loses every bet on the table to the blackjack. With an ace showing, the app asks about insurance and the user reports the blackjack is resolved immediately.

The plan's single "dealer peeks: yes" is therefore split into `dealer_peeks_on_ace = True` and `dealer_peeks_on_ten = False`. Effects:
- Against a ten, doubling and splitting carry extra risk: about 1 time in 13 the hole card is an ace and the whole doubled or split stake is lost. Expect the Phase 2 chart to hit, not double, 11 against a ten, and to be more cautious splitting against a ten. This is the usual pattern for games without a hole-card check.
- The house edge rises a little further from the plan's 0.4–0.5% reference. Validate the solver against the published 6D S17 DAS chart with `dealer_peeks_on_ten=True` and `double_totals=None`, then report the real rules.
- The shared-card logic is unchanged: both players face the same hidden ace, so a player who doubles into it loses more than one who just hits.

## Working assumptions agreed with the user (2026-11-13)

- **A bankrupt player keeps their leftover chips as their final balance.** So 5 beats 0, and two bankrupt players tie only if they hold the same amount. This is the user's call, not something seen in the app. `match.py` (Phase 3) should compare final balances as they stand and apply no special bankruptcy rule.
- **Six decks, freshly shuffled every round.** DraftKings' launch post says "the same six-deck shoe order in each of the five rounds", and the engine deals each round from a new shoe. A round uses at most a dozen or so of the 312 cards, so six decks behaves almost like an endless supply; the one place the count shows is Perfect Pairs (a perfect pair is impossible with one deck, 1.6% with six, 1.9% with an endless supply). The user's video recorder will log every card with its suit into `data/hand_log.csv`, and `infer_decks.py` (Phase 5) will use those cards to test the count against six.

## Phase 1 review by Opus (2026-11-13)

An Opus reviewer compared `play_round` against its own independent re-implementation over 200,000 random rounds (mixed deck counts, balances, side bets, insurance, both shoe models) and found no mismatch, no correctness bug and no rule mismatch. Acted on:
- Two test gaps closed (side bets reducing the chips left to double or split; ace-ten after a split losing to a hidden dealer blackjack) and one misleading test renamed.
- `match_tie_value` no longer hard-codes 5/9. It defaults to `None`, meaning "a tie is a refund", and `rules.tie_value` returns `1 / prize_multiple` unless a value is set.

Noted, not acted on yet:
- `DecisionContext` hands policies the live `Hand` objects. A policy that mutated them would corrupt the round. Agents are trusted for now.
- Shuffling a 312-card shoe costs more than playing the round. If a fast kernel is written it must either reproduce `rng.permutation` or redefine what a seed means (`test_shuffle_is_pinned` guards this).
- Still unconfirmed in the app: whether a player who is all-in can take even money on a blackjack (the engine says no, since insurance needs spare chips).

## Phase 2 (solver)

**S1. Pure Python and numpy, no numba.** `rivals/solver/exact.py` solves a whole rule set in about 6 seconds, fast enough that numba was not needed. `solver_for(rules)` and `basic_chart(rules)` cache per process.

**S2. What is exact.** Stand, hit and double values are exact for the cards left in the shoe, including the dealer's blackjack check: with a checked ace up, both the dealer's results and the player's next card are conditioned on the hole card not being a ten; with a ten up there is no check, so dealer blackjack is a live result that beats everything, doubles included. Tests check this against brute-force enumeration with exact fractions.

**S3. What is approximate: splits.** A split is valued as two hands that each start from the pair card with the other pair card removed. The EV ignores what one split hand learns from the other's cards. The distribution of the two-hand total (−4 to +4 units) treats the two hands as independent given the dealer's result, which keeps the important correlation (both hands face the same dealer) and drops the small card-removal one. Simulated rounds agree with both to within noise.

**S4. The solver takes an optional fixed strategy.** `Solver(rules, strategy=chart)` gives the exact value of playing a chart, or any rule of thumb, instead of the best play. Phase 3 can use this to price a human's mistakes exactly.

**S5. Not modeled by the solver:** surrender, blackjack after a split, and resplitting. It raises `NotImplementedError` for those rule settings. None applies to 21 Rivals.

**S6. `basic.py` builds a total-dependent chart**, averaging over the two-card hands that make each total. `BasicStrategy` plays it through `play_round`.

### Results

| Rules | House edge, best play | House edge, chart | Std of one round |
|---|---|---|---|
| Textbook (double any two cards, check under a ten, one card to split aces) | 0.457% | 0.460% | 1.147 |
| 21 Rivals as confirmed | 0.473% | 0.476% | 1.105 |

- Under textbook rules the derived chart is identical, cell for cell, to the published 6-deck S17 DAS chart, and the edge sits where the literature puts it for no resplitting.
- Under 21 Rivals rules the chart changes in three places: hit 11 against a ten (no double), do not split 8s against a ten, and no soft doubles at all (ace-8 and ace-9 may double but standing is better). Being able to hit split aces roughly cancels what the double restriction and the missing check under a ten cost.
- 16 million simulated rounds of the chart through `play_round` gave −0.501% ± 0.028% against the exact −0.476% (0.9 standard errors), and the simulated distribution of round results matches the exact one to four decimal places at every value from −4 to +4.

## Phase 3 groundwork (agents and matches)

**M1. `Agent` (in `rivals/agents/base.py`) has `bet`, `side_bets`, `act`, `take_insurance` and `reset`.** The base class bets the minimum and plays basic strategy, so a tactic overrides only what it changes. Each decision receives a `MatchState`: round index, balance, and the player's own earlier rounds. It never contains anything about the opponent, because the game is blind.

**M2. Illegal bets raise an error.** A tactic that bets more than its balance fails loudly instead of being silently clamped; `state.clamp_bet()` is there for tactics that want clamping.

**M3. `match.py` plays both agents on the same shoes** and `simulate()` runs many matches, optionally across processes. Match `i` always uses seed `seed + i`, so two tactics simulated with the same seed face the same cards and the same opponents, which removes most of the noise from comparing them. Each agent gets its own random stream, so two copies of a random strategy are two different people.

**M4. Speed.** About 270 µs per match on one core in pure Python (3,700 matches per second), so a million matches takes under a minute on eight cores. That is enough for Phase 3. Whether Phase 4 needs a compiled kernel depends on how many matches the optimizer wants.

**M5. A bankrupt player keeps their leftover chips**, as agreed: 5 beats 0.

## Phase 3 (evaluator and tactics)

**E1. `python -m rivals.evaluate tactics/file.py`** scores a tactic against the field: win, tie and loss rates with confidence intervals, the score, profit per $1 of entry fee, the same split by opponent type, and a comparison with the flat-minimum basic-strategy player. `--vs other.py` plays it against one specific tactic instead, and `--baseline other.py` adds more comparisons.

**E2. Comparisons are paired.** The tactic and each baseline play exactly the same matches (same shoes, same opponents with the same random streams), and the reported gain is the average per-match difference. That cuts the noise several-fold compared with two independent runs.

**E3. A tactic file defines one `Agent` subclass** (called `Tactic`, or the only one in the file). `tactics/_template.py` is the starting point; `tactics/flat_100.py` is a reference bettor.

## Phase 4 (optimizer)

**O1. The search exploits the blind format.** Because neither player sees the other and both get the same shoes, an opponent's result on a given match does not depend on what we do. So `build_scenarios` records each match once: what one unit would have won us each round (for every play style and for 1 to 4 bets' worth of chips available), what each side bet would have paid, and where sampled opponents finished. Trying a bet schedule is then arithmetic on arrays, with no cards dealt. This is why no compiled kernel was needed: recording 100,000 matches takes well under a minute and each candidate schedule is scored in milliseconds.

**O2. Backward induction over (hand, shared history, balance).** `solve_bet_policy` starts at hand 5 and works back. For each situation it tries every bet on every recorded match in that situation, plays the remaining hands with the choices already fixed, and keeps the best average score. The plan's "approximate DP with Monte Carlo rollouts" is this, with the rollouts being the recorded matches.

**O3. Shared history comes in three resolutions**, and the pipeline keeps whichever scores best on held-out matches: `pattern` (the exact win/loss/push sequence so far), `count` (how many wins and losses), `none`. A history seen in fewer than 300 recorded matches falls back to the no-history choice so rare patterns are not fitted to noise.

**O4. Bets are a ladder plus side-bet plays.** Main bets of 10, 25, 50, 100, 150, 200, 300, 400, 500, 750, 1000, half the stack and all-in; and a minimum main bet with 50, 100, 200, 400, half the rest or all the rest on either side bet. All amounts are multiples of 5, matching the app's chips. The plan's ladder was shorter and had no side-bet entries.

**O5. Play styles replace the plan's "deviation tables keyed on estimated lead".** A `seek` chart and an `avoid` chart are built like basic strategy but take the most (or least) volatile action whose EV is within 0.03 units of the best. Each main bet can be combined with either, and the search decides where they help, so "estimated lead" is not hand-coded: it is whatever the balance and history imply. Measured effect on a single round is small (standard deviation 1.137 and 1.097 against basic's 1.105, each costing about 0.07% of a bet), so bet size and side bets are the real variance tools; the styles matter mainly because playing differently from the opponent also changes the dealer's cards.

**O6. Honest scoring.** Three sets of matches that never overlap: the optimizer fits on seeds from 0, holds out seeds from 50,000,000, and `rivals.evaluate` scores on seeds from 20,000,000. Half of the hold-out picks the history mode; the other half, which influenced nothing, gives `final_score`. The last check is `python -m rivals.evaluate tactics/optimized.py`, which plays the policy through the real round engine.

**O7. `rivals/report/cheatsheet.py`** (Phase 5, brought forward) lists only the situations the policy actually reaches, merges neighbouring balances with the same instruction, and orders them by how often they occur.

**O8. History is what the player actually saw.** When the search plays a recorded match forward, each later bet is keyed on the main-bet result of the play style and chip cover actually used, exactly as the live agent sees it. The search's roll-forward therefore reproduces the real engine match for match (tested, including non-basic play styles). One approximation remains: when choosing the bet for hand N, the recorded matches are grouped by what a basic-strategy player would have seen in hands 1 to N−1, which differs from the player's own view in the few percent of matches where an earlier hand was played in another style.

## Phases 2–4 review by Opus (2026-11-13)

An Opus reviewer checked the solver against its own exact-fraction brute force on ten cases the tests did not cover (multi-step hits, soft hands, doubled split legs, the unchecked ten) and it matched to 1e-15. It reproduced every figure in the results table, found the bet arithmetic of the search identical to the real engine over 9,000 random-policy matches, and found no information leak in the backward induction and no engineering defect in the opponent models. Its verdict: the optimizer's scores and strategy are a faithful solution to the model. Whether the opponent model matches real players is a separate question.

Fixed after the review:
- `rivals.evaluate` scored on the same shoes the optimizer trained on (both started at seed 0). It now starts at 20,000,000 (O6). Measured inflation had been about 0.001 to 0.002.
- The search keyed later bets on a basic-strategy result the player never sees whenever a non-basic style was used (6.5% of matches). Now keyed on what was actually seen (O8).
- Strategy-card balance ranges were built from observed balances and could span a level with a different instruction. They now follow the policy's own balance levels.
- The history mode was chosen and reported on the same hold-out. The hold-out is now split in two (O6).
- `PolicyAgent` silently played basic strategy if a policy used a play style without carrying its chart. It now raises. The card command records matches with the policy's own charts.

Measured, not changed: the split distribution's mean differs from the split EV by at most 0.002 units at six decks (0.007 at one deck), and its standard deviation is within 0.4%.
