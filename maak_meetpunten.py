# -*- coding: utf-8 -*-
# DraveNavi - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""maak_meetpunten.py - maakt eenmalig (op de pc) een klein lijstje van alle NDW-meetpunten die snelheid meten.

Draai met: py -3.10 maak_meetpunten.py   ->  meetpunten.csv (id;lat;lon) naast dit script.
Meetpunten veranderen bijna nooit; af en toe opnieuw draaien is genoeg.
"""
import gzip
import os
import re
import urllib.request

URL = "https://opendata.ndw.nu/snelheden_en_intensiteiten_configuratie_meetlocaties.xml.gz"
data = gzip.decompress(urllib.request.urlopen(URL, timeout=120).read()).decode("utf-8", "replace")
stukken = data.split("<roa:measurementSite ")
uit, soorten = [], {}
for st in stukken[1:]:
    m = re.match(r'[^>]*id="([^"]+)"', st)
    if not m or "trafficSpeed" not in st:
        continue
    la = re.search(r"<loc:latitude>([-\d.]+)<", st)
    lo = re.search(r"<loc:longitude>([-\d.]+)<", st)
    if not la or not lo:
        continue
    sid = m.group(1)
    soorten[sid.split("_")[0]] = soorten.get(sid.split("_")[0], 0) + 1
    uit.append("%s;%.5f;%.5f" % (sid, float(la.group(1)), float(lo.group(1))))
pad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meetpunten.csv")
with open(pad, "w", encoding="utf-8") as f:
    f.write("\n".join(uit))
print("meetpunten met snelheid:", len(uit), "->", pad, os.path.getsize(pad) // 1024, "KB")
print("bronnen:", sorted(soorten.items(), key=lambda x: -x[1])[:12])
