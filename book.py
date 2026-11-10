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


def target_date(booking_day: dt.date | None = None) -> dt.date | None:
    """Data da prenotare: giorno in cui si prenota (default oggi) + days_ahead."""
    today = booking_day or dt.datetime.now(ZoneInfo(cfg["timezone"])).date()
    d = today + dt.timedelta(days=cfg["days_ahead"])
    if cfg.get("skip_weekends") and d.weekday() >= 5:
        return None
    if d.isoformat() in cfg.get("skip_dates", []):
        return None
    return d


LAST_BOOKED_FILE = ".last_booked"  # ultima data prenotata: evita il doppione tra i due run schedulati


def read_last_booked() -> str:
    try:
        return open(LAST_BOOKED_FILE).read().strip()
    except FileNotFoundError:
        return ""


def plan(now: dt.datetime, max_wait_min: int) -> tuple[str, dt.date, float]:
    """Per i run schedulati decide cosa fare in base all'ora italiana di avvio.
    Il cron di GitHub può arrivare con ore di ritardo, quindi il workflow parte più volte
    dal pomeriggio in poi e il primo run abbastanza vicino alla mezzanotte la aspetta.
    Ritorna (azione, giorno in cui si prenota, secondi di attesa):
      "wait" = sera: aspetta la mezzanotte e prenota appena scatta
      "exit" = troppo presto: ci penserà un run successivo
      "now"  = già passata la mezzanotte (run in ritardo): prenota subito"""
    if now.hour < 12:
        return "now", now.date(), 0.0
    tomorrow = now.date() + dt.timedelta(days=1)
    midnight = dt.datetime.combine(tomorrow, dt.time(0), tzinfo=now.tzinfo)
    wait = midnight.timestamp() - now.timestamp()  # via timestamp: corretto anche al cambio d'ora
    if wait > max_wait_min * 60:
        return "exit", tomorrow, wait
    return "wait", tomorrow, wait


def sleep_until(ts: float) -> None:
    """Dorme fino all'istante ts (epoch), a pezzi per non accumulare deriva."""
    while (left := ts - time.time()) > 0:
        time.sleep(min(left, 60))


def is_success(http_ok: bool, text: str) -> bool:
    """Alcune API rispondono 200 ma con un flag di esito negativo nel JSON."""
    if not http_ok:
        return False
    try:
        data = json.loads(text) if text.strip().startswith("{") else {}
    except ValueError:
        return True
    flags = [v for k, v in data.items() if k.lower() in ("success", "issuccess", "succeeded")]
    return not flags or all(flags)


def main() -> int:
    scheduled = os.environ.get("ONLY_AFTER_MIDNIGHT") == "1"
    booking_day, midnight_ts = None, None
    if scheduled:
        now = dt.datetime.now(ZoneInfo(cfg["timezone"]))
        action, booking_day, wait = plan(now, cfg.get("max_wait_minutes", 180))
        if action == "exit":
            print(f"Ora italiana {now:%H:%M}, mancano {wait / 3600:.1f} h a mezzanotte: troppo presto, esco.")
            return 0
        if action == "wait":
            midnight_ts = time.time() + wait
    d = target_date(booking_day)
    if d is None:
        print("Data target esclusa (weekend o skip_dates): niente da fare.")
        return 0
    date_str = d.isoformat()
    if scheduled and read_last_booked() == date_str:
        print(f"{date_str} già prenotato da un run precedente: esco.")
        return 0
    tpl = json.load(open(cfg["template_file"]))
    if midnight_ts:
        print(f"Aspetto la mezzanotte italiana per prenotare {date_str} (mancano {wait / 60:.0f} min).", flush=True)
        sleep_until(midnight_ts - 120)  # browser e token si preparano 2 minuti prima

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.get("headless", True), channel=os.environ.get("BROWSER_CHANNEL", cfg.get("browser_channel")) or None)
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
        us_date = d.strftime("%m/%d/%Y")

        def fill(s: str) -> str:
            return s.replace("{{DATE}}", date_str).replace("{{DATE_US}}", us_date)

        if "{{DATE" not in tpl["url"] + tpl["body"]:
            notify("❌ WeWork: il template non contiene la data da sostituire. Lancia fix_template.py.")
            browser.close()
            return 1
        url = fill(tpl["url"])
        body = fill(tpl["body"])

        if midnight_ts:
            sleep_until(midnight_ts + 1)  # un secondo dopo la mezzanotte
            print(f"Mezzanotte: invio la prenotazione ({dt.datetime.now(ZoneInfo(cfg['timezone'])):%H:%M:%S}).", flush=True)

        # Tentativi: sempre su 5xx/429; a mezzanotte anche su un rifiuto diverso da "pieno"
        # (es. finestra di prenotazione non ancora aperta per pochi secondi di scarto).
        tries = 5 if midnight_ts else cfg.get("max_retries", 3)
        for attempt in range(1, tries + 1):
            resp = page.request.fetch(url, method=tpl["method"], headers=headers,
                                      data=body or None, timeout=30_000)
            # Leggo la risposta PRIMA di chiudere il browser
            status, text = resp.status, resp.text()[:500]
            ok = is_success(resp.ok, text)
            print(f"Tentativo {attempt}: HTTP {status} – {text}", flush=True)
            server_busy = status >= 500 or status == 429
            too_early = bool(midnight_ts) and not ok and status not in (401, 403, 409) \
                and "overbooked" not in text.lower()
            if ok or not (server_busy or too_early):
                break
            time.sleep(3 if midnight_ts else 5 * attempt)

        ctx.storage_state(path=cfg["session_file"])  # salva la sessione rinfrescata
        browser.close()

    if ok or status == 409:
        open(LAST_BOOKED_FILE, "w").write(date_str + "\n")
    if ok:
        notify(f"✅ WeWork: posto prenotato per {date_str}.")
        return 0
    if status == 409:
        notify(f"ℹ️ WeWork {date_str}: conflitto (409), forse già prenotato. Risposta: {text}")
        return 0
    if status in (401, 403):
        notify(f"⚠️ WeWork {date_str}: non autorizzato ({status}). Sessione da rinnovare.")
        return 2
    notify(f"❌ WeWork {date_str}: prenotazione fallita ({status}). Risposta: {text}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        notify(f"❌ WeWork: errore inatteso: {e}")
        sys.exit(1)
