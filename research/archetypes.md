# Human opponent archetypes for 21 Rivals: research spec

*Psychology research agent (Opus), 2026-11-13. This is the spec for `agents/archetypes.py` and the population weights in `optimize/population.py`. Read alongside `docs/PLAN.md` and `docs/DECISIONS.md`.*

## How to read this document

Every number carries a label:

| Label | Meaning |
|---|---|
| **[S]** | Taken directly from a source (the source is named next to it). |
| **[D]** | Derived: computed by me from a source's numbers, or from my calibration simulations, which are anchored to sources (Section 4.1). |
| **[A]** | My assumption or judgment, with no direct source. Treat it as a prior to sweep, not a fact. |

Confidence: **H** = several consistent primary sources; **M** = one good source or several weaker ones; **L** = analogy, anecdote, or judgment.

Notation used in the parameter tables: `S` = the player's current balance; `h` = hand index 1..5; `R` = the player's reference point (default 1,000, see Section 5.1); "behind" means `S < R`; `base` = the archetype's base bet. Bets snap to the app's chip grid (Section 5.2), never go below 10, and never exceed `S`. "All-in" means bet `S` (the app has no table maximum).

**Bottom line on evidence quality.** The direction of most effects is well supported: inertia, pressing after wins, chasing after losses, end-of-session risk-seeking, passive play errors. Magnitudes for 21 Rivals specifically are not. The game launched on 2026-11-10, three days before this was written, and I found no player data, forum threads or reviews. **Every population share below is a prior with low confidence.** Shares should be swept and then updated from logged matches (Section 8).

---

## 0. Executive summary

### 0.1 Bet-style archetypes (dimension 1: how the player sizes bets across the 5 hands)

| # | Archetype | One-line description | Share (point) | Plausible range | Confidence |
|---|---|---|---|---|---|
| B1 | **Flat-min** | Bets 10 on every hand. A few wake up and shove on hand 5 when behind. | 12% | 6–25% | L |
| B2 | **Flat-small (default/rebettor)** | Bets the one-tap default 25, or 50, and repeats it with REPLAY. Occasional small adjustments. | 17% | 10–28% | L |
| B3 | **Flat-mid (unit bettor)** | Flat 100–200 (about 10–20% of the stack), with occasional adjustments. | 11% | 5–20% | L |
| B4 | **Presser (positive progression / house money)** | Raises after a win (often 2× via the PLAY 2x button), returns to base after a loss. | 16% | 8–25% | L–M |
| B5 | **Chaser (martingale / break-even)** | Doubles after a loss and returns to base after a win. Late in the match, bets to "get back to 1,000". | 8% | 3–15% | L |
| B6 | **Hero (early all-in)** | Bets 50–100% of the stack on hand 1 or 2. Then protects if up big, or keeps swinging if down. | 10% | 4–20% | L |
| B7 | **Closer (last-hand shover)** | Small and flat on hands 1–4. Large or all-in on hand 5 when behind 1,000, sometimes even when ahead. | 12% | 6–20% | L–M |
| B8 | **Protector (lead locker)** | Medium bets early. Once up by a threshold (+50 to +300), drops to the minimum for the rest of the match. | 5% | 2–10% | L |
| B9 | **Tactician (contest-aware)** | Reasons about the opponent and shared cards. Moderate variance early, bet sized to the field on hand 5, near-basic-strategy play. | 4% | 1–10% | L |
| B10 | **Erratic (gut bettor)** | Bet sizes drawn almost at random, from 1% to 100% of the stack, with no consistent rule. | 5% | 2–10% | L |

### 0.2 Play-skill tiers (dimension 2: how the player plays the cards; drawn conditionally on bet style, Section 6.1)

| # | Tier | One-line description | Share | Range | Confidence | Calibrated error profile [D] |
|---|---|---|---|---|---|---|
| P1 | **Solid** | Near basic strategy, rare slips. | 16% | 8–25% | L–M | Errors on 1.8% of hands; costs 0.19% of stake |
| P2 | **Casual (folk strategy)** | The typical casino player: stands too often on stiffs against high cards, under-doubles and under-splits. | 50% | 35–65% | M | Errors on 12.6% of hands; costs 1.2% of stake; 83% of errors passive |
| P3 | **Novice / gut** | Close to "never bust" heuristics, many missed doubles and splits, more insurance. | 34% | 20–50% | L–M | Errors on 28% of hands; costs 3.4% of stake; 84% passive |

### 0.3 Cross-cutting modules (independent of the two dimensions, or mildly correlated with them)

| Module | Content | Key defaults |
|---|---|---|
| Side bets | Three propensity classes: never / occasional / habitual | 54% / 31% / 15% of players. About 21% of hands carry a side bet. Typical size 10–25 chips [A/D] |
| Insurance | Depends on the play tier | Without a player blackjack: P1 1%, P2 6%, P3 15%. With a player blackjack (= even money): 10% / 45% / 55% [A] |
| Reference point | How "ahead/behind" is judged in a blind game | 80% of players use R = 1,000. 10% use a pessimistic R = 1,000 + 50–250. 10% (80% of Tacticians) estimate the opponent from shared outcomes [A] |
| Timeout | Forfeit (balance 0) | 1% of matches (range 0.2–3%) [A] |

### 0.4 What this population implies (Section 6.2; derived from this spec by simulation, not observed)

Hand-1 bets: 16% bet 10, 45% bet 11–50, 29% bet 51–200, 6% bet 201–999, 5% go all-in. 33% of players make a bet of 500 or more at some point. On hand 5, 25% of the players still alive bet at least half their stack and 19% go all-in. 14% end bankrupt. The field's median final balance is 1,000, and **47% of opponents finish above 1,000** [D]. On hands 2–4, the average bet after a win is 0.10 base units higher than after a non-win. That is a third of the Las Vegas pressing effect, a deliberate compromise with the online evidence of chasing (Section 5.4).

---

## 1. What is known about 21 Rivals itself

### 1.1 Facts from the official write-up and from the user's in-app checks

