"""Corregge un booking_template.json già registrato sostituendo la data
(in formato YYYY-MM-DD e MM/DD/YYYY) con i segnaposto usati da book.py.
Uso:  python fix_template.py 2026-10-16"""
import json
import sys

import yaml

if len(sys.argv) != 2:
    sys.exit("Uso: python fix_template.py <data registrata YYYY-MM-DD>")
iso = sys.argv[1]
y, m, d = iso.split("-")
us = f"{m}/{d}/{y}"

cfg = yaml.safe_load(open("config.yaml"))
path = cfg["template_file"]
tpl = json.load(open(path))
for key in ("url", "body"):
    tpl[key] = tpl[key].replace(iso, "{{DATE}}").replace(us, "{{DATE_US}}")
json.dump(tpl, open(path, "w"), indent=2, ensure_ascii=False)

n = (tpl["url"] + tpl["body"]).count("{{DATE")
print(f"Segnaposto data inseriti: {n}")
if n == 0:
    sys.exit("Nessuna data trovata nel template: controlla la data passata.")
