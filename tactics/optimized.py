"""The optimiser's current best strategy, as a tactic.

It reads ``tactics/optimized_policy.pkl``, which is written by:

    python -m rivals.optimize.pipeline
"""

from pathlib import Path

from rivals.agents.optimal import PolicyAgent
from rivals.optimize.pipeline import load_policy

_POLICY = load_policy(Path(__file__).with_name("optimized_policy.pkl"))


class Tactic(PolicyAgent):
    def __init__(self):
        super().__init__(_POLICY, name="optimized")
