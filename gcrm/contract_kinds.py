"""What kind of agreement a contract is. Checked here rather than by a database constraint, like
pipeline stages (migration 041), so a new kind is a code change and not a migration."""

from gcrm.contract_input import ContractInputError

CONTRACT_KINDS = ("teaching_course", "workshop", "consulting", "other")


def checked_kind(value) -> str:
    """The kind itself, or ContractInputError (a ValueError) when it is not one of CONTRACT_KINDS."""
    if value not in CONTRACT_KINDS:
        raise ContractInputError(f"unknown contract kind {value!r}; one of {', '.join(CONTRACT_KINDS)}",
                                 "contractPage.error.kind")
    return value
