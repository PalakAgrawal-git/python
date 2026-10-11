# Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning

A mini project that joins an **Arduino sensor station** (built and simulated in
Tinkercad Circuits) with a **real-time Python dashboard** (Streamlit + Plotly +
pandas + numpy).

```
heatwave_project/
├── app.py                       Streamlit dashboard (UI only)
├── heatwave/
│   ├── ingest.py                serial reader, Tinkercad-log parser, demo simulator
│   ├── analytics.py             heat index (Rothfusz) + trend forecast
│   └── alerts.py                IMD thresholds, alert levels, alert log, advice
├── arduino/heatwave_station.ino Arduino Uno sketch
├── sample_serial_log.txt        example Tinkercad Serial Monitor output
├── requirements.txt
└── README.md
```

---

## 1. Setup

Python 3.10+ is recommended.

```bash
cd heatwave_project
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run

```bash
streamlit run app.py
```

The browser opens at <http://localhost:8501>. Choose a **Data source** in the sidebar:

| Source | When to use | What to do |
|---|---|---|
| **Demo simulator** | No hardware needed | Pick a scenario. A new 10-minute reading arrives every 2 s (300x speed), so you can watch a heat wave build. |
| **Tinkercad log (paste / upload)** | You ran the circuit in Tinkercad | Open the Serial Monitor in Tinkercad, copy the text, paste it (or upload a saved file). "Bundled sample" uses `sample_serial_log.txt`. |
| **Live Arduino (serial port)** | Real Arduino plugged in by USB | Select the COM port and baud (9600), switch **Connect** on. Close the Arduino IDE Serial Monitor first, since only one program can hold the port. |

> Tinkercad runs in the browser and cannot open a COM port on your PC. That is why
> source 2 exists: you copy the Serial Monitor text across by hand.
> A Tinkercad run only lasts a minute or two, so the dashboard offers
> **"Treat each reading as N minutes"** to stretch it into hours of "weather".

---

## 3. Tinkercad circuit

### Parts
Arduino Uno, DHT22 temperature/humidity sensor, LCD 16x2, 3 LEDs (green, yellow,
red), piezo buzzer, 1 pushbutton (optional mute), resistors: 3 x 220 Ω (LEDs),
1 x 220 Ω (LCD backlight), 1 x 10 kΩ (DHT22 pull-up, only if your DHT22 has 4 pins),
breadboard.

### Pin map

| Part / pin | Connects to | Resistor |
|---|---|---|
| DHT22 VCC (+) | 5V | |
| DHT22 DATA (out) | **D7** | 10 kΩ from DATA to 5V (4-pin DHT22 only) |
| DHT22 GND (−) | GND | |
| LCD VSS (GND) | GND | |
| LCD VDD (VCC) | 5V | |
| LCD VO (contrast) | GND (or wiper of a 10 kΩ pot between 5V and GND) | |
| LCD RS | **D12** | |
| LCD RW | GND | |
| LCD E | **D11** | |
| LCD D0 to D3 | not connected | |
| LCD D4 | **D10** | |
| LCD D5 | **D9** | |
| LCD D6 | **D8** | |
| LCD D7 | **D13** | |
| LCD A (backlight +) | 5V | 220 Ω in series |
| LCD K (backlight −) | GND | |
| Green LED anode (long leg) | **D3** | 220 Ω in series |
| Yellow LED anode | **D4** | 220 Ω in series |
| Red LED anode | **D5** | 220 Ω in series |
| All LED cathodes (short leg) | GND | |
| Piezo + | **D6** | optional 100 Ω in series |
| Piezo − | GND | |
| Pushbutton leg 1 | **D2** (hardware interrupt INT0) | none (sketch uses `INPUT_PULLUP`) |
| Pushbutton leg 2 | GND | |

Tinkercad pin labels differ slightly between versions. Match by function (RS, E, D4 to D7, A/K).

### Step by step
1. New Circuit, drop in an **Arduino Uno** and a **breadboard (small)**.
2. Wire the Uno **5V** to the breadboard `+` rail and **GND** to the `−` rail.
3. **LCD:** place it, then wire it exactly as the table (VSS, VO, RW, K to GND; VDD to 5V; A through 220 Ω to 5V; RS D12, E D11, D4 D10, D5 D9, D6 D8, D7 D13).
4. **LEDs:** place green, yellow and red. For each, a 220 Ω resistor from the Uno pin (D3 / D4 / D5) to the anode; the cathode goes to the GND rail.
5. **Buzzer:** piezo `+` to D6, `−` to GND.
6. **Button:** one leg to D2, the other to GND.
7. **DHT22:** VCC to 5V, GND to GND, DATA to D7 (plus the 10 kΩ pull-up from DATA to 5V if it has 4 pins).
8. **Code** → switch to *Text*, paste `arduino/heatwave_station.ino`.
9. **Start Simulation**, click the DHT22 and drag the temperature slider up. Watch the LCD and LEDs change; above the severe threshold the red LED lights and the buzzer beeps. Press the button to mute it.
10. Open the **Serial Monitor** (bottom of the code panel), select all, copy, paste into the dashboard (source 2).

### If Tinkercad has no DHT22 / rejects the DHT library
Library and component availability in Tinkercad changes over time, so check your
own account. If the DHT22 part or `#include <DHT.h>` is not accepted, set
`#define USE_DHT22 0` at the top of the sketch and use the fallback:
**TMP36** (left pin 5V, middle pin A0, right pin GND, flat side facing you) for temperature
and a **potentiometer** (outer pins 5V and GND, wiper to A1) as a stand-in for humidity.
The Serial output format is identical, so the dashboard does not care.

