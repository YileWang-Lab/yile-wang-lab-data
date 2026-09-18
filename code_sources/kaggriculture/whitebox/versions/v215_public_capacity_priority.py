"""V215: V214 with the public room-guard liquidation preference.

This is a research-only white-box ablation.  It keeps every V204/V214
production parameter and changes only the day-close capacity post-process:
finished animal products are offered before sale-only crops, while WHEAT is
last and still protected by the live feed certificate.  No replay or future
action is embedded.
"""
from whitebox import agent as _agent
from whitebox import capital as _capital
from whitebox import hiring as _hiring
from whitebox import strategy as _strategy
from whitebox import tasks as _tasks
from route import router as _router


def _pin_v215_runtime():
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


def whitebox_v215_public_capacity_priority(obs):
    _pin_v215_runtime()
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
        market_variant="capacity_reserve_public_priority",
        plan_variant="crew_conditioned_inventory_execution",
        execution_variant="paid_production_fertilizer_manifest",
        spatial_route_multistart=False,
        paid_weed_turnover=False,
        land_turnover_option=True,
        bounded_land_quantity_frontier=True,
    )
