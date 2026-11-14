"""Presentation dataset: six months (June to mid-November 2026) of realistic
activity for VFF IMS, so every page has believable data to show.

    cd backend
    venv/Scripts/python.exe scripts/seed_presentation.py

What it does, in order:
  1. Tidies leftover test names (programs, stock items, shifts, zones, the
     duplicate demo employees) into realistic ones. Nothing is deleted, and
     rescue cases with photos are never touched.
  2. Adds two demo logins so all seven roles can be shown:
     fieldofficer@vff.org (General Staff) and sysadmin@vff.org (System
     Administrator), with the same password as seed_demo_users.py.
  3. Seeds employees, programs, stock movements, ledger entries, donations,
     rescue cases with timelines, outbreak zones, volunteers and shifts, leave
     and November attendance.

Each section checks for its own marker first and skips if it has already run,
so running the script again tops up anything missing and never duplicates.
It is not a reset: the case timeline is append-only, so seeded cases stay.

Money and stock go through the database's own functions
(inventory_apply_movement, record_donation_payment), so batches, costs and the
ledger agree exactly as they would after real use. Salaries are left alone and
new employees join in November, so the October payroll draft stays valid.
"""

import base64
import hashlib
import os
import random
import sys
from datetime import date, datetime, time, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client
from supabase.lib.client_options import ClientOptions

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PASSWORD = "Password123!"  # the demo password from seed_demo_users.py
TODAY = date(2026, 11, 14)
COLOMBO = timezone(timedelta(hours=5, minutes=30))
# Each section draws from its own generator, so a rerun recreates the same
# rows in every section however much an earlier section did this time.
rng = random.Random(2026)

URL = os.environ["SUPABASE_URL"]
KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
# A request that never answers used to hang the whole run; fail it instead.
OPTIONS = ClientOptions(postgrest_client_timeout=30)
sb = create_client(URL, KEY, options=OPTIONS)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def rows(table, columns="*", **eq):
    q = sb.table(table).select(columns)
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.execute().data or []


def first(table, columns="*", **eq):
    found = rows(table, columns, **eq)
    return found[0] if found else None


def at(d, hh=9, mm=0):
    """A Colombo local time on date d, as an ISO timestamp."""
    return datetime.combine(d, time(hh, mm), COLOMBO).isoformat()


def days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def weekdays(start, end):
    return [d for d in days(start, end) if d.weekday() < 5]


def token(seed):
    return base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()).decode().rstrip("=")


def ref(seed):
    return "VFF-" + hashlib.sha1(seed.encode()).hexdigest()[:12].upper()


def section(name, done):
    if done:
        print(f"- {name}: already seeded, skipped")
        return False
    print(f"- {name} ...")
    return True


def user_id(email):
    u = first("users", "id", email=email)
    return u["id"] if u else None


# ---------------------------------------------------------------------------
# 1. tidy leftover test names
# ---------------------------------------------------------------------------

PROGRAM_RENAMES = {
    "Test Program": dict(program_name="Peradeniya Campus ABC Camp", location="University of Peradeniya",
                         program_type="Sterilization", start_date="2026-06-14", end_date="2026-06-28",
                         total_animals_treated=64),
    "street dogs uop": dict(program_name="Kandy Lake Round Vaccination Day", location="Kandy",
                            program_type="Vaccination", start_date="2026-07-05", end_date="2026-07-05",
                            total_animals_treated=120),
    "ygjkji": dict(program_name="Kurunegala Mobile Vet Clinic", location="Kurunegala",
                   program_type="Free Clinic", start_date="2026-08-09", end_date="2026-08-10",
                   total_animals_treated=85),
    "sterilizing Project": dict(program_name="Galle Fort Sterilisation Week", location="Galle",
                                program_type="Sterilization", start_date="2026-09-07", end_date="2026-09-13",
                                total_animals_treated=72),
    "Emergency Animal Rescue": dict(location="Kandy District", program_type="Other",
                                    start_date="2026-10-01", end_date="2026-10-20", total_animals_treated=18),
    "wild life treatments": dict(program_name="Udawalawe Community Animal Clinic", location="Udawalawe",
                                 program_type="Free Clinic", start_date="2026-12-05", is_public=True,
                                 public_venue="Udawalawe Divisional Secretariat grounds",
                                 public_schedule="5 December, 8am to 2pm",
                                 public_notes="Free check-ups, deworming and vaccinations for dogs and cats."),
    "[TEST] QA Clinic": dict(program_name="Matara Community Dog Census", location="Matara",
                             program_type="Awareness", start_date="2026-10-10", end_date="2026-10-11",
                             total_animals_treated=40),
    "[TEST] QA Cancel me": dict(program_name="Negombo Beach Clinic (postponed)", location="Negombo",
                                program_type="Free Clinic"),
    "Rabies Vaccination Drive": dict(location="Kandy", program_type="Vaccination", start_date="2026-09-15",
                                     total_animals_treated=312, is_public=True,
                                     public_venue="Kandy Municipal Council grounds",
                                     public_schedule="Saturdays, 8am to 12pm, until end of December",
                                     public_notes="Free anti-rabies vaccination for dogs and cats. Bring your pet on a leash."),
    "Street Dog Sterilization": dict(location="Peradeniya", program_type="Sterilization", start_date="2026-10-05",
                                     total_animals_treated=96, is_public=True,
                                     public_venue="Faculty of Veterinary Medicine, University of Peradeniya",
                                     public_schedule="Weekdays, 9am to 3pm",
                                     public_notes="Free sterilisation for community and street dogs. Please do not feed animals after midnight before surgery."),
    "Distemper outbreak": dict(program_name="Distemper Response - Peradeniya", location="Peradeniya",
                               program_type="Other", start_date="2026-11-03", total_animals_treated=37),
}

ITEM_RENAMES = {
    "Rabies Vaccine": ("Anti-rabies vaccine (Nobivac, 1 dose)", 100),
    "Rabies vaccine (Asiri)": ("Anti-rabies vaccine (Rabisin, 1 dose)", 80),
    "Surgical Kits": ("Sterile surgical kits", 10),
    "Dog Food (20kg)": ("Dog food (20kg bag)", 15),
    "Bandages": ("Cohesive bandages (7.5cm)", 40),
    "Betadine": ("Povidone-iodine 10% (500ml)", 8),
    "Chains": ("Dog collars (adjustable)", 20),
    "string": ("Nylon slip leads", 20),
    "uniform": ("Surgical gloves (pair)", 150),
    "gas": ("Disposable syringes (box of 100)", 20),
    "mask": ("Surgical face masks (box of 50)", 20),
    "vitemins": ("Vitamin B complex injection (10ml)", 40),
    "Dog Leashes": ("Dog leashes", 20),
    "[TEST] QA Gauze": ("Sterile gauze swabs (pack of 100)", 15),
}

