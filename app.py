"""Heatwave Monitoring, Prediction and Early Warning - Streamlit dashboard.

Run with:   streamlit run app.py

Data flow:  source (demo / pasted Tinkercad log / live serial)
              -> heatwave.ingest     (parse + common DataFrame)
              -> heatwave.analytics  (heat index, trend forecast)
              -> heatwave.alerts     (IMD levels, alert log, advice)
              -> this file           (tiles, chart, tables, panels)
"""
import time
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from heatwave import alerts, analytics, ingest

st.set_page_config(page_title="Heatwave Early Warning", page_icon="🌡️", layout="wide")

SAMPLE_PATH = Path(__file__).parent / "sample_serial_log.txt"
SOURCE_DEMO = "Demo simulator"
SOURCE_PASTE = "Tinkercad log (paste / upload)"
SOURCE_SERIAL = "Live Arduino (serial port)"

# Demo timing: start with 4 days of history, then add one 10-minute reading
# every 2 real seconds so the dashboard "runs" at 300x speed.
DEMO_INIT_READINGS = 576
DEMO_STEP_MIN = 10
DEMO_SECONDS_PER_READING = 2


# =============================================================================
# Sidebar
# =============================================================================
st.sidebar.title("🌡️ Settings")
source = st.sidebar.radio("Data source", [SOURCE_DEMO, SOURCE_PASTE, SOURCE_SERIAL])

# ---- source-specific controls ------------------------------------------------
if source == SOURCE_DEMO:
    scenario = st.sidebar.selectbox("Scenario", ingest.SCENARIOS)
    st.sidebar.button("Restart demo", on_click=lambda: st.session_state.pop("demo_key", None))

elif source == SOURCE_PASTE:
    paste_mode = st.sidebar.radio("Input", ["Bundled sample", "Paste text", "Upload file"])
    pasted_text = ""
    if paste_mode == "Bundled sample":
        pasted_text = SAMPLE_PATH.read_text() if SAMPLE_PATH.exists() else ""
    elif paste_mode == "Paste text":
        pasted_text = st.sidebar.text_area(
            "Serial Monitor output", height=180,
            placeholder="millis,temperature,humidity\n2000,31.3,66.7\n4000,31.8,65.9")
    else:
        up = st.sidebar.file_uploader("Log file (.txt / .csv)", type=["txt", "csv", "log"])
        if up is not None:
            pasted_text = up.getvalue().decode("utf-8", errors="ignore")
    compress = st.sidebar.checkbox(
        "Treat each reading as N minutes", value=True,
        help="A Tinkercad run lasts only a minute or two. Stretch it so the log "
             "looks like hours of weather and the trend forecast makes sense.")
    minutes_per_reading = st.sidebar.number_input("Minutes per reading", 1, 120, 10) if compress else None
    log_date = st.sidebar.date_input("Log start date", date.today())
    log_time = st.sidebar.time_input("Log start time", dtime(6, 0))

else:
    ports = ingest.list_serial_ports()
    if ports:
        port = st.sidebar.selectbox("COM port", ports)
    else:
        port = st.sidebar.text_input("COM port (none detected)", "COM3",
                                     help="e.g. COM3 on Windows, /dev/ttyACM0 on Linux")
    baud = st.sidebar.selectbox("Baud rate", [9600, 19200, 57600, 115200], index=0,
                                help="Must match Serial.begin() in the sketch (9600).")
    connect = st.sidebar.toggle("Connect", value=False,
                                help="Opening the port resets most Arduino boards.")
    if not connect:
        ingest.close_reader()

# ---- common settings -----------------------------------------------------------
st.sidebar.divider()
station = st.sidebar.selectbox("Station type", list(alerts.STATION_THRESHOLDS))
normal_max = st.sidebar.number_input(
    "Normal max temperature (°C)", 10.0, 50.0, alerts.DEFAULT_NORMAL_MAX[station], 0.5,
    key=f"normal_{station}",
    help="Climatological normal maximum for your place and month (from IMD). "
         "The 'departure from normal' rule uses it.")
hw_temp, sev_temp = alerts.thresholds(station, normal_max)
st.sidebar.caption(f"Heat Wave from **{hw_temp:.1f} °C**, Severe from **{sev_temp:.1f} °C**")
debounce_n = st.sidebar.slider("Confirm alert after N readings", 1, 10, 3,
                               help="Avoids flickering when the temperature hovers near a threshold.")

st.sidebar.divider()
window_min = st.sidebar.slider("Forecast: fit window (minutes)", 30, 720, 180, 30)
horizon_min = st.sidebar.slider("Forecast: look ahead (minutes)", 30, 720, 180, 30)
max_points = st.sidebar.slider("Max points on chart", 100, 2000, 600, 100)

