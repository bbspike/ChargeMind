from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

from services import get_radiation_series, get_frank_day_local
from utils import fmt, sunset_guess, ORIENTATIONS, tilt_factor


# ---------------------------- PV / Helpers ----------------------------

def pv_kwh_from_radiation(sw_wm2: float, hours: float, cfg) -> float:
    """
    Converteer Open-Meteo shortwave_radiation (W/m2) naar PV-kWh voor jouw set-up.
    E[kWh] = (W/m2 * h / 1000) * kWp * (PR_base * ori_factor * tilt_factor)
    """
    ori_factor = ORIENTATIONS[cfg["orientation_choice"]]["factor"]
    tilt_fac = tilt_factor(cfg["tilt_deg"])
    pr_eff = cfg["pr_base"] * ori_factor * tilt_fac
    return (sw_wm2 * hours / 1000.0) * cfg["kwp"] * pr_eff


def _hour_bounds(dt):
    """Geeft (uur_begin, uur_eind) voor het uur waar dt in valt."""
    start = dt.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return start, end


def predict_soc_gain(now_soc_pct: float, radiation_series, start_dt, end_dt, cfg) -> float:
    """
    SOC-toename (%-punten) door PV-overschot tussen start_dt en end_dt.
    Neemt deeluren mee: PV per uur (of fractie) minus huislast; rest naar batterij tot 100%.
    """
    soc_gain_pct = 0.0
    t_hour, t_hour_end = _hour_bounds(start_dt)
    while t_hour < end_dt:
        seg_start = max(start_dt, t_hour)
        seg_end = min(end_dt, t_hour_end)

        if seg_end > seg_start:
            match = next((x for x in radiation_series if x["time"] == t_hour), None)
            if match:
                dur_h = (seg_end - seg_start).total_seconds() / 3600.0
                pv_kwh = pv_kwh_from_radiation(match["sw"], dur_h, cfg)
                house_kwh = cfg["house_load_kw"] * dur_h
                surplus = max(0.0, pv_kwh - house_kwh)
                gain_pct = (surplus / cfg["battery_kwh"]) * 100.0
                cap = 100.0 - (now_soc_pct + soc_gain_pct)
                if gain_pct > cap:
                    gain_pct = max(0.0, cap)
                soc_gain_pct += gain_pct

        t_hour = t_hour_end
        t_hour_end = t_hour + timedelta(hours=1)

    return soc_gain_pct


def max_soc_increase_in_slot(hours: float, cfg) -> float:
    """Maximale SOC-stijging in uur-slot door laden (kWh -> %-punten)."""
    kwh_in = cfg["inverter_charge_kw"] * cfg["roundtrip_eff"] * hours
    return (kwh_in / cfg["battery_kwh"]) * 100.0


def max_soc_decrease_in_slot(hours: float, cfg) -> float:
    """Maximale SOC-daling in uur-slot door ontladen (kWh -> %-punten)."""
    kwh_out = cfg.get("inverter_discharge_kw", cfg["inverter_charge_kw"]) * cfg["discharge_eff"] * hours
    return (kwh_out / cfg["battery_kwh"]) * 100.0


# ---------------------------- Dagplanning ----------------------------