EMPLOYEE_RENAMES = {  # NIC (old) -> new identity; salaries are left alone
    "DEMO1V": ("Nadeesha", "Wickramasinghe", "198845602318", "2024-02-01"),
    "DEMO2V": ("Ashan", "Gunawardena", "197912304567", "2021-06-01"),
    "DEMO3V": ("Pradeep", "Bandara", "198603102874", "2022-09-15"),
    "DEMO4V": ("Ishara", "Jayawardena", "199475201456", "2023-03-01"),
    "DEMO5V": ("Kasun", "Herath", "199102504398", "2023-07-10"),
    "ORG1V": ("Oshadha", "Nagahawatte", "200112703456", "2025-01-06"),
    "ORG2V": ("Sanjeewa", "Rajapaksha", "198230907612", "2022-01-17"),
    "ORG3V": ("Dilani", "Fernando", "199056802211", "2023-05-02"),
    "ORG4V": ("Ruwani", "Senanayake", "199263401987", "2024-04-01"),
    "ORG5V": ("Tharindu", "Dissanayake", "199819805543", "2025-03-03"),
    # Joined in November: she is on the November payroll only, and an earlier
    # date would add her to the October draft.
    "123456788765432": ("Thilini", "Perera", "199258702345", "2026-11-02"),
}


def tidy():
    print("1. Tidying leftover test names")
    for old, fields in PROGRAM_RENAMES.items():
        p = first("programs", "id", program_name=old)
        if p:
            sb.table("programs").update(fields).eq("id", p["id"]).execute()
    for old, (new, reorder) in ITEM_RENAMES.items():
        i = first("inventory_items", "id", item_name=old)
        if i:
            sb.table("inventory_items").update({"item_name": new, "reorder_level": reorder}).eq("id", i["id"]).execute()
    for e in rows("employee_profile", "id,nic,epf_number"):
        if e["nic"] in EMPLOYEE_RENAMES:
            fn, ln, nic, joined = EMPLOYEE_RENAMES[e["nic"]]
            sb.table("employee_profile").update({
                "first_name": fn, "last_name": ln, "nic": nic, "date_joined": joined,
                "epf_number": e["epf_number"] or f"KY/{rng.randint(10000, 99999)}",
            }).eq("id", e["id"]).execute()
    for e in rows("employee_profile", "id,epf_number"):
        if not e["epf_number"]:
            sb.table("employee_profile").update({"epf_number": f"KY/{rng.randint(10000, 99999)}"}).eq("id", e["id"]).execute()
    shift_titles = {"Saturday sterialization clinic": "Saturday sterilisation clinic",
                    "sterilization clinic": "Weekday sterilisation clinic",
                    "sterilizing Project": "Galle sterilisation week - recovery care",
                    "street dogs uop": "Kandy Lake vaccination day - handlers",
                    "rescue project": "Emergency rescue - transport support",
                    "Distemper outbreak": "Distemper response - isolation ward help"}
    for old, new in shift_titles.items():
        for s in rows("volunteer_shifts", "id", title=old):
            sb.table("volunteer_shifts").update({"title": new}).eq("id", s["id"]).execute()
    for z in rows("outbreak_zones", "id,title"):
        t = z["title"]
        new = None
        if "Galle area" in t and t != "Suspected mange outbreak - Galle area":
            new = "Suspected mange outbreak - Galle area"
        elif t == "Suspected manage outbreak":
            new = "Suspected mange cluster - Matara"
        elif t == "leg disease":
            new = "Lameness in stray cattle - Kurunegala"
        if new:
            sb.table("outbreak_zones").update({"title": new}).eq("id", z["id"]).execute()
    # Test cases from QA runs, only those without a photo: the photos stay as they are.
    for c in rows("rescue_cases", "id,description,photo_url,animal_type"):
        d = (c["description"] or "")
        if not c["photo_url"] and (d.startswith("TEST") or d.startswith("[TEST]")):
            new = ("Stray cat with an injured paw near the bus stand." if c["animal_type"] == "Cat"
                   else "Dog limping near the junction, cannot put weight on its hind leg.")
            sb.table("rescue_cases").update({"description": new}).eq("id", c["id"]).execute()


# ---------------------------------------------------------------------------
# 2. logins and employees
# ---------------------------------------------------------------------------

NEW_EMPLOYEES = [
    # first, last, nic, salary, joined, login
    ("Lahiru", "Madushanka", "199733104562", 62000, "2026-11-02", "fieldofficer@vff.org"),
    ("Hasini", "Kumarasinghe", "199861202873", 68000, "2026-11-02", None),
    ("Chathura", "Wijesekara", "198904506671", 55000, "2026-11-03", None),
    ("Sachini", "Ekanayake", "199507803329", 140000, "2026-11-04", None),
]
LINKS = {"admin@vff.org": "198845602318", "director@vff.org": "197912304567", "staff@vff.org": "199102504398"}


def ensure_login(email, role_id):
    uid = user_id(email)
    if not uid:
        signup = create_client(URL, KEY)  # separate client: sign_up switches its session
        res = signup.auth.sign_up({"email": email, "password": PASSWORD})
        uid = res.user.id
        sb.table("users").upsert({"id": uid, "email": email, "role_id": role_id}).execute()
    else:
        sb.table("users").update({"role_id": role_id}).eq("id", uid).execute()
    return uid


def people():
    print("2. Logins and employees")
    ensure_login("fieldofficer@vff.org", 6)
    ensure_login("sysadmin@vff.org", 7)
    for email, nic in LINKS.items():
        uid, emp = user_id(email), first("employee_profile", "id,user_id", nic=nic)
        if uid and emp and not emp["user_id"] and not first("employee_profile", "id", user_id=uid):
            sb.table("employee_profile").update({"user_id": uid}).eq("id", emp["id"]).execute()
    for fn, ln, nic, salary, joined, login in NEW_EMPLOYEES:
        if first("employee_profile", "id", nic=nic):
            continue
        emp = sb.table("employee_profile").insert({
            "first_name": fn, "last_name": ln, "nic": nic, "base_salary": salary, "status": "Active",
            "date_joined": joined, "epf_number": f"KY/{rng.randint(10000, 99999)}",
            "user_id": user_id(login) if login else None,
        }).execute().data[0]
        for type_id, entitled in ((2, 2.0), (3, 7.0)):
            sb.table("leave_entitlements").insert({
                "employee_id": emp["id"], "leave_type_id": type_id, "year": 2026, "entitled_days": entitled,
                "carried_forward": 0, "adjustment": 0, "note": "Pro-rated: joined November 2026",
            }).execute()


