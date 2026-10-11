THRESHOLDS = {
    "Plains":  {"station": 40, "normal": 39},
    "Coastal": {"station": 37, "normal": 33},
    "Hilly":   {"station": 30, "normal": 25},
}

COLORS = {
    "NORMAL":           "#2ecc71",
    "WARNING":          "#f39c12",
    "HEAT WAVE":        "#e67e22",
    "SEVERE HEAT WAVE": "#e74c3c",
}

ADVICE = {
    "NORMAL":           "No special precautions needed.",
    "WARNING":          "Stay hydrated. Avoid outdoor work between 12-3 PM.",
    "HEAT WAVE":        "Avoid direct sun. Keep elderly and children indoors.",
    "SEVERE HEAT WAVE": "Stay indoors. Emergency services on high alert.",
}


def get_level(temp, station_type="Plains"):
    """Return IMD alert level for a given temperature reading."""
    t         = THRESHOLDS[station_type]
    departure = temp - t["normal"]

    if temp >= 47 or (temp >= t["station"] and departure >= 6.5):
        return "SEVERE HEAT WAVE"
    if temp >= 45 or (temp >= t["station"] and departure >= 4.5):
        return "HEAT WAVE"
    if temp >= 37:
        return "WARNING"
    return "NORMAL"
