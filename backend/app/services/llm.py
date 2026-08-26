import httpx
from app.core import config


async def complete(messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload = {"model": config.LLM_MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{config.LLM_BASE_URL}chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()