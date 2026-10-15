"""Passo 3 (ogni giorno, schedulato): prenota il posto a oggi + N giorni.
Exit code: 0 = ok/skip, 1 = errore prenotazione, 2 = sessione scaduta."""
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

import yaml
from playwright.sync_api import sync_playwright

cfg = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")))
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def notify(text: str) -> None:
    """Invia l'esito su ntfy (push sul telefono) e/o Teams. Non fa mai fallire lo script."""
    print(text)
    topic = os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic")
    if topic:
        try:
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                                         headers={"Title": "WeWork Meravigli", "Tags": "office"})
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"Notifica ntfy non inviata: {e}")
    hook = os.environ.get("TEAMS_WEBHOOK") or cfg.get("teams_webhook")
    if hook:
        try:
            req = urllib.request.Request(hook, data=json.dumps({"text": text}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"Notifica Teams non inviata: {e}")


def target_date() -> dt.date | None:
    today = dt.datetime.now(ZoneInfo(cfg["timezone"])).date()
    d = today + dt.timedelta(days=cfg["days_ahead"])
    if cfg.get("skip_weekends") and d.weekday() >= 5:
        return None
    if d.isoformat() in cfg.get("skip_dates", []):
        return None
    return d


def main() -> int:
    d = target_date()
    if d is None:
        print("Data target esclusa (weekend o skip_dates): niente da fare.")
        return 0
    date_str = d.isoformat()
    tpl = json.load(open(cfg["template_file"]))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.get("headless", True))
        ctx = browser.new_context(storage_state=cfg["session_file"])
        page = ctx.new_page()

        # Apro la web app: rinfresca i token e catturo l'Authorization corrente
        fresh = {}

        def on_request(req):
            if any(h in req.url for h in cfg["api_host_contains"]):
                auth = req.headers.get("authorization")
                if auth:
                    fresh["authorization"] = auth

        page.on("request", on_request)
        page.goto(cfg["start_url"], wait_until="networkidle", timeout=60_000)

        if "login" in page.url.lower() or "signin" in page.url.lower():
            notify("⚠️ WeWork: sessione scaduta. Rilancia save_session.py e aggiorna la sessione.")
            browser.close()
            return 2

        headers = {**tpl["headers"], **fresh}
        url = tpl["url"].replace("{{DATE}}", date_str)
        body = tpl["body"].replace("{{DATE}}", date_str)

        resp = None
        for attempt in range(1, cfg.get("max_retries", 3) + 1):
            resp = page.request.fetch(url, method=tpl["method"], headers=headers,
                                      data=body or None, timeout=30_000)
            if resp.status < 500 and resp.status != 429:
                break
            time.sleep(5 * attempt)

        ctx.storage_state(path=cfg["session_file"])  # salva la sessione rinfrescata
        browser.close()

    text = resp.text()[:500]
    if resp.ok:
        notify(f"✅ WeWork: posto prenotato per {date_str}.")
        return 0
    if resp.status == 409:
        notify(f"ℹ️ WeWork {date_str}: conflitto (409), forse già prenotato. Risposta: {text}")
        return 0
    if resp.status in (401, 403):
        notify(f"⚠️ WeWork {date_str}: non autorizzato ({resp.status}). Sessione da rinnovare.")
        return 2
    notify(f"❌ WeWork {date_str}: prenotazione fallita ({resp.status}). Risposta: {text}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        notify(f"❌ WeWork: errore inatteso: {e}")
        sys.exit(1)