# ---------------------------------------------------------------------------
# 3. programs and stock
# ---------------------------------------------------------------------------

NEW_PROGRAMS = [
    dict(program_name="School Awareness Programme - Kandy", status="Active", location="Kandy",
         program_type="Awareness", start_date="2026-11-01", total_animals_treated=0),
    dict(program_name="Colombo Year-End Adoption Fair", status="Upcoming", location="Colombo 07",
         program_type="Awareness", start_date="2026-12-13", is_public=True,
         public_venue="Viharamahadevi Park, Colombo 07", public_schedule="13 December, 9am to 4pm",
         public_notes="Meet rescued dogs and cats looking for homes. Adoption counselling on site."),
    dict(program_name="Jaffna Mobile Sterilisation Camp", status="Upcoming", location="Jaffna",
         program_type="Sterilization", start_date="2027-01-17", is_public=True,
         public_venue="Jaffna Municipal Council veterinary office",
         public_schedule="17 to 21 January, 8am to 3pm"),
]

NEW_ITEMS = [  # name, unit cost, reorder level
    ("DHPPi vaccine (Nobivac, 1 dose)", 950, 60),
    ("Ketamine 10% (10ml)", 2400, 12),
    ("Xylazine 2% (20ml)", 1500, 10),
    ("Absorbable sutures (Vicryl 2-0)", 1100, 30),
    ("Amoxicillin LA injection (100ml)", 3200, 6),
    ("Ivermectin 1% (50ml)", 1900, 6),
    ("Meloxicam injection (20ml)", 2100, 6),
    ("Ringer lactate IV (500ml)", 260, 40),
    ("Cat food (7kg bag)", 6500, 4),
    ("Elizabethan collars", 450, 15),
]

# Purchases: (date, item, qty, unit cost, batch, expiry)
PURCHASES = [
    ("2026-06-03", "DHPPi vaccine (Nobivac, 1 dose)", 300, 950, "NB-DH-2606", "2027-05-31"),
    ("2026-06-03", "Ketamine 10% (10ml)", 40, 2400, "KT-2606", "2027-06-30"),
    ("2026-06-03", "Xylazine 2% (20ml)", 30, 1500, "XZ-2606", "2027-03-31"),
    ("2026-06-05", "Absorbable sutures (Vicryl 2-0)", 120, 1100, "VC-2606", "2028-01-31"),
    ("2026-06-05", "Amoxicillin LA injection (100ml)", 20, 3200, "AM-2606", "2026-11-30"),
    ("2026-06-05", "Ivermectin 1% (50ml)", 20, 1900, "IV-2606", "2027-08-31"),
    ("2026-06-12", "Meloxicam injection (20ml)", 18, 2100, "MX-2606", "2027-04-30"),
    ("2026-06-12", "Ringer lactate IV (500ml)", 120, 260, "RL-2606", "2026-12-05"),
    ("2026-06-12", "Sterile surgical kits", 30, 2500, "SK-2606", None),
    ("2026-06-12", "Povidone-iodine 10% (500ml)", 24, 950, "PI-2606", "2027-12-31"),
    ("2026-06-12", "Sterile gauze swabs (pack of 100)", 60, 480, "GZ-2606", "2028-06-30"),
    ("2026-06-20", "Cat food (7kg bag)", 12, 6500, "CF-2606", "2027-02-28"),
    ("2026-06-20", "Elizabethan collars", 60, 450, "EC-2606", None),
    ("2026-08-04", "Amoxicillin LA injection (100ml)", 15, 3350, "AM-2608", "2027-07-31"),
    ("2026-08-04", "Ketamine 10% (10ml)", 30, 2450, "KT-2608", "2027-08-31"),
    ("2026-08-04", "Absorbable sutures (Vicryl 2-0)", 80, 1150, "VC-2608", "2028-07-31"),
    ("2026-09-10", "DHPPi vaccine (Nobivac, 1 dose)", 400, 980, "NB-DH-2609", "2027-08-31"),
    ("2026-09-10", "Ringer lactate IV (500ml)", 100, 270, "RL-2609", "2027-09-30"),
    ("2026-10-02", "Sterile surgical kits", 40, 2600, "SK-2610", None),
    ("2026-10-02", "Xylazine 2% (20ml)", 25, 1550, "XZ-2610", "2027-10-31"),
    ("2026-10-02", "Cat food (7kg bag)", 10, 6650, "CF-2610", "2027-06-30"),
    ("2026-11-05", "Povidone-iodine 10% (500ml)", 20, 980, "PI-2611", "2028-03-31"),
]

# Issues to active programs: (date, item, qty, program)
PROGRAM_ISSUES = [
    ("2026-09-19", "DHPPi vaccine (Nobivac, 1 dose)", 90, "Rabies Vaccination Drive"),
    ("2026-09-26", "Anti-rabies vaccine (Nobivac, 1 dose)", 80, "Rabies Vaccination Drive"),
    ("2026-10-10", "Anti-rabies vaccine (Rabisin, 1 dose)", 60, "Rabies Vaccination Drive"),
    ("2026-10-17", "DHPPi vaccine (Nobivac, 1 dose)", 110, "Rabies Vaccination Drive"),
    ("2026-10-31", "Anti-rabies vaccine (Nobivac, 1 dose)", 70, "Rabies Vaccination Drive"),
    ("2026-11-07", "DHPPi vaccine (Nobivac, 1 dose)", 95, "Rabies Vaccination Drive"),
    ("2026-10-06", "Ketamine 10% (10ml)", 18, "Street Dog Sterilization"),
    ("2026-10-06", "Xylazine 2% (20ml)", 14, "Street Dog Sterilization"),
    ("2026-10-06", "Absorbable sutures (Vicryl 2-0)", 60, "Street Dog Sterilization"),
    ("2026-10-06", "Sterile surgical kits", 22, "Street Dog Sterilization"),
    ("2026-10-20", "Ketamine 10% (10ml)", 20, "Street Dog Sterilization"),
    ("2026-10-20", "Meloxicam injection (20ml)", 6, "Street Dog Sterilization"),
    ("2026-10-20", "Elizabethan collars", 30, "Street Dog Sterilization"),
    ("2026-11-03", "Ketamine 10% (10ml)", 22, "Street Dog Sterilization"),
    ("2026-11-03", "Absorbable sutures (Vicryl 2-0)", 70, "Street Dog Sterilization"),
    ("2026-11-03", "Sterile surgical kits", 25, "Street Dog Sterilization"),
    ("2026-11-04", "Ringer lactate IV (500ml)", 60, "Distemper Response - Peradeniya"),
    ("2026-11-04", "Amoxicillin LA injection (100ml)", 6, "Distemper Response - Peradeniya"),
    ("2026-11-09", "Ringer lactate IV (500ml)", 45, "Distemper Response - Peradeniya"),
]


