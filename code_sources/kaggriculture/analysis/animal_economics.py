"""Exact replay of _daily_refresh_animals to find the $-optimal feeding duty cycle
per animal type. Base yield fires on schedule regardless of feed status; only the
CARE bonus depends on being fed (and cared) on the right days. An animal dies after
2 consecutive unfed days.
"""
ANIMALS = {
    "GOOSE": {"interval": 1, "max_held": 4, "egg_price": 40},
    "COW":   {"interval": 2, "max_held": 6, "egg_price": 230},
    "SHEEP": {"interval": 3, "max_held": 6, "egg_price": 225},
}
WHEAT_COST = 30  # rough blended $/unit (grow tile-opportunity or buy price)
DAYS = 200       # long horizon steady-state


def simulate(interval, max_held, feed_pattern):
    """feed_pattern(day) -> bool (feed+care that day). Returns (total_units_produced_ignoring_cap,
    total_units_actually_banked_respecting_cap, wheat_used, alive)."""
    consecutive_unfed = 0
    pending = 0
    yield_units = 0
    produced_raw = 0
    banked = 0
    wheat = 0
    for day in range(DAYS):
        fed = feed_pattern(day)
        cared = fed  # always care when feeding (free action, no cost)
        if fed:
            wheat += 1
        if fed:
            consecutive_unfed = 0
        else:
            consecutive_unfed += 1
        if consecutive_unfed >= 2:
            return produced_raw, banked, wheat, False, day
        # next_day = day+1 production check (mirrors _daily_refresh_animals but we
        # index by "day" as the day being refreshed, i.e. day D's refresh determines
        # production landing on day D+1)
        if (day + 1) % interval == 0:
            base = 1
            bonus = pending if fed else 0
            produced_raw += base + bonus
            yield_units = min(max_held, yield_units + base + bonus)
            pending = 0
        if fed and cared:
            pending += 1
    return produced_raw, yield_units, wheat, True, DAYS


def sweep(name, cfg):
    print(f"\n=== {name} (interval={cfg['interval']}) ===")
    patterns = {
        "full (feed every day)":        lambda d: True,
        "every-other (feed even days)": lambda d: d % 2 == 0,
        "every-3rd (feed d%3==0)":      lambda d: d % 3 == 0,
        "feed on production-1 & prod":  lambda d, iv=cfg["interval"]: (d % iv == iv - 1) or (d % iv == 0 and iv == 1),
    }
    for pname, pat in patterns.items():
        produced, capped_or_banked, wheat, alive, died_day = simulate(cfg["interval"], cfg["max_held"], pat)
        rate_day = produced / DAYS
        rev = produced * cfg["egg_price"]
        cost = wheat * WHEAT_COST
        net = rev - cost
        status = "ALIVE" if alive else f"DIED day {died_day}"
        print(f"  {pname:<32} produced={produced:>4} ({rate_day:.2f}/day)  wheat={wheat:>4} "
              f"({wheat/DAYS:.2f}/day)  net=${net:>7,.0f}  {status}")


if __name__ == "__main__":
    for name, cfg in ANIMALS.items():
        sweep(name, cfg)

    print("\n--- key ratios (net $ per wheat spent) ---")
    for name, cfg in ANIMALS.items():
        full_p, _, full_w, _, _ = simulate(cfg["interval"], cfg["max_held"], lambda d: True)
        print(f"{name}: full-feed {full_p/DAYS:.3f} eggs/day/wheat-day, "
              f"${cfg['egg_price']*full_p/DAYS:.1f} revenue/day, "
              f"${cfg['egg_price']*full_p/full_w:.1f} $/wheat-unit")
