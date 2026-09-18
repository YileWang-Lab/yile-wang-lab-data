"""V204: retain a deferred first-land action until live recertification.

V203 allowed a public released-tile alternative to defer an infeasible first
paid expansion once, but retained only the fact that it had waited.  If the
ordinary proposal layer never generated land again, the legal action vanished
forever even after cash recovered.  V204 retains the rule-derived eligibility
anchor and reopens the existing strict crop-land challenger from that point.
Every retry uses the current observation and must again pass positioned route,
cash, order, service-displacement and robust-value certificates.  No purchase
is forced and no opponent identity, replay key, fitted date, coordinate,
quantity or composition enters runtime.
"""
from whitebox import agent as _agent
from whitebox import hiring as _hiring
from whitebox import strategy as _strategy
from whitebox import tasks as _tasks
from whitebox import capital as _capital
from route import router as _router


def _pin_v204_runtime():
    """Seal every production environment seam inside this version."""
    _agent.ACT_BUDGET_MS = 180.0
    _hiring.MAX_HANDS = 20
    _hiring.SAFETY_MULT = 1.0
    _tasks._WATER_SLACK = 1
    _tasks._STRICT_FERT_ENABLED = True
    _tasks.WAVE_SIZE = 12
    _tasks.WAVE_GAP = 3
    _tasks.WAVE_GATE = True
    _tasks._EXACT_TOUR = False
    _tasks.DELIVER_MIN = 0
    _tasks.DELIVER_HOUR = 18
    _tasks.DAILY_FEED_HARD_CORE = False
    _router.SURVIVAL_FEED_ONLY_FALLBACK = False
    _capital.FAILURE_CLOSED_ANIMAL_ADMISSION = False
    _strategy.FEED_COVER_DAYS = 2
    _strategy.FEED_MAX = 16


def whitebox_v204_retained_land_commitment(obs):
    # Keep the entry self-contained.  Arena loads immutable historical bundles
    # in the same interpreter; importing V203's helper here would let that
    # bundle's older module signature leak into the candidate through
    # ``sys.modules`` and invalidate the A/B run.
    _pin_v204_runtime()
    return _agent.variant_agent(
        obs, capital_master=True, bank_sales="joint_routes",
        charge_activation_cost=True,
        capital_variant=(
            "crew_conditioned_positioned_scenario_late_land_"
            "challenger_deterministic"
        ),
        deterministic_routes=True,
        terminal_variant="state_opportunity_inserted_rescue",
        task_value_variant="bundle_master",
        market_variant="observation_only_timing",
        plan_variant="crew_conditioned_inventory_execution",
        execution_variant="paid_production_fertilizer_manifest",
        spatial_route_multistart=False,
        paid_weed_turnover=False,
        land_turnover_option=True,
        bounded_land_quantity_frontier=True,
    )