st.sidebar.divider()
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=(source != SOURCE_PASTE),
                                   key=f"auto_{source}")
refresh_s = st.sidebar.slider("Refresh every (seconds)", 1, 10, 2)


# =============================================================================
# Data loading: every source returns (DataFrame, notice_text)
# =============================================================================
def load_demo():
    ss = st.session_state
    key = (station, scenario)
    if ss.get("demo_key") != key:                       # first run, new scenario or restart
        ss["demo_key"] = key
        ss["demo_t0"] = time.time()
        ss["demo_start"] = (datetime.now().replace(second=0, microsecond=0)
                            - timedelta(minutes=DEMO_STEP_MIN * DEMO_INIT_READINGS))
        ss["demo_n"] = DEMO_INIT_READINGS
    if auto_refresh:                                    # time-based, so reruns don't skew it
        elapsed = int((time.time() - ss["demo_t0"]) / DEMO_SECONDS_PER_READING)
        ss["demo_n"] = min(DEMO_INIT_READINGS + elapsed, 4000)
    df = ingest.demo_data(ss["demo_n"], station, scenario, ss["demo_start"], DEMO_STEP_MIN)
    return df, "Synthetic demo data (Indian-summer pattern), one reading per 10 simulated minutes."


def load_pasted():
    rows, skipped = ingest.parse_text(pasted_text)
    start = datetime.combine(log_date, log_time)
    df = ingest.build_dataframe(rows, start, minutes_per_reading)
    return df, f"Parsed {len(rows)} readings; {skipped} unreadable lines skipped."


def load_serial():
    if not connect:
        return pd.DataFrame(), "Choose the port and baud rate, then switch on **Connect** in the sidebar."
    try:
        reader = ingest.get_reader(port, baud)
    except ImportError:
        return pd.DataFrame(), "pyserial is not installed (`pip install pyserial`)."
    except Exception as exc:
        return pd.DataFrame(), f"Could not open {port}: {exc}"
    if reader.error:
        return pd.DataFrame(), f"Serial error: {reader.error}"
    return reader.dataframe(), f"Live from {port} @ {baud} baud ({reader.skipped} bad lines skipped)."


# =============================================================================
# Small HTML helpers
# =============================================================================
def level_badge(level: int) -> str:
    color = alerts.LEVEL_COLORS[level]
    return (f"<div style='background:{color};color:white;padding:14px 18px;border-radius:10px;"
            f"font-size:1.5rem;font-weight:700;text-align:center'>{alerts.LEVEL_NAMES[level].upper()}</div>")


def advice_cards(current: int) -> str:
    html = ""
    for lvl in (alerts.NORMAL, alerts.HEAT_WAVE, alerts.SEVERE):
        color = alerts.LEVEL_COLORS[lvl]
        tint = f"{color}26" if lvl == current else "transparent"
        tag = " &nbsp;◀ current level" if lvl == current else ""
        items = "".join(f"<li>{a}</li>" for a in alerts.ADVICE[lvl])
        html += (f"<div style='border-left:6px solid {color};background:{tint};"
                 f"padding:8px 14px;margin-bottom:10px;border-radius:4px'>"
                 f"<b style='color:{color}'>{alerts.LEVEL_NAMES[lvl]}</b>{tag}"
                 f"<ul style='margin:4px 0 0 0;padding-left:20px'>{items}</ul></div>")
    return html


def make_chart(df, fc):
    d = df.tail(max_points)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["time"], y=d["temperature"], name="Temperature (°C)",
                             line=dict(color="#d62828", width=2)))
    fig.add_trace(go.Scatter(x=d["time"], y=d["heat_index"], name="Heat index (°C)",
                             line=dict(color="#1f77b4", width=2)))
    # Threshold lines
    fig.add_hline(y=hw_temp, line_dash="dash", line_color=alerts.LEVEL_COLORS[1],
                  annotation_text=f"Heat Wave {hw_temp:.1f} °C", annotation_position="top left")
    fig.add_hline(y=sev_temp, line_dash="dash", line_color=alerts.LEVEL_COLORS[2],
                  annotation_text=f"Severe {sev_temp:.1f} °C", annotation_position="top left")
    # Trend extrapolation (dotted) with a rough scatter band
    if fc["ok"]:
        t = fc["temp"]
        x = list(fc["times"]) + list(fc["times"])[::-1]
        y = list(t["pred"] + t["band"]) + list((t["pred"] - t["band"])[::-1])
        fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", showlegend=False,
                                 fillcolor="rgba(214,40,40,0.12)", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fc["times"], y=t["pred"], name="Temp trend extrapolation",
                                 line=dict(color="#d62828", dash="dot", width=2)))
        fig.add_trace(go.Scatter(x=fc["times"], y=fc["hi"]["pred"], name="Heat index trend extrapolation",
                                 line=dict(color="#1f77b4", dash="dot", width=2)))
    fig.update_layout(height=470, margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
                      yaxis_title="°C", template="plotly_white",
                      legend=dict(orientation="h", y=1.1, x=0))
    return fig


