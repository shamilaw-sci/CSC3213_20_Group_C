"""Whether a month's payroll is approved, which freezes that month's attendance."""

from supabase import Client


def payroll_approved(supabase: Client, month: int, year: int) -> bool:
    runs = supabase.table("payroll_runs").select("id, status") \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    return any(r.get("status") == "Approved" for r in runs)
