"""Pure obligation classification for the unified v2 contracts."""
from archctl.core.models import Model, Policy

GUARANTEE = ("Required obligations passed only within reported scope and coverage. "
             "Advisory failures and unknowns may remain; this is not universal structural conformance.")


def version(model: Model, contract: str) -> str:
    return f"archctl.{contract}.v2"


def policy_obligation(model: Model, policy: Policy, *, verification: bool = False) -> str:
    return policy.obligation


def add_reason(model: Model, obligations: dict, check: str, basis: str,
               decision: str, obligation: str = "required") -> None:
    entry = obligations.setdefault(check, {"id": check, "basis": "declared_requirement",
                                          "status": "not_executed", "required_by": []})
    reason = {"id": basis, "decision": decision, "obligation": obligation}
    if reason not in entry["required_by"]:
        entry["required_by"].append(reason)
    entry["obligation"] = ("required" if any(r["obligation"] == "required"
                           for r in entry["required_by"]) else "advisory")


def finding_dict(model: Model, finding) -> dict:
    return finding.to_dict()
