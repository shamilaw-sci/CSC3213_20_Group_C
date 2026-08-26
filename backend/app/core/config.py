# backend/app/core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY: str = os.environ.get("LLM_API_KEY")
LLM_BASE_URL: str = os.environ.get(
    "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
LLM_MODEL: str = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

if not LLM_API_KEY:
    raise ValueError("LLM_API_KEY not found in environment variables")