"""Create neutral, unreviewed architectural intent."""
from pathlib import Path
import yaml
from archctl.core.io import InputError, contained, write_text
from archctl.core.contracts import version


def initialize(root: Path) -> list[str]:
    target = contained(root, "architecture/model.yaml")
    if target.exists():
        raise InputError("Refusing to overwrite existing files: architecture/model.yaml")
    model = {"schema_version": version("authoring"), "enforcement": "strict",
             "system_id": "application", "name": "Unreviewed application scaffold",
             **{name: [] for name in ("domains", "components", "relationships", "interfaces",
                                      "policies", "verification", "workflows")}}
    write_text(target, yaml.safe_dump(model, sort_keys=False))
    return ["architecture/model.yaml"]
