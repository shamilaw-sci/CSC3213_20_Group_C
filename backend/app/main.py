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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import (
    hr,
    finance,
    inventory,
    auth,
    reports,
    admin,
    rescue_cases,
    programs,
    chat,
)


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
app.include_router(finance.router, prefix="/api/finance", tags=["Finance"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(rescue_cases.router, prefix="/api/rescue_cases", tags=["Rescue Cases"])
app.include_router(programs.router, prefix="/api/programs", tags=["Programs"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)