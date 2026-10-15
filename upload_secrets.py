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

print("\nOra imposta anche:")
print(f"  gh secret set NTFY_TOPIC -R {repo}   # il topic ntfy scelto")
print(f"  gh secret set GH_PAT -R {repo}       # token GitHub con permesso Secrets: read and write")
