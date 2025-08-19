import tkinter as tk
from tkinter import ttk, messagebox
from zoneinfo import ZoneInfo
import asyncio

from config import load_or_create_config, save_config
from planner import plan_day, estimate_arbitrage
from utils import fmt, fmt_hhmm, fmt_date, fmt_eur, fmt_kwh, fmt_pct, ORIENTATIONS

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


HELP = {
    "lat": "Breedtegraad (°). Bepaalt zonhoogte voor PV.",
    "lon": "Lengtegraad (°).",
    "kwp": "Piekvermogen PV (kWp).",
    "pr_base": "Basis Performance Ratio (verliezen omvormer/kabel/vervuiling), zonder richting/helling. Typisch 0.75–0.90.",
    "tilt_deg": "Hellingshoek van panelen (°). In NL is ~30–35° vaak ideaal.",
    "battery_kwh": "Batterijcapaciteit (kWh).",
    "min_soc_reserve": "Minimale SOC als nacht-reserve (%).",
    "house_load_kw": "Gem. huislast (kW) overdag. PV dekt dit eerst.",
    "inverter_charge_kw": "Max laadvermogen (kW) batterij/omvormer.",
    "inverter_discharge_kw": "Max ontlaadvermogen (kW).",
    "roundtrip_eff": "Rendement complete cyclus (~0.90).",
    "charge_eff": "Laadrendement (0–1), ~0.95.",
    "discharge_eff": "Ontlaadrendement (0–1), ~0.95.",
    "orientation_choice": "Richting dak/panelen. Noord=1, Zuid=5."
}


def build_advice_text(result: dict, arb: dict, tz, cfg: dict) -> str:
    """Bouw compacte adviestekst."""
    day_label = result.get("day_label", "Vandaag")
    base_dt   = result["base_dt"]
    soc_now   = result["soc_now"]

    c_s = result["cheap_start"]; c_e = result["cheap_end"]; c_p = result["cheap_price"]
    e_s = result["exp_start"];   e_e = result["exp_end"];   e_p = result["exp_price"]

    pv_before = result["pv_gain_before_charge_pct"]
    pv_after  = result["pv_gain_after_charge_pct"]
    soc_at_ch = result["soc_at_charge_start"]
    headroom  = result["headroom_pct"]
    deficit   = result["deficit_to_reserve_pct"]
    need_pct  = result["required_charge_pct"]
    max_charge = result["max_slot_charge_pct"]
    add_pct   = result["add_pct"]
    target    = result["target_soc_after_charge"]

    max_dis   = result["max_discharge_pct"]
    ach_min   = result["achievable_min_soc"]
    can_res   = result["can_reach_reserve"]
    charge_lim = result["charge_limited"]

    L = []
    L.append(f"=== 🔋 Slim advies ({day_label}) ===")
    if day_label.lower().startswith("v"):
        L.append(f"{fmt_date(base_dt, tz)} | Huidig SOC: {fmt_pct(soc_now)}")
    else:
        L.append(f"{fmt_date(base_dt, tz)} {fmt_hhmm(base_dt, tz)} | Verwachte SOC: {fmt_pct(soc_now)}")
    L.append("")
    L.append("— Tarieven —")
    L.append(f"Goedkoopste uur : {fmt_date(c_s, tz)} {fmt_hhmm(c_s, tz)}–{fmt_hhmm(c_e, tz)} | € {c_p:.3f}/kWh")
    L.append(f"Duurste uur     : {fmt_date(e_s, tz)} {fmt_hhmm(e_s, tz)}–{fmt_hhmm(e_e, tz)} | € {e_p:.3f}/kWh")
    L.append("")
    L.append("— Prognose SOC —")
    L.append(f"PV vóór laden    : +{pv_before:.1f} %-pt → SOC bij start ≈ {fmt_pct(soc_at_ch)}")
    L.append(f"PV ná laden      : +{pv_after:.1f} %-pt (headroom: {fmt_pct(headroom)})")
    L.append(f"Reserve (≥ {fmt_pct(cfg['min_soc_reserve'])}) tekort: {fmt_pct(deficit)}")
    L.append("")
    L.append("— Laadslot —")
    L.append(f"Benodigde bijlading: ~{fmt_pct(need_pct)}")
    L.append(f"Max bijladen in slot: ~{fmt_pct(max_charge)}")
    if charge_lim and add_pct < need_pct - 1e-6:
        L.append(f"Aanbevolen bijladen: ~{fmt_pct(add_pct)} (beperkt door laadsnelheid)")
    else:
        L.append(f"Aanbevolen bijladen: ~{fmt_pct(add_pct)}")
    L.append(f"➡️ Doel-SOC einde slot: **{fmt_pct(target)}**")
    L.append("")
    L.append("— Acties —")
    L.append(f"• Laad in {fmt_date(c_s, tz)} {fmt_hhmm(c_s, tz)}–{fmt_hhmm(c_e, tz)} tot **{fmt_pct(target)}**.")
    if can_res:
        L.append(f"• Ontlaad in {fmt_date(e_s, tz)} {fmt_hhmm(e_s, tz)}–{fmt_hhmm(e_e, tz)} tot **{fmt_pct(cfg['min_soc_reserve'])}** (nacht-reserve).")
    else:
        L.append(f"• Ontlaad in {fmt_date(e_s, tz)} {fmt_hhmm(e_s, tz)}–{fmt_hhmm(e_e, tz)} zoveel mogelijk (limiet omvormer).")
        L.append(f"  Max. ontlaadcapaciteit dure uur: ~{fmt_pct(max_dis)} → haalbaar minimum ≈ {fmt_pct(ach_min)}.")
    L.append("")
    L.append("— Kosten & prognose (kale marktprijzen) —")
    L.append(f"PV → batterij (gratis): ~{fmt_kwh(arb['pv_stored_kwh'])}")
    L.append(f"Net-inkoop voor laden : ~{fmt_kwh(arb['net_buy_kwh'])} @ €{result['cheap_price']:.4f}/kWh → {fmt_eur(arb['cost_eur'])}")
    L.append(f"Aflevering totaal     : ~{fmt_kwh(arb['deliver_kwh_total'])} @ €{result['exp_price']:.4f}/kWh → {fmt_eur(arb['revenue_eur'])}")
    L.append(f"⚖️  Verwachte marge    : {fmt_eur(arb['profit_eur'])}")
    L.append("Note: PV (gratis) en net (gekocht) apart; limiet ontladen toegepast.")
    L.append("")
    L.append("ℹ️  Aannames & bronnen")
    L.append("- Open-Meteo ‘shortwave_radiation’ (uurwaarden).")
    L.append("- Meegewogen: oriëntatie + helling → effectieve PR, PR-basis, huislast, (ont)laad-rendementen en vermogens.")
    L.append("- Zonsondergang 21:00 voor PV-headroom.")
    if result.get("note"):
        L.append(f"- {result['note']}")
    return "\n".join(L)


