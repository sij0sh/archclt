"""One public contract version for authoring and exchange objects."""

VERSION = "v2"


def version(contract: str) -> str:
    return f"archctl.{contract}.{VERSION}"
