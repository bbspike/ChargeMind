
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FE_GRAPHQL_ENDPOINTS = [
    "https://graphql.frankenergie.nl",
    "https://frank-graphql-prod.graphcdn.app/",
    "https://frank-api.nl/graphql",
]

def to_local(dt_str_or_dt, tz: ZoneInfo):
    if isinstance(dt_str_or_dt, datetime):
        return dt_str_or_dt.astimezone(tz)
    s = str(dt_str_or_dt)
    if s.endswith("Z"): s = s.replace("Z","+00:00")
    return datetime.fromisoformat(s).astimezone(tz)

def om_url(lat, lon, tzname):
    return (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=shortwave_radiation&timezone={tzname}"
    )

def get_radiation_series(cfg, tz: ZoneInfo):
    url = om_url(cfg["lat"], cfg["lon"], cfg["timezone"])
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    j = r.json()
    times = j["hourly"]["time"]
    rad = j["hourly"]["shortwave_radiation"]
    series = []
    for t, w in zip(times, rad):
        dt = datetime.fromisoformat(t).replace(tzinfo=tz)
        series.append({"time": dt, "sw": float(w)})
    return series

def fetch_graphql_day(start_date_str: str, end_date_str: str, tz: ZoneInfo):
    q = """
    query MarketPrices($startDate: Date!, $endDate: Date!) {
      marketPricesElectricity(startDate: $startDate, endDate: $endDate) {
        from
        till
        marketPrice
      }
    }
    """
    payload = {"query": q, "variables": {"startDate": start_date_str, "endDate": end_date_str}}
    headers = {"Content-Type": "application/json", "User-Agent": "fe-planner/1.0"}
    last_err = None
    for url in FE_GRAPHQL_ENDPOINTS:
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            r.raise_for_status()
            j = r.json()
            if j.get("errors"):
                last_err = RuntimeError(f"GraphQL error @ {url}: {j['errors']}"); continue
            data = (j.get("data") or {}).get("marketPricesElectricity") or []
            out = []
            for item in data:
                start = to_local(item["from"], tz)
                end = to_local(item["till"], tz)
                out.append({"start": start, "end": end, "price": float(item["marketPrice"])})
            if out:
                return out
            last_err = RuntimeError(f"Lege data @ {url}")
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Kon Frank Energie prijzen niet ophalen: {last_err}")

async def get_frank_day_local(which: str, tz: ZoneInfo):
    from datetime import datetime, timedelta
    today = datetime.now(tz).date()
    if which == "today":
        return fetch_graphql_day(today.isoformat(), (today+timedelta(days=1)).isoformat(), tz)
    else:
        tomorrow = today + timedelta(days=1)
        return fetch_graphql_day(tomorrow.isoformat(), (tomorrow+timedelta(days=1)).isoformat(), tz)