def move(item_id, qty, kind, d, program_id=None, case_id=None, unit_cost=None, batch=None, expiry=None, notes=None):
    return sb.rpc("inventory_apply_movement", {
        "p_item_id": item_id, "p_program_id": program_id, "p_quantity": qty,
        "p_transaction_type": kind, "p_transaction_date": d, "p_notes": notes,
        "p_unit_cost": unit_cost, "p_expire_date": expiry, "p_batch_number": batch,
        "p_rescue_case_id": case_id,
    }).execute().data


def programs_and_stock():
    rng = random.Random("programs_and_stock")
    print("3. Programs and stock")
    for p in NEW_PROGRAMS:
        if not first("programs", "id", program_name=p["program_name"]):
            sb.table("programs").insert(p).execute()
    if not section("stock movements", first("inventory_items", "id", item_name=NEW_ITEMS[0][0])):
        return
    for name, cost, reorder in NEW_ITEMS:
        sb.table("inventory_items").insert({"item_name": name, "current_stock": 0, "unit_cost": cost,
                                            "reorder_level": reorder, "supplier_name": rng.choice(
                                                ["Hemas Pharmaceuticals", "SPC Vet Supplies", "Baurs Animal Health",
                                                 "CIC Agri", "Slim Pharmaceuticals"])}).execute()
    item = {i["item_name"]: i["id"] for i in rows("inventory_items", "id,item_name")}
    prog = {p["program_name"]: p["id"] for p in rows("programs", "id,program_name")}
    for d, name, qty, cost, batch, expiry in PURCHASES:
        move(item[name], qty, "Restock", d, unit_cost=cost, batch=batch, expiry=expiry,
             notes="Delivery against purchase order")
    for d, name, qty, program in PROGRAM_ISSUES:
        move(item[name], qty, "Issue", d, program_id=prog[program], notes="Issued for clinic day")
    move(item["Ringer lactate IV (500ml)"], 12, "Return", "2026-11-12", program_id=prog["Distemper Response - Peradeniya"],
         notes="Unused after ward closed for the weekend")


# ---------------------------------------------------------------------------
# 4. ledger and donations
# ---------------------------------------------------------------------------

def ledger():
    rng = random.Random("ledger")
    if not section("ledger entries", first("financial_transactions", "id", memo="Grant - Dogs Trust Worldwide (sterilisation 2026)")):
        return
    prog = {p["program_name"]: p["id"] for p in rows("programs", "id,program_name")}
    entries = [
        ("2026-06-10", 1800000, "Income", "Cash", "Street Dog Sterilization", True, "Grant - Dogs Trust Worldwide (sterilisation 2026)"),
        ("2026-07-22", 950000, "Income", "Cash", "Rabies Vaccination Drive", True, "Grant - Humane Society International (rabies)"),
        ("2026-08-15", 600000, "Income", "Cash", None, False, "CSR contribution - Dialog Axiata PLC"),
        ("2026-09-28", 420000, "Income", "Cash", None, False, "World Rabies Day charity walk - Kandy"),
        ("2026-10-18", 750000, "Income", "Cash", None, False, "CSR contribution - John Keells Foundation"),
        ("2026-11-10", 500000, "Income", "Receivable", None, False, "Pledge - Rotary Club of Kandy (due December)"),
        ("2026-06-02", 64000, "Expense", "Cash", None, False, "Vehicle insurance - rescue van (annual)"),
        ("2026-07-14", 38000, "Expense", "Cash", None, False, "Rescue van service and tyres"),
        ("2026-10-08", 52000, "Expense", "Cash", None, False, "Rescue van brake repair"),
        ("2026-06-28", 48000, "Expense", "Cash", "Peradeniya Campus ABC Camp", False, "Camp logistics - tents and transport"),
        ("2026-08-10", 36500, "Expense", "Cash", "Kurunegala Mobile Vet Clinic", False, "Mobile clinic transport and meals"),
        ("2026-09-13", 41000, "Expense", "Cash", "Galle Fort Sterilisation Week", False, "Recovery kennels hire"),
        ("2026-11-11", 46000, "Expense", "Receivable", None, False, "Referral fees - Kandy Animal Hospital (November)"),
    ]
    for month in range(6, 12):
        d = date(2026, month, 1)
        entries += [
            (str(d), 85000, "Expense", "Receivable" if month == 11 else "Cash", None, False, "Clinic rent - Peradeniya"),
            (str(d + timedelta(days=11)), rng.randint(16000, 24000), "Expense", "Cash", None, False, "Electricity and water"),
            (str(d + timedelta(days=14)), rng.randint(28000, 46000), "Expense", "Cash", None, False, "Fuel - rescue van"),
            (str(d + timedelta(days=17)), 9500, "Expense", "Cash", None, False, "Telephone and internet"),
        ]
    for d, amount, kind, status, program, restricted, memo in entries:
        if d > str(TODAY):
            continue
        sb.table("financial_transactions").insert({
            "transaction_date": d, "amount": amount, "transaction_type": kind, "status": status,
            "program_id": prog.get(program), "is_restricted": restricted, "source_type": "manual", "memo": memo,
        }).execute()


FIRST = ["Nimal", "Kumari", "Sunethra", "Ruwan", "Dinesh", "Chamari", "Anura", "Malini", "Pradeep", "Shanika",
         "Mahesh", "Iresha", "Gayan", "Dilrukshi", "Asanka", "Nilmini", "Roshan", "Thushari", "Janaka", "Upeksha",
         "Kavindu", "Sewwandi", "Harsha", "Madhavi", "Supun", "Anjali", "Rukshan", "Fathima", "Arjun", "Priya"]