def run_gui():
    cfg = load_or_create_config()
    tz = ZoneInfo(cfg.get("timezone", "Europe/Amsterdam"))

    root = tk.Tk()
    root.title("ChargeMind 0.1")
    root.geometry("1280x820")

    paned = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
    paned.pack(fill="both", expand=True)

    # ========== LEFT: Settings (scrollable) ==========
    left_container = ttk.Frame(paned)
    paned.add(left_container, weight=1)

    canvas = tk.Canvas(left_container, borderwidth=0)
    scroll = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
    settings = ttk.Frame(canvas)
    settings.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=settings, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    # ========== RIGHT: Controls + Notebook ==========
    right = ttk.Frame(paned)
    paned.add(right, weight=3)

    frm = ttk.LabelFrame(right, text="Parameters")
    frm.pack(fill="x", padx=12, pady=8)

    choice_var = tk.StringVar(value="V")

    def on_choice():
        time_entry.configure(state="normal" if choice_var.get() == "M" else "disabled")

    ttk.Radiobutton(frm, text="Vandaag", variable=choice_var, value="V", command=on_choice).grid(
        row=0, column=0, padx=6, pady=6, sticky="w"
    )
    ttk.Radiobutton(frm, text="Morgen", variable=choice_var, value="M", command=on_choice).grid(
        row=0, column=1, padx=6, pady=6, sticky="w"
    )

    tk.Label(frm, text="Tijd (HH:MM, alleen morgen):").grid(row=1, column=0, sticky="e", padx=6)
    time_var = tk.StringVar(value="06:00")
    time_entry = tk.Entry(frm, textvariable=time_var, width=8, state="disabled")
    time_entry.grid(row=1, column=1, sticky="w", padx=6)

    tk.Label(frm, text="SOC (%)").grid(row=2, column=0, sticky="e", padx=6)
    soc_var = tk.StringVar(value="35")
    tk.Entry(frm, textvariable=soc_var, width=8).grid(row=2, column=1, sticky="w", padx=6)

    # Bereken knop
    ttk.Button(frm, text="Bereken", command=lambda: on_calc()).grid(row=0, column=4, rowspan=3, padx=12)

    # Instellingen velden
    widgets = {}

    def add_field(row, label, key, width=12):
        tk.Label(settings, text=label, font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, sticky="w", padx=8, pady=(10, 0)
        )
        var = tk.StringVar(value=str(cfg.get(key, "")))
        ent = tk.Entry(settings, textvariable=var, width=width)
        ent.grid(row=row, column=1, sticky="w", padx=8, pady=(10, 0))
        tk.Label(settings, text=HELP.get(key, ""), fg="#555", wraplength=360, justify="left").grid(
            row=row + 1, column=0, columnspan=2, sticky="w", padx=8
        )
        widgets[key] = var
        var.widget = ent
        return row + 2

    r = 0
    for lab, key in [
        ("Latitude", "lat"),
        ("Longitude", "lon"),
        ("PV kWp", "kwp"),
        ("PR base", "pr_base"),
        ("Tilt (°)", "tilt_deg"),
        ("Battery kWh", "battery_kwh"),
        ("Min SOC reserve %", "min_soc_reserve"),
        ("Huislast kW", "house_load_kw"),
        ("Laadvermogen kW", "inverter_charge_kw"),
        ("Ontlaadvermogen kW", "inverter_discharge_kw"),
        ("Roundtrip eff", "roundtrip_eff"),
        ("Laad eff", "charge_eff"),
        ("Ontlaad eff", "discharge_eff"),
    ]:
        r = add_field(r, lab, key)

    tk.Label(settings, text="Oriëntatie", font=("Segoe UI", 10, "bold")).grid(
        row=r, column=0, sticky="w", padx=8, pady=(10, 0)
    )
    ori_var = tk.IntVar(value=int(cfg.get("orientation_choice", 1)))
    cb = ttk.Combobox(
        settings, width=20, state="readonly", values=[f"{k} - {v['label']}" for k, v in ORIENTATIONS.items()]
    )
    idx = (ori_var.get() - 1) if 1 <= ori_var.get() <= 8 else 0
    cb.current(idx)
    cb.grid(row=r, column=1, sticky="w", padx=8, pady=(10, 0))
    tk.Label(settings, text=HELP["orientation_choice"], fg="#555", wraplength=360, justify="left").grid(
        row=r + 1, column=0, columnspan=2, sticky="w", padx=8
    )
    r += 2

    def save_settings():
        try:
            for k, var in widgets.items():
                val = var.get().strip().replace(",", ".")
                if k in ("tilt_deg",):
                    cfg[k] = int(float(val))
                else:
                    cfg[k] = float(val)
            cfg["orientation_choice"] = int(cb.get().split(" - ")[0])
            cfg["_configured"] = True
            save_config(cfg)
            messagebox.showinfo("OK", "Instellingen opgeslagen.")
        except Exception as e:
            messagebox.showerror("Fout", f"Onjuiste waarde: {e}")

    ttk.Button(settings, text="Instellingen opslaan", command=save_settings).grid(
        row=r, column=0, columnspan=2, pady=10, padx=8, sticky="w"
    )

    # Notebook: Advies + Grafieken
    nb = ttk.Notebook(right)
    nb.pack(fill="both", expand=True, padx=12, pady=8)

    advice_frame = ttk.Frame(nb)
    charts_frame = ttk.Frame(nb)
    nb.add(advice_frame, text="Advies")
    nb.add(charts_frame, text="Grafieken")

    out = tk.Text(advice_frame, wrap="word", font=("Consolas", 11))
    out.pack(fill="both", expand=True, padx=8, pady=8)

    fig = Figure(figsize=(7, 5), dpi=100)
    ax_price = fig.add_subplot(211)
    ax_soc = fig.add_subplot(212)
    canvas_plot = FigureCanvasTkAgg(fig, master=charts_frame)
    canvas_plot.get_tk_widget().pack(fill="both", expand=True)

    def on_calc():
        if not cfg.get("_configured", False):
            messagebox.showwarning(
                "Instellen vereist", "Stel links je instellingen in en klik op ‘Instellingen opslaan’."
            )
            return
        try:
            soc = float(soc_var.get().replace(",", "."))
        except Exception:
            messagebox.showerror("Fout", "SOC moet een getal zijn.")
            return

        choice = choice_var.get()
        hhmm = time_var.get().strip()

        try:
            res = asyncio.run(plan_day(cfg, choice, soc, hhmm))
        except Exception:
            messagebox.showinfo(
                "Tarieven nog niet beschikbaar",
                "Voor de gekozen dag zijn nog geen tarieven beschikbaar.\n"
                "Bij Frank komen tarieven voor morgen meestal rond 15:00 online."
            )
            return

        if "note" in res:
            out.delete("1.0", "end")
            out.insert("end", res["note"])
            return

        # Tekst
        arb = estimate_arbitrage(res, cfg)
        advice_text = build_advice_text(res, arb, tz=tz, cfg=cfg)
        out.delete("1.0", "end")
        out.insert("end", advice_text)

        # Grafieken
        import matplotlib.dates as mdates
        import matplotlib.patches as mpatches
        from datetime import timedelta

        ax_price.clear()
        ax_soc.clear()

        # Prijs: blok-uren (steps-post) + gekleurde spans voor laad/ontlaad
        t = res["series"]["times"]
        p = res["series"]["prices"]
        if t and p:
            # Maak staparrays: start van elk blok + eindpunt
            t_step, p_step = [], []
            for i in range(len(t)):
                t_step.append(t[i]);           p_step.append(p[i])
                t_end = t[i] + timedelta(hours=1)
                t_step.append(t_end);          p_step.append(p[i])
            ax_price.plot(t_step, p_step, drawstyle="steps-post")

            date_str = res.get("day_date", t[0].date())
            ax_price.set_title(f"Dagprijzen (€ / kWh) — {date_str}")
            ax_price.set_xlabel("Tijd")
            ax_price.set_ylabel("Prijs")
            ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

            # Spans
            charge_patch = mpatches.Patch(color="#ff6666", alpha=0.25, label="Laadslot")
            discharge_patch = mpatches.Patch(color="#66cc66", alpha=0.25, label="Ontlaadslot")
            ax_price.axvspan(res["cheap_start"], res["cheap_end"], color="#ff6666", alpha=0.25)
            ax_price.axvspan(res["exp_start"], res["exp_end"], color="#66cc66", alpha=0.25)
            ax_price.legend(handles=[charge_patch, discharge_patch], loc="lower center")

        # SOC-curve: gekleurde segmenten per oorzaak
        st = res["series"]["soc_times"]
        sv = res["series"]["soc_values"]
        causes = res["series"].get("soc_causes", [])
        color_map = {
            "pv": "#2ca02c",            # groen
            "grid_charge": "#d62728",   # rood
            "grid_discharge": "#ff7f0e",# oranje
            "reserve": "#9467bd",       # paars
            "none": "#1f77b4"           # fallback
        }
        if st and sv:
            nseg = max(0, len(sv) - 1)
            for i in range(nseg):
                cause = causes[i] if i < len(causes) else "none"
                ax_soc.plot([st[i], st[i + 1]], [sv[i], sv[i + 1]], color=color_map.get(cause, "#1f77b4"))

        ax_soc.set_title(f"SOC-curve (simulatie) — {res.get('day_date', '')}")
        ax_soc.set_xlabel("Tijd")
        ax_soc.set_ylabel("SOC (%)")
        ax_soc.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax_soc.axhline(cfg["min_soc_reserve"], linestyle="--")

        patches = [
            mpatches.Patch(color=color_map["pv"], label="PV"),
            mpatches.Patch(color=color_map["grid_charge"], label="Net laden"),
            mpatches.Patch(color=color_map["grid_discharge"], label="Net ontladen"),
            mpatches.Patch(color=color_map["reserve"], label="Reserve"),
        ]
        ax_soc.legend(handles=patches, loc="lower center")

        fig.tight_layout()
        canvas_plot.draw()

    # Welkomst-popup bij eerste keer (en focus direct op eerste veld)
    if not cfg.get("_configured", False):
        messagebox.showinfo(
            "Welkom bij ChargeMind",
            "Welkom! Vul eerst de instellingen links in en klik op ‘Instellingen opslaan’.\n\n"
            "De nauwkeurigheid hangt af van correcte invoer (oriëntatie, helling, kWp, rendementen, huislast, enz.).\n"
            "Aan dit advies kunnen geen rechten worden ontleend."
        )
        root.after(50, lambda: list(widgets.values())[0].widget.focus_set() if widgets else None)

    # Zorg dat tijdveld meteen de juiste state heeft
    on_choice()

    root.mainloop()
