
import json, os

DEFAULTS = {
    "lat": 51.95,
    "lon": 5.23,
    "kwp": 4.4,
    "pr_base": 0.80,
    "orientation_choice": 1,  # Noord default voor jouw case
    "tilt_deg": 18,
    "battery_kwh": 50.0,
    "min_soc_reserve": 35.0,
    "house_load_kw": 0.3,
    "inverter_charge_kw": 12.0,
    "inverter_discharge_kw": 12.0,
    "roundtrip_eff": 0.90,
    "charge_eff": 0.95,
    "discharge_eff": 0.95,
    "timezone": "Europe/Amsterdam",
    "_configured": False
}

CONFIG_PATH = "fe_planner_gui_config.json"

def load_or_create_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH,"r",encoding="utf-8") as f:
            return json.load(f)
    # first time -> force configuration
    with open(CONFIG_PATH,"w",encoding="utf-8") as f:
        json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    return DEFAULTS.copy()

def save_config(cfg):
    with open(CONFIG_PATH,"w",encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
