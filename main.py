import hmac
import logging
import os
from typing import Any

import requests
from fastapi import FastAPI, HTTPException


# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Environment variables
# -------------------------------------------------------------------

def required_env(name: str) -> str:
    """
    Read a required environment variable.

    The app will fail clearly during deployment when a required
    environment variable is missing.
    """
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")

    return value


HA_URL = required_env("HA_URL").rstrip("/")
HA_TOKEN = required_env("HA_TOKEN")

# Balcony sensors
HA_TEMP_ENTITY = required_env("HA_TEMP_ENTITY")
HA_HUMIDITY_ENTITY = required_env("HA_HUMIDITY_ENTITY")
HA_DEWPOINT_ENTITY = required_env("HA_DEWPOINT_ENTITY")

# Bedroom sensor
HA_BEDROOM_TEMP_ENTITY = required_env("HA_BEDROOM_TEMP_ENTITY")

# Public API authentication
PUBLIC_API_KEY = required_env("PUBLIC_API_KEY")


# -------------------------------------------------------------------
# FastAPI app
# -------------------------------------------------------------------

app = FastAPI(
    title="Home Assistant Climate API",
    description="Read balcony and bedroom climate data from Home Assistant.",
    version="2.0.0",
)


# -------------------------------------------------------------------
# Home Assistant helper functions
# -------------------------------------------------------------------

def verify_api_key(api_key: str) -> None:
    """
    Verify the API key supplied as a query parameter.
    """
    if not hmac.compare_digest(api_key, PUBLIC_API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )


def get_ha_state(entity_id: str) -> dict[str, Any]:
    """
    Retrieve the current state of a Home Assistant entity.
    """
    url = f"{HA_URL}/api/states/{entity_id}"

    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10,
        )

        if response.status_code == 404:
            logger.error("Home Assistant entity not found: %s", entity_id)

            raise HTTPException(
                status_code=502,
                detail=f"Home Assistant entity not found: {entity_id}",
            )

        response.raise_for_status()

    except requests.Timeout as exc:
        logger.exception(
            "Timeout while contacting Home Assistant for %s",
            entity_id,
        )

        raise HTTPException(
            status_code=504,
            detail="Home Assistant did not respond in time",
        ) from exc

    except requests.RequestException as exc:
        logger.exception(
            "Error while contacting Home Assistant for %s",
            entity_id,
        )

        raise HTTPException(
            status_code=502,
            detail="Could not retrieve data from Home Assistant",
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        logger.exception(
            "Invalid JSON received from Home Assistant for %s",
            entity_id,
        )

        raise HTTPException(
            status_code=502,
            detail="Home Assistant returned an invalid response",
        ) from exc

    return data


def state_to_float(entity: dict[str, Any]) -> float:
    """
    Convert a Home Assistant sensor state into a number.
    """
    entity_id = entity.get("entity_id", "unknown")
    state = entity.get("state")

    if state in (None, "unknown", "unavailable"):
        raise HTTPException(
            status_code=503,
            detail=f"Sensor is currently unavailable: {entity_id}",
        )

    try:
        return float(state)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Sensor does not contain a numeric value: {entity_id}",
        ) from exc


def read_measurement(entity_id: str) -> dict[str, Any]:
    """
    Retrieve and standardise one Home Assistant measurement.
    """
    entity = get_ha_state(entity_id)
    attributes = entity.get("attributes", {})

    return {
        "value": state_to_float(entity),
        "unit": attributes.get("unit_of_measurement"),
        "measured_at": entity.get("last_updated"),
        "entity_id": entity.get("entity_id", entity_id),
    }


def get_balcony_payload() -> dict[str, Any]:
    """
    Build the complete balcony response.
    """
    temperature = read_measurement(HA_TEMP_ENTITY)
    humidity = read_measurement(HA_HUMIDITY_ENTITY)
    dewpoint = read_measurement(HA_DEWPOINT_ENTITY)

    return {
        "temperature": temperature["value"],
        "humidity": humidity["value"],
        "dewpoint": dewpoint["value"],

        # Kept for compatibility with the existing endpoint.
        # This is the Home Assistant update time of the temperature sensor.
        "measured_at": temperature["measured_at"],

        "units": {
            "temperature": temperature["unit"] or "°C",
            "humidity": humidity["unit"] or "%",
            "dewpoint": dewpoint["unit"] or "°C",
        },

        # Separate timestamps in case the sensors were updated
        # at slightly different moments.
        "measured_at_by_sensor": {
            "temperature": temperature["measured_at"],
            "humidity": humidity["measured_at"],
            "dewpoint": dewpoint["measured_at"],
        },

        "entities": {
            "temperature": temperature["entity_id"],
            "humidity": humidity["entity_id"],
            "dewpoint": dewpoint["entity_id"],
        },
    }


def get_bedroom_payload() -> dict[str, Any]:
    """
    Build the bedroom response.
    """
    temperature = read_measurement(HA_BEDROOM_TEMP_ENTITY)

    return {
        "temperature": temperature["value"],
        "unit": temperature["unit"] or "°C",
        "measured_at": temperature["measured_at"],
        "entity_id": temperature["entity_id"],
    }


# -------------------------------------------------------------------
# API endpoints
# -------------------------------------------------------------------

@app.get("/")
def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "Home Assistant Climate API",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "balcony": "/balcony?api_key=YOUR_API_KEY",
            "bedroom": "/bedroom?api_key=YOUR_API_KEY",
            "climate": "/climate?api_key=YOUR_API_KEY",
            "docs": "/docs",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


@app.get("/balcony")
def balcony(api_key: str) -> dict[str, Any]:
    """
    Return balcony temperature, humidity and dew point.
    """
    verify_api_key(api_key)
    return get_balcony_payload()


@app.get("/bedroom")
def bedroom(api_key: str) -> dict[str, Any]:
    """
    Return the bedroom temperature.
    """
    verify_api_key(api_key)
    return get_bedroom_payload()


@app.get("/climate")
def climate(api_key: str) -> dict[str, Any]:
    """
    Return balcony and bedroom climate data in one response.
    """
    verify_api_key(api_key)

    return {
        "balcony": get_balcony_payload(),
        "bedroom": get_bedroom_payload(),
    }
