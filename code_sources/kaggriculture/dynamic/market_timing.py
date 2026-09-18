"""Sale timing inside the day, and the order-slot queue.

Two resources the agent currently spends without pricing them: WHICH STEP a
sale is placed on, and which of the ten order slots it occupies.

THE STEP MATTERS, AND THE ENGINE SAYS EXACTLY HOW MUCH
-----------------------------------------------------
Within one step the engine runs `_process_market` and only then
`_town_consume`. So a sale placed at step s is quoted against the inventory
BEFORE that step's drain, and the same sale one step later is quoted after it:

    inv entering s+1  =  inv(s) + (our sale) - d_tick(i) * [s mod 4 == 0]

Shops consume every 4 steps and the town centre every 24, so the drain arrives
in ticks, not continuously. Holding a sale across a tick boundary is therefore
worth exactly the inventory that tick removed, priced at the book's local slope:

    gain_per_unit(i) = |P_i'(q)| * d_tick(i)

That is a closed form, and it ranks the products the OPPOSITE way round from the
suppression term. Suppression favours the books the town cannot refill; timing
favours the ones it refills hardest, because those are the ones whose tick is
large. The agent's `FRONT_RUN_ITEMS` is MELON, MILK, STRAWBERRY, WOOL -- and
MELON's tick is a fraction of a unit, so holding it gains almost nothing while
handing the opponent a free step to sell first.

THE QUEUE
---------
`MAX_ORDERS` is 10 per turn and an order costs one slot whatever its size, so
slots should go to the highest total value, not to a fixed priority list. This
changes neither WHAT is sold nor HOW MUCH -- only which sales get a slot when
more than ten compete, and which step they land on.

Holding is capped at 3 steps by construction (the shop tick is every 4), so this
can never become the open-ended metering that measured -32,749: the sale goes
out within one tick either way.
"""
from dynamic import market_model as MM

SHOP_INTERVAL = 4
CENTER_INTERVAL = 24
TURNS_PER_DAY = 24
TICKS_PER_DAY = TURNS_PER_DAY // SHOP_INTERVAL      # 6 shop ticks a day


def tick_drain(item, shops):
    """Units the town removes at one SHOP tick. The daily centre tick is
    handled separately because it lands only at step % 24 == 0."""
    n = 0
    for shop in shops:
        products = MM.SHOP_PRODUCTS.get(shop, ())
        if item in products:
            n += 2 if len(products) == 1 else 1
    return n


def drain_at(item, step, shops):
    """Exact units removed at `step`. Mirrors `_town_consume`."""
    take = 0
    if step % SHOP_INTERVAL == 0:
        take += tick_drain(item, shops)
    if step % CENTER_INTERVAL == 0 and item in MM.TOWN_CENTER_PRODUCTS:
        take += 1
    return take


def hold_gain(item, inventory, step, shops, max_hold=3):
    """Dollars per unit gained by holding this sale until after the next drain.

        gain = |P'(q)| * (units the pending ticks remove)

    Returns (gain_per_unit, steps_to_hold). Zero means sell now: the book is on
    the floor, the town does not want this product, or no tick lands inside the
    window.
    """
    slope = MM.slope(item, int(inventory))
    if slope <= 0.0:
        return 0.0, 0
    best_gain, best_k = 0.0, 0
    removed = 0
    for k in range(0, max_hold + 1):
        removed += drain_at(item, step + k, shops)
        if k == 0:
            continue
        g = slope * removed
        if g > best_gain:
            best_gain, best_k = g, k
    return best_gain, best_k


def timing_table(shops, inventories=None):
    """Per-product hold value at a given book. Diagnostic: this is the table
    that says which products `FRONT_RUN_ITEMS` should actually contain."""
    rows = []
    for item in MM.PRODUCTS:
        inv = (inventories or {}).get(item, MM.MARKET_I0 + 20)
        gain, k = hold_gain(item, inv, 1, shops)
        rows.append((item, MM.price(item, inv), MM.slope(item, inv),
                     tick_drain(item, shops), gain, k))
    rows.sort(key=lambda r: -r[4])
    return rows


def front_run_items(shops, inventories=None, threshold=1.0):
    """The products worth holding a step for, derived rather than listed."""
    return tuple(r[0] for r in timing_table(shops, inventories) if r[4] >= threshold)


# ------------------------------------------------------------------- queue

class Order:
    __slots__ = ("item", "qty", "unit_value", "hold", "detail")

    def __init__(self, item, qty, unit_value, hold=0, detail=None):
        self.item = item
        self.qty = int(qty)
        self.unit_value = float(unit_value)
        self.hold = int(hold)
        self.detail = detail or {}

    @property
    def value(self):
        return self.qty * self.unit_value

    def __repr__(self):
        return (f"<SELL {self.item} x{self.qty} @{self.unit_value:.0f} "
                f"hold={self.hold}>")


def schedule(candidates, step, shops, market_inv, n_slots=10, max_hold=3,
             hold_threshold=0.0):
    """Choose which sales to place THIS step, and which to hold a tick.

    `candidates` are orders the sell policy has already decided to make. This
    never adds one and never changes a quantity -- it only decides placement.

    Returns (place_now, deferred).
    """
    now, held = [], []
    for c in candidates:
        inv = int(market_inv.get(c.item, MM.MARKET_I0))
        gain, k = hold_gain(c.item, inv, step, shops, max_hold)
        if k > 0 and gain > hold_threshold:
            c.hold = k
            held.append(c)
        else:
            c.hold = 0
            now.append(c)
    # A slot costs the same whatever the quantity, so rank by TOTAL value per
    # slot, not by value per unit.
    now.sort(key=lambda o: -o.value)
    n = max(0, int(n_slots))
    return now[:n], held + now[n:]
