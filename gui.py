
import tkinter as tk
from tkinter import ttk, messagebox
from zoneinfo import ZoneInfo
import asyncio

from config import load_or_create_config, save_config
from planner import plan_day, estimate_arbitrage
from utils import fmt, ORIENTATIONS

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

def run_gui():
    cfg = load_or_create_config()
    tz = ZoneInfo(cfg.get("timezone","Europe/Amsterdam"))

    root = tk.Tk()
    root.title("ChargeMind 0.1")
    root.geometry("1280x820")

    paned = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
    paned.pack(fill="both", expand=True)

    # Settings (left, scrollable)
    left_container = ttk.Frame(paned)
    paned.add(left_container, weight=1)

    canvas = tk.Canvas(left_container, borderwidth=0)
    scroll = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
    settings = ttk.Frame(canvas)
    settings.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0,0), window=settings, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    # Right pane: controls + notebook
    right = ttk.Frame(paned)
    paned.add(right, weight=3)

    frm = ttk.LabelFrame(right, text="Parameters")
    frm.pack(fill="x", padx=12, pady=8)

    choice_var = tk.StringVar(value="V")
    def on_choice():
        time_entry.configure(state="normal" if choice_var.get()=="M" else "disabled")
    ttk.Radiobutton(frm, text="Vandaag", variable=choice_var, value="V", command=on_choice).grid(row=0,column=0, padx=6,pady=6, sticky="w")
    ttk.Radiobutton(frm, text="Morgen",  variable=choice_var, value="M", command=on_choice).grid(row=0,column=1, padx=6,pady=6, sticky="w")

    tk.Label(frm, text="Tijd (HH:MM, alleen morgen):").grid(row=1, column=0, sticky="e", padx=6)
    time_var = tk.StringVar(value="06:00")
    time_entry = tk.Entry(frm, textvariable=time_var, width=8, state="disabled")
    time_entry.grid(row=1, column=1, sticky="w", padx=6)

    tk.Label(frm, text="SOC (%)").grid(row=2, column=0, sticky="e", padx=6)
    soc_var = tk.StringVar(value="35")
    tk.Entry(frm, textvariable=soc_var, width=8).grid(row=2, column=1, sticky="w", padx=6)

    ttk.Button(frm, text="Bereken", command=lambda: on_calc()).grid(row=0, column=4, rowspan=3, padx=12)

    # Settings fields
    widgets = {}
    def add_field(row, label, key, width=12):
        tk.Label(settings, text=label, font=("Segoe UI",10,"bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(10,0))
        var = tk.StringVar(value=str(cfg.get(key,"")))
        ent = tk.Entry(settings, textvariable=var, width=width)
        ent.grid(row=row, column=1, sticky="w", padx=8, pady=(10,0))
        tk.Label(settings, text=HELP.get(key,""), fg="#555", wraplength=360, justify="left").grid(row=row+1, column=0, columnspan=2, sticky="w", padx=8)
        widgets[key]=var
        var.widget = ent
        return row+2

    r=0
    for lab,key in [
        ("Latitude","lat"), ("Longitude","lon"), ("PV kWp","kwp"),
        ("PR base","pr_base"), ("Tilt (°)","tilt_deg"), ("Battery kWh","battery_kwh"),
        ("Min SOC reserve %","min_soc_reserve"), ("Huislast kW","house_load_kw"),
        ("Laadvermogen kW","inverter_charge_kw"), ("Ontlaadvermogen kW","inverter_discharge_kw"),
        ("Roundtrip eff","roundtrip_eff"), ("Laad eff","charge_eff"), ("Ontlaad eff","discharge_eff")
    ]:
        r = add_field(r, lab, key)

    tk.Label(settings, text="Oriëntatie", font=("Segoe UI",10,"bold")).grid(row=r, column=0, sticky="w", padx=8, pady=(10,0))
    ori_var = tk.IntVar(value=int(cfg.get("orientation_choice",1)))
    cb = ttk.Combobox(settings, width=20, state="readonly",
                      values=[f"{k} - {v['label']}" for k,v in ORIENTATIONS.items()])
    idx = (ori_var.get()-1) if 1 <= ori_var.get() <= 8 else 0
    cb.current(idx)
    cb.grid(row=r, column=1, sticky="w", padx=8, pady=(10,0))
    tk.Label(settings, text=HELP["orientation_choice"], fg="#555", wraplength=360, justify="left").grid(row=r+1, column=0, columnspan=2, sticky="w", padx=8)
    r += 2

    def save_settings():
        try:
            for k,var in widgets.items():
                val = var.get().strip().replace(",",".")
                if k in ("tilt_deg",):
                    cfg[k] = int(float(val))
                else:
                    cfg[k] = float(val)
            cfg["orientation_choice"] = int(cb.get().split(" - ")[0])
            cfg["_configured"] = True
            save_config(cfg)
            messagebox.showinfo("OK","Instellingen opgeslagen.")
        except Exception as e:
            messagebox.showerror("Fout", f"Onjuiste waarde: {e}")

    ttk.Button(settings, text="Instellingen opslaan", command=save_settings).grid(row=r, column=0, columnspan=2, pady=10, padx=8, sticky="w")

    # Notebook: Advies (text) + Grafieken
    nb = ttk.Notebook(right)
    nb.pack(fill="both", expand=True, padx=12, pady=8)

    advice_frame = ttk.Frame(nb)
    charts_frame = ttk.Frame(nb)
    nb.add(advice_frame, text="Advies")
    nb.add(charts_frame, text="Grafieken")

    out = tk.Text(advice_frame, wrap="word", font=("Consolas", 11))
    out.pack(fill="both", expand=True, padx=8, pady=8)

    fig = Figure(figsize=(7,5), dpi=100)
    ax_price = fig.add_subplot(211)
    ax_soc = fig.add_subplot(212)
    canvas_plot = FigureCanvasTkAgg(fig, master=charts_frame)
    canvas_plot.get_tk_widget().pack(fill="both", expand=True)

    def write(lines):
        out.delete("1.0","end")
        out.insert("end", "\n".join(lines))

    def on_calc():
        if not cfg.get("_configured", False):
            messagebox.showwarning("Instellen vereist", "Stel links je instellingen in en klik op ‘Instellingen opslaan’.")
            return
        try:
            soc = float(soc_var.get().replace(",", "."))
        except:
            messagebox.showerror("Fout", "SOC moet een getal zijn."); return
        choice = choice_var.get()
        hhmm = time_var.get().strip()

        try:
            res = asyncio.run(plan_day(cfg, choice, soc, hhmm))
        except Exception:
            messagebox.showerror("Geen tarieven beschikbaar",
                                 "Tarieven konden niet worden opgehaald. "
                                 "Voor de volgende dag zijn ze meestal rond 15:00 beschikbaar.")
            return

        if "note" in res:
            write([res["note"]]); return

        lines = []
        lines.append(f"=== 🔋 Slim advies ({res['day_label']}) ===")
        if choice == "V":
            lines.append(f"Nu | Huidig SOC: {res['soc_now']:.1f}%")
        else:
            lines.append(f"Basis-moment: {fmt(res['base_dt'], tz)} | Verwachte SOC: {res['soc_now']:.1f}%")

        lines.append("")
        lines.append(f"Goedkoopste uur: {fmt(res['cheap_start'], tz)} → {fmt(res['cheap_end'], tz)} | € {res['cheap_price']:.3f}/kWh")
        lines.append(f"Duurste uur:     {fmt(res['exp_start'], tz)} → {fmt(res['exp_end'], tz)} | € {res['exp_price']:.3f}/kWh")

        lines.append("")
        lines.append("— Prognose SOC —")
        lines.append(f"PV vóór laden: +{res['pv_gain_before_charge_pct']} %-pt → SOC bij start ≈ {res['soc_at_charge_start']}%")
        lines.append(f"PV ná laden tot zonsondergang: +{res['pv_gain_after_charge_pct']} %-pt (ruimte nodig: {res['headroom_pct']} %-pt)")
        lines.append(f"Reserve voor duurste uur (≥ {cfg['min_soc_reserve']}%): tekort = {res['deficit_to_reserve_pct']} %-pt")

        lines.append("")
        lines.append("— Laadslot —")
        lines.append(f"Benodigde bijlading (headroom/reserve): ~{res['required_charge_pct']} %-pt")
        lines.append(f"Max bijladen in laadslot:               ~{res['max_slot_charge_pct']} %-pt")
        lines.append(f"Aanbevolen bijladen:                    ~{res['add_pct']} %-pt")
        lines.append(f"➡️ Doel-SOC einde laadslot: **{res['target_soc_after_charge']}%**")
        if res.get('charge_limited', False):
            lines.append(f"⚠️  Laadlimiet goedkoop uur: haalbare doel-SOC ≈ {res['target_soc_after_charge']}% (beperkt door vermogen/duur).")

        lines.append("")
        lines.append("— Acties —")
        lines.append(f"• Laad in {fmt(res['cheap_start'], tz)}–{fmt(res['cheap_end'], tz)} tot **{res['target_soc_after_charge']}%**.")
        if res.get("can_reach_reserve", True):
            lines.append(f"• Ontlaad in {fmt(res['exp_start'], tz)}–{fmt(res['exp_end'], tz)} tot **{cfg['min_soc_reserve']:.1f}%** (nacht-reserve).")
        else:
            lines.append(f"• Ontlaad in {fmt(res['exp_start'], tz)}–{fmt(res['exp_end'], tz)} zoveel mogelijk (limiet omvormer).")
            lines.append(f"  Max. ontlaadcapaciteit dure uur: ~{res['max_discharge_pct']} %-pt → haalbaar minimum ≈ {res['achievable_min_soc']}%.")

        arb = estimate_arbitrage(res, cfg)
        lines.append("")
        lines.append("— Kosten & prognose (kale marktprijzen) —")
        lines.append(f"PV → batterij (gratis): ~{arb['pv_stored_kwh']} kWh")
        lines.append(f"Net-inkoop voor laden:  ~{arb['net_buy_kwh']} kWh @ €{arb['buy_allin_eur_kwh']}/kWh → €{arb['cost_eur']}")
        lines.append(f"Aflevering totaal (huis/net): ~{arb['deliver_kwh_total']} kWh @ €{arb['sell_allin_eur_kwh']}/kWh → €{arb['revenue_eur']}")
        lines.append(f"⚖️  Verwachte marge (grof): €{arb['profit_eur']}")
        lines.append(f"Note: PV-kWh (gratis) en net-kWh (gekocht) apart gewaardeerd; gelimiteerd op ontlaadvermogen tijdens duur uur.")

        lines.append("")
        lines.append("ℹ️  Weer/assumpties:")
        lines.append("- Bron: Open‑Meteo ‘shortwave_radiation’ (globale kortgolvige instraling) per uur.")
        lines.append("- Rekent mee: oriëntatie (Noord/… factor) + hellingfactor → effectieve PR; PR‑basis; huislast; laad/ontlaad‑rendementen; laadsnelheid/ontlaadsnelheid.")
        lines.append("- Zonsondergang: vaste schatting 21:00 voor PV‑na‑laden headroom.")
        lines.append("- Tarieven voor morgen meestal rond 15:00 beschikbaar.")

        out.delete("1.0","end"); out.insert("end","\n".join(lines))

        # Charts
        import matplotlib.dates as mdates
        import matplotlib.patches as mpatches
        ax_price.clear(); ax_soc.clear()

        # Price chart as hourly step with colored blocks and legend
        t = res["series"]["times"]; p = res["series"]["prices"]
        if t and p:
            ax_price.step(t, p, where="post")
            # Title with date
            date_str = res.get("day_date", t[0].date()) if t else ""
            ax_price.set_title(f"Dagprijzen (€ / kWh) — {date_str}")
            ax_price.set_xlabel("Tijd"); ax_price.set_ylabel("Prijs")
            # Time-only on axis
            ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            # Colored spans: red for charge, green for discharge
            charge_patch = mpatches.Patch(color="#ff6666", alpha=0.25, label="Laadslot")
            discharge_patch = mpatches.Patch(color="#66cc66", alpha=0.25, label="Ontlaadslot")
            ax_price.axvspan(res["cheap_start"], res["cheap_end"], color="#ff6666", alpha=0.25)
            ax_price.axvspan(res["exp_start"], res["exp_end"], color="#66cc66", alpha=0.25)
            ax_price.legend(handles=[charge_patch, discharge_patch], loc="lower center")

            # SOC chart with colored segments by cause
            st = res["series"]["soc_times"]; sv = res["series"]["soc_values"]
            causes = res["series"].get("soc_causes", [])
            if st and sv:
                color_map = {
                    "pv": "#2ca02c",            # groen
                    "grid_charge": "#d62728",   # rood
                    "grid_discharge": "#ff7f0e",# oranje
                    "reserve": "#9467bd",       # paars
                    "none": "#1f77b4"           # fallback
                }
                nseg = max(0, len(sv)-1)
                for i in range(nseg):
                    cause = causes[i] if i < len(causes) else "none"
                    ax_soc.plot([st[i], st[i+1]], [sv[i], sv[i+1]], color=color_map.get(cause, "#1f77b4"))
            ax_soc.set_title(f"SOC-curve (simulatie) — {res.get('day_date','')}")
            ax_soc.set_xlabel("Tijd"); ax_soc.set_ylabel("SOC (%)")
            ax_soc.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax_soc.axhline(cfg["min_soc_reserve"], linestyle="--")
            # Legend
            patches = [
                mpatches.Patch(color=color_map["pv"], label="PV"),
                mpatches.Patch(color=color_map["grid_charge"], label="Net laden"),
                mpatches.Patch(color=color_map["grid_discharge"], label="Net ontladen"),
                mpatches.Patch(color=color_map["reserve"], label="Reserve")
            ]
            ax_soc.legend(handles=patches, loc="lower center")

        fig.tight_layout()
        canvas_plot.draw()

    if not cfg.get("_configured", False):
        messagebox.showinfo(
            "Welkom",
            "Welkom! Vul eerst de instellingen links in en klik op ‘Instellingen opslaan’.\n\n"
            "Let op: de nauwkeurigheid hangt sterk af van correcte instellingen (oriëntatie, helling, kWp, rendementen, huislast, etc.).\n"
            "Aan dit advies kunnen geen rechten worden ontleend."
        )
        # Focus op eerste invoerveld na sluiten popup
        root.after(50, lambda: list(widgets.values())[0].widget.focus_set() if widgets else None)

    root.mainloop()
