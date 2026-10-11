"""Heat index (Rothfusz regression) and a simple short-term trend forecast."""
import numpy as np
import pandas as pd


def heat_index_c(temp_c, rh):
    """Heat index in deg C using the NWS Rothfusz regression.

    The regression works in Fahrenheit, so we convert in and out.
    For mild conditions the NWS uses a simpler (Steadman) formula; the
    regression is only used once the average of the two is >= 80 F.
    Two small NWS adjustments are applied for very dry / very humid air.
    Works on scalars or numpy arrays / pandas Series.
    """
    t = np.asarray(temp_c, dtype=float) * 9.0 / 5.0 + 32.0   # deg F
    r = np.asarray(rh, dtype=float)                           # % RH

    simple = 0.5 * (t + 61.0 + ((t - 68.0) * 1.2) + (r * 0.094))

    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r
          - 0.22475541 * t * r - 6.83783e-3 * t ** 2
          - 5.481717e-2 * r ** 2 + 1.22874e-3 * t ** 2 * r
          + 8.5282e-4 * t * r ** 2 - 1.99e-6 * t ** 2 * r ** 2)

    # Adjustment 1: very dry air (RH < 13 %, 80-112 F) lowers the index
    dry = (r < 13) & (t >= 80) & (t <= 112)
    adj_dry = ((13.0 - r) / 4.0) * np.sqrt(np.clip((17.0 - np.abs(t - 95.0)) / 17.0, 0, None))
    hi = np.where(dry, hi - adj_dry, hi)

    # Adjustment 2: very humid air (RH > 85 %, 80-87 F) raises the index
    humid = (r > 85) & (t >= 80) & (t <= 87)
    adj_humid = ((r - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    hi = np.where(humid, hi + adj_humid, hi)

    # Mild conditions: use the simple formula instead
    hi = np.where((simple + t) / 2.0 >= 80.0, hi, simple)

    return np.round((hi - 32.0) * 5.0 / 9.0, 1)


def heat_index_category(hi_c: float) -> str:
    """Approximate NWS-style heat-index risk band (thresholds in deg C)."""
    if hi_c < 27:
        return "Comfortable"
    if hi_c < 32:
        return "Caution"
    if hi_c < 39:
        return "Extreme caution"
    if hi_c < 51:
        return "Danger"
    return "Extreme danger"


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with a heat_index column added."""
    out = df.copy()
    out["heat_index"] = heat_index_c(out["temperature"], out["humidity"])
    return out


def forecast(df: pd.DataFrame, window_min: float, horizon_min: float, n_points: int = 30):
    """Simple linear TREND EXTRAPOLATION - not a weather model.

    Fits a straight line (numpy.polyfit, degree 1) to temperature and heat
    index over the last `window_min` minutes and extends it `horizon_min`
    minutes into the future. The band is +/- 1.96 x the residual standard
    deviation of the fit (a rough guide to scatter, not a true confidence
    interval). It knows nothing about the daily cycle, fronts or rain.

    Returns a dict with ok=False and a reason when there is too little data.
    """
    if df.empty:
        return {"ok": False, "reason": "No data yet."}
    last_t = df["time"].iloc[-1]
    win = df[df["time"] >= last_t - pd.Timedelta(minutes=window_min)]
    if len(win) < 5:
        return {"ok": False,
                "reason": f"Need at least 5 readings in the last {window_min:.0f} min "
                          f"(have {len(win)})."}

    # x = hours relative to the latest reading (<= 0 for the past)
    x = (win["time"] - last_t).dt.total_seconds().to_numpy() / 3600.0
    if np.ptp(x) == 0:
        return {"ok": False, "reason": "All readings share one timestamp."}

    xf = np.linspace(0.0, horizon_min / 60.0, n_points + 1)   # includes "now"
    result = {"ok": True, "n": len(win), "window_min": window_min,
              "horizon_min": horizon_min,
              "times": pd.DatetimeIndex(last_t + pd.to_timedelta(xf, unit="h"))}

    for key, col in (("temp", "temperature"), ("hi", "heat_index")):
        y = win[col].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        resid = y - (slope * x + intercept)
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - float(np.sum(resid ** 2)) / ss_tot if ss_tot > 0 else 0.0
        sigma = float(resid.std(ddof=2)) if len(y) > 2 else 0.0
        result[key] = {"slope_per_h": float(slope), "pred": slope * xf + intercept,
                       "band": 1.96 * sigma, "r2": r2}
    return result
