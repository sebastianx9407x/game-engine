# Match log

`hand_log.csv` holds real 21 Rivals hands: one row per hand, five rows per match. It feeds the deck-count estimate and the calibration of the opponent models.

The MATCH STATS screen at the end of a match shows each player's net result on every hand, so the opponent's numbers come straight from there. Leave a cell empty when you don't know it.

| Column | What to write |
|---|---|
| `match_id` | 1, 2, 3, … in the order played. |
| `date` | `YYYY-MM-DD`. |
| `mode` | `free` or `paid`. |
| `entry_fee` | Dollars; 0 for free play. |
| `hand` | 1 to 5. |
| `my_bet` | Main bet before any double or split. |
| `my_pairs_bet` | Perfect Pairs stake, 0 if none. |
| `my_total_bet` | 4-Card Total stake, 0 if none. |
| `my_cards` | Your cards in the order dealt, rank then suit: `Ks 7h 4d`. Ranks `A 2-9 T J Q K`, suits `s c h d`. After a split, separate the two hands with `/`: `8s Td / 8h 3c Ts`. |
| `dealer_cards` | Upcard first, then the hole card, then any draws. |
| `my_actions` | One letter per decision: `H` hit, `S` stand, `D` double, `P` split, `I` took insurance, `N` declined insurance. Example: `HS`. |
| `my_net` | Your number for the hand on the stats screen (side bets included). |
| `opp_net` | The opponent's number for the hand on the stats screen. |
| `notes` | Anything odd. |

Final balances are 1,000 plus the sum of the five nets, so they are not stored.

Do not put usernames in this file, yours or the opponent's: the repository is pushed to GitHub.

Suits matter. Seeing the same card twice in one round (same rank and suit) rules out a single deck, and how often it happens is what narrows down the deck count.
