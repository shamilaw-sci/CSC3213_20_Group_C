# Holiday calendar data

One CSV per year, transcribed from the official sources and loaded into the
`holidays` table by **HR → Schedules & Holidays → Import** (or
`POST /api/hr/holidays/import?year=YYYY`). Importing is idempotent.

| Column | Meaning | Source |
|---|---|---|
| `date`, `name` | As printed in the gazette | Annual Gazette Extraordinary under the Holidays Act, No. 29 of 1971 |
| `public`, `bank` | Gazette's `*` and `=` markers | same gazette |
| `mercantile` | Holiday under the Shop and Office Employees Act | Central Bank of Sri Lanka, `cbsl.gov.lk/en/about/about-the-bank/bank-holidays-<year>`; the gazette does not mark these |
| `source` | Where the row came from | — |

Whether a holiday is a **day off at VFF** is not in the file. The importer
applies VFF's policy (confirmed 2026-10-29): mercantile holidays and every
Full Moon Poya Day are days off; other public holidays are working days but
still shown in the calendar. HR can change any single day afterwards.

**Why a file per year instead of a rule.** Poya days follow the Sri Lankan
lunar calendar: a year can have 13 (2026 has Adhi Poson), and a full moon
near midnight can move the official day. Only the gazette is authoritative.
The importer cross-checks every Poya against an astronomical full-moon
calculation and warns if one is more than a day away. That catches typing
mistakes; it never adds or moves a date.

## Adding a year

1. Find the Gazette Extraordinary "Public and Bank Holidays for the Year
   YYYY" on documents.gov.lk (usually published mid-year, the year before).
2. Copy every row of its schedule, with `public`/`bank` from its markers.
3. Take `mercantile` from the Central Bank page for that year.
4. Cite both in `source`, open a PR, then import from the app.

## Files

| File | Gazette |
|---|---|
| `2026.csv` | Extraordinary No. 2438/22, 27 May 2025 (26 entries, 13 Poya days) |
| `2027.csv` | Extraordinary No. 2493/05, 16 June 2026 (25 entries, 12 Poya days) |
