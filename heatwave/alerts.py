"""Alert levels, IMD-style heatwave thresholds, the alert log and advisories.

IMD (India Meteorological Department) heatwave criteria, as used here
-------------------------------------------------------------------
A heat wave is declared when the MAXIMUM temperature of a station reaches:
    Plains  : >= 40 C     Coastal : >= 37 C     Hilly : >= 30 C
AND the departure from the normal maximum is >= 4.5 C  (Heat Wave)
                                           or >= 6.5 C  (Severe Heat Wave).
Independent of departure (absolute criterion):
    >= 45 C -> Heat Wave        >= 47 C -> Severe Heat Wave

NOTE: IMD applies these to the *daily maximum*. A live sensor gives
instantaneous readings, so each reading is used as a proxy for the maximum.
"""
import numpy as np
import pandas as pd

# ---- alert levels ---------------------------------------------------------
NORMAL, HEAT_WAVE, SEVERE = 0, 1, 2
LEVEL_NAMES = {NORMAL: "Normal", HEAT_WAVE: "Heat Wave", SEVERE: "Severe Heat Wave"}
LEVEL_COLORS = {NORMAL: "#2e9e4f", HEAT_WAVE: "#e6a100", SEVERE: "#d62828"}

# ---- station-type thresholds (deg C) ---------------------------------------
STATION_THRESHOLDS = {"Plains": 40.0, "Coastal": 37.0, "Hilly": 30.0}
# Rough default "normal maximum" per station type; the user can edit this
# in the sidebar because the real value depends on city and month.
DEFAULT_NORMAL_MAX = {"Plains": 39.0, "Coastal": 33.0, "Hilly": 25.0}

DEPARTURE_HEAT_WAVE = 4.5
DEPARTURE_SEVERE = 6.5
ABSOLUTE_HEAT_WAVE = 45.0
ABSOLUTE_SEVERE = 47.0


def thresholds(station: str, normal_max: float):
    """Return (heat_wave_temp, severe_temp): the temperature at which each
    level starts, combining the station threshold, the departure rule and
    the absolute 45 / 47 C rule.
    """
    base = STATION_THRESHOLDS[station]
    # Departure rule only counts once the station threshold is also reached
    hw = min(max(base, normal_max + DEPARTURE_HEAT_WAVE), ABSOLUTE_HEAT_WAVE)
    sev = min(max(base, normal_max + DEPARTURE_SEVERE), ABSOLUTE_SEVERE)
    return hw, sev


def classify(temps, hw: float, sev: float):
    """Vectorised classification: 0 normal, 1 heat wave, 2 severe."""
    t = np.asarray(temps, dtype=float)
    return np.where(t >= sev, SEVERE, np.where(t >= hw, HEAT_WAVE, NORMAL)).astype(int)


def debounce(levels, n: int):
    """Only change the 'confirmed' level after the new level has been seen
    n readings in a row. Stops the alert flickering when the temperature
    hovers around a threshold (sensor noise).
    """
    levels = list(levels)
    if not levels:
        return np.array([], dtype=int)
    current, candidate, count = levels[0], None, 0
    out = []
    for v in levels:
        if v == current:
            candidate, count = None, 0
        else:
            count = count + 1 if v == candidate else 1
            candidate = v
            if count >= max(1, n):
                current, candidate, count = v, None, 0
        out.append(current)
    return np.array(out, dtype=int)


def build_alert_log(df: pd.DataFrame) -> pd.DataFrame:
    """Alert log: one row each time the confirmed level changes.

    df needs columns: time, temperature, humidity, heat_index, level.
    """
    cols = ["Time", "Level", "Event", "Temp (°C)", "Humidity (%)", "Heat index (°C)"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    lvl = df["level"].to_numpy()
    rows = []
    for i in range(len(df)):
        prev = lvl[i - 1] if i > 0 else None
        if prev is None and lvl[i] == NORMAL:
            continue                      # normal at the start: nothing to log
        if prev is not None and lvl[i] == prev:
            continue
        if prev is None:
            event = "Alert active at start of data"
        elif lvl[i] > prev:
            event = "Escalated"
        else:
            event = "Eased"
        r = df.iloc[i]
        rows.append({
            "Time": r["time"], "Level": LEVEL_NAMES[int(lvl[i])], "Event": event,
            "Temp (°C)": r["temperature"], "Humidity (%)": r["humidity"],
            "Heat index (°C)": r["heat_index"],
        })
    return pd.DataFrame(rows, columns=cols)


# ---- early-warning advice ----------------------------------------------------
# General public-health guidance in the spirit of NDMA / IMD heat advisories.
ADVICE = {
    NORMAL: [
        "No heat alert. Carry on as usual.",
        "Keep drinking water regularly, even if you are not thirsty.",
        "Keep monitoring: the trend can change within hours.",
    ],
    HEAT_WAVE: [
        "Avoid going out in the sun between about 12:00 and 16:00.",
        "Drink water, ORS, lassi, buttermilk or lemon water often.",
        "Wear light, loose, light-coloured cotton clothes; cover head with a cloth or hat.",
        "Reschedule heavy outdoor work to early morning or evening.",
        "Watch for dizziness, headache, cramps or nausea; rest in shade and cool down.",
    ],
    SEVERE: [
        "Stay indoors in the coolest place available; go out only if essential.",
        "Stop outdoor labour and sports; open cooling centres / shade shelters.",
        "Check on elderly people, infants, pregnant women and people with illness.",
        "Never leave children or pets in a parked vehicle.",
        "Heatstroke signs (very high body temperature, confusion, no sweating, "
        "unconsciousness) are an emergency: cool the person and call 108 / 112.",
    ],
}
