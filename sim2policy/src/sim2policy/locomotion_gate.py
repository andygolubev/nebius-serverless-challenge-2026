"""Whether an acceptance gate is one a good-enough policy can actually clear.

Episode evidence is a sample, not an exact measurement: MJX reductions on GPU
are not bit-deterministic and legged gait is chaotic, so the same checkpoint on
the same seed can survive 934 steps once and 610 the next time.  A gate that
demands an exact count of perfect episodes therefore measures luck as much as
quality.

The G1 flat gate made this concrete.  At the measured per-episode survival of
~0.80 it required 10 of 10 and final publication required 20 of 20, which pass
with probability 10.7% and 1.2% -- about 1 in 1000 for both.  No training budget
changes that arithmetic, so the campaign was unfundable before it started.

A gate is admissible here when a policy meeting its own declared reliability
would clear it more often than not.  That still rejects a bad policy: 18 of 20
at 0.80 reliability passes only 20.6% of the time.
"""

from __future__ import annotations

from math import comb

# A gate a good-enough policy fails more often than it passes is not a
# measurement, it is a coin toss with a bill attached.
MIN_GATE_PASS_PROBABILITY = 0.5


def gate_pass_probability(episodes: int, required: int, reliability: float) -> float:
    """Probability that ``required`` of ``episodes`` succeed at ``reliability``.

    Episodes are treated as independent Bernoulli trials, which is the intended
    reading of a multi-seed evaluation.
    """
    n = int(episodes)
    k = int(required)
    p = float(reliability)
    if n <= 0:
        raise ValueError("episode count must be positive")
    if not 0 <= k <= n:
        raise ValueError("required horizons must be between zero and the episode count")
    if not 0.0 <= p <= 1.0:
        raise ValueError("reliability must be a probability")
    return sum(comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k, n + 1))


def minimum_reliability_for(
    episodes: int, required: int, *, target: float = MIN_GATE_PASS_PROBABILITY
) -> float:
    """Smallest per-episode reliability at which a gate clears ``target``."""
    low, high = 0.0, 1.0
    for _ in range(200):
        middle = (low + high) / 2
        if gate_pass_probability(episodes, required, middle) < target:
            low = middle
        else:
            high = middle
    return high
