"""Monotonic match clock.

The simulator's `minute` keeps counting in first-half stoppage time (46', 47'...) and the second half
restarts at 45', so raw minutes overlap. The clock folds first-half stoppage into 45 ("45+2" -> 45),
which makes it non-decreasing over the event stream.
"""


def clock(minute: int, period: int) -> int:
    return min(minute, 45) if period == 1 else minute


def ev_clock(e: dict) -> int:
    return clock(e["minute"], e["period"])


def rec_clock(minute: int, t: float, half_time: float) -> int:
    """Clock for simulator records (goals, shots, reds) that carry t but no period."""
    return clock(minute, 1 if t <= half_time else 2)