def plan(now_soc, day_prices, radiation_series, base_dt, cfg, tz: ZoneInfo):
    """
    Berekent laad/ontlaad-advies t.o.v. goedkoopste/duurste uur na base_dt.
    Houdt rekening met PV-voor/na, headroom, reserve, en laad/ontlaadlimieten.
    """
    future_prices = [x for x in day_prices if x["end"] > base_dt]
    if not future_prices:
        return {"note": "Geen (toekomstige) prijsblokken meer voor de gekozen dag."}

    cheap = min(future_prices, key=lambda x: x["price"])
    expensive = max(future_prices, key=lambda x: x["price"])

    # PV tot start laadslot
    soc_gain_before = predict_soc_gain(now_soc, radiation_series, base_dt, cheap["start"], cfg)
    soc_at_charge_start = min(100.0, now_soc + soc_gain_before)

    # PV na laadslot tot zonsondergang (headroom)
    sunset = sunset_guess(base_dt)
    if cheap["end"] > sunset:
        pv_after_pct = 0.0
    else:
        pv_after_pct = predict_soc_gain(soc_at_charge_start, radiation_series, cheap["end"], sunset, cfg)

    headroom_pct = max(0.0, 100.0 - (soc_at_charge_start + pv_after_pct))

    # Reserve-eis bij dure uur
    soc_gain_until_exp = predict_soc_gain(soc_at_charge_start, radiation_series, cheap["end"], expensive["start"], cfg)
    soc_pred_at_expensive = soc_at_charge_start + soc_gain_until_exp
    deficit_pct = max(0.0, cfg["min_soc_reserve"] - soc_pred_at_expensive)

    # Laadslot limiet
    slot_hours = (cheap["end"] - cheap["start"]).total_seconds() / 3600.0
    max_slot_charge_pct = max_soc_increase_in_slot(slot_hours, cfg)

    required_pct = max(headroom_pct, deficit_pct)
    charge_limited = max_slot_charge_pct + 1e-6 < required_pct

    # Wat we daadwerkelijk bijladen
    needed_pct = max(deficit_pct, 0.0)
    add_pct = min(max_slot_charge_pct, max(headroom_pct, needed_pct))
    target_soc_after_charge = min(100.0, soc_at_charge_start + add_pct)

    # Dure uur: kan je tot reserve ontladen binnen vermogen/duur?
    exp_hours = (expensive["end"] - expensive["start"]).total_seconds() / 3600.0
    max_discharge_pct = max_soc_decrease_in_slot(exp_hours, cfg)
    achievable_drop_pct = min(max_discharge_pct, max(0.0, target_soc_after_charge - cfg["min_soc_reserve"]))
    achievable_min_soc = target_soc_after_charge - achievable_drop_pct
    can_reach_reserve = achievable_min_soc <= cfg["min_soc_reserve"] + 1e-6

    return {
        "base_dt": base_dt,
        "soc_now": now_soc,

        "cheap_start": cheap["start"],
        "cheap_end": cheap["end"],
        "cheap_price": cheap["price"],

        "exp_start": expensive["start"],
        "exp_end": expensive["end"],
        "exp_price": expensive["price"],

        "soc_at_charge_start": round(soc_at_charge_start, 1),
        "pv_gain_before_charge_pct": round(soc_gain_before, 1),
        "pv_gain_after_charge_pct": round(pv_after_pct, 1),
        "headroom_pct": round(headroom_pct, 1),
        "deficit_to_reserve_pct": round(deficit_pct, 1),

        "required_charge_pct": round(required_pct, 1),
        "max_slot_charge_pct": round(max_slot_charge_pct, 1),
        "charge_limited": bool(charge_limited),

        "add_pct": round(add_pct, 1),
        "target_soc_after_charge": round(target_soc_after_charge, 1),

        "max_discharge_pct": round(max_discharge_pct, 1),
        "achievable_min_soc": round(achievable_min_soc, 1),
        "can_reach_reserve": bool(can_reach_reserve),
    }


def estimate_arbitrage(plan_out: dict, cfg: dict) -> dict:
    """
    Scheid PV (gratis) en net (gekocht) in de arbitrage.
    Knijp afgifte op dure uur tot max. ontlaadvermogen x duur.
    """
    battery_kwh = cfg["battery_kwh"]
    cheap_price = float(plan_out["cheap_price"])
    exp_price = float(plan_out["exp_price"])
    ceff = max(1e-9, cfg.get("charge_eff", 1.0))
    deff = cfg.get("discharge_eff", 1.0)

    # PV-kant (gratis)
    pv_pct = (plan_out["pv_gain_before_charge_pct"] + plan_out["pv_gain_after_charge_pct"]) / 100.0
    pv_stored_kwh = pv_pct * battery_kwh
    pv_deliver_kwh = pv_stored_kwh * deff
    pv_revenue = pv_deliver_kwh * exp_price

    # Net-kant (bijladen in goedkoop uur)
    net_pct = plan_out["add_pct"] / 100.0
    net_stored_kwh = net_pct * battery_kwh
    grid_buy_kwh = net_stored_kwh / ceff
    net_deliver_kwh = net_stored_kwh * deff
    net_cost = grid_buy_kwh * cheap_price
    net_revenue = net_deliver_kwh * exp_price

    # Begrenzen op ontlaadcapaciteit in dure uur
    total_deliver = pv_deliver_kwh + net_deliver_kwh
    exp_hours = (plan_out["exp_end"] - plan_out["exp_start"]).total_seconds() / 3600.0
    max_kwh_out_exp = cfg.get("inverter_discharge_kw", cfg["inverter_charge_kw"]) * deff * exp_hours

    if total_deliver > max_kwh_out_exp:
        scale = max_kwh_out_exp / total_deliver if total_deliver > 0 else 1.0
        pv_deliver_kwh *= scale
        net_deliver_kwh *= scale
        pv_revenue = pv_deliver_kwh * exp_price
        net_revenue = net_deliver_kwh * exp_price

    total_revenue = pv_revenue + net_revenue
    total_cost = net_cost
    profit = total_revenue - total_cost

    return {
        "pv_stored_kwh": round(pv_stored_kwh, 3),
        "net_buy_kwh": round(grid_buy_kwh, 3),
        "deliver_kwh_total": round(pv_deliver_kwh + net_deliver_kwh, 3),
        "buy_allin_eur_kwh": round(cheap_price, 4),
        "sell_allin_eur_kwh": round(exp_price, 4),
        "cost_eur": round(total_cost, 2),
        "revenue_eur": round(total_revenue, 2),
        "profit_eur": round(profit, 2),
        "remarks": "PV (gratis) + net (gekocht) apart; gelimiteerd op ontlaadvermogen tijdens dure uur."
    }


