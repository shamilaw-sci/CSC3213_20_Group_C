"""Rules about an employee record that more than one router enforces."""

from fastapi import HTTPException


def is_active(employee: dict) -> bool:
    # A missing status reads as Active, as in attendance_month and leave.
    return (employee.get("status") or "Active") == "Active"


def require_active(employee: dict, doing: str) -> None:
    """
    Refuse self-service for a deactivated employee. Deactivating keeps the
    login link, so their history stays attached, but they no longer clock in
    or take on new leave; reactivating restores both.
    """
    if not is_active(employee):
        raise HTTPException(
            status_code=403,
            detail=f"This employee record is inactive, so it can't be used to {doing}. Contact HR to reactivate it.",
        )
