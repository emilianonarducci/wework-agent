"""Passo 1 (circa una volta al mese): login manuale e salvataggio della sessione.
Funziona anche con SSO/MFA perché il login lo fai tu nel browser.
La sessione viene salvata da sola appena il login è completato: non serve premere nulla."""
import sys
import time

import yaml
from playwright.sync_api import sync_playwright

cfg = yaml.safe_load(open("config.yaml"))
TIMEOUT_MIN = 9
PROFILE_DIR = ".login_profile"  # profilo del browser di login (resta sul PC, è nel .gitignore)


def app_url(ctx) -> str:
    """URL (senza query) della pagina dell'app se si è dentro, cioè non sulla pagina di login."""
    for page in ctx.pages:
        url = page.url.split("?")[0].split("#")[0]
        low = url.lower()
        if low.startswith(cfg["start_url"].lower()) and "login" not in low and "signin" not in low:
            return url
    return ""


with sync_playwright() as p:
    opts = dict(headless=False, channel=cfg.get("browser_channel") or None)
    try:
        ctx = p.chromium.launch_persistent_context(PROFILE_DIR, **opts)
    except Exception:
        opts["channel"] = "chrome"  # Chromium di Playwright assente: uso Chrome installato
        ctx = p.chromium.launch_persistent_context(PROFILE_DIR, **opts)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(cfg["start_url"])
    print(f"Fai il login nel browser (SSO/MFA inclusi) e arriva alla home: salvo da solo (attendo fino a {TIMEOUT_MIN} minuti)...",
          flush=True)
    deadline = time.time() + TIMEOUT_MIN * 60
    stable, last = 0, None
    # Login completato = si resta su una pagina dell'app (non di login) per qualche secondo di fila
    while stable < 4:
        if time.time() > deadline or not ctx.pages:
            ctx.close()
            sys.exit("Login non completato: sessione NON salvata.")
        # Non time.sleep: con l'API sincrona di Playwright gli URL si aggiornano solo durante
        # una chiamata a Playwright, altrimenti page.url resta fermo alla pagina di login.
        ctx.pages[0].wait_for_timeout(2000)
        url = app_url(ctx)
        if url != last:
            print(f"  pagina: {url or '(login)'}", flush=True)
        stable = stable + 1 if url and url == last else 0
        last = url
    ctx.storage_state(path=cfg["session_file"])
    print(f"Sessione salvata in {cfg['session_file']}")
    ctx.close()
