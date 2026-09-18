"""V250: audited C06 public-state policy with 60% sale reserve.

The only change from V239 is a live market rule: retain 60% of the C06
per-item reserve fraction before the final liquidation window.  This is
computed from current public market prices, town demand, shed load, and the
visible opponent supply; it is not an opponent-specific schedule.
"""
from whitebox.versions import v239_public_scenario_c06 as _c06

_c06.RESERVE_FRACTION = {
    item: float(value) * 0.60
    for item, value in _c06.RESERVE_FRACTION.items()
}


def whitebox_v250_public_scenario_sale60(obs):
    return _c06.agent(obs)