LAST = ["Perera", "Fernando", "Silva", "Jayasinghe", "Bandara", "Wijeratne", "Gunasekara", "Rathnayake",
        "Senanayake", "Herath", "Karunaratne", "Weerasinghe", "Dias", "Rajapakse", "Abeysekera", "Kumara",
        "Liyanage", "Samarasinghe", "Nawaz", "Sivakumar"]
MESSAGES = ["For the street dogs near my office.", "In memory of our dog Bruno.", "Keep up the great work!",
            "Thank you for helping the animals of Kandy.", "For the sterilisation programme.",
            "Happy to support the rabies drive.", None, None, None, None]


def donations():
    """Row by row (keyed on gateway_ref), so an interrupted run resumes."""
    rng = random.Random("donations")
    print("- donations ...")
    prog = {p["program_name"]: p for p in rows("programs", "id,program_name,start_date")}
    targets = [prog["Rabies Vaccination Drive"], prog["Street Dog Sterilization"]]
    start = date(2026, 6, 1)
    for n in range(72):
        d = start + timedelta(days=rng.randint(0, (TODAY - start).days - 1))
        amount = rng.choice([1000, 1000, 1500, 2000, 2500, 2500, 3000, 5000, 5000, 10000, 15000, 25000])
        anon = rng.random() < 0.25
        open_targets = [t for t in targets if t["start_date"] and t["start_date"] <= str(d)]
        program = rng.choice(open_targets) if open_targets and rng.random() < 0.3 else None
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        created = at(d, rng.randint(7, 21), rng.randint(0, 59))
        values = {
            "amount": amount, "currency": "LKR", "purpose": "program" if program else "general",
            "program_id": program["id"] if program else None, "is_anonymous": anon,
            "donor_name": None if anon else f"{fn} {ln}",
            # An anonymous donation keeps no contact details at all (DB check).
            "donor_email": None if anon else f"{fn.lower()}.{ln.lower()}{n}@example.com",
            "donor_phone": None if anon else f"07{rng.randint(0, 8)}{rng.randint(1000000, 9999999)}",
            "message": rng.choice(MESSAGES), "status": "pending", "gateway": "payhere",
            "gateway_ref": ref(f"donation-{n}"), "created_at": created,
        }
        paid_at = (datetime.fromisoformat(created) + timedelta(minutes=rng.randint(2, 6))).isoformat()
        row = first("donations", "*", gateway_ref=values["gateway_ref"])
        if row and row["status"] == "paid" and row["thank_you_sent_at"]:
            continue  # done on an earlier run
        if not row:
            row = sb.table("donations").insert(values).execute().data[0]
        if row["status"] == "pending":
            try:
                sb.rpc("record_donation_payment", {"p_donation_id": row["id"], "p_amount": row["amount"]}).execute()
            except Exception:
                # supabase-py 2.3 mistakes a returned row with a "message" field
                # (the donor's message) for an error. The re-read below is the
                # real check.
                pass
            row = first("donations", "*", id=row["id"])
            if row["status"] != "paid":
                raise RuntimeError(f"donation {row['gateway_ref']} was not recorded as paid")
        # Paid "now" by the function; backdate it. thank_you_sent_at also stops
        # the thank-you page from trying to email a made-up donor.
        sb.table("donations").update({"paid_at": paid_at, "thank_you_sent_at": paid_at}).eq("id", row["id"]).execute()
        sb.table("financial_transactions").update({"transaction_date": created[:10]}).eq(
            "id", row["finance_transaction_id"]).execute()


# ---------------------------------------------------------------------------
# 5. rescue cases with timelines, outbreak zones
# ---------------------------------------------------------------------------

PLACES = [  # name, lat, lng, weight
    ("Kandy", 7.2906, 80.6337, 22), ("Peradeniya", 7.2690, 80.5960, 16), ("Katugastota", 7.3333, 80.6167, 8),
    ("Gampola", 7.1643, 80.5696, 6), ("Colombo", 6.9271, 79.8612, 10), ("Dehiwala", 6.8511, 79.8659, 4),
    ("Negombo", 7.2083, 79.8358, 5), ("Galle", 6.0535, 80.2210, 6), ("Matara", 5.9549, 80.5550, 4),
    ("Kurunegala", 7.4863, 80.3647, 6), ("Nuwara Eliya", 6.9497, 80.7891, 3), ("Jaffna", 9.6615, 80.0255, 3),
    ("Anuradhapura", 8.3114, 80.4037, 3), ("Ratnapura", 6.6828, 80.3992, 4),
]
SPOTS = ["the market", "the bus stand", "the railway station", "the junction", "the temple road",
         "the hospital car park", "the school gate", "the clock tower", "the university hostels", "the lake road"]
CASES = {
    "Dog": [
        ("High", "Hit by a three-wheeler near {spot}, bleeding from the head and unable to stand.", "Road traffic injury with active bleeding."),
        ("High", "Deep wound on the neck from a tight rope collar near {spot}, smells infected.", "Infected wound needing prompt cleaning."),
        ("High", "Vomiting and shaking near {spot}, possible poisoning.", "Possible poisoning, time-critical."),
        ("High", "Old dog with a maggot-infested wound on the back near {spot}.", "Myiasis requires urgent treatment."),
        ("Medium", "Limping on the right hind leg near {spot}, cannot put weight on it.", "Likely fracture or sprain, stable."),
        ("Medium", "Severe mange, hair loss and open sores, very thin, near {spot}.", "Skin disease and malnutrition, not acute."),
        ("Medium", "Swollen, discharging eye on a street dog near {spot}.", "Eye infection, treat soon."),
        ("Medium", "Mother dog with five puppies under a shelter near {spot}, looks weak.", "Nursing mother, needs food and check-up."),
        ("Low", "Puppy wandering alone near {spot}, seems healthy but hungry.", "No visible injury."),
        ("Low", "Friendly street dog with a small cut on the ear near {spot}.", "Minor wound."),
    ],
    "Cat": [
        ("High", "Cat hit by a vehicle near {spot}, dragging its back legs.", "Possible spinal injury."),
        ("Medium", "Kitten with eyes crusted shut near {spot}.", "Eye infection in a kitten."),
        ("Medium", "Cat with a large abscess on the face near {spot}.", "Abscess needs draining."),
        ("Low", "Mother cat and kittens in a construction site near {spot}.", "Healthy, needs relocation."),
        ("Low", "Cat stuck on a roof near {spot} for two days.", "Trapped but uninjured."),
    ],
    "Cow": [
        ("High", "Cow with a plastic bag stuck in its mouth near {spot}, not eating.", "Obstruction, risk of choking."),
        ("Medium", "Calf with an injured foreleg tied up near {spot}.", "Leg injury, stable."),
    ],
    "Other": [
        ("Medium", "Injured crow unable to fly near {spot}.", "Wing injury in a bird."),
        ("Low", "Tortoise found on the road near {spot}.", "Uninjured, needs relocation."),
    ],
}
NOTES = ["Vet examined: wound cleaned and dressed, antibiotics started.", "X-ray done, no fracture. Pain relief given.",
         "Eating again and walking on all four legs.", "Moved to the recovery kennel for observation.",
         "Stitches removed, healing well.", "Fluids given overnight; much brighter this morning.",
         "Owner traced through the neighbours; advised on care.", "Dewormed and vaccinated before release."]
