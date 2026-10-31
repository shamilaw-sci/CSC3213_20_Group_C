import sys
import os
import logging
logging.basicConfig(level=logging.INFO)

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Running this file directly puts app/ on sys.path rather than backend/, so the
# "app" package cannot import itself. The __main__ block below exists to be run
# that way, so put backend/ on the path instead of requiring PYTHONPATH to be
# set by hand.
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

vendor_dir = os.path.join(backend_dir, "_vendor")
if os.path.exists(vendor_dir) and vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import (
    hr,
    hr_calendar,
    attendance_month,
    leave,
    finance,
    inventory,
    auth,
    reports,
    admin,
    rescue_cases,
    programs,
    chat,
    volunteers,
)


# A volunteer's link token is their only credential, and it travels in the URL
# path. uvicorn's access logger writes the full path for every request, so
# without this every token would be written to disk in plaintext on first use —
# and then shipped to wherever those logs are aggregated.
#
# Implemented as a logging filter rather than by moving the token to a header:
# the whole point is a link a coordinator can paste into WhatsApp, so it has to
# be in the URL. The filter rewrites the path in the log record's args, leaving
# the request itself untouched.
_TOKEN_IN_PATH = re.compile(r"(/my-assignments/)[^/\s?]+")


class RedactVolunteerToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access formats as (client, method, path, http_version, status);
        # the path is index 2. Guarded rather than assumed, so a uvicorn change
        # degrades to "not redacted" rather than crashing every request's log.
        if record.args and isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str) and "/my-assignments/" in path:
                args = list(record.args)
                args[2] = _TOKEN_IN_PATH.sub(r"\1<redacted>", path)
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(RedactVolunteerToken())


app = FastAPI(title="VFF IMS API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root Endpoint
@app.get("/")
async def root():
    return {"message": "VFF Integrated Management System API is online"}

# Include Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(hr.router, prefix="/api/hr", tags=["HR"])
app.include_router(hr_calendar.router, prefix="/api/hr", tags=["HR: schedules & holidays"])
app.include_router(attendance_month.router, prefix="/api/hr", tags=["HR: attendance month"])
app.include_router(leave.router, prefix="/api/leave", tags=["Leave"])
app.include_router(finance.router, prefix="/api/finance", tags=["Finance"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(rescue_cases.router, prefix="/api/rescue_cases", tags=["Rescue Cases"])
app.include_router(programs.router, prefix="/api/programs", tags=["Programs"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(volunteers.router, prefix="/api/volunteers", tags=["Volunteers"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)