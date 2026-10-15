"""Passo 2 (una tantum): registra la chiamata API di prenotazione.
Prenoti a mano UNA volta; lo script cattura le richieste POST/PUT/PATCH,
ti fa scegliere quella giusta e la salva come template sostituendo la data con {{DATE}}."""
import json
import yaml
from playwright.sync_api import sync_playwright

cfg = yaml.safe_load(open("config.yaml"))
VOLATILE = {"cookie", "authorization", "content-length", "host", "x-request-id",
            "x-amzn-trace-id", "traceparent", "sec-ch-ua", "sec-ch-ua-mobile",
            "sec-ch-ua-platform", "user-agent", "origin", "referer"}

booking_date = input("Data che prenoterai a mano (YYYY-MM-DD): ").strip()
captured = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(storage_state=cfg["session_file"])
    page = ctx.new_page()

    def on_request(req):
        if req.method in ("POST", "PUT", "PATCH") and any(h in req.url for h in cfg["api_host_contains"]):
            body = req.post_data or ""
            captured.append({"method": req.method, "url": req.url,
                             "headers": dict(req.headers), "body": body})

    page.on("request", on_request)
    page.goto(cfg["start_url"])
    input(f"\nPrenota a mano un posto per il {booking_date} nel browser, poi premi INVIO... ")
    ctx.storage_state(path=cfg["session_file"])
    browser.close()

candidates = [c for c in captured if booking_date in c["url"] or booking_date in c["body"]]
if not candidates:
    print("Nessuna richiesta contiene la data in formato YYYY-MM-DD. Tutte le richieste catturate:")
    candidates = captured
if not candidates:
    raise SystemExit("Nessuna richiesta catturata. Controlla api_host_contains in config.yaml.")

for i, c in enumerate(candidates):
    print(f"\n[{i}] {c['method']} {c['url']}\n    {c['body'][:300]}")
idx = int(input("\nNumero della richiesta di prenotazione: "))
c = candidates[idx]

template = {
    "method": c["method"],
    "url": c["url"].replace(booking_date, "{{DATE}}"),
    "headers": {k: v for k, v in c["headers"].items() if k.lower() not in VOLATILE},
    "body": c["body"].replace(booking_date, "{{DATE}}"),
}
json.dump(template, open(cfg["template_file"], "w"), indent=2, ensure_ascii=False)
print(f"\nTemplate salvato in {cfg['template_file']}.")
print("Controllalo: se la data compare anche in altri formati (es. epoch ms) va adattata a mano.")
print("Ricordati di cancellare dall'app la prenotazione di prova, se non ti serve.")