OUTCOME_NOTES = {"Released": "Released back to its area after recovery.", "Rehomed": "Adopted by a family in the neighbourhood.",
                 "Transferred": "Transferred to the university vet hospital for surgery.",
                 "Died": "Passed away despite treatment.", "Not found": "Searched the area twice; could not locate the animal."}


CASE_MARKER = "Dog limping near Peradeniya junction after a fall from the bridge railing; vet referral requested."


def cases():
    """Case by case (keyed on description and reported time), so an
    interrupted run resumes. Every random draw for a case happens before the
    database is checked, so a rerun reproduces exactly the same cases."""
    rng = random.Random("cases")
    print("- rescue cases ...")
    now = datetime.now(COLOMBO)
    workers = [uid for uid in (user_id(e) for e in ("staff@vff.org", "fieldofficer@vff.org", "s21444@sci.pdn.ac.lk",
                                                     "palindaabaya@gmail.com", "abayakoonpalinda@gmail.com")) if uid]
    assigners = [uid for uid in (user_id("hr@vff.org"), user_id("director@vff.org")) if uid]
    item = {i["item_name"]: i["id"] for i in rows("inventory_items", "id,item_name")}
    supplies = ["Cohesive bandages (7.5cm)", "Sterile gauze swabs (pack of 100)", "Povidone-iodine 10% (500ml)",
                "Amoxicillin LA injection (100ml)", "Meloxicam injection (20ml)", "Ringer lactate IV (500ml)"]
    weights = [w for *_, w in PLACES]
    start = date(2026, 6, 1)
    for n in range(115):
        animal = rng.choices(["Dog", "Cat", "Cow", "Other"], [64, 26, 6, 4])[0]
        urgency, text, reason = rng.choice(CASES[animal])
        place, lat, lng, _ = rng.choices(PLACES, weights)[0]
        spot = rng.choice(SPOTS)
        description = text.format(spot=spot)
        if n == 0:  # the section marker
            animal, urgency, description = "Dog", "Medium", CASE_MARKER
            reason, (place, lat, lng, _) = "Possible fracture, stable.", PLACES[1]
        reported_day = start + timedelta(days=rng.randint(0, (TODAY - start).days))
        reported = datetime.combine(reported_day, time(rng.randint(6, 20), rng.randint(0, 59)), COLOMBO)
        if reported > now:
            reported = now - timedelta(hours=1)
        age = (TODAY - reported_day).days
        if age > 10:
            final = "Resolved"
        else:
            final = rng.choices(["Resolved", "In Treatment", "Reported"], [35, 40, 25])[0]
        assignee = rng.choice(workers) if final != "Reported" or rng.random() < 0.3 else None
        values = {
            "animal_type": animal, "description": description, "status": "In Treatment" if final != "Reported" else "Reported",
            "lat": round(lat + rng.uniform(-0.03, 0.03), 5), "lng": round(lng + rng.uniform(-0.03, 0.03), 5),
            "assigned_to": assignee, "reported_at": reported.isoformat(), "updated_at": reported.isoformat(),
            "urgency": urgency, "urgency_reason": reason, "urgency_source": "ai",
        }
        events, t, supply = [], reported, None
        if assignee:
            t += timedelta(minutes=rng.randint(20, 300))
            by = assignee if rng.random() < 0.6 else rng.choice(assigners)
            events.append({"event_type": "assign", "assignee_id": assignee, "author_id": by, "created_at": t})
        if final != "Reported":
            t += timedelta(minutes=rng.randint(30, 600))
            events.append({"event_type": "status", "from_status": "Reported", "to_status": "In Treatment",
                           "author_id": assignee, "created_at": t})
            if rng.random() < 0.35:
                supply = (rng.choice(supplies), rng.randint(1, 3), t.date())
            for _ in range(rng.choice([0, 1, 1, 2])):
                t += timedelta(hours=rng.randint(6, 48))
                events.append({"event_type": "note", "body": rng.choice(NOTES), "author_id": assignee, "created_at": t})
        update = {}
        if final == "Resolved":
            outcome = rng.choices(list(OUTCOME_NOTES), [46, 14, 24, 8, 8])[0]
            t += timedelta(hours=rng.randint(12, 96))
            if t > now:
                t = now - timedelta(hours=2)
            events.append({"event_type": "status", "from_status": "In Treatment", "to_status": "Resolved",
                           "author_id": assignee, "created_at": t})
            events.append({"event_type": "outcome", "outcome": outcome, "body": OUTCOME_NOTES[outcome],
                           "author_id": assignee, "created_at": t})
            update = {"status": "Resolved", "outcome": outcome, "resolved_at": t.isoformat(), "updated_at": t.isoformat()}
        events = [e for e in events if e["created_at"] <= now]  # nothing from the future
        if not update and events:
            update = {"updated_at": events[-1]["created_at"].isoformat()}

        if rows("rescue_cases", "id", description=description, reported_at=values["reported_at"]):
            continue  # done on an earlier run
        case = sb.table("rescue_cases").insert(values).execute().data[0]
        if supply and supply[2] <= TODAY:
            try:
                move(item[supply[0]], supply[1], "Issue", str(supply[2]), case_id=case["id"], notes="Used on rescue case")
            except Exception:
                pass  # out of that item on that day: the case still stands without it
        for e in events:
            sb.table("rescue_case_events").insert({"case_id": case["id"], **e, "created_at": e["created_at"].isoformat()}).execute()
        if update:
            sb.table("rescue_cases").update(update).eq("id", case["id"]).execute()


