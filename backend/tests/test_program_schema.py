from datetime import date

from app.schemas.finance import ProgramCreate


def test_program_create_accepts_optional_budget_and_dates():
    payload = ProgramCreate(
        program_name="Wildlife Rescue",
        total_animals_treated=120,
        status="Active",
        budget_amount=5000.0,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    data = payload.model_dump()

    assert data["program_name"] == "Wildlife Rescue"
    assert data["budget_amount"] == 5000.0
    assert data["start_date"] == date(2026, 1, 1)
    assert data["end_date"] == date(2026, 12, 31)