From `21-rivals.md` (DraftKings Network launch post, 2026-11-10, <https://dknetwork.draftkings.com/2026/11/10/21-rivals-draftkings-head-to-head-card-game-launch/>) and `docs/DECISIONS.md`:

- Five rounds and a six-minute clock. Running out of time forfeits the match. Same shoe order, same dealer cards and same player cards as long as decisions match.
- Prize: a $1 entry pays $1.80 and a $5 entry pays $9. A tie refunds the entry fee, so the objective is P(win) + (5/9)·P(tie) (DECISIONS D10c).
- Side bets have no cap besides the balance. The app accepted 600 on a side bet next to a 10 main bet (D8). Side-bet results appear only after the hand (D10a).
- A balance under 10 is bankrupt and the match ends (D10b).
- A free-play mode exists. The user has run checks in it.

### 1.2 The game client: a public development build of the actual 21 Rivals front end

**Finding [S, primary, verified 2026-11-13].** A development build of the game client is publicly reachable at <https://ggskills-blackjack-dev.low6.com/>. Its code names DraftKings directly: `brandGameName()` returns `'21 Rivals'` when the brand is `dk`, with the comment *"DraftKings brands it "21 Rivals""*. Otherwise the game is called "Rapid Blackjack". The developer is Mini Win Games (assets at `games.miniwingames.com`), and the dev environment is hosted by Low6, a B2B free-to-play and skill-games firm. The DraftKings variant uses the same code as the unbranded build. It is a dev build (v0.1.1), so production can differ. Treat each item below as "very likely, confirm in the app".

| UI or rule fact found in the client | Behavioral relevance |
|---|---|
| `STARTING_BALANCE = 1000`, `TOTAL_HANDS = 5`, `MIN_BET = 10`, `GAME_TIME_SECONDS = 360` | Confirms the format. |
| Chip denominations `[5, 10, 25, 100, 500, 1000]`. **Default selected chip = 25** (`let selectedChipDenom = 25; // default denomination`). Betting is "tap the table to place chips". | A single tap bets **25, not 10**. Betting the minimum takes a deliberate chip change, so lazy bettors cluster at 25/50/75/100. All-in on hand 1 is two taps (select the 1000 chip, tap). |
| **REPLAY** button: re-places the previous round's main and side bets. Once per round, only if affordable. | Makes "same bet again" the lowest-effort option, which produces inertia. |
| **PLAY 2x** button: doubles the currently placed main and side bets, if affordable, and can be pressed again. | Makes "let it ride" (pressing) and martingale doubling one or two taps. It also doubles side bets. |
| Info panel: "Maximum one split per hand"; **"Double available when player shows 9, 10 or 11"**; "A balance of less than 10 chips will result in bankruptcy"; "TIMEOUT will result in a balance of 0"; insurance "costs half your stake and pays 2 to 1". | The double rule **conflicts with the current assumption** (double on any two cards; `RulesConfig` has no doubling-restriction flag). It needs checking in free play. If it holds, soft doubles do not exist and part of the error model drops out (Section 4.7). |
| DraftKings **skips the in-game tutorial** (`BRANDS_WITHOUT_TUTORIAL = ['dk']`). Rules are in an info overlay only. | Side-bet payouts and the double rule are less salient to DraftKings players. |
| Hand totals are shown on screen, including soft totals (e.g. "4/14"). | Removes arithmetic errors, which cause some live-casino mistakes. |
| Insurance is a YES/NO popup. It auto-declines if the player can't afford it. | A popup forces an explicit decision. It also burns clock time. |
| Win celebrations only when profit ≥ 100 chips: big win (≥100) 3.5 s, huge (≥250) 4.0 s, mega (≥500) 4.5 s, "sensational" (≥1,000) 5.0 s. Tap to dismiss. | Slot-style reward cues appear only for larger bets. A possible nudge toward bets of 100 or more (hypothesis, Section 5.11). |
| Results screen: a per-hand table (You / Dealer / Perfect Pairs / Four Card Total / Main / Balance) and the final balance. No opponent information during play. | Confirms the blind format. Whether the opponent's final balance is ever shown is not visible in this build (Section 8). |

### 1.3 Who the opponents are

- **Where:** the launch states (MA, NH, NC, VA, FL, AL, NY, TX) have no legal real-money online casino. So 21 Rivals is a skill-contest product for **DraftKings sportsbook and DFS customers who mostly cannot play online casino blackjack for money** [S: state list from the DraftKings post; the iGaming status is my own background knowledge, not re-checked for 2026, M]. Their blackjack experience comes from land casinos, social or sweepstakes apps, and home games.
- **Demographics of US sports bettors:** about 70% male (Morning Consult), 72% male and 65% aged 25–44 (YouGov 2024 survey of current and prospective bettors), and 48% of men aged 18–49 hold an online sportsbook account (Siena, January 2025). DraftKings is the most-used sportsbook, at 35% of US bettors (YouGov 2024) [S, via search summaries; M]. Young men are the group most prone to risk-taking.
- **Stakes:** entries start at $1 (pays $1.80) [S: user]. Low stakes and free chips point to recreational risk appetite (Section 5.5).
- **Familiarity with head-to-head contests:** DFS head-to-head contests are a core DraftKings product. Some players will think "beat one opponent", which raises the Tactician and Closer shares relative to a casino population [A].

### 1.4 Community evidence about 21 Rivals: none yet

Searches for "21 Rivals", "DraftKings Rivals" and Reddit threads (2026-11-13) returned only the DraftKings launch post. No Reddit threads, reviews or strategy posts exist yet. That is expected three days after launch. A related patent, "Blackjack Duel" (US 2021/0398394; inventors Wikell, Bjorklund, Dahlin and Lindell of Växjö, Sweden), describes the same-cards duel format with 1,000 starting chips, time limits and skill-based matchmaking. It contains no behavioral data. **The game-specific evidence is therefore limited to the UI facts above. Everything about how 21 Rivals players actually bet is inferred from analogous settings.**

---

## 2. Taxonomy: why bet style and play skill are separate dimensions, plus modules

**Evidence that betting and playing are separable traits:**

- In Carlin & Robinson's (2009) Las Vegas table data, error rates are flat across bet sizes from $5 to $500: 9% at ≤$10, 8% at $11–20, 11% at $21–50, 9% at $55–100, 10% at $105–500. Only the $1,000+ bets were cleaner (3%) [S]. The passive-error share was 67–100% at every bet size [S]. How much people bet does not predict how well they play.
- Zender (2009) found higher-limit players' errors cost about half as much as low-limit players' (0.68% vs 1.18% of money wagered at the same Strip casino) [S]. That is a mild positive skill–stake correlation in a real-money casino. With free chips the correlation could reverse: big bets come from thrill-seekers, not from experienced high rollers [A].
- Bennis (2004) describes betting systems (progressions, the hot/cold table) and playing strategy ("pseudo-basic strategy") as separate belief systems, each with its own folk rules [S, qualitative].

**Decision:** model each opponent as **bet style (B1–B10) × play tier (P1–P3)**, plus side-bet, insurance, reference-point and timeout modules. Use a conditional distribution P(tier | style) to capture the mild correlations (Section 6.1).

**How this maps to the plan's list:**

| Plan archetype | Here | Why |
|---|---|---|
| Flat-min | B1 | Kept. It is rarer than in casinos because the default chip is 25 (Section 5.2). |
| Flat-mid (50–200) | **Split** into B2 Flat-small (25–75, default-driven) and B3 Flat-mid (100–250) | The UI default and REPLAY produce a distinct cluster at 25/50. Unit bettors at 100–200 behave differently, with 2–8× the per-hand swing of a 25–50 bettor. |
| Hero / all-in | B6 | Kept. |
| Martingale / chaser | B5 | Kept, with a break-even-targeting rule (Thaler & Johnson break-even effect; Andrade & Iyer). |
| Press-the-win | B4 | Kept, with a house-money slope (Zhang 2008) and a three-win stopping rule (Bennis 2004). |
| Protector | B8 | Kept, as a "lock the lead" threshold rule (Eil & Lien 2014; Jeopardy leaders). |
| Gut player | **Moved** to the play dimension as P3 Novice. The betting side of "gut" became B10 Erratic. | "Gut" describes play errors. Erratic sizing (Haghani & Dewey 2016) is a separate trait. |
| Last-hand shover | B7 Closer, plus hand-5 rules inside every style | The last-round effect is general (McKenzie et al. 2016), not confined to one type. |
| *(new)* | B9 Tactician | Sharp, contest-aware opponents exist (DFS crowd, early adopters) and matter for robustness. |
| *(new)* | B10 Erratic | Observed as its own pattern ("betting too small and then too big", Haghani & Dewey 2016). |

---

## 3. Bet-style archetypes

### 3.0 Conventions shared by all bet styles

- **Units.** Casual players think in absolute chips (25, 100), not fractions of the stack. Bets are given in chips unless marked "×S" (fraction of the current balance) [A; consistent with Jetter & Walker's 2017 anchoring on displayed values].
- **Snapping.** After computing a bet: if it is ≥ S − 5, make it S (all-in). Otherwise round to the nearest "round" value (multiples of 25 below 100, of 50 below 250, of 100 below 1,000, of 500 above). With probability 0.2, round to the nearest 5 instead (an exact count) [A]. When the intended all-in is an awkward number (say 1,135), use exactly S with probability 0.6 and round down to the nearest 100 with probability 0.4 (4+ chip taps are tedious) [A].
- **Feasibility.** Main bet plus side bets ≤ S (DECISIONS D9). An all-in player cannot double, split or insure, so the play policy must fall back to "hit/stand only" (D9).
- **Outcome classes** for the reaction rules: *win* (net > 0, including a double win), *blackjack* (net = +1.5·bet), *loss* (net < 0), *push* (net = 0). With a split, classify by the round's net result.
- **Noise.** On top of each style's discrete choices, multiply non-minimum bets by lognormal noise (σ = 0.15) before snapping [A]. Wagenaar's (1988) observation that the same gambler varies in the same situation supports stochastic rules.

---

### B1. Flat-min

**Behavior evidence**
- Small, constant wagers are a recognizable pattern. In a positive-EV coin game, some subjects chose "to bet small and constant wagers, apparently trying to reduce the probability of ruin and maximize the probability of ending up a winner" (Haghani & Dewey 2016) [S, qualitative]. That is exactly the min-bettor's logic in a winner-take-all game.
- Real-money tables cluster at the minimum: the modal bet in Carlin & Robinson's data was $10 (1,974 of 4,394 hands, 45%) [S/D].
- Inertia is the norm in app play: in an online casino game, players changed their stake on only 1.9% of rounds after a loss and 0.8% after a win, and "seemed to pick a certain amount and rarely changed the stake" (Chen et al. 2022) [S].
- Contest players often under-bet when behind ("Many players are reluctant to bet big when behind"; Curtis 1995) [S, anecdotal].

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Hand-1 bet | 10 (p=0.90); 25 (0.07); 50 (0.03) | 10 with p 0.8–0.97 | L | [A] |
| Same bet on hands 2–4 | p=0.90 (else 25: 0.07, 50: 0.03) | 0.8–0.97 | L | [A]; inertia from Chen et al. 2022 |
| Reaction to win / loss / push / blackjack | none (multiplier 1.0) | — | M | [A], definitional |
| Hand 5, behind (S < R): big bet | p=0.15; size ×S ∈ {1.0: 0.5, 0.5: 0.3, 0.25: 0.2} | 0.05–0.30 | L | [A]; last-round effect, Section 5.6 |
| Hand 5, ahead: big bet | p=0.02 | 0–0.05 | L | [A] |
| Side-bet class (never / occasional / habitual) | 0.75 / 0.20 / 0.05 | — | L | [A] |
| P(play tier P1 / P2 / P3) | 0.20 / 0.50 / 0.30 | — | L | [A] |

**21 Rivals translation.** With free chips and a P(win) objective, flat-min is a coherent "let the opponent bust" plan. It almost always ends within about ±50 of 1,000: 5 hands × 10 chips, a little more after doubles or splits, +15 per blackjack. Its P(win) is roughly the share of opponents who finish below that band, very roughly 45–55% against this spec's field [D, rough: 47% of the simulated field finishes above 1,000]. Two things shrink the share relative to casinos. First, the default chip is 25, so betting 10 takes intent. Second, many players feel that betting 10 on 5 hands is "not playing". Expect flat-min to be more common among cautious players, among those who misread the game as "lose as little as possible", and among people protecting a mental "win the entry back" frame.

**Share: 12% (6–25%), confidence L.** It is below the casino share of near-minimum bets (about 45%) because the UI defaults to 25 and the format rewards variance. It is not tiny, because "bet small and hope they bust" is an intuitive heuristic in winner-take-all contests.

---

### B2. Flat-small (default / rebettor)

**Behavior evidence**
- Defaults and displayed numbers anchor bets. Jeopardy! Daily Double wagers move about $29 per $100 increase in the clue's dollar value (elasticity about 0.3). More than half of wagers fall within $500 of the clue value, even though the average maximum wager available is $5,914 (Jetter & Walker 2017; 12,596 wagers) [S].
- The app's one-tap bet is 25, and REPLAY repeats the last bet in one tap (Section 1.2) [S].
- Inertia dominates in app play (Chen et al. 2022: stake changes on 1–2% of rounds) [S]. Blackjack forces a chip placement every round, so changes are more common than in slot-like games, but REPLAY lowers that cost [A].
- "Nearly all experienced players increase their bets after wins and decrease them after losses" (Bennis 2004) [S, qualitative]. So even "flat" bettors adjust sometimes.

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Hand-1 bet | 25 (0.55); 50 (0.30); 75 (0.10); 20 (0.05) | modal 25 | L | [A]; default-chip anchor |
| After a win: P(change) | 0.35 (else repeat via REPLAY) | 0.2–0.5 | L | [A]; tuned so the population shows net pressing (Section 5.4) |
| After a win, if changing (×previous) | ×2 (0.55), ×1.5 (0.35), ×0.5 (0.10) | — | L | [A]; direction from Zhang 2008 and Bennis 2004 ("increase after wins") |
| After a loss: P(change) | 0.30 (else repeat) | 0.15–0.45 | L | [A] |
| After a loss, if changing (×previous) | ×0.5 (0.60), ×2 (0.25), ×1.5 (0.15) | — | L | [A]; Bennis "decrease after losses", plus a chasing minority (Section 5.4) |
| After a push | repeat | — | M | [A] |
| After a blackjack | as after a win | — | L | [A] |
| Hand 5, behind: big bet | p=0.30; ×S ∈ {1.0: 0.5, 0.5: 0.3, 0.25: 0.2} | 0.15–0.45 | L | [A]; Section 5.6 |
| Hand 5, ahead: big bet | p=0.10; ×S ∈ {1.0: 0.3, 0.5: 0.4, 0.25: 0.3} | 0.03–0.2 | L | [A]; reference-independent last-round effect |
| Side-bet class | 0.55 / 0.30 / 0.15 | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.10 / 0.50 / 0.40 | — | L | [A] |

**21 Rivals translation.** This is the "I'm just playing blackjack" player: normal-feeling stakes, quick taps, little thought about the opponent. With the clock running and REPLAY available, repeating is cheap. Hand 5 is the one point where a third of them do something bigger.

**Share: 17% (10–28%), confidence L.** It is the largest single cluster because it follows from the lowest-effort path in the UI.

---

### B3. Flat-mid (unit bettor)

**Behavior evidence**
- Average stakes are moderate fractions of bankroll even among sophisticated subjects: 15% of bankroll on average in a positive-EV coin game (Haghani & Dewey 2016) [S]. A 100-chip "unit" (10%) is a natural round number for a 1,000 stack [A].
- Casino players' bets span a wide range (Carlin & Robinson: $5 to $1,100 at one table) [S]. A minority bet several times the table minimum. Zender's "common strategist" wagers 4–5× the minimum (Zender 2018) [S].

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Hand-1 bet | 100 (0.55); 200 (0.20); 50 (0.15); 150 (0.05); 250 (0.05) | modal 100 | L | [A] |
| P(change) after a win or loss, and the change multipliers | as B2 | — | L | [A] |
| Hand 5, behind: big bet | p=0.35; sizes as B2 | 0.2–0.5 | L | [A] |
| Hand 5, ahead: big bet | p=0.10 | 0.03–0.2 | L | [A] |
| Side-bet class | 0.55 / 0.30 / 0.15 | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.15 / 0.55 / 0.30 | — | L | [A] |

**21 Rivals translation.** Ten percent per hand feels like "real" risk with only 5 hands. These players produce final balances of roughly 500–1,500, so they are the main competitors for any strategy that aims to land "a bit above 1,000".

**Share: 11% (5–20%), confidence L.**

---

### B4. Presser (positive progression / house money)

**Behavior evidence**
- **Field evidence from blackjack tables.** Among 71 Las Vegas players (3,675 hands), winning the previous hand raised the next bet by **0.25–0.30 betting units** (unit = the player's modal bet; t ≈ 8–9; robust to individual fixed effects). Cumulative winnings raised bets by **0.08 units per unit won** (house money), while cumulative losses raised them by only 0.02 per unit (break-even; not significant with fixed effects) (Zhang 2008, Stanford honors thesis) [S].
- **Ethnography.** "Nearly all experienced players increase their bets after wins and decrease them after losses, often with the explicit justification that they are hot." Positive progressions are "far more common in blackjack than Martingale", and stopping rules such as "return to the base bet after three wins" are common. Players see betting big with house money as correct ("You have to bet big when you get some money from the casino") (Bennis 2004) [S, qualitative].
- **Roulette field data.** After a win, players covered 13.62 numbers versus 9.21 after a loss (+48%), and placed 1.53 versus 1.38 outside bets (+11%). 80% of the players who quit did so right after a losing spin (Croson & Sundali 2005; 139 players, 24,131 bets) [S].
- **Online casino, blackjack.** The next bet rose 13.5% per standard deviation of the prior win (BC PlayNow data, 2,000 typical gamblers). This is confounded by prior bet size (Zhang et al. 2024) [S].
- **Baccarat field data.** Bets increase with streak length, and more after winning streaks. Multiple and long-shot bets rise after winning streaks (Abe et al. 2021; 7.9M games, 3,986 players) [S, abstract].
- **Lab: framing.** In a two-stage betting frame, risk-taking is higher after gains (house money). In a portfolio frame it is higher after losses (Weber & Zuchel 2005) [S]. 21 Rivals is a betting frame.
- **Lab: computer blackjack.** Recent wins, combined with control over a skill-relevant choice, increased bet size (Chau & Phillips 1995; 12 Hong Kong undergraduates playing for money) [S, abstract; small sample].

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Base bet | 25 (0.25); 50 (0.35); 100 (0.30); 200 (0.10) | — | L | [A] |
| After a win: next = previous × | 2.0 (0.45, "let it ride" / 2x button); 1.5 (0.30); 1.0 (0.20); reset to base (0.05) | mean ×1.6 (1.3–1.9) | L–M | [A], scaled so the population mean matches Zhang 2008 (Section 5.4) |
| After the 3rd consecutive win | reset to base with p=0.40, else as above | 0.2–0.6 | L | [S, qualitative: Bennis 2004]; p is [A] |
| After a loss | base (0.70); ×0.5 (0.15); keep (0.15) | — | L–M | [A]; Bennis 2004 |
| After a push | keep | — | M | [A] |
| After a blackjack | as after a win; the 1.5× payout feeds the house-money term | — | L | [A] |
| House-money slope | +0.08 chips per chip above R | 0.03–0.15 | M | [S: Zhang 2008, β₁ = 0.08 units/unit] |
| Soft cap | if bet > 0.5·S, cap at 0.5·S with p=0.8 | — | L | [A] |
| Hand 5, behind | all-in with p=0.40 | 0.2–0.6 | L | [A] |
| Hand 5, ahead | keep pressing (rules above) with p=0.6; switch to base with p=0.4 | — | L | [A]; Eil & Lien 2014 (staying ahead) |
| Side-bet class | 0.45 / 0.35 / 0.20 | — | L | [A]; thrill-seeking correlation |
| P(tier P1 / P2 / P3) | 0.15 / 0.55 / 0.30 | — | L | [A] |

**21 Rivals translation.** The PLAY 2x button and the ≥100-profit celebrations make pressing a one-tap, rewarded habit. Free chips feel like house money from the first hand (Section 5.5). Each win is shared with the opponent (same cards, unless decisions diverge), so a Presser's balance swings up exactly when the opponent's does. After a shared win the Presser bets bigger, which raises the variance of the comparison. Winning hands 1–3 (about 0.43³ ≈ 8% of matches [D]) can grow a 50 base into a 400 bet on hand 4.

**Share: 16% (8–25%), confidence L–M.** Pressing is the best-documented dynamic among table-game players. It is held below 20% here because most players are flat (inertia) and because online data show loss-chasing as well (B5).

---

### B5. Chaser (martingale / break-even seeker)

**Behavior evidence**
- **Online data.** In BC's PlayNow casino, the next blackjack bet rose **28.5% per standard deviation of the immediately prior loss** (roulette 60%, slots 25%), while cumulative losses reduced bets (−3% per SD for blackjack, an affordability effect) (Zhang et al. 2024) [S]. Caveat: the model does not control for the previous bet, so "big loss → big next bet" partly reflects persistence.
- **Lab, planned vs actual.** When planning, people bet less after an anticipated loss. After an actual loss they bet significantly more than planned. According to the press release, 40% of losers deviated from their plan and 90% of those bet more, so about 36% of losers escalated beyond plan [D] (Andrade & Iyer 2009) [S: abstract and press release].
- **Break-even effect.** After a loss, gambles that offer a chance to get back to even become attractive (Thaler & Johnson 1990) [S, direction]. In the commonly cited problem versions, about 40% accept a fair coin flip after a $30 loss, versus 70–77% after a $30 gain, and about 60–70% take a gamble that can restore break-even [S, secondary blog summary; **not verified against the original paper**]. Among experienced online poker players: strong evidence of a "break-even effect", with more risk and aggression while losing within a session (Eil & Lien 2014) [S]. Players play looser after a big loss than after a big win, and the share increases with loss size (Smith, Levere & Kurtzman 2009). For example, in 6-max games 135 players loosened after big losses versus 68 after big wins [S, via PokerNews summary]. CBOT traders with morning losses were about 16% more likely to take above-average afternoon risk (Coval & Shumway 2005) [S].
- **Martingale beliefs.** "Quite a few participants felt that some sort of doubling down, or Martingale betting strategy, was optimal" (Haghani & Dewey 2016) [S]. In live blackjack, however, martingale and chasing are "not common" and "explicitly condemned" by experienced players. Two of about 75 players admitted chasing (Bennis 2004) [S].
- **Unrealized losses invite risk.** After a paper (unrealized) loss, people take more risk. After a realized loss, they avoid risk (Imas 2016) [S]. Inside a 21 Rivals match, losses are unrealized until the match ends.

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Base bet | 25 (0.30); 50 (0.35); 100 (0.30); 10 (0.05) | — | L | [A] |
| After a loss: next = previous × | 2 (0.65, via REPLAY + 2x); 1.5 (0.15); 3 (0.05); 1 (0.15) | — | L | [A] |
| If the doubled bet exceeds S | all-in (0.6); else repeat the previous bet (0.4) | — | L | [A] |
| After a win | base (0.8); keep (0.2) | — | L | [A] |
| After a push | keep | — | M | [A] |
| Break-even targeting (h ≥ 4 and S < R) | with p=0.5, bet (R − S) + base | 0.3–0.7 | L | [A]; Thaler & Johnson break-even effect |
| Hand 5, behind | with p=0.6: break-even target (half the time) or all-in (half the time) | 0.4–0.8 | L | [A] |
| Side-bet class | 0.55 / 0.30 / 0.15 | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.10 / 0.50 / 0.40 | — | L | [A] |

**21 Rivals translation.** REPLAY then 2x makes doubling two taps. Five hands cap a martingale at four doublings (base 50 → 800). The classic martingale signature appears: most Chasers finish slightly above 1,000, and a few lose heavily. Under the spec, 62% of Chasers end above 1,000 [D]. Shared losses, such as a dealer blackjack or a dealer 20 that beats everyone, push Chasers to double exactly when the opponent also lost. That matters for predicting the opponent's next bet.

**Share: 8% (3–15%), confidence L.** The range is wide because the sources disagree: online records show strong reactions to immediate losses, while live blackjack players condemn martingale (see Section 5.4). The point estimate sits at half the Presser share because the best-quantified live blackjack source shows net pressing (Zhang 2008).

---

### B6. Hero (early all-in)

**Behavior evidence**
- **All-in is common even when it is clearly bad.** With a 60% coin, a $25 stake, 30 minutes and a $250 cap, **18 of 61 (30%) finance-literate subjects bet their entire bankroll on one flip** at some point. 28% went bust; only 21% reached the cap (Haghani & Dewey 2016) [S].
- **Lottery appetite.** Long-shot betting is popular, and sports bettors favor parlays. Abe et al. (2021) find that long-shot bets rise after winning streaks [S]. The share of parlay bets among DraftKings users was not found in this search.
- **Free chips feel like house money.** Gains are segregated and feel like house money (Thaler & Johnson 1990). Less transparent or less "real" money is spent more readily ("Monopoly money", Raghubir & Srivastava 2008: scrip is spent more freely than cash of the same face value) [S].
- **Contest culture.** In a $500 buy-in mini-tournament, "the whole table had the betting bug" (Curtis 1995) [S, anecdotal]. On TV elimination blackjack, players went all-in "on the crowd's urging" and made "ego-driven" maximum bets (Kaplan 2006, Cigar Aficionado) [S, anecdotal].

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Hand-1 bet (×1,000) | 1.0 (0.45); 0.5 (0.30); 0.3 (0.15); 0.15 (0.10) | P(all-in on hand 1) 0.3–0.6 | L | [A]; Haghani & Dewey all-in prevalence |
| If S ≥ 1,500 after a swing (redrawn each hand) | protect, bet 10 (0.5); big, 0.5·S (0.3); moderate, 0.15·S (0.2) | — | L | [A]; Eil & Lien 2014 (ahead → less risk) |
| If 10 ≤ S < 1,000 | ×S: 1.0 (0.35); 0.5 (0.25); 0.2 (0.40) | — | L | [A]; break-even |
| If 1,000 ≤ S < 1,500 | 0.2·S | — | L | [A] |
| Hand 5, behind | all-in, p=0.8 | 0.6–0.95 | L | [A] |
| Side-bet class | 0.35 / 0.35 / 0.30 | — | L | [A] |
| P(big side bet ≥ 100 chips \| a side bet placed) | 0.10 | 0.03–0.25 | L | [A]; the app has no side-bet cap (DECISIONS D8) |
| P(tier P1 / P2 / P3) | 0.05 / 0.40 / 0.55 | — | L | [A] |

**21 Rivals translation.** "Free chips, one opponent: double up or go home." All-in on hand 1 is two taps. A Hero who wins one hand at about 2,000 beats most of the field, so the heuristic isn't crazy. An all-in also removes doubling and splitting from that hand (D9). That forces hit/stand play and makes the Hero's result on the hand depend mainly on hit/stand choices. Under the spec, 44% of Heroes end bankrupt and 16% end at 2,000 or more [D].

**Share: 10% (4–20%), confidence L.** The anchor is the 30% who went all-in at least once in a positive-EV game with real money. Here chips are free and the horizon is 5 hands, but a real entry fee is at stake. Only a third of all-in behavior is assigned to this early type; the rest sits in B7, B10 and the hand-5 rules.

---

### B7. Closer (last-hand shover)

**Behavior evidence**
- **Last-round effect.** In three lab experiments simulating a racing day (the first two played for points with no money), the probability of choosing the long shot was **+19 percentage points higher in the last round** (+11 pp after controlling for a rising trend). In Experiment 2, the long-shot choice in round 8 was 69% when round 8 was the last round versus 56% when it was not (+17 pp in regression). The effect was **largely reference-independent**: "Winning or losing, bettors prefer to 'go out with a bang'" (McKenzie et al. 2016) [S].
- **Field.** Long-shot betting increases in the last race of the day: McGlothlin (1956, 9,605 races), Ali (1977, 20,247 harness races), Metzger (1985, 11,313 races) [S, as reviewed by McKenzie et al. 2016]. **Conflicting:** a large 1992–2001 US dataset (Snowberg & Wolfers 2010) reportedly shows no end-of-day effect [S, via secondary summary; not verified].
- **Catch-up when behind** (break-even effect: Thaler & Johnson 1990; Eil & Lien 2014) [S].
- **Tournament practice.** Experts advise trailing players to bet the maximum late ("When in doubt, put it out"), while amateurs are "reluctant to bet big when behind" (Curtis 1995) [S, anecdotal]. So many casual players under-shove relative to the optimum, and the Closer is the subset who shove.
- **Visible-score analog.** In Final Jeopardy!, leaders without a lock wager to cover second place 86% of the time (136 of 158 games, Season 24; J! Archive) [S], and trailers often over-bet (The Jeopardy! Fan analysis) [S, qualitative]. In 21 Rivals the score is hidden, so this kind of reasoning has to run against R = 1,000.

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Base bet, hands 1–4 | 10 (0.35); 25 (0.40); 50 (0.25) | — | L | [A] |
| Hands 2–4 | after a win: 2× base with p=0.35, else base. After a loss or push: base | — | L | [A]; mild pressing |
| Hand 4, if S < 900 | 0.5·S with p=0.25 | 0.1–0.4 | L | [A] |
| Hand 5, behind (S < R) | all-in (0.65); 0.6·S (0.20); base (0.15) | P(≥ 0.5·S) 0.7–0.95 | L–M | [A]; break-even + last-round effect |
| Hand 5, ahead (S ≥ R) | all-in (0.25); bet 10 (0.50); 0.25·S (0.25) | P(all-in) 0.1–0.4 | L–M | [A]; McKenzie's reference-independent effect scaled to a +15–20 pp shift |
| Side bets | class 0.55 / 0.35 / 0.10. Occasional side-bettors place 70% of their side bets on hand 5 | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.20 / 0.55 / 0.25 | — | L | [A] |

**21 Rivals translation.** "Save it for the end." In a blind game the trigger is "I'm below 1,000", which is ambiguous: a player at 980 may shove even though the field's median is about 1,000. The hand-5 shove is often a fixed plan formed before the match, which is why it fires even when the player is ahead. Every Closer's hand-5 result is driven by the same shared hand, so a dealer bust on hand 5 sends all shovers to about 2× their stack.

**Share: 12% (6–20%), confidence L–M.** The last-round effect is among the best-replicated findings here. The specific share of committed "Closers" is judgment.

---

### B8. Protector (lead locker)

**Behavior evidence**
- Experienced poker players "reduce effort and risk-taking" when ahead within a session (Eil & Lien 2014) [S].
- Jeopardy! leaders bet to secure the lead (86% cover bets; J! Archive) [S].
- Tournament advice for leaders is to match the trailer's bets or bet small, the "lock" logic (Wong 1992; Kaplan 2006) [S, prescriptive].
- Round-number goals: people work harder just below round thresholds (.300 hitters, SAT retakes; Pope & Simonsohn 2011) [S, contested by a later SABR replication]. Lock thresholds are likely to be round (+100, +200) [A].

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Base bet, while not locked | 100 (0.4); 200 (0.3); 50 (0.2); 300 (0.1) | — | L | [A] |
| Lock threshold T (lock when S ≥ R + T) | 50 (0.2); 100 (0.4); 200 (0.3); 300 (0.1) | — | L | [A]; round numbers |
| Bet once locked (sticky for the rest of the match) | 10 (0.8); 25 (0.2) | — | L | [A] |
| If S < 1,000 | base (0.6); break-even target (R − S) + base (0.4) | — | L | [A] |
| Hand 5, behind | all-in with p=0.5 | 0.3–0.7 | L | [A] |
| Side-bet class | 0.75 / 0.20 / 0.05 | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.25 / 0.55 / 0.20 | — | L | [A] |

**21 Rivals translation.** In a blind match the Protector cannot know whether +100 is enough, so the threshold is a guess anchored on round numbers. Protectors produce a cluster of final balances at 1,050–1,350 (71% finish above 1,000 under the spec [D]). That cluster is a natural target for a strategy that aims to clear it.

**Share: 5% (2–10%), confidence L.**

---

### B9. Tactician (contest-aware)

**Behavior evidence**
- Professionals respond to rank incentives by taking more risk when underperforming, while students do not respond (Kirchler, Lindner & Weitzel 2018; 657 professionals and 432 students) [S]. Rank-aware risk management is a learned skill, so it is rare among casual players.
- In two-person risk-taking tournaments, lab subjects mostly followed the theory's predictions on correlation and leads (Nieken & Sliwka 2010) [S, abstract]. Subjects raise risk when contest targets are hard (Gaba & Kalra 1999) [S, abstract]. Some people reason correctly about contest structure.
- Final Jeopardy! betting is mostly rational, but best-response failures rise with complexity (Metrick 1995) [S, abstract].
- The DraftKings audience includes DFS players who think in terms of field distributions [A].

**Quantified parameters** (a heuristic stand-in for a sharp human. The real stress test is `robust.py`.)

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Hands 1–4 bet (×S) | 0.05 (0.3); 0.10 (0.4); 0.15 (0.3) | — | L | [A] |
| Hand 5 | S < 1,100: ×S 1.0 (0.5) or 0.6 (0.5). S ≥ 1,300: 10. Otherwise 0.35·S. | — | L | [A] |
| Reference model | shared-outcome estimate of the opponent, p=0.8 | — | L | [A] |
| Variance-seeking play when behind on hand 5 | p_var_dev = 0.5 (double and split more often; Section 4.2) | 0–1 | L | [A]; tournament practice (Wong 1992; Kaplan 2006: "doubling down with many hands players wouldn't normally double on") |
| Insurance and side bets | used as variance tools by state: buys variance when behind, sheds it when ahead | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.70 / 0.30 / 0.00 | — | L | [A] |

**21 Rivals translation.** This player is what the project itself is building. They exist from day one (the user is one) and their share grows as strategy content spreads. They matter mostly for robustness: they break strategies that exploit naive Closers.

**Share: 4% (1–10%), confidence L.**

---

### B10. Erratic (gut bettor)

**Behavior evidence**
- "Participants generally [were] very erratic with their fractional betting patterns, betting too small and then too big." The average bet was 15% of bankroll, with no convergence over time (Haghani & Dewey 2016) [S].
- The same gambler varies in the same situation (Wagenaar 1988, as reviewed by Massaro) [S].
- Hot/cold and "luck" beliefs drive bets in ways that look random from outside (Bennis 2004; Keren & Wagenaar 1985) [S, qualitative].

**Quantified parameters**

| Parameter | Point | Range | Conf. | Source / label |
|---|---|---|---|---|
| Each hand: P(all-in) | 0.10 | 0.05–0.2 | L | [A] |
| Otherwise bet = S·f, with log f ~ Uniform(log 0.01, 0) | — | — | L | [A] |
| Side-bet class | 0.35 / 0.35 / 0.30 | — | L | [A] |
| P(tier P1 / P2 / P3) | 0.05 / 0.40 / 0.55 | — | L | [A] |

**21 Rivals translation.** Mobile, distracted, "feel" players. They add tail mass at both ends (26% bankrupt and 14% at 2,000+ under the spec [D]).

**Share: 5% (2–10%), confidence L.**

---

## 4. Play-skill tiers

### 4.0 What the literature says about real players' play errors

| Source | Setting | Key numbers |
|---|---|---|
| Carlin & Robinson 2009 | Las Vegas table, 6 decks, S17, DAS, Bally MP-21 recognition data. 4,394 hands, 1,393 rounds | About 10% of hands contain an error (396 of 4,287 single-hand deals = 9.2% [D]). **80% of errors are passive** (failing to hit, double or split) even though basic strategy calls for passive action only 46% of the time. Basic-strategy followers won 48.1% of hands, deviators 36.6%. Passive errors lost more than $2 per $1 won. After any player at the table doubled down in the prior round, a given error was 12–15 pp more likely to be passive. **No player bought insurance in the entire sample.** [S] |
| Zender 2009 (Casino Enterprise Management) | 7 casinos (Las Vegas, Detroit, Oregon, Atlantic City), 7,584 hands | 901 errors = **11.9% of hands** (including insurance and surrender), "1 in 8.5 hands". An error costs 7% of that hand's wager on average. Average error cost **0.83%** of money wagered (±0.06): downtown Las Vegas 0.94%, Strip 0.93%, Atlantic City 0.55%, Detroit 0.54%, Oregon 1.28%. High-limit players 0.68% vs low-limit 1.18%. Surrender misused on 4.4% of hands where offered. [S] |
| Griffin 1987, via Zender 2009 | Atlantic City, Las Vegas, Reno, Tahoe. 11,024 observations | 1,718 errors (**15.6%** [D]). Error factor **1.41%** (Atlantic City 1.13%, Las Vegas 1.67%). Griffin put the "uninformed tourist" at about 3%. [S] |
| Keren & Wagenaar 1985 | 112 regular players, Amsterdam | 44% of errors were failing to take a card; 16% were taking a card in error. Poor insurance play against an ace. [S, **secondary only**: Psychology Today blog. Original not accessed] |
| Wagenaar 1988 (as reviewed by Massaro) | Amsterdam casinos | Hard 13: players hit **50%** of the time against a dealer 2 and **8%** against a 6 (basic strategy: stand on both). "In general, players tend to stand when they should hit." The same player chooses differently in the same situation. [S] |
| Bennis 2004 | About 75 players, Indiana riverboat casinos, 1999 ethnography | "Not one used the basic strategy consistently." "Nearly all players take even money"; "a clear majority stand on 16 against a dealer's 10". Insuring good hands (19/20) is common, but "never take insurance" is "perhaps equally or more common". [S, qualitative] |
| Zender & Uyal (billzender.com, posted 2026) | Industry estimate | Good players 5–10% of customers (+0.4%), "common" strategists about 85–90% (+0.8%), "WTF" players about 5% (+1.2%). Common errors: standing on 12 vs 2/3, too few doubles and splits, insurance with a blackjack. [S, practitioner estimate] |
| Las Vegas Advisor reader poll 2017 | 1,031 self-selected readers (an advantage-play audience) | 22% claim perfect basic strategy, 13% an abbreviated version, 7% hunches. [S; not representative] |

**Conflicts.** Error rates per hand range from 9% (Carlin & Robinson) through 12% (Zender) to 16% (Griffin). Cost ranges from 0.8% (Zender) and 1% (Grosjean 2000, via Zender) through 1.4% (Griffin) to the old rule of thumb of 2–3%. Insurance ranges from zero takers in Las Vegas (Carlin & Robinson) to near-universal even money in Indiana (Bennis). These differences likely reflect place, era and population. I calibrate P2 to the middle of the range and keep the extremes as sweep bounds.

### 4.1 Calibration method

No source gives error probabilities by situation, except Wagenaar's two hard-13 numbers and Bennis's qualitative ones. I set per-situation probabilities and tuned them with a simulator until the aggregates matched the sources. The simulator (`scratchpad/calc/errsim3.py`, not part of the repo) uses an infinite deck, S17, dealer peek, DAS, one split, playable split aces, no surrender and 3:2 blackjack. It plays each tier on common random numbers against a basic-strategy twin over 400,000 hands.

| Tier | Hands with ≥1 error | EV cost vs basic strategy (% of initial bet) | Passive share of errors | Targets |
|---|---|---|---|---|
| P1 Solid | 1.8% | 0.19% | 76% | Zender's "good" players add 0.2–0.4% |
| P2 Casual | 12.6% | 1.22% | 83% | Carlin 9.2% / Zender 11.9% / Griffin 15.6% of hands; cost 0.83–1.41%; Carlin 80% passive |
| P3 Novice | 28.3% | 3.42% | 84% | Griffin's "uninformed tourist" about 3% |
| *Pure never-bust* (hit hard ≤11 and soft ≤17, no doubles or splits) | — | 5.6% (EV about −6.1%) | — | Sub-mode of P3 [D] |
| *Pure mimic-the-dealer* (hit ≤16 including soft, stand 17+) | — | 5.0% (EV about −5.6%) | — | Commonly cited at about 5.5% [D] |

The basic-strategy baseline came out at −0.42% ± 0.18% per hand, consistent with DECISIONS' −0.39% ± 0.15% at 6 decks.

Where the casual tier's errors come from, as a share of all hands [D]: standing on stiffs vs 7–A 6.2%; hitting stiffs vs 2–6 1.6%; missed soft doubles 1.0%; standing on 12 vs 2/3 0.7%; missed splits other than A/8 0.6%; standing on soft 18 vs 9–A 0.5%; missed double on 9 0.5%, on 11 0.5%, on 10 0.4%; standing on soft 17 0.2%; splitting tens 0.2%.

### 4.2 Per-situation error parameters (the play-tier spec)

Each row is the probability, at each decision point that fits the row (two-card or multi-card), that the player takes the listed wrong action instead of basic strategy. Draw independently at every decision. That independence is the noise model (Wagenaar's inconsistency finding).

| Situation (basic-strategy action) | Error action | P1 Solid | P2 Casual | P3 Novice | Anchor |
|---|---|---|---|---|---|
| Hard 16 vs 10 (H) | Stand | 0.06 | **0.45** | **0.75** | Bennis: "a clear majority stand" among experienced players. Population average under the spec ≈ 0.50 [D] |
| Hard 12/13/14/15/16 vs T (H), base rates | Stand | .01/.01/.02/.03/.06 | .08/.12/.18/.26/.45 | .30/.40/.55/.65/.75 | Error rises as the total approaches 16 and the upcard approaches 10 (Bennis; Keren & Wagenaar) |
| Upcard multiplier for the row above (7/8/9/T/A) | × | .6/.8/1/1/1 | .5/.65/.85/1/.9 | .7/.8/.95/1/.95 | [A] |
| Hard 12 vs 2 / vs 3 (H) | Stand | .05/.03 | .45/.35 | .70/.65 | Zender & Uyal: a "common" error ("never hit a busting hand vs a bust card") |
| Hard 13 vs 2/3/4/5/6 (S) | Hit | .01 | .30/.18/.10/.06/.05 | **.50**/.30/.18/.10/**.08** | Wagenaar: 50% hit 13 vs 2 and 8% vs 6 → P3 |
| Hard 14 / 15–16 vs 2–6 (S) | Hit | .01 | 13-row × 0.6 / × 0.4 | 13-row × 0.7 / × 0.5 | [A] |
| Hard 12 vs 4/5/6 (S) | Hit | .02 | .15/.10/.08 | .30/.22/.20 | [A] |
| Hard 17–18 (S) | Hit | 0 | .005 | .02 | [A] |
| 11 vs 2–8 (D) | Hit (miss the double) | .01 | .08 | .30 | [A]; "skipping a double on 11" is often cited as a common costly miss |
| Multiplier on missed doubles vs 9/T | × | 2.0 | 1.8 | 1.5 | [A] |
| 10 vs 2–9 (D) | Hit | .02 | .12 | .40 | [A] |
| 9 vs 3–6 (D) | Hit | .05 | .45 | .85 | [A] |
| 11 vs A (H under S17) | Double | .50 | .60 | .50 | [A]. Costs almost nothing. |
| 10 vs T/A; 9 vs 2 or 7+; 8 vs 5–6 (H) | Double | .02/.02/0 | .08/.05/.02 | .15/.10/.05 | [A] |
| Soft doubles A2–A7 vs weak upcards (D) | Hit, or stand on A7 | .08 | .55 | .90 | Zender & Uyal: "less aggressive with double downs" |
| Soft 18 vs 9/T/A (H) | Stand | .08 | .60 | .85 | Widely called the most-misplayed soft hand (practitioner sources) |
| Soft 17 (H, or D vs 3–6) | Stand | .01 | .15 | .45 | P3 mimics the dealer, who stands on soft 17 |
| Soft 13–16 (H) | Stand | 0 | .02 | .10 | [A] |
| A,A (P) | Don't split | 0 | .03 | .15 | [A] |
| 8,8 vs 9/T/A (P) | Don't split; play as 16 | .05 | .25 | .55 | [A] |
| 8,8 vs 2–8 (P) | Don't split | .01 | .06 | .30 | [A] |
| Other basic-strategy splits (2s, 3s, 6s, 7s, 9s, 4s vs 5–6) | Don't split | .08 | .40 | .70 | Zender & Uyal: "less aggressive with … splits" |
| 10,10 (S) | Split | .005 | .02 | .08 | [A] |
| Endgame variance seeking (behind on hand 5 with a big bet) | Extra doubles/splits beyond basic strategy, with probability p_var_dev | 0 (Tactician 0.5) | 0 | 0 | [A]; tournament practice (Section 3, B9) |

When a missed split leads to playing the pair as a hard total, apply the same tier's hard-total rows (for example, 8,8 played as 16). When doubling is illegal (all-in, or the double rule in 4.7), basic strategy falls back to the no-double action and the "miss the double" rows don't apply.

### 4.3 P1 Solid

- **Evidence:** Zender's 5–10% "good" players (+0.4%) and the 22% of a self-selected advantage-play audience claiming perfect basic strategy [S]. The "skill contest" branding attracts people who study [A].
- **Parameters:** column P1 in 4.2. Insurance 0.01 without a blackjack and 0.10 with one (Section 4.6).
- **21 Rivals translation:** with free chips and a P(win) objective, some solid players will knowingly deviate to buy or shed variance (that is B9). The plain P1 player just plays basic strategy.
- **Share: 16% (8–25%), confidence L–M.** Higher than Zender's casino 5–10% because of the skill framing and an engaged early-adopter crowd. Lower than the LVA poll because that audience is advantage players.

### 4.4 P2 Casual (folk basic strategy)

- **Evidence:** the casino average (Carlin & Robinson; Zender; Griffin), "pseudo-basic strategy" (Bennis), regret-driven omission bias (Carlin & Robinson: errors of omission are four times as common as errors of commission).
- **Parameters:** column P2 in 4.2. Insurance 0.06 without a blackjack and 0.45 with one.
- **21 Rivals translation:** the stakes are free chips, but the objective is real money, so regret avoidance (Carlin & Robinson's mechanism) should survive [A]. The on-screen totals remove counting mistakes [S: client]. The missing tutorial means DraftKings players get no prompt about doubles or splits [S: client].
- **Share: 50% (35–65%), confidence M.** It is the majority type in every casino source.

### 4.5 P3 Novice / gut

- **Evidence:** Griffin's "uninformed tourist" (~3%); Wagenaar's hard-13 pattern; the never-bust and mimic-the-dealer folk strategies described by Wagenaar (reviewed as costing about 8% and 6%; my simulation gives about 5.6% and 5.0% under these rules); Zender & Uyal's "WTF" players.
- **Parameters:** column P3 in 4.2. Insurance 0.15 without a blackjack (×2 holding hard 19–20, ×0.5 holding a stiff, following Bennis's "insure good hands") and 0.55 with one. **Optional sub-modes**, each a fraction of P3: 15% *pure never-bust* and 10% *pure mimic-the-dealer*, with 5% per-decision noise toward the P3 table [A].
- **21 Rivals translation:** many DraftKings sports bettors in these states play blackjack rarely. Expect more novices than on a Las Vegas table. Totals are displayed, which helps a little.
- **Share: 34% (20–50%), confidence L–M.** Well above Zender's casino 5%, because the casino population self-selects for blackjack experience and this one does not. The tier's cost (3.4%) matches Griffin's estimate for the "uninformed tourist" (about 3%), which sits well above his whole-sample average of 1.41%.

### 4.6 Insurance and even money

| Parameter | P1 | P2 | P3 | Range | Conf. | Basis |
|---|---|---|---|---|---|---|
| P(take insurance), dealer ace, no player blackjack | 0.01 | 0.06 | 0.15 | 0–0.30 | L | Carlin & Robinson: 0 takers in about 107 ace-up rounds (≈1,393/13 [D]; roughly 340 player-hands at about 3.15 players per round [D]). Bennis: insuring 19/20 common for some, "never insure" equally common. Zender & Uyal: "hunches" on insurance. The 21 Rivals popup makes the option salient [A]. |
| Hand multiplier (hard 19–20 / stiffs) | ×1 | ×2 / ×0.5 | ×2 / ×0.5 | — | L | Bennis: "only when it makes sense. If I have a 19 or a 20" |
| P(take insurance), player blackjack vs ace (= even money) | 0.10 | 0.45 | 0.55 | 0.2–0.9 | L | Bennis: "nearly all players take even money" (Indiana). The app labels it "INSURANCE?", not "even money", so fewer will recognize the "sure thing" [A] |

Behavioral note for the engine: the player's first two cards are shared, so **both players face the same insurance decision** on the same blackjack-vs-ace hand. Divergent choices always create a balance difference: the insurer gets +1 bet, while the non-insurer gets +1.5 if the dealer has no blackjack and 0 (push) if the dealer does.

### 4.7 Rule caveat that changes the play model

The client build says "Double available when player shows 9, 10 or 11". If production matches:

- Soft doubles are impossible. Basic strategy changes (A7 stands vs 2–8 and hits 9–A; A2–A6 just hit), and the "missed soft double" and "over-double 8 vs 5–6" rows disappear. P2's error rate falls by about 1 pp of hands [D].
- Add a `double_totals: frozenset[int] | None` flag to `RulesConfig` (None = any two cards). Test it in free play: try doubling a soft 18 against a 5.

---

## 5. Cross-cutting findings (apply to all archetypes)

### 5.1 Reference point: 1,000, and judging "ahead/behind" without seeing the opponent

- **Evidence.** Prior outcomes are evaluated against a reference point; gains are segregated as "house money" and losses invite break-even gambles (Thaler & Johnson 1990). The starting stack is the natural status-quo reference (Kahneman & Tversky 1979, standard prospect theory). In Zhang's (2008) blackjack data, gains and losses relative to the buy-in drive bets asymmetrically (β = 0.08 vs 0.02) [S]. Round numbers act as goals (Pope & Simonsohn 2011) [S, contested].
- **Blind format [A].** Most players cannot form an estimate of the opponent, so they fall back on 1,000. A minority realizes that the opponent got the same dealer and the same first cards ("the dealer busted, so they probably won too"). An even smaller minority considers that the field's typical final balance is about 1,000.

| Parameter | Point | Range | Conf. | Label |
|---|---|---|---|---|
| P(R = 1,000) | 0.80 | 0.6–0.95 | L | [A] |
| P(R = 1,000 + U(50, 250), pessimist) | 0.10 | 0–0.2 | L | [A] |
| P(R = shared-outcome estimate of the opponent) | 0.10 overall (0.8 for B9, 0.05 for others) | 0.03–0.25 | L | [A] |
| Shared-outcome estimate | R_est = 1,000 + Σ_k r_k·b̂_k, where r_k is the hand-k net outcome per unit for a basic-strategy player on the shared cards and b̂_k = 50 is an assumed typical opponent bet | — | L | [A] |
| Dead zone for "behind" | behind if S < R − δ, with δ ~ U(0, 30) | — | L | [A] |

### 5.2 Round numbers and UI defaults

- **Evidence.** Wagers anchor on displayed values (elasticity about 0.3) and cluster near them (Jetter & Walker 2017) [S]. The app's default chip is 25 and the chips are 5/10/25/100/500/1000 [S: client]. REPLAY and 2x make repetition and doubling cheap [S: client].
- **Parameters.** Use the snapping rules in 3.0. Target the population's hand-1 bets to fall about 80% on {10, 25, 50, 75, 100, 150, 200, 250, 500, 1000} [A]. When a player doubles their previous bet, assume they used the 2x button with p = 0.7 [A]. The button also doubles any side bets already placed [S: client], so a player who carried a side bet forward with REPLAY doubles it too.

### 5.3 Bet inertia

- **Evidence.** Stake changes happen on 1–2% of rounds in an online casino game (Chen et al. 2022) [S]. Live blackjack players adjust more, but around a mode (Zhang 2008 uses the modal bet as the unit) [S]. The large bwin tracking datasets report only aggregates, such as a median of 49 bets of €4 per playing day and median losses of 5.5% of wagers, with the top 5% placing 188 bets of €25 (LaBrie et al. 2008) [S, abstract]. They say nothing about bet changes from hand to hand, so they don't constrain these parameters.
- **Parameter.** For flat styles, P(repeat) = 0.65–0.9. Across the whole population, the spec gives P(next bet = previous bet) ≈ 0.54 over hands 2–5 [D: `mixsim_v3.py`, before bet noise]. Plausible real range: 0.5–0.8 [A]. Pressers, Chasers, Heroes, Erratics and Tacticians change bets by design.

### 5.4 Outcome-contingent bet changes: targets for the whole population, and the conflicts

| Quantity | Evidence | Target for the simulated population |
|---|---|---|
| Next bet after a win, vs after a loss or push | +0.25–0.30 of a modal-bet unit after a previous-hand win (Zhang 2008, Las Vegas) [S]. +13.5% per SD of prior win (online blackjack, confounded; Zhang et al. 2024) [S]. Roulette: +11% (outside) to +48% (inside numbers) after a win (Croson & Sundali 2005) [S] | **Spec produces +0.10 units** (bet level after a win minus after a non-win, hands 2–4, in units of the player's median bet) [D: `mixsim_v3.py`]. That is a third of the Las Vegas effect, because online data also show chasing and 5-hand players follow plans. **Sweep 0 to +0.30.** Median change 0 |
| Next bet after a loss | +28.5% per SD of prior loss (online blackjack, confounded) [S]. About 36% of losers bet more than planned (Andrade & Iyer 2009) [S/D]. Live blackjack: chasing rare (Bennis 2004) [S] | Mean change after a loss ≈ −0.05 to +0.25; heavy right tail from Chasers [A] |
| Effect of cumulative gains | +0.08 units per unit ahead (Zhang 2008) [S]. +2% per SD (online blackjack; Zhang et al. 2024) [S] | Built into B4. Others 0 [A] |
| Effect of cumulative losses | +0.02 units per unit behind, not significant (Zhang 2008) [S]. −3% per SD online (affordability) [S]. Strong break-even effect in poker (Eil & Lien 2014) [S] | Mostly through end-of-match rules (B5, B7) [A] |
| Effect of streaks | Gambler's fallacy only after streaks of 5+ in roulette (Croson & Sundali 2005); 85% of bets go against a streak of 6+ [S] | Ignore within 5 hands, apart from hot-hand pressing (B4) [A] |

**Conflicts, reported rather than resolved.** (1) Pressing (Bennis, Zhang 2008, Croson & Sundali, Abe et al. at long streaks) versus chasing (Zhang et al. 2024 immediate losses, Andrade & Iyer, Smith et al. in poker, Abe et al. at short streaks). (2) House money for casual gamblers (Thaler & Johnson; Zhang 2008) versus "staying ahead" for experienced players (Eil & Lien 2014). The spec therefore keeps both Presser (16%) and Chaser (8%) plus Protector (5%), makes the flat styles lean toward pressing, and treats **the Presser:Chaser ratio as a top sensitivity parameter.** Calibration note: an earlier draft with Presser 14% / Chaser 10% and symmetric flat-style changes produced **no** net pressing (−0.01 units). That contradicted the best-quantified live blackjack source (Zhang 2008) and the ethnographic consensus (Bennis 2004), so the spec was retuned.

### 5.5 Free chips with a real prize: house money, the realization effect and contest incentives

- **House money.** Free chips are the purest form of "house money" (Thaler & Johnson 1990) [S]. Less "real" currency is spent more freely (Raghubir & Srivastava 2008) [S]. Expect larger average bets than casino habit would suggest.
- **But the stakes are real.** The match result pays money ($1.80 on a $1 entry). In Kirchler et al. (2018), rank incentives changed professionals' risk-taking but not students' [S]. For casual players, the "contest" frame may not change bet sizing much beyond the house-money effect [A].
- **Unrealized losses.** Within the match, losses stay unrealized until the end, which promotes break-even risk-taking (Imas 2016) [S].
- **Net assumption [A]:** the average hand-1 bet is about 8–12% of the stack (casino norm: 2–5% of a trip bankroll per hand [A]; Haghani & Dewey's +EV coin game: 15%). That is what the spec produces (about 11%) [D].

### 5.6 The last hand: end-of-match risk shift

- **Evidence.** Last-round long-shot preference rises by 11–19 pp, partly independent of being ahead or behind (McKenzie et al. 2016) [S]. Field last-race effects in older data, contested in newer data [S]. The break-even effect when behind [S]. Experts shove more than amateurs (Curtis 1995) [S, anecdotal].
- **What the spec produces [D: `mixsim_v3.py`]:** 95% of players are still alive on hand 5. Of those, **25% bet at least half their stack and 19% go all-in**, and 84% of these big hand-5 bettors are behind 1,000. Hand-5 side bets also rise (Closers). Plausible real range for the hand-5 big-bet rate: 10–35% [A].
- **Hand 4** shows a smaller pre-shift (Closer hand-4 rule; Chaser break-even targeting from h ≥ 4).

### 5.7 Shared shocks: dealer blackjack, dealer bust, shared player blackjack

Because the first two cards are shared, a **player blackjack is shared** (both players get it). A dealer blackjack (after the peek) costs both players their main bet, unless one insured. A dealer bust pays everyone who didn't bust. Under the sequential-shoe default (DECISIONS D4), the dealer's draws can differ between the two players once their decisions diverge.

- **Reaction rules [A]:** after a dealer blackjack, apply each style's loss rule. In addition, "hot/cold believers" (Bennis: "many players bet low when they believe … the dealer is hot") halve their next bet with p = 0.15. This applies to B2, B3 and B4.
- **Evidence:** Carlin & Robinson found no significant change in error rates after a prior-round blackjack. There was a marginal increase in passive errors (+10 pp given an error), the "hot table" effect [S]. No data exist on bet reactions to a dealer blackjack specifically.
- **Engine relevance:** after a shared shock, the opponent's balance change is largely predictable (same sign, proportional to their bet), and their next bet follows their style's win or loss rule.

### 5.8 Time pressure and the clock

- **Budget.** 360 s for 5 rounds is 72 s per round [S]. Client animation and display time is roughly 6–12 s per round: deal animations of about 400 ms per card, banners of 1.5–2.5 s, win celebrations of 3.5–5 s (skippable) [D: client]. A human needs about 15–30 s per round for a bet and 2–4 decisions [A]. So the clock rarely binds, and most players should finish with 1–3 minutes to spare [D/A].
- **Evidence.** Time pressure leaves risk attitudes for gains unchanged and increases risk aversion for losses, with more weight on break-even probabilities (Kocher, Pahlke & Trautmann 2013) [S]. There is qualified support for more risk-seeking for gains under time pressure (Young et al. 2012) [S]. Time pressure was a manipulated factor in simulated blackjack betting (Phillips & Amrhein 1989) [S, abstract only].
- **Parameters [A]:** P(timeout) = 0.01 per match (range 0.002–0.03), hazard concentrated on hands 4–5. Timing out sets the balance to 0 [S: client]. No other time effect by default. Optional sensitivity: 10% of players are "rushed" and get +20% on P3-style error probabilities.

### 5.9 Side bets

**Odds under these rules [D: exact combinatorics, `scratchpad/calc/sidebets.py`].**

| Decks | Perfect Pairs: P(perfect / colored / mixed) | P(any pair) | Perfect Pairs EV per unit | 4 Card Total: P(36–37 / 38–39 / 40+) | P(any 4CT win) | 4 Card Total EV per unit |
|---|---|---|---|---|---|---|
| 1 | 0 / 1.96% / 3.92% | 5.88% | −47.1% | 6.76% / 4.25% / 2.81% | 13.8% | −10.6% |
| 2 | 0.97% / 1.94% / 3.88% | 6.80% | −22.3% | 6.83% / 4.36% / 3.04% | 14.2% | −6.9% |
| 6 | 1.61% / 1.93% / 3.86% | 7.40% | **−6.11%** | 6.88% / 4.43% / 3.19% | 14.5% | **−4.49%** |
| 8 | 1.69% / 1.93% / 3.86% | 7.47% | −4.10% | 6.88% / 4.44% / 3.20% | 14.5% | −4.19% |

Both side bets depend only on the first four cards, which are shared, so **both players always get the same side-bet result**. Divergence comes only from stake size.

**Uptake evidence.** Casino "utilization" (the share of main-game players who also bet the side bet): about 15% is the minimum acceptable, 25% a conservative projection for 21+3 at a locals casino, and about 50% or more a success (Zender 2021, GGB) [S]. A typical 21+3 bet is $8 (table range $5–$50) and "usually less than the main bet" [S]. Example customer: $20 main and $5 side (Zender 2018) [S]. Side bets attract players who want more "gamble" (Zender 2021) [S, qualitative]. I found no data on online or app uptake.

| Parameter | Point | Range | Conf. | Label |
|---|---|---|---|---|
| Side-bet class shares (never / occasional / habitual) | 54% / 31% / 15% (by style, Section 6.1) | habitual 5–30% | L | [A/D] |
| P(side bet on a hand), occasional class | 0.25 (Closers: 70% of these on hand 5) | 0.1–0.4 | L | [A] |
| P(side bet on a hand), habitual class | 0.90 (REPLAY carries it forward) | 0.7–1 | L | [A] |
| Which side bet | Perfect Pairs only 0.40; 4 Card Total only 0.30; both 0.30 | — | L | [A]; Perfect Pairs is the familiar casino bet |
| Side-bet size | 10 (0.45); 25 (0.35); 50 (0.10); 100+ (0.10, mostly B6/B10) | — | L | [A]; 25 is the default chip. Side-bet minimum unconfirmed (D8) |
| P(side bet ≥ 25% of S) | 0.02 per side bet overall; 0.10 for B6; 0.05 for B10; state-dependent for B9 | — | L | [A]; no cap (D8) |
| Implied population share of hands with a side bet | ≈ 21% | 10–35% | L | [D]; consistent with casino utilization of 15–30% |

### 5.10 Gambler's fallacy and hot hand over a 5-hand horizon

- **Evidence.** In roulette, the gambler's fallacy appears only after streaks of 5 or more (85% of bets go against a streak of 6+); the "hot hand" in one's own outcomes appears after single wins (Croson & Sundali 2005). The two biases correlate across individuals (Sundali & Croson 2006) [S]. In blackjack betting the gambler's fallacy "plays almost no role", while hot-hand pressing is the norm (Bennis 2004) [S]. In the coin experiment, people bet on tails after strings of heads (Haghani & Dewey 2016) [S].
- **Parameter.** No separate gambler's-fallacy module. Hot-hand behavior lives in B4 and in the "after a win" change rules [A].

### 5.11 Smaller effects

- **Rebound after aggressive play.** After any player at the table doubled down in the prior round, errors were more likely to be passive (+12–15 pp given an error; Carlin & Robinson 2009) [S]. Optional: after the player's own losing double, scale passive-error probabilities by ×1.15 on the next hand [A].
- **Win celebrations** appear only for profit ≥ 100 [S: client]. Hypothesis [A]: they reinforce bets of 100 or more after a celebrated win, much as slot-machine audiovisual "win" cues reinforce play. Optional parameter: +10% on the next bet after a celebrated win for B2, B3 and B4. Unvalidated.
- **Big wins and losses in poker**: players play looser after big losses (Smith et al. 2009) [S]. This is covered by B5 and B7.

### 5.12 Free play versus paid contests

Use free-play logs with caution: opponents in free mode have nothing at stake. Expect more Heroes and Erratics and fewer Flat-min players [A, by analogy with hypothetical-versus-real incentive results, e.g. Holt & Laury (2002), standard references]. Keep separate population weights for free and paid play.

---

## 6. Population mix: "the DraftKings field"

### 6.1 Joint distribution of bet style and play tier

| Style | Share | P(P1) | P(P2) | P(P3) | Side-bet class (never / occasional / habitual) |
|---|---|---|---|---|---|
| B1 Flat-min | 0.12 | 0.20 | 0.50 | 0.30 | 0.75 / 0.20 / 0.05 |
| B2 Flat-small | 0.17 | 0.10 | 0.50 | 0.40 | 0.55 / 0.30 / 0.15 |
| B3 Flat-mid | 0.11 | 0.15 | 0.55 | 0.30 | 0.55 / 0.30 / 0.15 |
| B4 Presser | 0.16 | 0.15 | 0.55 | 0.30 | 0.45 / 0.35 / 0.20 |
| B5 Chaser | 0.08 | 0.10 | 0.50 | 0.40 | 0.55 / 0.30 / 0.15 |
| B6 Hero | 0.10 | 0.05 | 0.40 | 0.55 | 0.35 / 0.35 / 0.30 |
| B7 Closer | 0.12 | 0.20 | 0.55 | 0.25 | 0.55 / 0.35 / 0.10 |
| B8 Protector | 0.05 | 0.25 | 0.55 | 0.20 | 0.75 / 0.20 / 0.05 |
| B9 Tactician | 0.04 | 0.70 | 0.30 | 0.00 | state-dependent |
| B10 Erratic | 0.05 | 0.05 | 0.40 | 0.55 | 0.35 / 0.35 / 0.30 |
| **Marginal** | 1.00 | **0.16** | **0.50** | **0.34** | **0.54 / 0.31 / 0.15** |

Correlations [A]: free-chip thrill-seekers (B6, B10) skew toward novices, and contest-aware types (B9, B8, B7) skew toward better play. This is a reversal of the casino pattern, where high-limit players make fewer errors (Zender 2009).

### 6.2 Implied population moments [D: from `mixsim_v3.py` (session scratchpad), 200,000 simulated players, independent hands; not observed data]

| Quantity | Value |
|---|---|
| Hand-1 bet: 10 / 11–50 / 51–200 / 201–999 / all-in | 15.5% / 44.6% / 28.5% / 6.2% / 5.1% |
| P(any bet ≥ 500 chips during the match) | 32.5% |
| P(alive on hand 5); P(hand-5 bet ≥ 50% of stack \| alive); P(hand-5 all-in \| alive) | 94.8%; 24.6% (84% of them behind 1,000); 18.6% |
| P(next bet = previous bet), hands 2–5 | 54% (before bet noise) |
| Bet level after a win minus after a non-win (hands 2–4, units of the player's median bet) | +0.10 (Zhang 2008 Las Vegas: +0.25–0.30) |
| P(bankrupt by the end) | 13.9% |
| P(final > 1,000) | 46.9% |
| Final balance quantiles (10th / 25th / 50th / 75th / 90th) | 0 / 800 / 1,000 / 1,170 / 1,700; mean 995 |
| By style: P(bankrupt), P(final > 1,000), P(final ≥ 2,000) | B1 2.0%, 44.8%, 0.6% · B2 4.5%, 43.8%, 1.6% · B3 7.2%, 43.3%, 4.0% · B4 11.6%, 41.4%, 3.9% · B5 7.9%, 61.5%, 0.8% · B6 44.1%, 42.2%, 16.1% · B7 21.9%, 50.9%, 8.5% · B8 11.7%, 70.9%, 0.6% · B9 17.2%, 52.0%, 6.6% · B10 26.4%, 36.2%, 14.0% |

Use these as **implementation checks**. Fable's `archetypes.py` should reproduce them within a few percentage points when hands are drawn independently. Exact agreement isn't expected: the check simulation had no lognormal bet noise and a cruder snapping rule than Section 3.0. These are not predictions with known accuracy.

---

## 7. Implementation notes for the programmer

### 7.1 Suggested parameter schema

All probabilities are floats in [0, 1]. Distributions are lists of `(value, prob)` pairs that sum to 1. Amounts are chips unless the name says `_frac`. Defaults are the point estimates above.

```python
from dataclasses import dataclass, field
Dist = list[tuple[float, float]]          # (value, probability)

@dataclass(frozen=True)
class ReferenceModel:
    p_fixed_1000: float = 0.80
    p_pessimist: float = 0.10              # R = 1000 + U(lo, hi)
    pessimist_range: tuple[int, int] = (50, 250)
    p_shared_estimate: float = 0.10        # R estimated from shared outcomes
    assumed_opp_bet: float = 50
    behind_deadzone: tuple[int, int] = (0, 30)

@dataclass(frozen=True)
class SideBetParams:
    cls_probs: tuple[float, float, float] = (0.54, 0.31, 0.15)   # never / occasional / habitual
    p_hand_occasional: float = 0.25
    p_hand_habitual: float = 0.90
    which: Dist = field(default_factory=lambda: [("pp", .40), ("4ct", .30), ("both", .30)])
    size: Dist = field(default_factory=lambda: [(10, .45), (25, .35), (50, .10), (100, .10)])
    p_big_frac: float = 0.02               # side bet >= 25% of S
    hand5_concentration: float = 0.0       # e.g. 0.7 for Closers' occasional bets

@dataclass(frozen=True)
class EndgameRule:                         # applied on hand 5 (and hand 4 where noted)
    p_big_if_behind: float
    big_frac_if_behind: Dist               # fractions of S
    p_big_if_ahead: float = 0.0
    big_frac_if_ahead: Dist = field(default_factory=lambda: [(1.0, 1.0)])
    p_breakeven_target: float = 0.0        # bet (R - S) + base
    hand4_trigger: tuple[float, float, float] | None = None   # (S_threshold, prob, frac)

@dataclass(frozen=True)
class BetStyle:
    name: str
    share: float
    first_bet: Dist                        # chips, or fractions if first_bet_is_frac
    first_bet_is_frac: bool = False
    p_change_after_win: float = 0.35       # flat styles: P(apply on_win) after a win, else repeat
    p_change_after_loss: float = 0.30      # flat styles: P(apply on_loss) after a loss, else repeat
    on_win: Dist = field(default_factory=lambda: [(1.0, 1.0)])     # multipliers on previous bet;
    on_loss: Dist = field(default_factory=lambda: [(1.0, 1.0)])    # use the sentinel value -1 for "reset to base"
    on_push: Dist = field(default_factory=lambda: [(1.0, 1.0)])
    reset_after_n_wins: tuple[int, float] | None = None            # (n, prob), e.g. (3, 0.40)
    house_money_slope: float = 0.0         # extra chips per chip above R
    soft_cap_frac: tuple[float, float] | None = None               # (frac of S, prob applied)
    if_over_balance_allin_prob: float = 0.6
    lock: tuple[Dist, Dist] | None = None  # (threshold T dist, locked bet dist) for Protector
    endgame: EndgameRule | None = None
    allin_hazard: float = 0.0              # per hand (Erratic)
    noise_sigma: float = 0.15
    p_tier: tuple[float, float, float] = (0.16, 0.50, 0.34)        # P1, P2, P3
    sidebet_cls: tuple[float, float, float] = (0.54, 0.31, 0.15)

@dataclass(frozen=True)
class PlayTier:
    name: str
    share: float
    err: dict[str, float]                  # keys in 7.3; values are probabilities
    upcard_scale: dict[int, float]
    double_miss_vs_9T_mult: float
    p_insure_no_bj: float
    insure_hand_mult: dict[str, float]     # {"hard19_20": 2.0, "stiff": 0.5}
    p_insure_with_bj: float
    p_var_dev: float = 0.0                 # endgame variance-seeking deviations
    submodes: Dist = field(default_factory=list)   # e.g. [("never_bust", .15), ("mimic", .10)]
    submode_noise: float = 0.05

@dataclass(frozen=True)
class Population:
    styles: list[BetStyle]
    tiers: list[PlayTier]
    reference: ReferenceModel
    p_timeout: float = 0.01
    timeout_hands: Dist = field(default_factory=lambda: [(4, .4), (5, .6)])
```

Each opponent draws its style, then its tier from `style.p_tier`, then its side-bet class and reference model **once per match**. Per-decision randomness comes from the RNG stream assigned to that opponent, independent of the shoe stream, so that common-random-number comparisons stay valid.

### 7.2 Per-hand bet algorithm (pseudo-code)

```text
if h == 1: b = draw(first_bet) (× 1000 if frac)
else:      b = style_rule(prev_b, prev_outcome, S, h, history)   # repeat / on_win / on_loss / lock / hazard
b += house_money_slope * max(0, S - R)
apply soft cap; apply endgame (h == 5, or the hand-4 trigger); apply noise; snap; clamp to [10, S]
side bets: class → P(side bet this hand) → which → size; enforce main + side <= S
```

### 7.3 Play-error situation keys (for `PlayTier.err`)

`stand_stiff_hi[12..16]`, `stand_12_lo[2,3]`, `hit_stiff_lo[(t,u)]`, `hit_17_18`, `fail_double_{9,10,11}`, `over_double_{11A,10,9,8}`, `fail_soft_double`, `stand_soft18_hi`, `stand_soft17`, `stand_soft_low`, `fail_split_{A,8_hi,8_lo,other}`, `split_tens`. These match the calibration script `errsim3.py` (in this agent's session scratchpad, not in the repo, and it may not persist). Everything needed is in the Section 4.2 tables, so copy them from there. Apply errors on top of the solver's basic-strategy action **for the legal action set** (no doubling when all-in or when a double rule forbids it).

### 7.4 Parameters that most deserve sensitivity sweeps (in priority order)

1. **Low-variance versus high-variance share.** (B1 + B2) against (B6 + B7 + B10). This sets the shape of the field's final-balance distribution: the cluster near 1,000 against the mass at 0 and the right tail. Sweep B1 from 5% to 30% and B6 from 3% to 20%.
2. **Hand-5 behavior.** `p_big_if_behind` across styles (scale all of them by ×0.5 to ×1.5), and the reference-independent `p_big_if_ahead` (0 to 0.3).
3. **Presser:Chaser ratio** (from 3:1 to 1:2). This decides how the field reacts to shared wins and shared losses.
4. **Hand-1 all-in rate** (2% to 12%).
5. **Side-bet uptake and size**, including the rare large side bet. These are shared-outcome variance; the engine should test the tails.
6. **Play-tier mix** (P3 from 20% to 50%). This moves the field's EV drift (about −1% to −3% of total action).
7. **Even-money / insurance-with-blackjack rate** (0.2 to 0.9). This creates divergence on shared blackjack-vs-ace hands.
8. **Reference model** (share of players using shared-outcome inference, 0% to 25%).
9. **P(timeout)** (0.2% to 3%). Each timeout is a free win for the other player.

### 7.5 Validation

- With hands drawn independently, the mixture should reproduce Section 6.2 within about ±3–5 percentage points (see the caveat there).
- With `PlayTier` errors applied over the solver's basic strategy, the simulated error rates and costs should match Section 4.1 (within ±1 pp of hands and ±0.2% of stake).
- Flat-min against Flat-min with the same tier and seed must tie every match only if their play is also mirrored (use the same decision RNG). This catches leaks of decision randomness into shoe randomness.

---

## 8. Open questions and what to calibrate from real play logs

1. **Is the opponent's final balance ever shown?** If the app reveals it after a match, log it every time. It is the single most informative quantity: the empirical CDF of opponents' final balances, plus the share at 0 (bankrupt), at exactly 1,000 and at round numbers. If only win/loss is shown, P(win | my final x) ≈ F_opp(x) conditional on the shared cards. Logging (my final balance, W/L/T, per-hand shared outcomes) lets an isotonic or Bayesian fit recover F_opp, especially if the user varies their own final balance on purpose.
2. **The double rule.** The client says "9, 10 or 11". Test a soft double in free play.
3. **Default chip and buttons in production.** Is the default 25? Are REPLAY and 2x present? These drive B2 and B4/B5 frequencies.
4. **Insurance and even-money frequencies** cannot be observed directly. They can be inferred if opponents' balances are shown on matches that had a blackjack against an ace.
5. **Side-bet minimum** (10 or 5?) and how often opponents use side bets. Inferable from final-balance granularity: payouts of 25:1, 12:1, 6:1, 2:1, 8:1 and 10:1 leave fingerprints.
6. **Free versus paid populations.** Keep separate weight vectors.
7. **Matchmaking.** If DraftKings uses skill or ELO matching (Low6's platform advertises "ELO matchmaking"; the Blackjack Duel patent claims skill matching), a winning player will face sharper opponents over time. Raise B9 and P1 shares as the user's record improves.
8. **Changes over time.** Expect B9 and P1 to grow as strategy content appears; re-check quarterly.
9. **Evidence I could not verify:** exact Thaler & Johnson percentages (blog summary only); Keren & Wagenaar's detailed tables (secondary only); the Snowberg & Wolfers finding of no end-of-day effect (secondary summary); the "14.6% of hands" figure attributed to Schiller & Gobet (2012) (not verified; not used).

**What to log per match** (extends `data/hand_log.csv`): match ID; entry fee; mode (free/paid); per hand: own bet, side bets, own cards, dealer cards, insurance offered/taken, own actions, net result; final balance; opponent's final balance if shown; W/L/T; time remaining at the end.

---

## 9. References

Verification status: **[R]** = I read the full text or the primary page; **[A]** = abstract or official summary only; **[2]** = secondary source only.

**Blackjack play and betting**
- Carlin, B. I., & Robinson, D. T. (2009). Fear and loathing in Las Vegas: Evidence from blackjack tables. *Judgment and Decision Making*, 4(5), 385–396. NBER WP 14955: <https://www.nber.org/papers/w14955.pdf> [R]
- Bennis, W. (2004). Blackjack playing strategies and beliefs: A view from the field. *Journal of Gambling Issues*, 10. doi:10.4309/jgi.2004.10.1. <https://cdspress.ca/?p=7756> (PDF: <https://cdspress.ca/wp-content/uploads/2022/07/Will-Bennis-.pdf>) [R]
- Bennis, W. M. (2004). *Experience, Values, Beliefs, and the Sociocultural Context in Gambling Decision Making: A Field Study of Casino Blackjack* (PhD dissertation, University of Chicago). <https://knowledge.uchicago.edu/records/xnyeb-ad025> [A]
- Keren, G., & Wagenaar, W. A. (1985). On the psychology of playing blackjack: Normative and descriptive considerations with implications for decision theory. *Journal of Experimental Psychology: General*, 114(2), 133–158. [2: via Carlin & Robinson 2009, and the Psychology Today "In Excess" blog post "Basic Instinct" (Oct 2013), <https://www.psychologytoday.com/us/blog/in-excess/201310/basic-instinct>]
- Wagenaar, W. A. (1988). *Paradoxes of Gambling Behaviour*. Hove: Erlbaum. Reviewed by D. W. Massaro, *American Journal of Psychology* (book review, pp. 290–296, c. 1989–90): <https://bpb-us-e1.wpmucdn.com/sites.ucsc.edu/dist/0/158/files/2018/12/Waganaar-27oga42.pdf> [R: review only]
- Zender, B. (2009). Player error factors in blackjack: How poor are poor players? *Casino Enterprise Management*, April 2009, 70–73. <https://wizardofodds.com/image/ask-the-wizard/how-poor-are-bj-players.pdf> [R] (cites Griffin, P. (1991), *Extra Stuff*, and Grosjean, J. (2000), *Beyond Counting*)
- Zender, B., & Uyal, A. Steps to determining an accurate mathematical house advantage for blackjack. billzender.com (posted 2026-01-27). <https://billzender.com/steps-to-determining-an-accurate-mathematical-house-advantage-for-blackjack/> [R]
- Zender, B. (2018). Shortcut for more accurate player ratings in blackjack. <https://billzender.com/shortcut-for-more-accurate-player-ratings-in-blackjack/> [R]
- Zender, B. (2021). Increasing blackjack revenue through blackjack side bets, Part 1. *GGB News*, Jan 26, 2021. <https://ggbmagazine.com/article/increasing-blackjack-revenue-through-blackjack-side-bets-part-1> [R]
- Zhang, Z. (2008). *Testing the House Money & Break Even Effects on Blackjack Players in Las Vegas* (Honors thesis, Stanford University, Dept. of Economics). <https://purl.stanford.edu/hs316gy2015> (PDF: <https://stacks.stanford.edu/file/druid:hs316gy2015/zhang_z_2008_honors_thesis.pdf>) [R]
- Chau, A. W., & Phillips, J. G. (1995). Effects of perceived control upon wagering and attributions in computer blackjack. *Journal of General Psychology*, 122(3), 253–269. [A]
- Phillips, J. G., & Amrhein, P. C. (1989). Factors influencing wagers in simulated blackjack. *Journal of Gambling Behavior*, 5, 99–111. doi:10.1007/BF01019757. <https://digitalcommons.montclair.edu/psychology-facpubs/224> [A]
- Las Vegas Advisor (2017). Reader poll on blackjack skills, Apr 5 – May 10, 2017. <https://www.lasvegasadvisor.com/poll/2017-04-05/> [R]
- Schiller, M. R. G., & Gobet, F. R. (2012). A comparison between cognitive and AI models of blackjack strategy learning. *KI 2012*, LNCS 7526, 143–155. <https://researchonline.lse.ac.uk/id/eprint/102844> [A; the 14.6% figure seen in a search snippet is not verified and not used]
- Speelman, R. C. (2016). *Using behavioral skills training to promote optimal blackjack strategies* (PhD dissertation, SIU Carbondale). <https://opensiuc.lib.siu.edu/dissertations/1265> [A]

**Bet dynamics, chasing and house money**
- Thaler, R. H., & Johnson, E. J. (1990). Gambling with the house money and trying to break even. *Management Science*, 36(6), 643–660. <https://ideas.repec.org/a/inm/ormnsc/v36y1990i6p643-660.html> [A; percentages via the blog <https://readingthemarkets.blogspot.com/2009/08/risk-aversion-gambling-with-house-money.html>, 2]
- Zhang, K., Rights, J. D., Deng, X., Lesch, T., & Clark, L. (2024). Within-session chasing of losses and wins in an online eCasino. *Scientific Reports*, 14, 20353. <https://doi.org/10.1038/s41598-024-70738-3> [R]
- LaBrie, R. A., Kaplan, S. A., LaPlante, D. A., Nelson, S. E., & Shaffer, H. J. (2008). Inside the virtual casino: A prospective longitudinal study of actual Internet casino gambling. *European Journal of Public Health*, 18(4), 410–416. <https://read.qxmd.com/read/18434382/inside-the-virtual-casino-a-prospective-longitudinal-study-of-actual-internet-casino-gambling> [A]
- Chen, Z., Doekemeijer, R. A., Noël, X., & Verbruggen, F. (2022). Winning and losing in online gambling: Effects on within-session chasing. *PLoS ONE*, 17(8), e0273359. <https://pmc.ncbi.nlm.nih.gov/articles/PMC9387854/> [R]
- Croson, R., & Sundali, J. (2005). The gambler's fallacy and the hot hand: Empirical data from casinos. *Journal of Risk and Uncertainty*, 30(3), 195–209. <https://www.stat.berkeley.edu/~aldous/157/Papers/croson.pdf> [R]
- Sundali, J., & Croson, R. (2006). Biases in casino betting: The hot hand and the gambler's fallacy. *Judgment and Decision Making*, 1(1), 1–12. <https://repository.upenn.edu/oid_papers/252> [A]
- Abe, N., et al. (2021). Effects of sequential winning vs. losing on subsequent gambling behavior: Analysis of empirical data from casino baccarat players. *International Gambling Studies*, 21(1), 103–118. doi:10.1080/14459795.2020.1817969. <https://repository.kulib.kyoto-u.ac.jp/dspace/handle/2433/270382> [A; co-authors not checked]
- Andrade, E. B., & Iyer, G. (2009). Planned versus actual betting in sequential gambles. *Journal of Marketing Research*, 46(3), 372–383. [A; 40%/90% from Berkeley Haas press release, 2: <https://newsroom.haas.berkeley.edu/research/uc-berkeley-marketing-professors-find-even-when-gamblers-predetermine-spending-budget/>]
- Imas, A. (2016). The realization effect: Risk-taking after realized versus paper losses. *American Economic Review*, 106(8), 2086–2109. doi:10.1257/aer.20140386 [A]
- Weber, M., & Zuchel, H. (2005). How do prior outcomes affect risk attitude? Comparing escalation of commitment and the house-money effect. *Decision Analysis*, 2(1), 30–43. <https://econpapers.repec.org/RePEc:inm:ordeca:v:2:y:2005:i:1:p:30-43> [A]
- Coval, J. D., & Shumway, T. (2005). Do behavioral biases affect prices? *Journal of Finance*, 60(1), 1–34. <https://ideas.repec.org/a/bla/jfinan/v60y2005i1p1-34.html> [A]
- Haghani, V., & Dewey, R. (2016). Rational decision-making under uncertainty: Observed betting patterns on a biased coin. SSRN 2856963 / arXiv:1701.01427. <https://arxiv.org/pdf/1701.01427> [R]
- Smith, G., Levere, M., & Kurtzman, R. (2009). Poker player behavior after big wins and big losses. *Management Science*, 55(9), 1547–1555. [A; counts via PokerNews <https://www.pokernews.com/strategy/changing-strategy-big-win-loss-regression-to-mean-26808.htm>, 2]
- Eil, D., & Lien, J. W. (2014). Staying ahead and getting even: Risk attitudes of experienced poker players. *Games and Economic Behavior*, 87, 50–69. <https://econpapers.repec.org/RePEc:eee:gamebe:v:87:y:2014:i:c:p:50-69> [A]
- Lambrecht, M. (2023, rev. 2025). More skill, less bias? Breaking down break-even effects in poker. Helsinki GSE Discussion Paper 10. <https://helsinkigse.fi/discussion-papers/discussio-paper-10-first-version> [2]
- Post, T., van den Assem, M. J., Baltussen, G., & Thaler, R. H. (2008). Deal or no deal? Decision making under risk in a large-payoff game show. *American Economic Review*, 98(1), 38–71. <https://econpapers.repec.org/RePEc:aea:aecrev:v:98:y:2008:i:1:p:38-71> [A]
- Gertner, R. (1993). Game shows and economic behavior: Risk-taking on "Card Sharks". *Quarterly Journal of Economics*, 108(2), 507–521. [A]

**End of session, tournaments and rank incentives**
- McKenzie, C. R. M., Sher, S., Müller-Trede, J., Lin, C., Liersch, M. J., & Rawstron, A. G. (2016). Are longshots only for losers? A new look at the last race effect. *Journal of Behavioral Decision Making*, 29, 25–36. <https://pages.ucsd.edu/~mckenzie/McKenzieetal2016JBDM.pdf> [R] (reviews McGlothlin 1956; Ali 1977; Metzger 1985)
- Snowberg, E., & Wolfers, J. (2010). Explaining the favorite–longshot bias: Is it risk-love or misperceptions? *Journal of Political Economy*, 118(4). [2: "no end-of-day effect" per Suhonen's summary]
- Wong, S. (1992). *Casino Tournament Strategy*. Pi Yee Press. [book; not read; cited for standard tournament principles]
- Wong, S. (1995). Blackjack tournament strategy. *Blackjack Forum*, XV(3). <https://www.lasvegasadvisor.com/gambling-with-an-edge/blackjack-tournament-strategy/> [R]
- Curtis, A. (1995). Beyond Wong: Professional casino tournament tips. *Blackjack Forum*, XV(3). <https://www.lasvegasadvisor.com/gambling-with-an-edge/beyond-wong-professional-casino-tournament-tips/> [R]
- Kaplan, M. (2006). Playing with the pros. *Cigar Aficionado*, May/June 2006. <https://www.cigaraficionado.com/article/playing-with-the-pros-8743> [R]
- Metrick, A. (1995). A natural experiment in "Jeopardy!". *American Economic Review*, 85(1), 240–253. <https://econpapers.repec.org/RePEc:aea:aecrev:v:85:y:1995:i:1:p:240-53> [A]
- J! Archive. Final Jeopardy! round statistics, Season 24. <https://www.j-archive.com/finalstats.php?season=24> [R]
- Jetter, M., & Walker, J. K. (2017). Anchoring in financial decision-making: Evidence from Jeopardy! *Journal of Economic Behavior & Organization*, 141, 164–176. IZA DP 10151: <https://www.iza.org/publications/dp/10151> [A]
- Kirchler, M., Lindner, F., & Weitzel, U. (2018). Rankings and risk-taking in the finance industry. *Journal of Finance*, 73(5), 2271–2302. <https://econpapers.repec.org/RePEc:bla:jfinan:v:73:y:2018:i:5:p:2271-2302> [A]
- Nieken, P., & Sliwka, D. (2010). Risk-taking tournaments: Theory and experimental evidence. *Journal of Economic Psychology*, 31(3), 254–268. <https://econpapers.repec.org/RePEc:eee:joepsy:v:31:y:2010:i:3:p:254-268> [A]
- Gaba, A., & Kalra, A. (1999). Risk behavior in response to quotas and contests. *Marketing Science*, 18(3), 417–434. <https://ideas.repec.org/a/inm/ormksc/v18y1999i3p417-434.html> [A]
- Pope, D., & Simonsohn, U. (2011). Round numbers as goals: Evidence from baseball, SAT takers, and the lab. *Psychological Science*, 22(1). <https://repository.upenn.edu/oid_papers/19/> [A; contested by a SABR replication]

**Time pressure, money form, incentives**
- Kocher, M. G., Pahlke, J., & Trautmann, S. T. (2013). Tempus fugit: Time pressure in risky decisions. *Management Science*, 59(10), 2380–2391. <https://econpapers.repec.org/RePEc:inm:ormnsc:v:59:y:2013:i:10:p:2380-2391> [A]
- Young, D. L., Goodie, A. S., Hall, D. B., & Wu, E. (2012). Decision making under time pressure, modeled in a prospect theory framework. *Organizational Behavior and Human Decision Processes*, 118(2), 179–188. <https://pmc.ncbi.nlm.nih.gov/articles/PMC3375992> [A]
- Raghubir, P., & Srivastava, J. (2008). Monopoly money: The effect of payment coupling and form on spending behavior. *Journal of Experimental Psychology: Applied*, 14(3), 213–225. <https://pubmed.ncbi.nlm.nih.gov/18808275/> [A]
- Holt, C. A., & Laury, S. K. (2002). Risk aversion and incentive effects. *American Economic Review*, 92(5), 1644–1655. [standard reference, cited for hypothetical vs real incentives; not re-read]
- Kahneman, D., & Tversky, A. (1979). Prospect theory: An analysis of decision under risk. *Econometrica*, 47(2), 263–291. [standard reference]

**21 Rivals, DraftKings and the player population**
- DraftKings Network (2026-11-10). 21 Rivals, DraftKings' new head-to-head card game, launches today. <https://dknetwork.draftkings.com/2026/11/10/21-rivals-draftkings-head-to-head-card-game-launch/> [R]
- Mini Win Games / Low6. "Rapid Blackjack" development client v0.1.1, branded "21 Rivals" for DraftKings. <https://ggskills-blackjack-dev.low6.com/> (page source inspected 2026-11-13) [R, primary]
- Low6 sales page (PvP tournaments, ELO matchmaking). <https://sales.low6.com/> [R]
- Wikell, J., Bjorklund, B., Dahlin, M., & Lindell, R. Blackjack Duel. US Patent Application 2021/0398394. <https://ipiq.io/patents/1210208> [R: summary page]
- Sports-bettor demographics: Morning Consult <https://pro.morningconsult.com/analysis/despite-widespread-legality-public-opinion-on-sports-betting-is-still-mixed>; YouGov via GGB <https://ggbnews.com/article/yougov-study-looks-at-sportsbook-demographics> and SBC Americas <https://sbcamericas.com/2024/04/26/yougov-sports-betting-report/>; Siena <https://sri.siena.edu/2025/02/18/22-of-all-americans-half-of-men-18-49-have-active-online-sports-betting-account/> [2: search summaries]

**Calculations by this agent** (outside the repo, in the session scratchpad; available on request): `sidebets.py` (exact side-bet odds), `errsim3.py` (play-tier calibration), `heur.py` (never-bust and mimic-the-dealer costs), `mixsim_v3.py` (population moments for the final spec; `mixsim.py` is the earlier draft described in Section 5.4).
