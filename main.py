import os
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI(title="Home Climate API", version="1.0.0")

HA_URL = os.environ["HA_URL"].rstrip("/")
HA_TOKEN = os.environ["HA_TOKEN"]

TEMP_ENTITY = os.environ.get(
    "HA_TEMP_ENTITY",
    "sensor.ewelink_snzb_02p_temperatuur_2",
)
HUMIDITY_ENTITY = os.environ.get(
    "HA_HUMIDITY_ENTITY",
    "sensor.ewelink_snzb_02p_luchtvochtigheid_2",
)
DEWPOINT_ENTITY = os.environ.get(
    "HA_DEWPOINT_ENTITY",
    "sensor.dauwpunt_balkon",
)

PUBLIC_API_KEY = os.environ.get("PUBLIC_API_KEY")


async def get_state(entity_id: str) -> dict[str, Any]:
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            detail = "Home Assistant heeft het token geweigerd."
        elif exc.response.status_code == 404:
            detail = f"Entiteit niet gevonden: {entity_id}"
        else:
            detail = f"Home Assistant gaf status {exc.response.status_code}."

        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Home Assistant is niet bereikbaar.",
        ) from exc


def read_number(state: dict[str, Any], entity_id: str) -> float:
    value = state.get("state")

    if value in {None, "unknown", "unavailable"}:
        raise HTTPException(
            status_code=503,
            detail=f"Geen actuele waarde voor {entity_id}.",
        )

    try:
        return round(float(value), 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Ongeldige waarde voor {entity_id}.",
        ) from exc


def check_api_key(api_key: str | None) -> None:
    if PUBLIC_API_KEY and api_key != PUBLIC_API_KEY:
        raise HTTPException(status_code=401, detail="Ongeldige API-key.")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "ok",
        "endpoint": "/balcony",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/balcony")
async def balcony(api_key: str | None = None) -> dict[str, Any]:
    check_api_key(api_key)

    temperature_state = await get_state(TEMP_ENTITY)
    humidity_state = await get_state(HUMIDITY_ENTITY)
    dewpoint_state = await get_state(DEWPOINT_ENTITY)

    timestamps = [
        state.get("last_updated")
        for state in (
            temperature_state,
            humidity_state,
            dewpoint_state,
        )
        if state.get("last_updated")
    ]

    return {
        "location": "Amsterdam",
        "temperature_c": read_number(temperature_state, TEMP_ENTITY),
        "humidity_pct": read_number(humidity_state, HUMIDITY_ENTITY),
        "dewpoint_c": read_number(dewpoint_state, DEWPOINT_ENTITY),
        "measured_at": (
            max(timestamps)
            if timestamps
            else datetime.now().astimezone().isoformat()
        ),
        "source": "Home Assistant",
    }