def zones():
    if not section("outbreak zones", first("outbreak_zones", "id", title="Canine distemper cluster - Peradeniya")):
        return
    by = user_id("director@vff.org")
    sb.table("outbreak_zones").insert([
        {"animal_type": "Dog", "title": "Canine distemper cluster - Peradeniya",
         "description": "Eleven dogs with nasal discharge, coughing and twitching reported around Peradeniya town since early November. Keep pets vaccinated and away from sick strays.",
         "center_lat": 7.2690, "center_lng": 80.5960, "radius_km": 3, "declared_by": by,
         "declared_at": at(date(2026, 11, 2), 11), "is_active": True, "resolved_at": None},
        {"animal_type": "Dog", "title": "Parvovirus cases - Negombo",
         "description": "Several puppies with bloody diarrhoea in the Negombo fishing village area.",
         "center_lat": 7.2083, "center_lng": 79.8358, "radius_km": 2, "declared_by": by,
         "declared_at": at(date(2026, 8, 18), 10), "is_active": False, "resolved_at": at(date(2026, 9, 20), 15)},
    ]).execute()


# ---------------------------------------------------------------------------
# 6. volunteers and shifts
# ---------------------------------------------------------------------------

SKILLS = ["animal_handling", "transport_driving", "veterinary", "fostering", "fundraising", "admin_office",
          "media_photography", "community_outreach"]
AVAIL = ["weekday_mornings", "weekday_afternoons", "weekday_evenings", "weekends", "on_call"]


def volunteers():
    """Row by row (volunteers by email, shifts by title and date), so an
    interrupted run resumes. Random draws happen before each database check."""
    rng = random.Random("volunteers")
    print("- volunteers and shifts ...")
    reviewers = [user_id("hr@vff.org"), user_id("director@vff.org")]
    names = ["Amaya Perera", "Kavindu Senaratne", "Nethmi Wijesinghe", "Ravindu Jayawardena", "Hiruni Gamage",
             "Sahan Rathnayake", "Dulani Abeywickrama", "Yasiru Fernando", "Pavithra Kumari", "Isuru Bandara",
             "Thisuri Silva", "Mohamed Rizan", "Ayesha Nazeer", "Kajan Sivaraj", "Oshini Weerakoon",
             "Chamod Dissanayake", "Senuri Herath", "Lakshan Peiris", "Minoli de Alwis", "Tharushi Ekanayake",
             "Dimuth Karunaratne", "Nadeeka Liyanage", "Ruchira Samarakoon", "Hansika Jayasuriya"]
    statuses = ["approved"] * 14 + ["pending"] * 4 + ["rejected"] * 3 + ["inactive"] * 3
    approved = []
    for n, (name, status) in enumerate(zip(names, statuses)):
        email = name.lower().replace(" ", ".").replace("de.", "de") + "@example.com"
        applied = date(2026, 6, 1) + timedelta(days=rng.randint(0, 150))
        if status == "pending":
            applied = TODAY - timedelta(days=rng.randint(1, 9))
        reviewed = applied + timedelta(days=rng.randint(1, 5)) if status != "pending" else None
        values = {
            "full_name": name, "email": email, "phone": f"07{rng.randint(0, 8)}{rng.randint(1000000, 9999999)}",
            "skills": rng.sample(SKILLS, rng.randint(1, 3)), "availability": rng.sample(AVAIL, rng.randint(1, 2)),
            "status": status, "access_token": token(f"volunteer-{email}"),
            "applied_at": at(applied, rng.randint(8, 21)), "reviewed_at": at(reviewed, 10) if reviewed else None,
            "reviewed_by": rng.choice(reviewers) if reviewed else None,
            "link_shared_at": at(reviewed + timedelta(days=1), 11) if status == "approved" and rng.random() < 0.6 else None,
            "staff_notes": "Vet student, good with nervous dogs." if status == "approved" and n % 5 == 0 else None,
        }
        v = first("volunteers", "id", email=email) or sb.table("volunteers").insert(values).execute().data[0]
        if status == "approved":
            approved.append(v["id"])

    prog = {p["program_name"]: p["id"] for p in rows("programs", "id,program_name")}
    creator = user_id("staff@vff.org")
    shifts = [
        ("2026-06-20", "Peradeniya ABC camp - surgery support", "Peradeniya Campus ABC Camp", "University of Peradeniya", "08:00", "13:00", 6),
        ("2026-07-05", "Kandy Lake vaccination day - handlers", "Kandy Lake Round Vaccination Day", "Kandy Lake Round", "07:30", "12:30", 8),
        ("2026-08-09", "Kurunegala mobile clinic - registration desk", "Kurunegala Mobile Vet Clinic", "Kurunegala town hall", "08:00", "14:00", 4),
        ("2026-09-26", "Rabies drive - Saturday clinic", "Rabies Vaccination Drive", "Kandy Municipal Council grounds", "08:00", "12:00", 6),
        ("2026-10-17", "Rabies drive - Saturday clinic", "Rabies Vaccination Drive", "Kandy Municipal Council grounds", "08:00", "12:00", 6),
        ("2026-11-07", "Distemper response - ward support", "Distemper Response - Peradeniya", "Peradeniya isolation ward", "09:00", "15:00", 4),
        ("2026-11-21", "Rabies drive - Saturday clinic", "Rabies Vaccination Drive", "Kandy Municipal Council grounds", "08:00", "12:00", 6),
        ("2026-11-28", "Sterilisation - post-op recovery", "Street Dog Sterilization", "Faculty of Veterinary Medicine, Peradeniya", "09:00", "15:00", 4),
        ("2026-12-05", "Udawalawe clinic - transport and setup", "Udawalawe Community Animal Clinic", "Udawalawe", "06:00", "15:00", 5),
        ("2026-12-13", "Adoption fair - stall volunteers", "Colombo Year-End Adoption Fair", "Viharamahadevi Park, Colombo 07", "08:30", "16:30", 10),
    ]
    for d, title, program, location, start, end, needed in shifts:
        picked = rng.sample(approved, min(len(approved), needed + rng.randint(-2, 1)))
        plan = []
        for vid in picked:
            past = d < str(TODAY)
            response = (rng.choices(["accepted", "declined"], [85, 15])[0] if past
                        else rng.choices(["accepted", "pending", "declined"], [50, 40, 10])[0])
            assigned = date.fromisoformat(d) - timedelta(days=rng.randint(5, 10))
            plan.append({
                "volunteer_id": vid, "response": response,
                "responded_at": at(assigned + timedelta(days=1), 19) if response != "pending" else None,
                "decline_reason": "Exams that week" if response == "declined" and rng.random() < 0.5 else None,
                "assigned_by": creator, "assigned_at": at(assigned, 11),
            })
        if first("volunteer_shifts", "id", title=title, shift_date=d):
            continue  # done on an earlier run
        s = sb.table("volunteer_shifts").insert({
            "title": title, "description": f"Help the team at {location}. Wear closed shoes; water and lunch provided.",
            "location": location, "shift_date": d, "start_time": start, "end_time": end,
            "volunteers_needed": needed, "is_cancelled": False, "created_by": creator,
            "created_at": at(date.fromisoformat(d) - timedelta(days=12), 10), "program_id": prog.get(program),
        }).execute().data[0]
        for a in plan:
            sb.table("volunteer_assignments").insert({**a, "shift_id": s["id"]}).execute()


