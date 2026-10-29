# -*- coding: utf-8 -*-
# DraveNavi - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""verkeer.py - live verkeersinformatie van NDW (open data van de Nederlandse overheid, gratis).

Elke paar minuten halen we 'actueel_beeld' op: wegwerkzaamheden, afsluitingen en obstakels
(pijlwagens, pech, ongelukken). Daarna kijken we welke berichten op jouw route liggen.
"""
import gzip
import math
import re
import threading
import time
from datetime import datetime, timezone

import geo
import netwerk

URL = "https://opendata.ndw.nu/actueel_beeld.xml.gz"
CEL = 0.0006          # ~50-65 m: rastergrootte om snel te zien of iets op de route ligt

_RECORD = re.compile(r'<sit:situationRecord xsi:type="sit:(\w+)"(.*?)</sit:situationRecord>', re.S)


def _tijd(t):
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")[:26] + ("+00:00" if "Z" in t else "")).timestamp()
    except Exception:
        try:
            return datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return None


def lees(xml, nu=None):
    """XML -> lijst berichten: dict(soort, tekst, punten[(lat, lon)], eind)."""
    nu = nu or time.time()
    uit = []
    for m in _RECORD.finditer(xml):
        xtype, body = m.group(1), m.group(2)
        eind = re.search(r"<com:overallEndTime>([^<]+)<", body)
        begin = re.search(r"<com:overallStartTime>([^<]+)<", body)
        if eind and (_tijd(eind.group(1)) or 1e18) < nu:
            continue
        if begin and (_tijd(begin.group(1)) or 0) > nu + 600:
            continue                                    # begint pas later
        punten = []
        for pl in re.findall(r"<loc:posList>([^<]+)<", body):
            getallen = [float(x) for x in pl.split()]
            for i in range(0, len(getallen) - 1, 2):
                punten.append((getallen[i], getallen[i + 1]))
        for la, lo in re.findall(r"<loc:latitude>([-\d.]+)</loc:latitude>\s*<loc:longitude>([-\d.]+)<", body):
            punten.append((float(la), float(lo)))
        if not punten:
            continue
        if punten and abs(punten[0][0]) < 10 and abs(punten[0][1]) > 40:    # lon/lat omgedraaid? dan wisselen
            punten = [(b, a) for a, b in punten]
        oorzaak = (re.search(r"<sit:causeType>(\w+)<", body) or [None, ""])[1]
        beheer = (re.search(r"<sit:roadOrCarriagewayOrLaneManagementType>(\w+)<", body) or [None, ""])[1]
        obstakel = (re.search(r"<sit:vehicleObstructionType>(\w+)<", body) or [None, ""])[1]
        tekst = " ".join(re.findall(r'<com:value lang="nl">([^<]{3,120})</com:value>', body)[1:3])
        if xtype == "Accident" or oorzaak == "accident":
            soort = "ongeluk"
        elif beheer in ("roadClosed", "carriagewayClosures") or xtype == "ReroutingManagement":
            soort = "dicht"
        elif xtype in ("VehicleObstruction", "GeneralObstruction", "AnimalPresenceObstruction"):
            soort = "obstakel"
        elif xtype in ("AbnormalTraffic",):
            soort = "file"
        elif oorzaak in ("roadMaintenance", "roadworks", "constructionWork") or xtype in ("RoadOrCarriagewayOrLaneManagement",
                                                                                         "MaintenanceWorks", "ConstructionWorks"):
            soort = "werk"
        else:
            continue
        uit.append(dict(soort=soort, tekst=tekst, punten=punten[:60], obstakel=obstakel, beheer=beheer))
    return uit


class Verkeer:
    def __init__(self):
        self.berichten = []
        self.tijd = 0
        self.fout = None
        self.bezig = False

    def ververs(self, elke=300):
        if self.bezig or time.time() - self.tijd < elke:
            return
        self.bezig = True
        threading.Thread(target=self._haal, daemon=True).start()

    def _haal(self):
        try:
            data = gzip.decompress(netwerk.haal(URL, tijd=30)).decode("utf-8", "replace")
            self.berichten = lees(data)
            self.fout = None
        except Exception as e:
            self.fout = str(e)
        self.tijd = time.time()
        self.bezig = False

    def op_route(self, route, vanaf_m=0.0, marge_m=45):
        """Berichten die op het nog komende stuk van de route liggen -> [(meters vanaf begin, bericht)]."""
        if not route or not self.berichten:
            return []
        cellen = {}
        for i in range(len(route.punten) - 1):
            if route.cum[i + 1] < vanaf_m:
                continue
            a, b = route.punten[i], route.punten[i + 1]
            n = max(1, int(geo.afstand(a, b) / 30))
            for k in range(n + 1):
                la = a[0] + (b[0] - a[0]) * k / n
                lo = a[1] + (b[1] - a[1]) * k / n
                c = (int(la / CEL), int(lo / CEL))
                if c not in cellen:
                    cellen[c] = route.cum[i] + (route.cum[i + 1] - route.cum[i]) * k / n
        if not cellen:
            return []
        uit = []
        for b in self.berichten:
            beste = None
            for p in b["punten"]:
                c0, c1 = int(p[0] / CEL), int(p[1] / CEL)
                for dc in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                    m = cellen.get((c0 + dc[0], c1 + dc[1]))
                    if m is not None and (beste is None or m < beste):
                        beste = m
            if beste is not None and beste >= vanaf_m - 20:
                uit.append((beste, b))
        uit.sort(key=lambda x: x[0])
        return uit


def vermijd_vlakken(berichten, max_aantal=12):
    """Afsluitingen -> kleine vierkantjes die openrouteservice moet vermijden (GeoJSON MultiPolygon)."""
    vlakken = []
    for _, b in berichten:
        if b["soort"] != "dicht":
            continue
        p = b["punten"][len(b["punten"]) // 2]
        d = 0.00045
        vlakken.append([[[p[1] - d, p[0] - d], [p[1] + d, p[0] - d], [p[1] + d, p[0] + d], [p[1] - d, p[0] + d],
                          [p[1] - d, p[0] - d]]])
        if len(vlakken) >= max_aantal:
            break
    return {"type": "MultiPolygon", "coordinates": vlakken} if vlakken else None


# ------------------------------------------------------------------ files (uit de snelheidsmetingen langs de weg)
SNEL_URL = "https://opendata.ndw.nu/snelheden_en_intensiteiten_meetgegevens.xml.gz"
CEL_FIJN = 0.00015    # ~15 m: zo fijn dat we de rijbaan van de andere kant niet meetellen
LANGZAAM = 35         # km/u: lager = file (alleen op wegen waar je normaal harder rijdt)


def lees_meetpunten(pad):
    punten = {}
    try:
        with open(pad, encoding="utf-8") as f:
            for regel in f:
                d = regel.strip().split(";")
                if len(d) == 3:
                    punten[d[0]] = (float(d[1]), float(d[2]))
    except Exception:
        pass
    return punten


def lees_snelheden(gzbytes, gezocht):
    """Leest de grote meetgegevens in stukjes; alleen de meetpunten in 'gezocht' -> {id: km/u}."""
    import io
    uit = {}
    rest = ""
    sp = re.compile(r"<com:speed>([-\d.]+)<")
    with gzip.GzipFile(fileobj=io.BytesIO(gzbytes)) as g:
        while True:
            brok = g.read(2 * 1024 * 1024)
            tekst = rest + (brok.decode("utf-8", "replace") if brok else "")
            delen = tekst.split("<roa:siteMeasurements>")
            rest = delen.pop() if brok else ""
            for d in delen if brok else delen + [rest]:
                i = d.find('id="')
                if i < 0:
                    continue
                sid = d[i + 4:d.find('"', i + 4)]
                if sid in gezocht:
                    v = [float(x) for x in sp.findall(d)]
                    v = [x for x in v if 0 < x < 250]
                    if v:
                        uit[sid] = sum(v) / len(v)
            if not brok:
                break
    return uit


class Files:
    """Kijkt elke paar minuten of er op de meetpunten langs jouw route bijna niemand doorrijdt."""

    def __init__(self, meetpunten_pad):
        self.pad = meetpunten_pad
        self.meetpunten = None
        self.langs_route = []        # [(meters vanaf begin, id)] voor de huidige route
        self.route_id = None
        self.files = []              # [(begin m, eind m, km/u)]
        self.tijd = 0
        self.bezig = False
        self.fout = None

    def zet_route(self, route):
        if self.meetpunten is None:
            self.meetpunten = lees_meetpunten(self.pad)
        if id(route) == self.route_id:
            return
        self.route_id = id(route)
        cellen = {}
        for i in range(len(route.punten) - 1):
            a, b = route.punten[i], route.punten[i + 1]
            n = max(1, int(geo.afstand(a, b) / 8))
            for k in range(n + 1):
                la = a[0] + (b[0] - a[0]) * k / n
                lo = a[1] + (b[1] - a[1]) * k / n
                c = (int(la / CEL_FIJN), int(lo / CEL_FIJN))
                if c not in cellen:
                    cellen[c] = route.cum[i] + (route.cum[i + 1] - route.cum[i]) * k / n
        lijst = []
        for sid, (la, lo) in self.meetpunten.items():
            m = cellen.get((int(la / CEL_FIJN), int(lo / CEL_FIJN)))
            if m is not None:
                lijst.append((m, sid))
        self.langs_route = sorted(lijst)
        self.files = []
        self.tijd = 0

    def ververs(self, elke=180):
        if self.bezig or not self.langs_route or time.time() - self.tijd < elke:
            return
        self.bezig = True
        threading.Thread(target=self._haal, daemon=True).start()

    def _haal(self):
        try:
            gezocht = {sid for _, sid in self.langs_route}
            snel = lees_snelheden(netwerk.haal(SNEL_URL, tijd=40), gezocht)
            traag = [(m, snel[sid]) for m, sid in self.langs_route if sid in snel and snel[sid] < LANGZAAM]
            files = []
            for m, v in traag:                     # minstens 2 trage meetpunten binnen 1,5 km = file
                if files and m - files[-1][1] < 1500:
                    files[-1] = [files[-1][0], m, min(files[-1][2], v), files[-1][3] + 1]
                else:
                    files.append([m, m, v, 1])
            self.files = [(a, b, v) for a, b, v, n in files if n >= 2]
            self.fout = None
        except Exception as e:
            self.fout = str(e)
        self.tijd = time.time()
        self.bezig = False
