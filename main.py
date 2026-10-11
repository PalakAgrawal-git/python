"""
Heatwave Early Warning System
------------------------------
Python concepts used:
  - tkinter + ttk       GUI widgets, layout managers, event handling
  - sqlite3             persistent database (INSERT, SELECT, DELETE)
  - threading           background demo loop (non-blocking UI)
  - matplotlib (TkAgg)  chart embedded inside a Tkinter window
  - re / math           serial-line parsing and heat-index formula
  - OOP                 HeatwaveApp class, HeatwaveDB class
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from database import HeatwaveDB
from heatwave.analytics import heat_index, linear_trend
from heatwave.alerts import get_level, COLORS, ADVICE
from heatwave.ingest import demo_reading, parse_text, SCENARIO_NAMES

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Colour palette
BG      = "#1a1a2e"
SIDEBAR = "#16213e"
TILE    = "#0f3460"
WHITE   = "#ffffff"
GRAY    = "#aaaaaa"
ACCENT  = "#e94560"


class HeatwaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Heatwave Early Warning System")
        self.geometry("1150x720")
        self.minsize(900, 600)
        self.configure(bg=BG)

        # State
        self.db      = HeatwaveDB(os.path.join(SCRIPT_DIR, "heatwave.db"))
        self._step   = 0
        self._stop   = threading.Event()
        self._thread = None
        self._running = False

        # Tkinter variables (linked to widgets)
        self.source_var   = tk.StringVar(value="demo")
        self.scenario_var = tk.StringVar(value=SCENARIO_NAMES[0])
        self.station_var  = tk.StringVar(value="Plains")

        self._build_ui()
        self._refresh()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=SIDEBAR, width=230)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        tk.Label(sb, text="⚙  Settings", font=("Arial", 13, "bold"),
                 bg=SIDEBAR, fg=WHITE).pack(pady=(20, 12))

        # Data source radio buttons
        tk.Label(sb, text="Data Source", font=("Arial", 9),
                 bg=SIDEBAR, fg=GRAY).pack(anchor="w", padx=15)
        for val, txt in [("demo", "Demo Simulator"), ("tinkercad", "Tinkercad Log")]:
            ttk.Radiobutton(sb, text=txt, variable=self.source_var, value=val,
                            command=self._on_source_change).pack(anchor="w", padx=24, pady=2)

        # Scenario dropdown (Combobox)
        tk.Frame(sb, bg=SIDEBAR, height=10).pack()
        tk.Label(sb, text="Scenario", font=("Arial", 9),
                 bg=SIDEBAR, fg=GRAY).pack(anchor="w", padx=15)
        ttk.Combobox(sb, textvariable=self.scenario_var,
                     values=SCENARIO_NAMES, state="readonly", width=22).pack(padx=15)

        # Station type dropdown
        tk.Frame(sb, bg=SIDEBAR, height=10).pack()
        tk.Label(sb, text="Station Type", font=("Arial", 9),
                 bg=SIDEBAR, fg=GRAY).pack(anchor="w", padx=15)
        ttk.Combobox(sb, textvariable=self.station_var,
                     values=["Plains", "Coastal", "Hilly"],
                     state="readonly", width=22).pack(padx=15)

        # Start / Stop button
        tk.Frame(sb, bg=SIDEBAR, height=18).pack()
        self._start_btn = tk.Button(
            sb, text="▶  Start Demo", font=("Arial", 11, "bold"),
            bg=ACCENT, fg=WHITE, relief="flat", cursor="hand2",
            command=self._toggle_demo,
        )
        self._start_btn.pack(padx=15, fill="x", ipady=5)

        # Clear database button
        tk.Frame(sb, bg=SIDEBAR, height=8).pack()
        tk.Button(sb, text="🗑  Clear Database", font=("Arial", 10),
                  bg="#2d2d2d", fg=WHITE, relief="flat",
                  cursor="hand2", command=self._clear_data).pack(padx=15, fill="x", ipady=3)

        # Reading count label
        tk.Frame(sb, bg=SIDEBAR, height=20).pack()
        self._count_var = tk.StringVar(value="Readings saved: 0")
        tk.Label(sb, textvariable=self._count_var, font=("Arial", 9),
                 bg=SIDEBAR, fg=GRAY).pack()

    def _build_main(self):
        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        tk.Label(main, text="Heatwave Monitoring, Prediction and Early Warning",
                 font=("Arial", 15, "bold"), bg=BG, fg=WHITE).pack(anchor="w")
        tk.Label(main, text="Tkinter · SQLite · Arduino/Tinkercad — Python mini project",
                 font=("Arial", 9), bg=BG, fg=GRAY).pack(anchor="w", pady=(0, 8))

        self._build_tiles(main)

        # Tabbed notebook
        nb = ttk.Notebook(main)
        nb.pack(fill="both", expand=True, pady=(8, 0))
        self._build_chart_tab(nb)
        self._build_table_tab(nb)
        self._build_tinkercad_tab(nb)

        self._build_alert_log(main)

    def _build_tiles(self, parent):
        """Four metric tiles: Temperature, Humidity, Heat Index, Alert Level."""
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")

        specs = [
            ("Temperature", "temp_val",  "—  °C"),
            ("Humidity",    "hum_val",   "—  %"),
            ("Heat Index",  "hi_val",    "—  °C"),
            ("Alert Level", "alert_val", "——"),
        ]
        for col, (title, attr, default) in enumerate(specs):
            tile = tk.Frame(row, bg=TILE)
            tile.grid(row=0, column=col, padx=4, sticky="nsew")
            row.columnconfigure(col, weight=1)
            tk.Label(tile, text=title, font=("Arial", 9), bg=TILE, fg=GRAY).pack(pady=(8, 0))
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            lbl = tk.Label(tile, textvariable=var, font=("Arial", 20, "bold"),
                           bg=TILE, fg=WHITE)
            lbl.pack(pady=(2, 8))
            if title == "Alert Level":
                self._alert_lbl = lbl

    def _build_chart_tab(self, nb):
        """Matplotlib chart embedded inside a Tkinter Frame."""
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Chart  ")

        self._fig = Figure(figsize=(6, 3), dpi=96, facecolor=BG)
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor("#0d0d1a")
        self._fig.tight_layout(pad=1.5)

        self._canvas = FigureCanvasTkAgg(self._fig, master=frame)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_table_tab(self, nb):
        """Treeview showing rows from SQLite database."""
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  SQLite Data  ")

        cols = ("Timestamp", "Temp (°C)", "Humidity (%)", "Heat Index (°C)", "Alert")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=140, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tk.Button(frame, text="Refresh Table", font=("Arial", 9),
                  bg="#2d2d2d", fg=WHITE, relief="flat",
                  command=self._refresh_table).pack(side="bottom", pady=4)

    def _build_tinkercad_tab(self, nb):
        """Paste / load a Tinkercad Serial Monitor log and import it."""
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Tinkercad Log  ")

        tk.Label(frame, text="Paste Tinkercad Serial Monitor output, or load a file:",
                 bg=BG, fg=GRAY, font=("Arial", 9)).pack(anchor="w", padx=8, pady=(8, 2))

        btn_row = tk.Frame(frame, bg=BG)
        btn_row.pack(fill="x", padx=8)
        for text, cmd in [("Load File",    self._load_file),
                           ("Load Sample",  self._load_sample),
                           ("✔ Import",     self._import_log)]:
            bg = ACCENT if "Import" in text else "#2d2d2d"
            tk.Button(btn_row, text=text, font=("Arial", 9), bg=bg, fg=WHITE,
                      relief="flat", cursor="hand2", command=cmd).pack(side="left", padx=(0, 6))

        self._log_text = scrolledtext.ScrolledText(
            frame, bg="#0d0d1a", fg=WHITE,
            font=("Courier", 9), insertbackground=WHITE, height=12,
        )
        self._log_text.pack(fill="both", expand=True, padx=8, pady=6)

        self._import_status = tk.StringVar(value="")
        tk.Label(frame, textvariable=self._import_status,
                 bg=BG, fg="#2ecc71", font=("Arial", 9)).pack(anchor="w", padx=8)

    def _build_alert_log(self, parent):
        frame = tk.Frame(parent, bg=SIDEBAR)
        frame.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text="Alert Log", font=("Arial", 9),
                 bg=SIDEBAR, fg=GRAY).pack(anchor="w", padx=8)
        self._alert_log = scrolledtext.ScrolledText(
            frame, height=4, bg="#0d0d1a", fg=WHITE,
            font=("Courier", 9), state="disabled",
        )
        self._alert_log.pack(fill="x", padx=6, pady=(0, 6))

    # ── Demo control ──────────────────────────────────────────────────────────

    def _on_source_change(self):
        if self.source_var.get() == "tinkercad" and self._running:
            self._stop_demo()

    def _toggle_demo(self):
        if self._running:
            self._stop_demo()
        else:
            self._start_demo()

    def _start_demo(self):
        self._step = 0
        self._stop.clear()
        self._running = True
        self._start_btn.config(text="⏹  Stop Demo", bg="#555555")
        self._thread = threading.Thread(target=self._demo_loop, daemon=True)
        self._thread.start()

    def _stop_demo(self):
        self._stop.set()
        self._running = False
        self._start_btn.config(text="▶  Start Demo", bg=ACCENT)

    def _demo_loop(self):
        """Runs in a background thread; generates one reading every 2 seconds."""
        while not self._stop.is_set():
            temp, hum = demo_reading(self.scenario_var.get(), self._step)
            self._save_reading(temp, hum)
            self._step += 1
            self._stop.wait(2)   # wait 2 s between readings

    # ── Data layer ────────────────────────────────────────────────────────────

    def _save_reading(self, temp, hum):
        hi    = heat_index(temp, hum)
        level = get_level(temp, self.station_var.get())
        self.db.insert(temp, hum, hi, level)
        # Schedule UI updates on the main thread (thread-safe)
        self.after(0, self._refresh)
        self.after(0, self._log_entry, temp, hum, hi, level)

    # ── UI refresh ────────────────────────────────────────────────────────────

    def _refresh(self):
        rows = self.db.fetch_recent(100)
        if not rows:
            return
        _, temp, hum, hi, level = rows[-1]

        self.temp_val.set(f"{temp}  °C")
        self.hum_val.set(f"{hum}  %")
        self.hi_val.set(f"{hi}  °C")
        self.alert_val.set(level)
        self._alert_lbl.config(fg=COLORS.get(level, WHITE))
        self._count_var.set(f"Readings saved: {self.db.count()}")

        self._refresh_chart(rows)
        self._refresh_table(rows)

    def _refresh_chart(self, rows=None):
        if rows is None:
            rows = self.db.fetch_recent(100)
        ax = self._ax
        ax.clear()
        ax.set_facecolor("#0d0d1a")

        if rows:
            temps  = [r[1] for r in rows]
            his    = [r[3] for r in rows]
            labels = [r[0][-8:] for r in rows]    # last 8 chars = HH:MM:SS
            xs     = list(range(len(rows)))

            ax.plot(xs, temps, color="#3498db", linewidth=1.5, label="Temp (°C)")
            ax.plot(xs, his,   color="#e74c3c", linewidth=1.5, label="Heat Index (°C)")

            # Show trend extrapolation as a dashed line
            if len(temps) >= 5:
                trend = linear_trend(temps, 5)
                tx    = list(range(len(temps), len(temps) + 5))
                ax.plot(tx, trend, color="#3498db", linewidth=1,
                        linestyle="--", alpha=0.6, label="Trend")

            step = max(1, len(xs) // 8)
            ax.set_xticks(xs[::step])
            ax.set_xticklabels(labels[::step], rotation=30, fontsize=7, color=GRAY)
            ax.tick_params(colors=GRAY)
            for spine in ax.spines.values():
                spine.set_color("#333333")
            ax.legend(fontsize=8, facecolor=BG, edgecolor="#333", labelcolor=WHITE)

        ax.set_ylabel("°C", color=GRAY, fontsize=9)
        self._fig.tight_layout(pad=1.2)
        self._canvas.draw_idle()

    def _refresh_table(self, rows=None):
        """Reload the Treeview from SQLite data."""
        if rows is None:
            rows = self.db.fetch_recent(100)
        self._tree.delete(*self._tree.get_children())
        for row in reversed(rows[-50:]):   # newest first
            self._tree.insert("", "end", values=row)

    def _log_entry(self, temp, hum, hi, level):
        ts  = datetime.now().strftime("%H:%M:%S")
        msg = f"[{ts}]  T={temp}°C  H={hum}%  HI={hi}°C  →  {level}\n"
        self._alert_log.config(state="normal")
        self._alert_log.insert("end", msg)
        self._alert_log.see("end")
        self._alert_log.config(state="disabled")

    # ── Tinkercad log import ──────────────────────────────────────────────────

    def _import_log(self):
        text     = self._log_text.get("1.0", "end")
        readings = parse_text(text)
        if not readings:
            messagebox.showwarning(
                "No readings found",
                "No valid lines found.\nExpected format:  millis,temperature,humidity",
            )
            return
        for temp, hum in readings:
            hi    = heat_index(temp, hum)
            level = get_level(temp, self.station_var.get())
            self.db.insert(temp, hum, hi, level)
        self._import_status.set(f"✔  Imported {len(readings)} readings.")
        self._refresh()

    def _load_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            try:
                with open(path, "r") as f:
                    self._log_text.delete("1.0", "end")
                    self._log_text.insert("end", f.read())
            except OSError as e:
                messagebox.showerror("Error", str(e))

    def _load_sample(self):
        sample = os.path.join(SCRIPT_DIR, "sample_serial_log.txt")
        try:
            with open(sample, "r") as f:
                self._log_text.delete("1.0", "end")
                self._log_text.insert("end", f.read())
        except FileNotFoundError:
            messagebox.showwarning("Not found", "sample_serial_log.txt not found.")

    # ── Clear data ────────────────────────────────────────────────────────────

    def _clear_data(self):
        if messagebox.askyesno("Clear Database", "Delete all readings from the SQLite database?"):
            self.db.clear()
            self._tree.delete(*self._tree.get_children())
            self._alert_log.config(state="normal")
            self._alert_log.delete("1.0", "end")
            self._alert_log.config(state="disabled")
            for attr, default in [("temp_val", "—  °C"), ("hum_val", "—  %"),
                                   ("hi_val",   "—  °C"), ("alert_val", "——")]:
                getattr(self, attr).set(default)
            self._alert_lbl.config(fg=WHITE)
            self._count_var.set("Readings saved: 0")
            self._refresh_chart([])
            self._import_status.set("")


if __name__ == "__main__":
    app = HeatwaveApp()
    app.mainloop()
