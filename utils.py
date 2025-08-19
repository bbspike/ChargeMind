
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ORIENTATIONS = {
    1: {"label": "Noord",       "factor": 0.65},
    2: {"label": "Noord-Oost",  "factor": 0.75},
    3: {"label": "Oost",        "factor": 0.88},
    4: {"label": "Zuid-Oost",   "factor": 0.95},
    5: {"label": "Zuid",        "factor": 1.00},
    6: {"label": "Zuid-West",   "factor": 0.95},
    7: {"label": "West",        "factor": 0.88},
    8: {"label": "Noord-West",  "factor": 0.75},
}

TILT_TABLE = [
    (0, 0.90), (10, 0.95), (20, 0.98), (30, 1.00), (35, 1.00),
    (40, 0.99), (50, 0.97), (60, 0.94)
]

def linear_interp(x, table):
    table = sorted(table, key=lambda t: t[0])
    if x <= table[0][0]: return table[0][1]
    if x >= table[-1][0]: return table[-1][1]
    for i in range(len(table)-1):
        x0,y0 = table[i]; x1,y1 = table[i+1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t*(y1 - y0)
    return table[-1][1]

def tilt_factor(tilt_deg: float) -> float:
    return max(0.70, min(1.05, linear_interp(tilt_deg, TILT_TABLE)))

def fmt(dt_aware, tz: ZoneInfo) -> str:
    return dt_aware.astimezone(tz).strftime("%d-%m %H:%M")

def sunset_guess(base_dt: datetime) -> datetime:
    return base_dt.replace(hour=21, minute=0, second=0, microsecond=0)

# utils.py (toevoegen)
def fmt_hhmm(dt, tz):
    return dt.astimezone(tz).strftime("%H:%M")

def fmt_date(dt, tz):
    return dt.astimezone(tz).strftime("%d-%m")

def fmt_eur(v):
    # voor hele/halve centen mooi: €0.01 → €0.01; €0.0 → €0.00
    return f"€ {v:.2f}"

def fmt_kwh(v):
    return f"{v:.3f} kWh"

def fmt_pct(v):
    return f"{v:.1f}%"
