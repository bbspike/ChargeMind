# ⚡ ChargeMind

**ChargeMind** is een slimme planner voor thuisbatterijen en dynamische energietarieven.  
De applicatie combineert marktprijzen, zonnepanelenopbrengst (via weerdata) en je eigen instellingen om te adviseren **wanneer je het beste kunt laden of ontladen**.  

Het doel is **energiekosten minimaliseren** en **autonomie maximaliseren**: zoveel mogelijk eigen zonne-energie gebruiken en strategisch inkopen bij goedkope uren.

---

## ✨ Wat doet ChargeMind?

- **Slimme laad/ontlaadadviezen**: berekent voor vandaag of morgen het goedkoopste uur om te laden en het duurste uur om te ontladen.
- **Zonne-opbrengst simulatie**: houdt rekening met oriëntatie, hellingshoek en verwachte zoninstraling.
- **Batterijbeperkingen**: houdt rekening met omvormer-vermogen en (on)haalbare SOC-doelen.
- **Actieschema**: toont in tekst (en grafiek) welke actie je moet ondernemen, inclusief tijden en doelen.
- **Visualisaties**:
  - Dagprijs-verloop met markering van laad- en ontlaad-uren.
  - SOC-curve met invloed van PV, netladen en ontladen.

---

## 🛠️ Installatie

### 1. Clone de repository
```bash
git clone https://github.com/<jouw-repo>/ChargeMind.git
cd ChargeMind
2. Vereisten installeren

ChargeMind draait op Python 3.10+.
Installeer dependencies met:

pip install -r requirements.txt


Standaard gebruikte libraries:

tkinter (GUI)

matplotlib (grafieken)

requests (API-calls Open-Meteo)

python_frank_energie (Frank Energie API)

zoneinfo (tijdzones)

3. Starten
python main.py


Bij de eerste start verschijnt een configuratie-wizard waarin je locatie, PV-configuratie en batterijgegevens invult.
Deze worden opgeslagen in fe_planner_config.json.

🚀 Gebruik

Start de applicatie (main.py).

Kies of je een advies wilt voor vandaag of morgen.

Vul je huidige of verwachte batterij-SOC in.

Bekijk het advies:

Tekstueel schema met tijden en SOC-doelen.

Grafieken met dagprijzen en SOC-verloop.

Optioneel: pas instellingen aan (locatie, PV, batterij, omvormer).

📊 Voorbeeldoutput

Advies (tekstueel):

=== 🔋 Slim advies (Vandaag) ===
Nu: 19-08 09:55 | Huidig SOC: 39.0%

Goedkoopste uur: 19-08 14:00 → 19-08 15:00 | € 0.001/kWh
Duurste uur:     19-08 20:00 → 19-08 21:00 | € 0.125/kWh

— Acties —
• Laad in 19-08 14:00–15:00 tot **90.8%**.
• Ontlaad in 19-08 20:00–21:00 tot **35.0%** (nachtreserve).


Grafieken:

📈 Dagprijzen (uurbloklijn, laadslot rood, ontlaadslot groen).

🔋 SOC-curve (kleurcodering per oorzaak: PV = groen, netladen = rood, ontladen = oranje, reserve = paars).

🌍 Databronnen

Frank Energie API – dynamische elektriciteitsprijzen.

Open-Meteo API – zoninstraling en weerprognoses (zonnekracht, bewolkingsgraad).

Eigen configuratie – PV-richting, hellingshoek, batterijcapaciteit en omvormervermogen.

📌 Roadmap

Komende uitbreidingen waar aan gewerkt wordt:

🔌 Directe koppeling met omvormers (Solis, Dyness, enz.).

🏢 Integratie energieleveranciers voor meer marktdata.

☀️ Meer METEO-variabelen (temperatuur, bewolkingsgraad, seizoenscorrectie).

📱 Web- of mobiele versie naast Tkinter GUI.

📊 Uitgebreidere rapportage (export naar CSV/Excel).

⚠️ Disclaimer

ChargeMind is een hulpmiddel voor energiebesparing.
De berekeningen zijn afhankelijk van de juistheid van instellingen en beschikbaarheid van externe databronnen.
Er kunnen geen rechten worden ontleend aan de adviezen.