# ---------------------------- Orchestratie voor GUI/CLI ----------------------------

async def plan_day(cfg, choice, soc, hhmm):
    """
    - choice: 'V' (vandaag) of 'M' (morgen)
    - soc: SOC % op het basismoment
    - hhmm: alleen gebruikt bij 'M' (morgen) als 'HH:MM'
    Retourneert advies + series voor grafieken.
    """
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    radiation_series = get_radiation_series(cfg, tz)

    if choice.upper() == "V":
        base_dt = now
        day_prices = await get_frank_day_local('today', tz)
        label = "Vandaag"
        day_date = base_dt.date()
    else:
        hh, mm = map(int, hhmm.split(":"))
        tomorrow = (now + timedelta(days=1)).date()
        base_dt = datetime.combine(tomorrow, dtime(hour=hh, minute=mm), tzinfo=tz)
        day_prices = await get_frank_day_local('tomorrow', tz)
        label = "Morgen"
        day_date = tomorrow

    future = [x for x in day_prices if x["end"] > base_dt]
    if not future:
        return {
            "note": "Geen (toekomstige) prijsblokken voor het gekozen moment. "
                    "Tarieven voor morgen zijn meestal rond 15:00 beschikbaar."
        }

    result = plan(soc, day_prices, radiation_series, base_dt, cfg, tz)
    result["day_label"] = label

    # --- Series voor grafieken ---
    # Dagprijzen van de gekozen dag
    day_prices_full = [x for x in day_prices if x["start"].date() == day_date]
    times = [x["start"] for x in day_prices_full]
    prices = [x["price"] for x in day_prices_full]
    # Extra eindpunt toevoegen voor nette trap tot einde laatste blok
    if day_prices_full:
        times_plot = times + [day_prices_full[-1]["end"]]
        prices_plot = prices + [prices[-1]]
    else:
        times_plot, prices_plot = [], []

    # SOC-curve met oorzaken per segment
    t = base_dt.replace(minute=0, second=0, microsecond=0)
    end = base_dt.replace(hour=23, minute=59, second=59, microsecond=0)
    soc_curve_t = []
    soc_curve_v = []
    soc_causes = []  # oorzaak segment [i -> i+1]
    soc_now = soc

    ceff = cfg.get("charge_eff", 0.95)
    deff = cfg.get("discharge_eff", 0.95)
    ch_kw = cfg["inverter_charge_kw"]
    dis_kw = cfg.get("inverter_discharge_kw", ch_kw)

    while t <= end:
        soc_curve_t.append(t)
        soc_curve_v.append(max(0.0, min(100.0, soc_now)))

        t_next = t + timedelta(hours=1)
        cause = "none"

        # PV bijdrage dit uur
        rad = next((r["sw"] for r in radiation_series if r["time"] == t), 0.0)
        pv_kwh = pv_kwh_from_radiation(rad, 1.0, cfg)
        surplus = max(0.0, pv_kwh - cfg["house_load_kw"] * 1.0)
        if surplus > 0:
            pv_add = (surplus / cfg["battery_kwh"]) * 100.0
            if soc_now + pv_add > 100.0:
                pv_add = max(0.0, 100.0 - soc_now)
            if pv_add > 0:
                soc_now += pv_add
                cause = "pv"

        # Laden in goedkoopste uur richting target
        if result["cheap_start"] <= t < result["cheap_end"] and soc_now < result["target_soc_after_charge"] - 1e-6:
            headroom_pct = max(0.0, result["target_soc_after_charge"] - soc_now)
            max_pct_this_hour = (ch_kw * cfg["roundtrip_eff"]) / cfg["battery_kwh"] * 100.0
            add = min(headroom_pct, max_pct_this_hour)
            if add > 0:
                soc_now = min(100.0, soc_now + add)
                cause = "grid_charge"

        # Ontladen in dure uur richting reserve
        if result["exp_start"] <= t < result["exp_end"] and soc_now > cfg["min_soc_reserve"] + 1e-6:
            floor = cfg["min_soc_reserve"]
            max_drop_pct = (dis_kw * deff) / cfg["battery_kwh"] * 100.0
            drop = min(max_drop_pct, max(0.0, soc_now - floor))
            if drop > 0:
                soc_now = max(floor, soc_now - drop)
                cause = "grid_discharge"

        # Plateau op reserve (handig voor kleur)
        if abs(soc_now - cfg["min_soc_reserve"]) < 1e-6:
            cause = "reserve"

        soc_causes.append(cause)
        t = t_next

    # Zorg dat causes exact per segment is (len = len(points)-1)
    if len(soc_causes) >= len(soc_curve_v):
        soc_causes = soc_causes[:len(soc_curve_v) - 1]

    # Voor titels in grafieken
    result["day_date"] = day_date

    result["series"] = {
        "times": times_plot,
        "prices": prices_plot,
        "soc_times": soc_curve_t,
        "soc_values": soc_curve_v,
        "soc_causes": soc_causes
    }

    return result
