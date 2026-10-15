"""Passo 1 (una tantum): login manuale e salvataggio della sessione.
Funziona anche con SSO/MFA perché il login lo fai tu nel browser."""
import yaml
from playwright.sync_api import sync_playwright

cfg = yaml.safe_load(open("config.yaml"))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel=cfg.get("browser_channel") or None)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(cfg["start_url"])
    input("\nFai il login nel browser (SSO/MFA inclusi), arriva alla home, poi premi INVIO qui... ")
    ctx.storage_state(path=cfg["session_file"])
    print(f"Sessione salvata in {cfg['session_file']}")
    browser.close()
