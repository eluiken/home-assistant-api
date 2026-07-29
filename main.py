@app.get("/balcony")
async def balcony(api_key: str | None = None):
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
        "measured_at": max(timestamps) if timestamps else None,
        "source": "Home Assistant",
    }
