# 21 Rivals strategy engine

A simulation engine for DraftKings' 21 Rivals (head-to-head blackjack on shared cards). It looks for the way of betting and playing that most often finishes ahead of a human opponent.

- `docs/PLAN.md` is the original plan.
- `docs/DECISIONS.md` is what was actually built, every rule confirmed in the app, and why.
- `research/archetypes.md` is the research on how real opponents bet and play.

## Setup

```sh
python3.13 -m venv ~/.venvs/blackjack-engine
ln -s ~/.venvs/blackjack-engine .venv
.venv/bin/pip install -e ".[dev,notebooks]"
.venv/bin/python -m pytest
```

The environment lives outside this folder because iCloud breaks editable installs inside `~/Documents` (see D1a in `docs/DECISIONS.md`).

## Try an idea

Copy `tactics/_template.py`, change how it bets or plays, then score it against the simulated field:

```sh
.venv/bin/python -m rivals.evaluate tactics/my_idea.py
.venv/bin/python -m rivals.evaluate tactics/my_idea.py --vs tactics/flat_100.py   # against one tactic
```

## Find the best bet schedule

```sh
.venv/bin/python -m rivals.optimize.pipeline --matches 200000   # writes tactics/optimized_policy.pkl
.venv/bin/python -m rivals.evaluate tactics/optimized.py        # scores it on fresh matches
```

## Look things up

```python
from rivals.solver import solver_for, basic_chart

print(basic_chart().render())                      # basic strategy for the real rules
print(solver_for().evaluate("8s 8d", "Tc").actions)  # every action's EV and outcome odds
```

## Log real matches

Real hands go in `data/hand_log.csv`; the columns are described in `data/README.md`.

## Layout

| Path | What it holds |
|---|---|
| `rivals/rules.py` | Every rule, as one config object |
| `rivals/resolve.py` | Plays one round (the reference implementation) |
| `rivals/solver/` | Exact odds for every decision; basic strategy |
| `rivals/agents/` | The player interface, human opponent models, the optimised player |
| `rivals/match.py` | Head-to-head matches on shared shoes |
| `rivals/optimize/` | The opponent population and the bet-schedule search |
| `rivals/report/` | The strategy card |
| `tactics/` | Strategy ideas, one file each |
| `notebooks/` | Charts and validation |
