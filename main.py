"""
Heatwave Data Management Dashboard
------------------------------------
Python concepts demonstrated:
  tkinter + ttk  — GUI (Entry, Button, Combobox, Treeview, messagebox)
  sqlite3        — CRUD database (INSERT, SELECT, UPDATE, DELETE)
  OOP            — HeatwaveDashboard class, HeatwaveDB class
  Exception handling, StringVar, trace, column sorting
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date

from database import HeatwaveDB

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#1a1a2e"
PANEL   = "#16213e"
TILE    = "#0f3460"
WHITE   = "#ffffff"
GRAY    = "#aaaaaa"
ACCENT  = "#e94560"

ALERT_COLORS = {
    "NORMAL":           "#2ecc71",
    "WARNING":          "#f1c40f",
    "HEAT WAVE":        "#e67e22",
    "SEVERE HEAT WAVE": "#e74c3c",
}


def get_alert_level(temp):
    """Return IMD alert level for a given temperature (°C)."""
    if temp >= 47:
        return "SEVERE HEAT WAVE"
    if temp >= 45 or temp >= 40:
        return "HEAT WAVE"
    if temp >= 37:
        return "WARNING"
    return "NORMAL"


class HeatwaveDashboard(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Heatwave Data Management Dashboard")
        self.geometry("1100x660")
        self.minsize(900, 560)
        self.configure(bg=BG)

        self.db         = HeatwaveDB()
        self._edit_id   = None   # tracks which row is being edited

        self._build_ui()
        self._load_records()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_stats_bar()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        self._build_form(body)
        self._build_table(body)

    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Heatwave Data Management Dashboard",
                 font=("Arial", 15, "bold"), bg=ACCENT, fg=WHITE).pack(
            side="left", padx=20, pady=12)

    def _build_stats_bar(self):
        bar = tk.Frame(self, bg=TILE)
        bar.pack(fill="x")

        self._v_total  = tk.StringVar(value="Total Records: 0")
        self._v_avg    = tk.StringVar(value="Avg Temp: —")
        self._v_max    = tk.StringVar(value="Max Temp: —")
        self._v_events = tk.StringVar(value="Heat Wave Events: 0")

        for var in (self._v_total, self._v_avg, self._v_max, self._v_events):
            tk.Label(bar, textvariable=var, font=("Arial", 10, "bold"),
                     bg=TILE, fg=WHITE).pack(side="left", padx=24, pady=7)

    # ── Add / Edit form ───────────────────────────────────────────────────────

    def _build_form(self, parent):
        frame = tk.Frame(parent, bg=PANEL, width=270)
        frame.pack(side="left", fill="y", padx=(0, 12))
        frame.pack_propagate(False)

        self._form_title = tk.StringVar(value="Add New Record")
        tk.Label(frame, textvariable=self._form_title, font=("Arial", 12, "bold"),
                 bg=PANEL, fg=WHITE).pack(pady=(18, 14))

        # Input fields
        for label, attr in [
            ("City",              "v_city"),
            ("Date (YYYY-MM-DD)", "v_date"),
            ("Temperature (°C)",  "v_temp"),
            ("Humidity (%)",      "v_hum"),
        ]:
            tk.Label(frame, text=label, font=("Arial", 9),
                     bg=PANEL, fg=GRAY).pack(anchor="w", padx=16)
            var = tk.StringVar()
            setattr(self, attr, var)
            tk.Entry(frame, textvariable=var, font=("Arial", 11),
                     bg="#0d0d1a", fg=WHITE, insertbackground=WHITE,
                     relief="flat").pack(fill="x", padx=16, pady=(2, 9), ipady=5)

        self.v_date.set(str(date.today()))

        # Alert level preview (auto-calculated)
        tk.Label(frame, text="Alert Level (auto)", font=("Arial", 9),
                 bg=PANEL, fg=GRAY).pack(anchor="w", padx=16)
        self._alert_lbl = tk.Label(frame, text="—", font=("Arial", 11, "bold"),
                                    bg="#0d0d1a", fg=WHITE, anchor="w")
        self._alert_lbl.pack(fill="x", padx=16, pady=(2, 14), ipady=5)
        self.v_temp.trace_add("write", self._preview_alert)

        # Submit button
        self._submit_btn = tk.Button(
            frame, text="+ Add Record", font=("Arial", 11, "bold"),
            bg=ACCENT, fg=WHITE, relief="flat", cursor="hand2",
            command=self._submit,
        )
        self._submit_btn.pack(fill="x", padx=16, ipady=6)

        tk.Frame(frame, bg=PANEL, height=6).pack()
        tk.Button(frame, text="Clear / Cancel", font=("Arial", 10),
                  bg="#2d2d2d", fg=WHITE, relief="flat", cursor="hand2",
                  command=self._clear_form).pack(fill="x", padx=16, ipady=4)

    # ── Records table ─────────────────────────────────────────────────────────

    def _build_table(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(side="left", fill="both", expand=True)

        # Search bar + delete button
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x", pady=(0, 8))

        tk.Label(top, text="Search:", font=("Arial", 10),
                 bg=BG, fg=GRAY).pack(side="left")
        self._v_search = tk.StringVar()
        self._v_search.trace_add("write", lambda *_: self._load_records())
        tk.Entry(top, textvariable=self._v_search, font=("Arial", 10),
                 bg="#0d0d1a", fg=WHITE, insertbackground=WHITE,
                 relief="flat", width=28).pack(side="left", padx=(6, 0), ipady=4)

        tk.Button(top, text="Delete Selected", font=("Arial", 10),
                  bg="#c0392b", fg=WHITE, relief="flat", cursor="hand2",
                  command=self._delete_record).pack(side="right")
        tk.Button(top, text="Edit Selected", font=("Arial", 10),
                  bg="#2980b9", fg=WHITE, relief="flat", cursor="hand2",
                  command=self._load_into_form).pack(side="right", padx=(0, 6))

        # Treeview
        cols = ("ID", "City", "Date", "Temp (°C)", "Humidity (%)", "Alert Level")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=22)

        for col, w in zip(cols, (45, 150, 110, 90, 100, 160)):
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=w, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Colour-code rows by alert level
        for level, color in ALERT_COLORS.items():
            self._tree.tag_configure(level, foreground=color)

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _preview_alert(self, *_):
        try:
            level = get_alert_level(float(self.v_temp.get()))
            self._alert_lbl.config(text=level, fg=ALERT_COLORS.get(level, WHITE))
        except ValueError:
            self._alert_lbl.config(text="—", fg=WHITE)

    def _submit(self):
        city = self.v_city.get().strip()
        date_str = self.v_date.get().strip()

        try:
            temp = float(self.v_temp.get())
            hum  = float(self.v_hum.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Temperature and Humidity must be numbers.")
            return

        if not city or not date_str:
            messagebox.showerror("Missing Fields", "City and Date cannot be empty.")
            return

        if not (0 <= hum <= 100):
            messagebox.showerror("Invalid Input", "Humidity must be between 0 and 100.")
            return

        alert = get_alert_level(temp)

        if self._edit_id:
            self.db.update(self._edit_id, city, date_str, temp, hum, alert)
            self._edit_id = None
        else:
            self.db.insert(city, date_str, temp, hum, alert)

        self._clear_form()
        self._load_records()

    def _load_into_form(self):
        """Fill the form with the selected row for editing."""
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a record to edit.")
            return
        vals = self._tree.item(sel[0])["values"]
        self._edit_id = vals[0]
        self.v_city.set(vals[1])
        self.v_date.set(vals[2])
        self.v_temp.set(vals[3])
        self.v_hum.set(vals[4])
        self._form_title.set("Edit Record")
        self._submit_btn.config(text="✔ Save Changes", bg="#2980b9")

    def _delete_record(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a record to delete.")
            return
        if messagebox.askyesno("Confirm Delete", "Delete the selected record?"):
            record_id = self._tree.item(sel[0])["values"][0]
            self.db.delete(record_id)
            self._load_records()

    def _load_records(self, *_):
        q    = self._v_search.get().strip() if hasattr(self, "_v_search") else ""
        rows = self.db.search(q) if q else self.db.fetch_all()
        self._tree.delete(*self._tree.get_children())
        for row in rows:
            self._tree.insert("", "end", values=row, tags=(row[5],))
        self._update_stats()

    def _update_stats(self):
        s = self.db.get_stats()
        if s and s[0]:
            self._v_total.set(f"Total Records: {s[0]}")
            self._v_avg.set(f"Avg Temp: {s[1]} °C")
            self._v_max.set(f"Max Temp: {s[2]} °C")
            self._v_events.set(f"Heat Wave Events: {s[3]}")
        else:
            self._v_total.set("Total Records: 0")
            self._v_avg.set("Avg Temp: —")
            self._v_max.set("Max Temp: —")
            self._v_events.set("Heat Wave Events: 0")

    def _clear_form(self):
        self._edit_id = None
        self.v_city.set("")
        self.v_date.set(str(date.today()))
        self.v_temp.set("")
        self.v_hum.set("")
        self._alert_lbl.config(text="—", fg=WHITE)
        self._form_title.set("Add New Record")
        self._submit_btn.config(text="+ Add Record", bg=ACCENT)

    def _sort_by(self, col):
        """Sort Treeview rows by the clicked column header."""
        data = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        try:
            data.sort(key=lambda x: float(x[0]))
        except ValueError:
            data.sort(key=lambda x: x[0].lower())
        for i, (_, k) in enumerate(data):
            self._tree.move(k, "", i)


if __name__ == "__main__":
    app = HeatwaveDashboard()
    app.mainloop()
