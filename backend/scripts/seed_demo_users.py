"""Demo logins: one per role, all with the password below.

    cd backend
    venv/Scripts/python.exe scripts/seed_demo_users.py           # create or fix
    venv/Scripts/python.exe scripts/seed_demo_users.py --check   # report only, writes nothing

Safe to run again, on a new Supabase project or the team's:
  - Adds any of the seven roles that are missing. init.sql creates only Admin
    and Director; the rest are added in id order, so a new project gets the
    same ids (1-7) as the team's.
  - Creates each login that doesn't exist yet, already confirmed so it can sign
    in straight away, and sets its role by name. Role ids used to be hardcoded
    here with HR Officer and Finance Officer swapped, so a re-run moved hr@ and
    finance@ into each other's roles.
  - Gives the first five logins an employee profile if they have none, so they
    can clock in and request leave. Logins that are already linked to an
    employee are left alone. fieldofficer@ gets its employee from
    seed_presentation.py, and System Administrator holds no self-service
    permissions, so neither is given one here.

Needs SUPABASE_URL and the service_role SUPABASE_KEY in backend/.env.
"""

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PASSWORD = "Password123!"

# In id order, as in the team's roles table and app/core/permissions.py UserRole.
ROLES = ["Admin", "Director", "Finance Officer", "HR Officer", "Operations Lead",
         "General Staff", "System Administrator"]

# (email, role, employee profile or None)
USERS = [
    ("admin@vff.org", "Admin", ("Admin", "User", "199000000001")),
    ("director@vff.org", "Director", ("Director", "User", "199000000002")),
    ("finance@vff.org", "Finance Officer", ("Finance", "User", "199000000003")),
    ("hr@vff.org", "HR Officer", ("HR", "User", "199000000004")),
    ("staff@vff.org", "Operations Lead", ("Operations", "User", "199000000005")),
    ("fieldofficer@vff.org", "General Staff", None),
    ("sysadmin@vff.org", "System Administrator", None),
]


def find_auth_user(sb, email):
    """An auth account with no public.users row, e.g. if the signup trigger didn't fire."""
    page = 1
    while True:
        users = sb.auth.admin.list_users(page=page, per_page=200)
        for u in users:
            if (u.email or "").lower() == email:
                return u.id
        if len(users) < 200:
            return None
        page += 1


def main(check):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in backend/.env.")
    sb = create_client(url, key)
    changes = 0

    def act(message, write):
        nonlocal changes
        changes += 1
        print(f"  {'would ' if check else ''}{message}")
        if not check:
            return write()

    print("Roles")
    role_ids = {r["role_name"]: r["id"] for r in sb.table("roles").select("id, role_name").execute().data or []}
    for name in ROLES:
        if name not in role_ids:
            row = act(f"add role {name}", lambda: sb.table("roles").insert({"role_name": name}).execute().data[0])
            role_ids[name] = row["id"] if row else None

    print("Logins")
    for email, role, profile in USERS:
        role_id = role_ids[role]
        row = (sb.table("users").select("id, role_id").eq("email", email).execute().data or [None])[0]
        uid = row["id"] if row else find_auth_user(sb, email)

        if not uid:
            def create():
                res = sb.auth.admin.create_user({"email": email, "password": PASSWORD, "email_confirm": True})
                return res.user.id
            uid = act(f"create {email} ({role})", create)
        if not row:
            act(f"set {email} to {role}",
                lambda: sb.table("users").upsert({"id": uid, "email": email, "role_id": role_id}).execute())
        elif row["role_id"] != role_id:
            act(f"change {email} from role {row['role_id']} to {role} ({role_id})",
                lambda: sb.table("users").update({"role_id": role_id}).eq("id", uid).execute())

        if profile and uid:
            linked = sb.table("employee_profile").select("id").eq("user_id", uid).execute().data
            if not linked:
                first, last, nic = profile
                if sb.table("employee_profile").select("id").eq("nic", nic).execute().data:
                    print(f"  skip employee for {email}: NIC {nic} is already in use")
                    continue
                act(f"add employee {first} {last} for {email}",
                    lambda: sb.table("employee_profile").insert({
                        "user_id": uid, "first_name": first, "last_name": last, "nic": nic,
                        "base_salary": 60000, "status": "Active", "date_joined": "2026-01-01",
                    }).execute())

    if not changes:
        print("Nothing to change: every role and demo login is already in place.")
    elif check:
        print(f"{changes} change(s) needed. Run without --check to make them.")
    else:
        print(f"Done: {changes} change(s). Every demo login uses the password {PASSWORD}")


if __name__ == "__main__":
    main(check="--check" in sys.argv[1:])
