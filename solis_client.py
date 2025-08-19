# solis_client.py
import base64, hashlib, hmac, json, requests
from datetime import datetime, timezone
from typing import Optional

SOLIS_BASE = "https://www.soliscloud.com:13333"
CT_JSON = "application/json"

def _rfc1123_now() -> str:
    # e.g. 'Tue, 19 Aug 2025 18:10:00 GMT'
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def _content_md5(body_bytes: bytes) -> str:
    return base64.b64encode(hashlib.md5(body_bytes).digest()).decode()

def _signature(secret: str, method: str, md5_b64: str, content_type: str, date_hdr: str, path: str) -> str:
    # StringToSign as per docs:
    # METHOD \n Content-MD5 \n Content-Type \n Date \n Path
    msg = f"{method}\n{md5_b64}\n{content_type}\n{date_hdr}\n{path}"
    dig = hmac.new(secret.encode(), msg.encode(), hashlib.sha1).digest()
    return base64.b64encode(dig).decode()

class SolisClient:
    """
    Minimal SolisCloud Platform API v2 client (read-only).
    For write/control you need Device Control API enablement from Solis.
    """
    def __init__(self, api_id: str, api_secret: str, timeout: int = 20):
        self.api_id = api_id
        self.api_secret = api_secret
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        url = SOLIS_BASE + path
        body = json.dumps(payload, separators=(",", ":")).encode()
        md5_b64 = _content_md5(body)
        date_hdr = _rfc1123_now()
        sign = _signature(self.api_secret, "POST", md5_b64, CT_JSON, date_hdr, path)
        headers = {
            "Content-Type": CT_JSON,
            "Content-MD5": md5_b64,
            "Date": date_hdr,
            "Authorization": f"API {self.api_id}:{sign}",
            "User-Agent": "ChargeMind/0.1"
        }
        r = requests.post(url, headers=headers, data=body, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if j.get("code") not in (0, "0", 200):  # Solis returns {code:0} on success
            raise RuntimeError(f"Solis API error: {j}")
        return j

    def inverter_detail(self, sn: str, day_str: str) -> dict:
        """
        /v1/api/inverterDetail
        Body (per docs v2.0.2): {"sn":"<serial>","time":"YYYY-MM-DD"}
        """
        return self._post("/v1/api/inverterDetail", {"sn": sn, "time": day_str})

    def get_battery_soc(self, sn: str) -> Optional[float]:
        """
        Attempts to read 'batteryCapacitySoc' from inverterDetail 'data'.
        Returns float percent or None.
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        j = self.inverter_detail(sn, today)
        data = j.get("data") or {}
        # Field names seen in docs/examples:
        # - batteryCapacitySoc (percentage)
        # - or nested under 'storage' for some models
        soc = data.get("batteryCapacitySoc")
        if soc is None and isinstance(data.get("storage"), dict):
            soc = data["storage"].get("batteryCapacitySoc")
        if soc is None:
            # Some accounts expose 'now' page via dayDetail:
            # (left as future enhancement if needed)
            return None
        try:
            return float(soc)
        except Exception:
            return None

    # --------- OPTIONAL (requires Device Control API enablement) ----------
    def push_time_of_use(self, sn: str, charge_start_hhmm: str, charge_end_hhmm: str,
                         discharge_start_hhmm: str, discharge_end_hhmm: str,
                         target_soc_pct: float, reserve_soc_pct: float) -> None:
        """
        Stub: Device Control API has different endpoints/params and must be explicitly enabled.
        Without that enablement this will fail server-side.
        """
        raise NotImplementedError(
            "Device Control API niet geactiveerd voor dit account. "
            "Vraag 'Device Control API' rechten aan bij Solis support."
        )
