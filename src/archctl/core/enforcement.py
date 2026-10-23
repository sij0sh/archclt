"""Pure obligation classification for the unified v2 contracts."""
GUARANTEE = ("Required obligations passed only within reported scope and coverage. "
             "Advisory failures and unknowns may remain; this is not universal structural conformance.")


def version(contract: str) -> str:
    return f"archctl.{contract}.v2"


def add_reason(obligations: dict, check: str, basis: str,
               decision: str, obligation: str = "required") -> None:
    entry = obligations.setdefault(check, {"id": check, "basis": "declared_requirement",
                                          "status": "not_executed", "required_by": []})
    reason = {"id": basis, "decision": decision, "obligation": obligation}
    if reason not in entry["required_by"]:
        entry["required_by"].append(reason)
    entry["obligation"] = ("required" if any(r["obligation"] == "required"
                           for r in entry["required_by"]) else "advisory")
