"""One-way authoring migration; legacy formats never select output contracts."""
from copy import deepcopy
from archctl.core.io import InputError


def migrate_document(document: dict) -> dict:
    value = deepcopy(document)
    schema = value.get("schema_version")
    if schema not in {"archctl.authoring.v1", "archctl.authoring.v2"}:
        raise InputError("Unsupported authoring schema_version")
    legacy = schema == "archctl.authoring.v1"
    if legacy and "enforcement" in value:
        raise InputError("Legacy v1 intent cannot declare enforcement")
    mode = value.get("enforcement", "strict")
    if mode == "selective-v2":
        mode = "selective"
    if mode not in {"strict", "selective"}:
        raise InputError("Unsupported enforcement mode")
    value.update(schema_version="archctl.authoring.v2", enforcement=mode)
    for policy in value.get("policies", []):
        if legacy:
            if "obligation" in policy:
                raise InputError("Legacy v1 policy cannot declare obligation")
            policy["obligation"] = ("required" if policy.get("kind") == "required_verification"
                                    or policy.get("severity", "error") == "error" else "advisory")
        elif policy.get("obligation") not in {"required", "advisory"}:
            raise InputError("policy.obligation must be required or advisory")
    return value