### Thresholds on the Arduino
Edit `STATION_THRESHOLD_C` (40 plains / 37 coastal / 30 hilly) and `NORMAL_MAX_C`
at the top of the sketch. Keep them in line with the dashboard sidebar.

---

## 4. Alert logic (IMD)

A heat wave is based on the **maximum temperature**:

| | Plains | Coastal | Hilly |
|---|---|---|---|
| Station threshold | 40 °C | 37 °C | 30 °C |

* **Heat Wave:** threshold reached **and** departure from normal ≥ 4.5 °C
* **Severe Heat Wave:** threshold reached **and** departure ≥ 6.5 °C
* **Absolute rule:** ≥ 45 °C is a Heat Wave and ≥ 47 °C is Severe, whatever the departure

Both rules are merged into two numbers shown in the sidebar:
`heat wave from = min(max(threshold, normal + 4.5), 45)`,
`severe from = min(max(threshold, normal + 6.5), 47)`.

**Simplifications (worth stating in your report):**
* IMD uses the *daily* maximum; the station gives instantaneous readings, so each reading stands in for the maximum.
* The normal maximum is typed in by you (IMD publishes it per station and month). The defaults (39 / 33 / 25 °C) are only rough placeholders.
* The dashboard confirms a level change only after N readings in a row (default 3) to avoid flicker. The Arduino reacts to every reading.
* Heat index uses the NWS Rothfusz regression, which was fitted to US conditions. Treat it as a guide.

## 5. Forecast: what it is and is not

The forecast fits a straight line (`numpy.polyfit`, degree 1) to the last N minutes
of data and extends it. It is a **simple trend extrapolation, not a weather model**.
It knows nothing about the daily cycle, wind, clouds, rain or fronts. For example, a
window that ends just after the afternoon peak will project cooling that is just the
evening, not a real forecast. Use it as a "where is this heading in the next few
hours" hint only.

---

## 6. How the I/O path reaches the dashboard

```
 DHT22  --(1-wire protocol on D7)-->  Arduino Uno  --(UART over USB, 9600 baud)-->  PC
                                          |                                         |
                      LCD / LEDs / buzzer / button(INT0)               pyserial thread -> parse_line
                                                                               |
                                                  DataFrame -> heat index -> IMD level -> forecast
                                                                               |
                                                             Streamlit tiles, chart, alert log
```

1. **Sensor.** The DHT22 digitises temperature and humidity itself and sends them to the Arduino as a 40-bit pulse train on one wire (D7). The DHT library decodes that. The sensor can only be read about every 2 s, so the sketch samples on a 2000 ms timer using `millis()` (never `delay()`, so the rest of the program stays responsive).
2. **Interrupt.** The mute button is wired to D2, the Uno's external-interrupt pin INT0. `attachInterrupt()` makes the CPU jump to `onMutePressed()` the instant the pin falls, even in the middle of other code. The ISR only sets a `volatile` flag; `loop()` then stops the buzzer. This is why polling is not needed and a button press is never missed. Two other interrupts also work silently in the background: Timer0's overflow interrupt keeps `millis()` counting, and the UART's transmit interrupt drains the serial buffer so `Serial.print` returns quickly.
3. **Serial transfer.** Each reading is sent as one text line `millis,temperature,humidity` (UART, 9600 baud, 8N1). Over USB the Uno appears as a COM port. In Tinkercad the same text appears in the Serial Monitor window instead.
4. **Into Python.**
   * *Live:* `ingest.SerialReader` runs `pyserial.readline()` in a background thread so the web page never freezes waiting. Each valid line is stamped with the PC clock and queued.
   * *Tinkercad:* you paste the text; `ingest.parse_text()` does the same parsing and anchors `millis` to a start time you choose.
   * Either way, bad lines (headers, half-lines, NaN, out-of-range values) are skipped, never crash the app.
5. **Analytics and display.** `analytics` adds the heat index and the trend forecast, `alerts` applies the IMD rules, and `app.py` redraws tiles, chart and alert log. With auto-refresh on, only the dashboard section re-runs every few seconds (`st.fragment(run_every=...)`).

---

## 7. Troubleshooting

* **No ports listed / cannot open port:** install the Arduino USB driver, close the Arduino IDE Serial Monitor, then re-select the port.
* **Garbage or no rows:** baud rate in the sidebar must equal `Serial.begin(9600)`.
* **"Forecast unavailable":** the fit window needs at least 5 readings.
* **Pasted Tinkercad log shows 0 readings:** make sure you copied lines like `2000,31.3,66.7`.
