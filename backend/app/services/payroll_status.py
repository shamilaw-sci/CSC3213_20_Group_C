"""Whether a month's payroll is approved, which freezes that month's attendance."""

from supabase import Client


def payroll_approved(supabase: Client, month: int, year: int) -> bool:
    runs = supabase.table("payroll_runs").select("id, status, payroll_month, payroll_year") \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    return any(r.get("status") == "Approved" and r.get("payroll_month") == month and r.get("payroll_year") == year
               for r in runs)
