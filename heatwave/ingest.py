"""Getting data in: three sources, one common DataFrame format.

Every source ends up as a DataFrame with columns:
    time (datetime64), temperature (deg C), humidity (% RH)
"""
import threading
from collections import deque
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# DHT22 working range; anything outside is treated as a corrupt line
TEMP_RANGE = (-40.0, 80.0)
HUM_RANGE = (0.0, 100.0)


# =============================================================================
# 1. Parsing the Arduino CSV format:  millis,temperature,humidity
# =============================================================================
def parse_line(line: str):
    """Parse one serial line. Returns (millis, temp, hum) or None.

    Headers, blank lines, comments, half-received lines, NaN and
    out-of-range values all return None instead of raising.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.replace(";", ",").replace("\t", ",").split(",")]
    if len(parts) != 3:
        return None
    try:
        millis, temp, hum = float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:                       # e.g. the header line
        return None
    if not all(np.isfinite([millis, temp, hum])) or millis < 0:
        return None
    if not (TEMP_RANGE[0] <= temp <= TEMP_RANGE[1] and HUM_RANGE[0] <= hum <= HUM_RANGE[1]):
        return None
    return int(millis), temp, hum


def parse_text(text: str):
    """Parse a block of text. Returns (list_of_rows, number_of_skipped_lines).
    Header/blank/comment lines are not counted as 'skipped'."""
    rows, skipped = [], 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.lower().startswith("millis"):
            continue
        parsed = parse_line(s)
        if parsed is None:
            skipped += 1
        else:
            rows.append(parsed)
    return rows, skipped


def build_dataframe(rows, start: datetime, minutes_per_reading=None) -> pd.DataFrame:
    """Turn parsed rows into the common DataFrame.

    Arduino millis() only measures time since power-up (and restarts at 0 if
    the board resets), so we anchor it to a real start time:
      * minutes_per_reading=None -> use the millis differences as real time
      * minutes_per_reading=N    -> pretend each reading is N minutes apart.
        Handy because a Tinkercad run lasts a minute or two, while a heatwave
        develops over hours.
    """
    if not rows:
        return pd.DataFrame(columns=["time", "temperature", "humidity"])
    millis = np.array([r[0] for r in rows], dtype=float)
    # Handle millis() restarting at 0 after a reset: keep time increasing
    offset, fixed = 0.0, millis.copy()
    for i in range(1, len(millis)):
        if millis[i] < millis[i - 1]:
            offset += millis[i - 1] + 1000.0
        fixed[i] = millis[i] + offset
    if minutes_per_reading:
        elapsed_s = np.arange(len(rows)) * minutes_per_reading * 60.0
    else:
        elapsed_s = (fixed - fixed[0]) / 1000.0
    return pd.DataFrame({
        "time": pd.to_datetime(start) + pd.to_timedelta(elapsed_s, unit="s"),
        "temperature": [r[1] for r in rows],
        "humidity": [r[2] for r in rows],
    })


# =============================================================================
# 2. Live serial port (real Arduino) - pyserial in a background thread
# =============================================================================
def list_serial_ports():
    """Names of serial ports found on this PC (empty if pyserial missing)."""
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


class SerialReader:
    """Reads CSV lines from the Arduino in a background thread so the
    dashboard never blocks waiting for the port."""

    def __init__(self, port: str, baud: int, max_rows: int = 5000):
        import serial                       # imported here: demo mode needs no pyserial
        self.key = (port, baud)
        self.rows = deque(maxlen=max_rows)  # (pc_time, temperature, humidity)
        self.error = None
        self.skipped = 0
        self._stop = threading.Event()
        self._ser = serial.Serial(port, baud, timeout=1)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                raw = self._ser.readline().decode("utf-8", errors="ignore")
            except Exception as exc:        # cable unplugged, port closed ...
                self.error = str(exc)
                return
            if not raw.strip() or raw.lower().startswith("millis"):
                continue
            parsed = parse_line(raw)
            if parsed is None:
                self.skipped += 1
            else:
                # Timestamp with the PC clock at the moment of arrival
                self.rows.append((datetime.now(), parsed[1], parsed[2]))

    def dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(list(self.rows), columns=["time", "temperature", "humidity"])

    def clear(self):
        self.rows.clear()

    def close(self):
        self._stop.set()
        try:
            self._ser.close()
        except Exception:
            pass


_reader = None
_lock = threading.Lock()


def get_reader(port: str, baud: int) -> SerialReader:
    """Return the shared reader, (re)opening the port if settings changed."""
    global _reader
    with _lock:
        alive = _reader is not None and _reader._thread.is_alive()
        if _reader is None or _reader.key != (port, baud) or not alive:
            if _reader is not None:
                _reader.close()
            _reader = SerialReader(port, baud)
        return _reader


def close_reader():
    global _reader
    with _lock:
        if _reader is not None:
            _reader.close()
            _reader = None


# =============================================================================
# 3. Built-in demo simulator: synthetic Indian-summer data
# =============================================================================
SCENARIOS = ["Heat wave developing", "Severe heat wave", "Normal summer"]
_STATION_TEMP_OFFSET = {"Plains": 0.0, "Coastal": -4.0, "Hilly": -12.0}
_STATION_HUM_OFFSET = {"Plains": 0.0, "Coastal": 20.0, "Hilly": 5.0}


def demo_data(n: int, station: str, scenario: str, start: datetime,
              step_min: int = 10, seed: int = 7) -> pd.DataFrame:
    """Generate n synthetic readings, one every step_min minutes.

    Model: mean level + daily sine cycle (peak ~15:00, minimum ~03:00)
    + a heat-wave anomaly that depends on the scenario
    + smooth random noise (AR(1)), so values drift like a real sensor.
    Humidity falls as temperature rises (dry heat of the plains).

    The random numbers are drawn in sequence from fixed seeds, so asking
    for n+1 readings returns the same first n readings - the chart simply
    extends instead of jumping around.
    """
    rng = np.random.default_rng(seed)            # temperature noise
    rng_h = np.random.default_rng(seed + 1)      # separate stream for humidity noise,
    idx = np.arange(n)                           # so each stays stable as n grows
    hours = idx * step_min / 60.0
    clock_hour = start.hour + start.minute / 60.0 + hours

    base_mean, amplitude = 32.0, 7.5            # plains, May
    diurnal = amplitude * np.cos(2 * np.pi * (clock_hour - 15.0) / 24.0)

    days = hours / 24.0
    if scenario == "Heat wave developing":
        anomaly = 8.0 * np.clip(days / 4.0, 0, 1)        # builds up over 4 days
    elif scenario == "Severe heat wave":
        anomaly = 7.5 + 0.5 * np.sin(days)               # stays very hot
    else:
        anomaly = np.zeros(n)

    # AR(1) noise: each value remembers 80 % of the previous one
    shocks = rng.normal(0.0, 0.35, n)
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.8 * noise[i - 1] + shocks[i]

    temp = base_mean + _STATION_TEMP_OFFSET[station] + diurnal + anomaly + noise
    hum = 90.0 - 3.2 * (temp - _STATION_TEMP_OFFSET[station] - 27.0)
    hum = hum + _STATION_HUM_OFFSET[station] + rng_h.normal(0.0, 2.0, n)

    return pd.DataFrame({
        "time": pd.to_datetime(start) + pd.to_timedelta(idx * step_min, unit="min"),
        "temperature": np.round(temp, 1),
        "humidity": np.round(np.clip(hum, 8.0, 98.0), 1),
    })