# ---------------------------------------------------------------------------
# 7. leave and November attendance
# ---------------------------------------------------------------------------

def leave_and_attendance():
    """Leave by employee and start date, attendance by employee and day, so an
    interrupted run resumes."""
    rng = random.Random("leave_and_attendance")
    print("- leave and attendance ...")
    hr = user_id("hr@vff.org")
    emps = rows("employee_profile", "id,user_id,date_joined,status")
    emps.sort(key=lambda e: e["id"])  # stable order, so a rerun picks the same people
    staff = [e for e in emps if e["status"] == "Active" and (e["date_joined"] or "2000") < "2026-11-01"]
    plan = [  # (type, start, end, status, reason)
        (1, "2026-07-20", "2026-07-22", "Approved", "Family wedding in Matara"),
        (3, "2026-08-11", "2026-08-12", "Approved", "Fever, medical certificate attached"),
        (2, "2026-09-04", "2026-09-04", "Approved", "Personal errand at the bank"),
        (1, "2026-10-12", "2026-10-16", "Approved", "Annual trip to Ella"),
        (3, "2026-11-05", "2026-11-05", "Approved", "Dental appointment"),
        (1, "2026-12-22", "2026-12-24", "Approved", "Christmas with family"),
        (1, "2026-11-24", "2026-11-25", "Pending", "Sister's graduation in Colombo"),
        (2, "2026-11-27", "2026-11-27", "Pending", "House moving"),
        (1, "2026-12-29", "2026-12-31", "Pending", "Year-end holiday"),
        (2, "2026-10-02", "2026-10-02", "Rejected", "Short notice, clinic day"),
    ]
    on_leave = {}
    for n, (type_id, s, e, status, reason) in enumerate(plan):
        emp = staff[n % len(staff)]
        working = len(weekdays(date.fromisoformat(s), date.fromisoformat(e)))
        requested = date.fromisoformat(s) - timedelta(days=rng.randint(4, 14))
        if requested > TODAY:
            requested = TODAY - timedelta(days=1)
        if not rows("leave_requests", "id", employee_id=emp["id"], start_date=s):
            sb.table("leave_requests").insert({
                "employee_id": emp["id"], "leave_type_id": type_id, "start_date": s, "end_date": e, "half_day": "none",
                "days": working, "reason": reason, "status": status, "requested_by": emp["user_id"] or hr,
                "requested_at": at(requested, 9),
                "decided_by": hr if status != "Pending" else None,
                "decided_at": at(requested + timedelta(days=1), 14) if status != "Pending" else None,
                "decision_note": "Clinic day, please pick another date." if status == "Rejected" else None,
            }).execute()
        if status == "Approved":
            for d in weekdays(date.fromisoformat(s), date.fromisoformat(e)):
                on_leave[(emp["id"], d)] = True

    existing = {(a["employee_id"], a["target_date"]) for a in rows("attendance_log", "employee_id,target_date")}
    for emp in [e for e in emps if e["status"] == "Active"]:
        joined = date.fromisoformat(emp["date_joined"]) if emp["date_joined"] else date(2000, 1, 1)
        for d in weekdays(date(2026, 11, 2), date(2026, 11, 13)):
            day_rng = random.Random(f"attendance-{emp['id']}-{d}")  # same answer on every run
            if d < joined or (emp["id"], str(d)) in existing or on_leave.get((emp["id"], d)) or day_rng.random() < 0.03:
                continue
            cin = datetime.combine(d, time(7, 40), COLOMBO) + timedelta(minutes=day_rng.randint(0, 55))
            cout = datetime.combine(d, time(16, 25), COLOMBO) + timedelta(minutes=day_rng.randint(0, 70))
            sb.table("attendance_log").insert({
                "employee_id": emp["id"], "target_date": str(d), "clock_in": cin.isoformat(),
                "clock_out": cout.isoformat(), "worked_hours": round((cout - cin).total_seconds() / 3600, 2),
                "is_locked": d <= date(2026, 11, 6),
            }).execute()


# ---------------------------------------------------------------------------

def team():
    if not section("program teams", first("program_assignments", "id", role_on_program="Lead veterinarian")):
        return
    emp = {e["first_name"] + " " + e["last_name"]: e["id"] for e in rows("employee_profile", "id,first_name,last_name")}
    teams = {
        "Rabies Vaccination Drive": [("Pradeep Bandara", "Lead veterinarian"), ("Ishara Jayawardena", "Vet nurse"), ("Kasun Herath", "Field coordinator")],
        "Street Dog Sterilization": [("Sanjeewa Rajapaksha", "Surgeon"), ("Hasini Kumarasinghe", "Vet nurse"), ("Lahiru Madushanka", "Field officer")],
        "Distemper Response - Peradeniya": [("Sachini Ekanayake", "Ward veterinarian"), ("Tharindu Dissanayake", "Field officer")],
        "School Awareness Programme - Kandy": [("Thilini Perera", "Presenter"), ("Chathura Wijesekara", "Driver")],
        "Colombo Year-End Adoption Fair": [("Nadeesha Wickramasinghe", "Organiser"), ("Kamala Silva", "Adoption counsellor")],
        "Udawalawe Community Animal Clinic": [("Pradeep Bandara", "Lead veterinarian"), ("Chathura Wijesekara", "Driver")],
    }
    progs = {p["program_name"]: p["id"] for p in rows("programs", "id,program_name")}
    for program, members in teams.items():
        for name, role in members:
            if program in progs and name in emp:
                try:
                    sb.table("program_assignments").insert({"program_id": progs[program], "employee_id": emp[name],
                                                            "role_on_program": role}).execute()
                except Exception:
                    pass  # already on the team


if __name__ == "__main__":
    tidy()
    people()
    programs_and_stock()
    print("4. Money")
    ledger()
    donations()
    print("5. Rescue")
    cases()
    zones()
    print("6. Volunteers")
    volunteers()
    print("7. People admin")
    leave_and_attendance()
    team()
    print("Done.")
