# 21 Rivals Strategy Engine — Plan

## Context
21 Rivals (DraftKings) is a head-to-head, asynchronous blackjack contest. Goal: build a Python simulation engine that finds the strategy that **maximizes probability of finishing with more chips than the opponent**, by modeling how real humans bet and play. The plan is written here (Opus) and the engine gets built by Fable. A live overlay comes later (see note at the end).

The repo currently holds only `21-rivals.md`, the official rules write-up. No code yet.

### Game facts (from `21-rivals.md` + user)
- Both players start with 1,000 chips and play 5 hands (1 hand = 1 round). Min bet 10, no max other than balance.
- Each hand uses a fresh seeded shoe. **The deck count is unconfirmed** (DraftKings says 6, the user isn't sure). It's a config value, see "Deck count" below. Both players get the **same dealer cards (including the hole card)**, and the same player cards as long as their decisions match.
- Dealer stands on all 17s. BJ pays 3:2, win 1:1, insurance 2:1, push returns the bet.
- One split allowed. Double allowed on any first two cards, including after a split. Split aces can be hit.
- Side bets (optional, every hand): Perfect Pairs (25/12/6:1) and 4-Card Total (36–37 2:1, 38–39 8:1, 40+ 10:1, ace = 11).
- **Blind**: you never see the opponent's balance during play. Higher final balance wins. 6-minute clock.

### Core strategic insight that shapes the design
Since the cards are shared, a "mirror" opponent who bets and plays exactly like you **always ties**. All edge comes from **divergence**: different bet sizes, different play decisions, and different side bets on the same cards. That makes this a P(win) problem, not an EV problem. Standard basic strategy is only the baseline. The real strategy is:
1. **Bet sizing relative to the expected opponent**, conditioned on the shared history. If hand 2 was a dealer blackjack, you know your opponent lost hand 2 too, and you can predict how a typical human reacts (chasing, tilting, shrinking bets).
2. **Play deviations** that buy or shed variance depending on whether you are probably ahead or behind the human field.
3. **Side bets as variance tools.** They're −EV, but they pay out on cards both players share.

## Who does what
| Role | Model / agent | Owns |
|---|---|---|
| Planning, specs, review | Opus (this session) | This plan, interface specs for each module, code review of Fable's work |
| **Engine coding (most of the code)** | **Fable** | Everything under `rivals/` and `tests/` |
| Human-psychology research | Opus research subagent (deep-research style, web search) | `research/archetypes.md`: how real blackjack players bet and play, with sources |
| Simulation notebooks + visuals | Opus subagent | `notebooks/*.ipynb` that *call* the engine (no engine logic in the notebooks) |
| Tactic ideas | User + Opus | `tactics/*.py` plug-in files, run head-to-head against the field |

Step 0 after approval: save these role preferences to project memory.

**Subagent model rule:** the psychology research agent and the notebook agent must run on **Opus at max effort**, never Fable. If a Fable session launches either one, it must pass `model: "opus"` and `effort: "max"` explicitly. Before launching the research agent, check whether `research/archetypes.md` already exists. If it does, the research is done.

> **Note to Fable:** this outline is a starting point, not a contract. If the module layout, interfaces, algorithms or phase order need to change once you're in the code (for performance, correctness, or because a better design turns up), go ahead and change them. Write down each significant change and the reason in `docs/DECISIONS.md` so Opus and the notebooks stay in sync. The fixed parts are the **goals**: correct 21 Rivals rules, shared-shoe head-to-head simulation, P(win) as the objective, and archetypes grounded in the research. The **structure** is not fixed.

## Psychology research agent → archetypes
A dedicated research subagent studies how people play regular blackjack and casual or social casino games before any archetype gets coded. Its deliverable is `research/archetypes.md`, with one section per archetype containing:
- **Behavior evidence:** e.g. loss-chasing, the house-money effect (betting bigger after wins), the break-even effect (risk-seeking when down), the gambler's fallacy and hot-hand belief, common deviations from basic strategy (standing on 12–16, never splitting 8s or doubling 11, always taking insurance), and how often players use the min bet in free-chip or app games.
- **Quantified parameters** where the literature gives them (bet-change multipliers after a win or loss, how often each mistake happens), plus an estimated **share of the population**, each with a confidence level and a source.
- **A 21 Rivals translation:** how a 5-hand, 1,000-chip, blind, timed format probably shifts that behavior. Examples: last-hand shoves, clock pressure leading to rushed or default stands.

Fable then codes `agents/archetypes.py` straight from that spec, with every parameter exposed. The population weights in `optimize/population.py` start from the research shares and get swept in sensitivity analysis.

## User-proposed tactics
`tactics/` is a plug-in folder. Each tactic is a small Python class implementing the `Agent` interface: `bet()`, `side_bets()`, `act()`. A template is provided so a new idea takes about 20 lines. One command, `python -m rivals.evaluate tactics/my_idea.py`, reports:
- P(win), P(tie), P(loss) against the field, with confidence intervals
- Results against each archetype separately
- How the tactic compares to the current best policy

Optimizer results get saved as tactics too, so the human and machine strategies compete in one leaderboard (`notebooks/04_tactic_leaderboard.ipynb`).

## Deck count
- `RulesConfig.num_decks` is configurable. Every headline result is re-run at 1, 2, 6 and 8 decks, and the notebook shows whether the recommendations change. They should mostly not: play deviations shift slightly and Perfect Pairs odds shift noticeably.
- **Inferring it from real play:** `rivals/infer_decks.py` takes logged hands (cards seen per round) and computes the likelihood of each deck count. One clue: seeing the exact same card (same rank and suit) more than once in a single round rules out a 1-deck shoe. The user logs their cards while playing, and the estimate tightens over matches.

## Architecture (Python 3.12, numpy, numba for hot loops, pytest)

```
blackjack-engine/
  pyproject.toml
  rivals/
    rules.py        # RulesConfig dataclass: every rule above, plus unknowns as flags (defaults below)
    cards.py        # rank/suit/color encoding, card values
    shoe.py         # seeded 6-deck shuffle per hand; deterministic dealer vs player card streams
    hand.py         # hand state, legal actions (hit/stand/double/split/insurance)
    resolve.py      # play one hand against a given shoe + decision policy → net chips (+ side bets)
    side_bets.py    # Perfect Pairs, 4-Card Total payout logic
    solver/
      exact.py      # exact composition-dependent EV *and full outcome distribution* per (hand, upcard, action)
      basic.py      # derives the basic strategy chart from exact.py (validation baseline)
    agents/
      base.py       # Agent interface: bet(hand_idx, my_chips, history), side_bets(...), act(hand_state, ctx)
      archetypes.py # human models (see below), each parameterized + stochastic
      optimal.py    # policy produced by the optimizer
    match.py        # head-to-head match sim: both agents on the SAME 5 seeded shoes (common random numbers)
    optimize/
      bet_policy.py # search over bet schedules: f(hand_idx, my_chips, shared_history) → bet
      play_policy.py# variance-seeking vs variance-averse deviation tables, keyed on "estimated lead"
      population.py # weighted mix of archetypes = "the DraftKings field"
      robust.py     # iterated best response → check exploitability vs a strong (non-human) opponent
    report/
      cheatsheet.py # outputs a human-memorizable strategy card (bet ladder + deviations)
    evaluate.py     # CLI: score any tactic file vs the field
    infer_decks.py  # deck-count likelihood from logged hands
  research/
    archetypes.md   # psychology research agent output (spec for archetypes.py)
  tactics/
    _template.py    # copy this to propose a tactic
  data/
    hand_log.csv    # user's real hands, for deck inference + archetype calibration
  tests/
  notebooks/        # Opus-built, visualization only, import rivals.*
    01_engine_validation.ipynb   # basic strategy chart heatmap, EV convergence plots
    02_outcome_distributions.ipynb # per-decision net-unit distributions (variance tools)
    03_archetype_matchups.ipynb  # each archetype's final-chip distribution, head-to-head matrix
    04_tactic_leaderboard.ipynb  # P(win) leaderboard with CIs, user tactics vs optimized
    05_bet_policy_maps.ipynb     # optimal bet by hand # × chip state heatmaps
    06_sensitivity.ipynb         # deck count + population-mix sweeps
```

### Rule defaults to confirm in-game (all configurable in `RulesConfig`)
Dealer peeks for BJ: **yes**. Surrender: **no**. Double/split needs enough balance to cover the extra bet: **yes**. Match-level tie (equal balances): **counts as 0.5**. Max bet = current balance. Dealer cards fixed regardless of player draws: **yes** (implied by "same dealer cards").

### Human opponent archetypes (`agents/archetypes.py`)
Each has bet behavior plus play behavior, with noise:
- **Flat-min**: bets 10 every hand, plays basic strategy (very common, low variance)
- **Flat-mid**: bets 50–200 flat
- **Hero / all-in**: bets most or all of the stack on 1–2 hands
- **Martingale / chaser**: doubles the bet after a loss
- **Press-the-win**: raises the bet after a win
- **Protector**: shrinks bets after winning hands
- **Gut player**: plays common human mistakes (stands on 12–16 vs. high cards, never splits 8s, always takes insurance, doubles too rarely or too often)
- **Last-hand shover**: shoves on hand 5 if it believes it is behind

The population mix weights are the main unknown. Provide sensible priors, run sensitivity sweeps, and later let observed match results (W/L logs from real play) update the weights.

### Optimization approach
1. **Exact solver first** (`solver/exact.py`): for every decision, compute the full distribution of net units (−4…+4 including split/double), not just the EV. Validate it by reproducing the known 6D S17 DAS basic strategy chart and its house edge (~0.4–0.5%).
2. **Joint match simulation**: draw 5 shoes from a seed, play my policy and an opponent sampled from the population on the identical shoes, and record win/tie/loss. Run millions of matches with numba plus multiprocessing.
3. **Policy search**: the objective is P(win) + 0.5·P(tie) against the population.
   - Bets: discrete ladder {10, 25, 50, 100, 200, 300, 500, all-in}, state = (hand_idx, my_chips bucket, shared-outcome history). Search hand by hand, from hand 5 back to hand 1, with Monte Carlo rollouts (approximate DP).
   - Plays: pick a basic vs. high-variance vs. low-variance action set, depending on the estimated lead over the field.
   - Side bets: decide whether, and how much, to add per state.
4. **Robustness check** (`robust.py`): run iterated best response against the optimized policy. This shows how badly it fails against a sharp opponent and lets us blend toward a safer policy if needed.
5. **Output**: a one-page cheat sheet (bet ladder by hand and situation, plus key play deviations) that can be memorized and used within the 6-minute clock.

## Build phases
Phases 1–2 run in parallel with the research agent.
1. **Fable:** `rules`, `cards`, `shoe`, `hand`, `resolve`, `side_bets` + unit tests. **Research agent:** `research/archetypes.md`.
2. **Fable:** `solver/exact.py` + `basic.py`. **Opus notebook agent:** notebooks 01–02.
3. **Fable:** `agents` (from the research spec) + `match.py` + `evaluate.py` + tactic template. Sanity test: mirror vs. mirror gives exactly 100% ties. **Notebook agent:** notebook 03.
4. **Fable:** `optimize/*`. **User + Opus:** first batch of tactics. **Notebook agent:** notebooks 04–05.
5. **Fable:** `robust.py`, `infer_decks.py`, `report/cheatsheet.py`. **Notebook agent:** notebook 06.
6. (Later, gated on the note below) the overlay.

Opus reviews each Fable phase before the next one starts.

## Verification
- `pytest`: payouts (BJ 3:2, insurance, side-bet tables), split/double rules, determinism (same seed gives same shoe), shared dealer cards when decisions diverge.
- The solver's basic strategy matches the published 6D S17 DAS chart. Simulated basic-strategy EV converges to the exact EV.
- Mirror match: 100% ties. Policy vs. itself: ~50% win rate. Flat-min vs. flat-min: all ties.
- The optimized policy's P(win) against the population is reported with confidence intervals and with sensitivity to the population weights.

## Note on the overlay
Before building a live recommendation overlay, check DraftKings' Terms of Use. This is a paid contest against other customers, and real-time assistance software in those is commonly prohibited, which can risk account closure and voided prizes. The cheat sheet is safe: memorizing a strategy is just studying. Decide on the overlay after that check.

## Free-to-play mode as the testing ground
Use the free 21 Rivals mode (confirm it exists in the app) to:
- Log real hands into `data/hand_log.csv` to infer the deck count and confirm the rule defaults (dealer blackjack check, surrender, match ties).
- Calibrate the archetype population weights against real opponents.
- Try an overlay prototype there first, if the Terms of Use allow it. For paid contests, use the memorized cheat sheet.