# =============================================================================
# The dashboard body (re-run on a timer when auto-refresh is on)
# =============================================================================
def dashboard():
    if source == SOURCE_DEMO:
        raw, notice = load_demo()
    elif source == SOURCE_PASTE:
        raw, notice = load_pasted()
    else:
        raw, notice = load_serial()

    st.caption(notice)
    if raw.empty:
        st.info("No readings yet. Pick a data source in the sidebar, paste a log, "
                "or switch to the demo simulator.")
        return

    # ---- analytics pipeline ----------------------------------------------------
    df = analytics.add_metrics(raw)
    df["raw_level"] = alerts.classify(df["temperature"], hw_temp, sev_temp)
    df["level"] = alerts.debounce(df["raw_level"], debounce_n)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    level = int(last["level"])
    fc = analytics.forecast(df, window_min, horizon_min)

    # ---- metric tiles -----------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temperature", f"{last['temperature']:.1f} °C",
              f"{last['temperature'] - prev['temperature']:+.1f} °C", delta_color="inverse")
    c2.metric("Humidity", f"{last['humidity']:.0f} %",
              f"{last['humidity'] - prev['humidity']:+.1f} %", delta_color="off")
    c3.metric("Heat index", f"{last['heat_index']:.1f} °C",
              analytics.heat_index_category(last["heat_index"]), delta_color="off",
              help="Rothfusz regression: what the temperature 'feels like' with humidity.")
    with c4:
        st.markdown("**Alert level**")
        st.markdown(level_badge(level), unsafe_allow_html=True)
    st.caption(f"Station: {station} | normal max {normal_max:.1f} °C | "
               f"last reading {last['time']:%d %b %H:%M:%S}. IMD rules use the daily maximum; "
               "here each reading is used as a stand-in for it.")

    # ---- chart + forecast ---------------------------------------------------------
    st.plotly_chart(make_chart(df, fc))

    st.subheader("Short-term trend extrapolation")
    proj_level = level
    if fc["ok"]:
        proj_temp = float(fc["temp"]["pred"][-1])
        proj_level = int(alerts.classify([max(fc["temp"]["pred"])], hw_temp, sev_temp)[0])
        f1, f2, f3 = st.columns(3)
        f1.metric("Recent trend", f"{fc['temp']['slope_per_h']:+.2f} °C / hour")
        f2.metric(f"Temperature in {horizon_min / 60:.1f} h", f"{proj_temp:.1f} °C")
        f3.metric("Level if trend continues", alerts.LEVEL_NAMES[proj_level])
        st.caption(f"⚠️ A straight line fitted to the last {fc['n']} readings "
                   f"(≈{window_min} min window, R² = {fc['temp']['r2']:.2f}) and extended forward. "
                   "This is a simple trend extrapolation, **not a weather model**: it ignores the "
                   "daily temperature cycle, wind, clouds and rain, and gets less reliable the "
                   "further ahead it looks. Shaded band = ±1.96 × residual scatter.")
    else:
        st.info(f"Forecast unavailable: {fc['reason']}")

    # ---- alert log + early warning ---------------------------------------------------
    left, right = st.columns([3, 2])
    log = alerts.build_alert_log(df)
    with left:
        st.subheader("Alert log")
        if log.empty:
            st.caption("No alerts in this data yet.")
        else:
            shown = log.iloc[::-1].copy()                       # newest first
            shown["Time"] = shown["Time"].dt.strftime("%d %b %H:%M:%S")
            st.dataframe(shown, hide_index=True, height=320)
        st.download_button("⬇️ Download alert log (CSV)", log.to_csv(index=False),
                           "alert_log.csv", "text/csv", key="dl_alert_log")
        with st.expander("Latest readings"):
            st.dataframe(df.tail(50).iloc[::-1], hide_index=True)
    with right:
        st.subheader("Early warning")
        if proj_level > level:
            st.warning(f"Trend heads-up: if the current trend continues, the level could rise to "
                       f"**{alerts.LEVEL_NAMES[proj_level]}** within {horizon_min / 60:.1f} h.")
        st.markdown(advice_cards(level), unsafe_allow_html=True)
        st.caption("General guidance in the spirit of NDMA/IMD heat advisories. "
                   "Always follow your local authority's official warnings.")


st.title("Heatwave Monitoring, Prediction and Early Warning")
st.caption("Climate Intelligence dashboard: Arduino/Tinkercad sensor station + Python analytics")

if auto_refresh:
    st.fragment(run_every=refresh_s)(dashboard)()      # re-runs only this function on a timer
else:
    dashboard()
