import re
import math
import random

SCENARIOS = {
    "Heat wave developing": {"base": 33.0, "rise": 0.3,  "hum": 65, "hum_fall": 0.5},
    "Severe heat wave":     {"base": 40.0, "rise": 0.5,  "hum": 50, "hum_fall": 0.8},
    "Normal summer day":    {"base": 30.0, "rise": 0.1,  "hum": 70, "hum_fall": 0.2},
    "Cooling after rain":   {"base": 38.0, "rise": -0.4, "hum": 80, "hum_fall": -1.0},
}
SCENARIO_NAMES = list(SCENARIOS.keys())


def parse_line(line):
    """Parse one Tinkercad serial line (millis,temp,humidity). Returns (temp, hum) or None."""
    m = re.match(r"^\s*\d+\s*,\s*([\d.]+)\s*,\s*([\d.]+)", line.strip())
    if m:
        temp, hum = float(m.group(1)), float(m.group(2))
        if -40 < temp < 80 and 0 <= hum <= 100:
            return temp, hum
    return None


def parse_text(text):
    """Parse all valid readings from a Tinkercad Serial Monitor paste."""
    return [r for line in text.splitlines() if (r := parse_line(line))]


def demo_reading(scenario, step):
    """Return (temp, humidity) for the given scenario and step number."""
    s        = SCENARIOS.get(scenario, list(SCENARIOS.values())[0])
    # diurnal cycle: each step = 2 minutes of simulated time
    hour     = (step * 2 / 60) % 24
    diurnal  = 3.0 * math.cos(2 * math.pi * (hour - 15) / 24)
    temp     = s["base"] + s["rise"] * step + diurnal + random.uniform(-0.3, 0.3)
    hum      = max(10.0, min(100.0, s["hum"] - s["hum_fall"] * step + random.uniform(-1, 1)))
    return round(temp, 1), round(hum, 1)
