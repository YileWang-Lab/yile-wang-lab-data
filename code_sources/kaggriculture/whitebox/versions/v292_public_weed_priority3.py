"""V292 diagnostic: give all visible weeds a medium cleanup priority."""
from whitebox.versions import v250_public_scenario_sale60 as _v250
_c06 = _v250._c06
_base_jobs = _c06._field_jobs
def _field_jobs(obs, farm, private, roles, liquidation):
    jobs = _base_jobs(obs, farm, private, roles, liquidation)
    if not liquidation:
        for job in jobs:
            if job.get("reason") == "dig_weed":
                job["priority"] = 3
                job["value"] = max(float(job.get("value", 0)), 180.0)
    return jobs
_c06._field_jobs = _field_jobs
def whitebox_v292_public_weed_priority3(obs):
    return _c06.agent(obs)

