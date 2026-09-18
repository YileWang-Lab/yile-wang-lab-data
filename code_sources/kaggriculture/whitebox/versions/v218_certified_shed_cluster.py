"""V218: route-clustered V204 with certified shed-cell relocation.

The ordinary proposal still uses the V204 non-shed action space.  The
service-cluster challenger is the only path that can select a central access
cell, and it must pass its existing current/future route and unified
Stackelberg certificate before the layout is retained for execution.
"""
from whitebox import agent as _agent
from whitebox import capital as _capital
from whitebox import hiring as _hiring
from whitebox import strategy as _strategy
from whitebox import tasks as _tasks
from route import router as _router


def _pin_v218_runtime():
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


def whitebox_v218_certified_shed_cluster(obs):
    _pin_v218_runtime()
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
        execution_variant=(
            "paid_fertilizer_productive_shed_relocation_manifest"
        ),
        spatial_route_multistart=False,
        paid_weed_turnover=False,
        productive_shed_relocation=True,
        service_cluster_layout=True,
        land_turnover_option=True,
        bounded_land_quantity_frontier=True,
    )
