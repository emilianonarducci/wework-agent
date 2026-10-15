"""Carica sessione e template come secret GitHub (compressi + base64).
Uso:  python upload_secrets.py tuo-utente/wework-agent
Richiede la GitHub CLI (gh) già autenticata: `gh auth login`."""
import base64
import gzip
import subprocess
import sys

MAX_SECRET = 48 * 1024  # limite GitHub per singolo secret

if len(sys.argv) != 2:
    sys.exit("Uso: python upload_secrets.py <owner>/<repo>")
repo = sys.argv[1]

for name, path in (("STORAGE_STATE_GZ_B64", "storage_state.json"),
                   ("BOOKING_TEMPLATE_GZ_B64", "booking_template.json")):
    value = base64.b64encode(gzip.compress(open(path, "rb").read())).decode()
    if len(value) > MAX_SECRET:
        sys.exit(f"{path} è troppo grande per un secret ({len(value)} byte): scrivimi e lo riduciamo.")
    subprocess.run(["gh", "secret", "set", name, "-R", repo], input=value.encode(), check=True)
    print(f"✓ {name} impostato ({len(value)} byte)")

# Chiave per cifrare la sessione rinnovata salvata nel repo: generata qui, mai mostrata
existing = subprocess.run(["gh", "secret", "list", "-R", repo], capture_output=True, text=True).stdout
if "SESSION_KEY" not in existing:
    import secrets as _s
    subprocess.run(["gh", "secret", "set", "SESSION_KEY", "-R", repo],
                   input=_s.token_urlsafe(32).encode(), check=True)
    print("✓ SESSION_KEY generata e impostata")

# Dice al workflow di usare la sessione appena caricata invece di quella salvata nel repo
subprocess.run(["git", "pull", "-q"], check=False)
open(".session_source", "w").write("secret\n")
subprocess.run(["git", "add", ".session_source"], check=True)
if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
    subprocess.run(["git", "commit", "-qm", "Nuova sessione caricata"], check=True)
    subprocess.run(["git", "push", "-q"], check=True)
print("✓ Workflow impostato per usare la nuova sessione")
