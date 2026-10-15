# Agente prenotazione WeWork (oggi + 7 giorni, a mezzanotte) – GitHub Actions

Ogni mattina GitHub Actions lancia `book.py`, che riproduce la chiamata API di prenotazione
registrata una volta, con la data di oggi + 7 giorni (weekend esclusi). L'esito arriva come
notifica push sul telefono tramite l'app **ntfy**. Tutto gratuito e senza PC acceso.

## 1. Sul tuo PC (una volta)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

python save_session.py      # login manuale (SSO/MFA ok) -> storage_state.json
python record_booking.py    # prenoti a mano una volta -> booking_template.json
python book.py              # test locale (facoltativo)
```

## 2. Repository GitHub

1. Crea un repo **privato** (es. `wework-agent`) e fai push di questa cartella.
   `storage_state.json` e `booking_template.json` sono nel `.gitignore`: **non vanno committati**.
2. Installa la GitHub CLI e fai `gh auth login`.
3. Carica sessione e template come secret:
   ```bash
   python upload_secrets.py tuo-utente/wework-agent
   ```
   Lo script genera anche `SESSION_KEY`: a ogni run il workflow salva nel repo la sessione
   rinnovata, cifrata con quella chiave (`storage_state.enc`), così non scade. Nessun token personale serve.

## 3. Notifiche sul telefono (ntfy)

1. Installa l'app **ntfy** (iOS/Android) e iscriviti a un topic con un nome lungo e casuale
   (es. `wework-emi-8f3k29xq`): chiunque conosca il nome può leggere le notifiche.
2. `gh secret set NTFY_TOPIC -R tuo-utente/wework-agent` con quel nome.

## 4. Test e schedulazione

- Tab **Actions → Prenota WeWork → Run workflow** per provarlo subito.
- Poi parte da solo ogni notte alle 00:02 ora italiana (gestisce in automatico ora legale e solare).
  Per cambiare i giorni di anticipo modifica `days_ahead` in `config.yaml`.

## Notifiche che ricevi

✅ prenotato · ℹ️ già prenotato · ⚠️ sessione scaduta · ❌ errore.
Con ⚠️: rilancia `save_session.py` sul PC e poi `python upload_secrets.py ...`.

## Limiti da sapere

- I cron di GitHub possono partire con qualche minuto (a volte di più) di ritardo.
- WeWork potrebbe trattare diversamente una sessione usata da IP di data center:
  se le prenotazioni falliscono con 401/403 anche subito dopo il login, è probabilmente questo.
- Se WeWork cambia API, rilancia `record_booking.py` e `upload_secrets.py`.
- Verifica termini d'uso WeWork e policy EY sull'automazione dell'account.
