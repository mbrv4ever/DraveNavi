# -*- coding: utf-8 -*-
# DraveNavi - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""wandel.py - Wandelen (bijvoorbeeld met de hond): je route bijhouden, Leon zegt hoe ver je bent, en een boekje
met al je wandelingen (per week en per maand).

De wandelingen staan in DraveNavi-data/wandelingen.json, op je eigen telefoon.
"""
import json
import math
import os
import time

import pygame

import geo

PAARS = (154, 90, 230)
PAARS_D = (60, 36, 110)
GEEL = (255, 222, 60)
ZILVER = (226, 226, 236)
GRIJS = (154, 150, 170)
ZWART = (10, 8, 16)
PANEEL = (24, 18, 42)
ROOD = (200, 58, 58)
GROEN = (70, 200, 110)
SPOOR = (255, 150, 30)

DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
           "november", "december"]


def afstand(a, b):
    """Meters tussen twee (lat, lon)-punten."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def km_tekst(m):
    km = m / 1000.0
    return ("%.1f km" % km).replace(".", ",") if km < 10 else "%d km" % round(km)


def duur_tekst(sec):
    sec = int(sec)
    u, m = sec // 3600, (sec % 3600) // 60
    return "%d uur %d min" % (u, m) if u else "%d min" % m


def km_clip(m):
    """De Leon-clip voor een halve of hele kilometer (tot 10 km)."""
    halven = int(round(m / 500.0))
    if 1 <= halven <= 20:
        return "w_km%d" % halven
    return None


def ontstekel(pts):
    """Haalt de 'stekels' uit een spoor: de GPS springt soms even weg en weer terug (heen-en-weer-lijntjes).
    Een punt waar het spoor scherp omkeert (de route erlangs is veel langer dan de rechte weg) gaat eruit."""
    pts = [p for p in pts if p and len(p) >= 2]
    for _ in range(4):
        if len(pts) < 3:
            break
        uit = [pts[0]]
        weg = 0
        for i in range(1, len(pts) - 1):
            a, b, c = uit[-1], pts[i], pts[i + 1]
            d1, d2, d13 = afstand(a, b), afstand(b, c), afstand(a, c)
            if d1 > 12 and d2 > 12 and d13 < 0.45 * (d1 + d2):    # scherp heen en terug: een stekel
                weg += 1
                continue
            uit.append(b)
        uit.append(pts[-1])
        pts = uit
        if not weg:
            break
    return pts


def spoor_meters(pts):
    return sum(afstand(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


# ------------------------------------------------------------------ opslag
def laad(self):
    if not hasattr(self, "wandelingen"):
        try:
            with open(os.path.join(self.data, "wandelingen.json"), encoding="utf-8") as f:
                self.wandelingen = json.load(f)
        except Exception:
            self.wandelingen = []
        veranderd = False
        for w in self.wandelingen:                    # oude wandelingen één keer opschonen (versie 1.0.1)
            if not w.get("schoon") and len(w.get("punten", [])) > 2:
                w["punten"] = ontstekel(w["punten"])
                m = spoor_meters(w["punten"])
                if m < w.get("meters", 0):
                    w["meters"] = round(m)
                w["schoon"] = 1
                veranderd = True
        if veranderd:
            bewaar_wandelingen(self)
    return self.wandelingen


def bewaar_wandelingen(self):
    try:
        with open(os.path.join(self.data, "wandelingen.json"), "w", encoding="utf-8") as f:
            json.dump(self.wandelingen, f)
    except Exception:
        pass


def maat_naam(self):
    n = (self.inst.get("hond") or "").strip()
    return ("Wandelen met " + n) if n else "Wandelen"


# ------------------------------------------------------------------ wandelen
def start_wandeling(self):
    laad(self)
    self.wandeling = dict(start=time.time(), meters=0.0, punten=[], laatst=None, gezegd=0, stop_vraag=0, t=time.time())
    p = self.plek()
    if p:
        self.wandeling["punten"].append([round(p[0], 6), round(p[1], 6)])
        self.wandeling["laatst"] = p
    self.volg = True
    if self.zoom < 15:
        self.zoom = 16
        self._route_px = None
    self.stem.zeg("w_start", voorrang=True)
    self.naar("wandel")


def _log(self, regel):
    """Logboekje van de GPS tijdens het wandelen (DraveNavi-data/wandel_log.csv), om fouten te kunnen vinden.
    Hoogstens 1 regel per 2 seconden; na 2 MB begint hij opnieuw."""
    try:
        import os
        nu = time.time()
        if nu - getattr(self, "_log_t", 0) < 2:
            return
        self._log_t = nu
        pad = os.path.join(self.data, "wandel_log.csv")
        if not os.path.exists(pad) or os.path.getsize(pad) > 2_000_000:
            with open(pad, "w", encoding="utf-8") as f:
                f.write("tijd;lat;lon;nauwkeurig;meters\n")
        with open(pad, "a", encoding="utf-8") as f:
            f.write(regel + "\n")
    except Exception:
        pass


def wandel_update(self):
    w = getattr(self, "wandeling", None)
    if not w:
        return
    p = self.plek()
    if not p or self.gps.oud() > 15:
        return
    nauw = self.gps.nauwkeurig or 99
    _log(self, "%d;%.6f;%.6f;%.0f;%.0f" % (time.time(), p[0], p[1], nauw, w["meters"]))
    # 1.0.4: grens was 25 m - tussen de huizen is de GPS vaak 25-40 m nauwkeurig, dan telde er NIETS (29-10-2026)
    if nauw > 45 and not self.gps.demo:               # te onnauwkeurig: niet meetellen
        return
    # het gemiddelde van de laatste metingen (de goede tellen zwaarder): dat haalt het meeste gewiebel eruit
    nu_t = time.time()
    ruw = [r for r in w.setdefault("ruw", []) if nu_t - r[3] < 10] + [(p[0], p[1], max(3.0, nauw), nu_t)]
    w["ruw"] = ruw[-6:]
    if not self.gps.demo:
        g = [1.0 / (r[2] * r[2]) for r in w["ruw"]]
        p = (sum(r[0] * k for r, k in zip(w["ruw"], g)) / sum(g), sum(r[1] * k for r, k in zip(w["ruw"], g)) / sum(g))
    if w["laatst"] is None:
        w["laatst"] = p
        w["punten"].append([round(p[0], 6), round(p[1], 6)])
        return
    d = afstand(w["laatst"], p)
    drempel = max(8.0, min(20.0, nauw * 0.8))       # kleine sprongetjes van de GPS tellen niet
    if d >= drempel:
        tussen = max(1.0, time.time() - w.get("t", 0))
        tempo = d / tussen
        if tempo > 3.0 and tussen < 30 and not self.gps.demo:   # te snel voor lopen: een sprong van de GPS, overslaan
            return
        if tempo > 3.5 and not self.gps.demo:          # lang weg en heel ver: opnieuw beginnen vanaf hier
            w["laatst"], w["t"] = p, time.time()
            return
        # was de app even weg (telefoon op slot)? dan telt het rechte stuk ertussen mee
        w["t"] = time.time()
        w["meters"] += d
        w["laatst"] = p
        w["punten"].append([round(p[0], 6), round(p[1], 6)])
        self._spoor_px = None
        # Leon: elke halve kilometer
        halven = int(w["meters"] // 500)
        if halven > w["gezegd"]:
            w["gezegd"] = halven
            clip = km_clip(halven * 500)
            if clip:
                self.stem.zeg("w_je_hebt", clip, "w_gelopen")


def stop_wandeling(self):
    w = getattr(self, "wandeling", None)
    if not w:
        return
    nu = time.time()
    if nu - w.get("stop_vraag", 0) > 4:                 # eerst vragen: in je zak tik je zo per ongeluk ergens op
        w["stop_vraag"] = nu
        self.meld("Tik nog een keer op Stop om de wandeling te bewaren.", 4)
        return
    laad(self)
    self.wandeling = None
    sec = nu - w["start"]
    if w["meters"] >= 50:
        pts = ontstekel(w["punten"])
        w["meters"] = min(w["meters"], spoor_meters(pts)) if len(pts) > 1 else w["meters"]
        if len(pts) > 2500:                            # niet te groot bewaren
            stap = len(pts) / 2500.0
            pts = [pts[int(i * stap)] for i in range(2500)] + [pts[-1]]
        self.wandelingen.insert(0, dict(start=w["start"], sec=round(sec), meters=round(w["meters"]), punten=pts, schoon=1))
        bewaar_wandelingen(self)
        self.stem.zeg("w_klaar", voorrang=True)
        self.meld("Lekker gewandeld! %s in %s." % (km_tekst(w["meters"]), duur_tekst(sec)), 6)
        self.kijk = self.wandelingen[0]
        self._spoor_px = None
        self.naar("wandelingen")
    else:
        self.meld("Wandeling gestopt (te kort om te bewaren).", 4)
        self.naar("kaart")


# ------------------------------------------------------------------ tekenen
def teken_spoor(self, ox, oy):
    """Het oranje spoor van de wandeling (bezig of bekijken) op de kaart."""
    w = getattr(self, "wandeling", None)
    pts = w["punten"] if w else ((getattr(self, "kijk", None) or {}).get("punten") if self.scherm in ("wandelingen", "wandel_kijk") else None)
    if not pts or len(pts) < 2:
        return
    sl = (self.zoom, len(pts), id(pts))
    if getattr(self, "_spoor_px", None) is None or self._spoor_px[0] != sl:
        self._spoor_px = (sl, [geo.naar_pixel(a, b, self.zoom) for a, b in ontstekel(pts)])
    xy = [(x + ox, y + oy) for x, y in self._spoor_px[1]]
    pygame.draw.lines(self.venster, (40, 20, 0), False, xy, 14)
    pygame.draw.lines(self.venster, SPOOR, False, xy, 8)
    pygame.draw.circle(self.venster, ZWART, (int(xy[0][0]), int(xy[0][1])), 12)
    pygame.draw.circle(self.venster, GROEN, (int(xy[0][0]), int(xy[0][1])), 8)


def knop_op_kaart(self, x, y, w):
    """De knop 'Wandelen' op het kaartscherm (alleen bij Lopen)."""
    self.knop((x, y, w, 70), maat_naam(self), lambda: start_wandeling(self), kleur=(90, 50, 10), rand=SPOOR,
              font=self.f_mid if self.f_mid.size(maat_naam(self))[0] > w - 30 else self.f)


def scherm_wandel(self):
    v = self.venster
    W, H = self.W, self.H
    w = getattr(self, "wandeling", None)
    if not w:
        self.naar("kaart")
        return
    liggend = W > H
    sec = time.time() - w["start"]
    if liggend:
        P = 400
        self.teken_kaart(pygame.Rect(P, 0, W - P, H), 0.5)
        paneel = pygame.Rect(0, 0, P, H)
    else:
        paneel = pygame.Rect(0, 0, W, 250)
        self.teken_kaart(pygame.Rect(0, paneel.bottom, W, H - paneel.bottom - 150), 0.5)
    pygame.draw.rect(v, PANEEL, paneel)
    if liggend:
        pygame.draw.line(v, SPOOR, (P, 0), (P, H), 4)
    else:
        pygame.draw.line(v, SPOOR, (0, paneel.bottom), (W, paneel.bottom), 4)
    self.tekst(maat_naam(self), self.f, SPOOR, 20, 18, max_b=paneel.w - 40)
    self.tekst(km_tekst(w["meters"]), self.f_reus, ZILVER, 20, 64)
    self.tekst(duur_tekst(sec), self.f_groot, GEEL, 20, 160)
    if sec > 60 and w["meters"] > 100:
        tempo = (sec / 60.0) / (w["meters"] / 1000.0)
        self.tekst("%d min per km" % round(tempo), self.f_klein, GRIJS, paneel.w - 20 if not liggend else 20,
                   178 if not liggend else 222, rechts=not liggend)
    if self.gps.oud() > 15:
        self.tekst("GPS-signaal kwijt", self.f, ROOD, 20, 262 if liggend else paneel.bottom + 14)
    vraag = time.time() - w.get("stop_vraag", 0) < 4
    if liggend:
        self.knop((16, H - 118, P - 32, 100), "Nog een keer: stop" if vraag else "Stop", lambda: stop_wandeling(self),
                  kleur=ROOD, rand=GEEL if vraag else ZILVER)
        zoom_knoppen(self, W - 100, H - 16)
    else:
        onder = pygame.Rect(0, H - 150, W, 150)
        pygame.draw.rect(v, PANEEL, onder)
        pygame.draw.line(v, PAARS, (0, onder.y), (W, onder.y), 3)
        self.knop((16, onder.y + 22, W - 32, 106), "Tik nog een keer: stoppen" if vraag else "Stop de wandeling",
                  lambda: stop_wandeling(self), kleur=ROOD, rand=GEEL if vraag else ZILVER,
                  font=self.f if vraag else self.f_groot)
        zoom_knoppen(self, W - 100, onder.y - 16)


def zoom_knoppen(self, x, onderkant):
    v = self.venster
    self.knop((x, onderkant - 270, 84, 84), "+", lambda: self.wissel_zoom(self.zoom + 1), kleur=PANEEL, font=self.f_groot)
    self.knop((x, onderkant - 176, 84, 84), "-", lambda: self.wissel_zoom(self.zoom - 1), kleur=PANEEL, font=self.f_groot)
    self.knop((x, onderkant - 82, 84, 76), "", lambda: self.volg_mij(), kleur=GEEL if self.volg else PANEEL)
    r = self.knoppen[-1][0]
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 18, 5)
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 6)


def _week_maand(lijst):
    nu = time.localtime()
    begin_week = time.mktime((nu.tm_year, nu.tm_mon, nu.tm_mday - nu.tm_wday, 0, 0, 0, 0, 0, -1))
    begin_maand = time.mktime((nu.tm_year, nu.tm_mon, 1, 0, 0, 0, 0, 0, -1))
    week = sum(x["meters"] for x in lijst if x["start"] >= begin_week)
    maand = sum(x["meters"] for x in lijst if x["start"] >= begin_maand)
    return week, maand, sum(x["meters"] for x in lijst)


def datum_tekst(t):
    lt = time.localtime(t)
    vandaag = time.localtime()
    if lt.tm_yday == vandaag.tm_yday and lt.tm_year == vandaag.tm_year:
        dag = "Vandaag"
    elif time.time() - t < 6 * 86400:
        dag = DAGEN[lt.tm_wday].capitalize()
    else:
        dag = "%d %s" % (lt.tm_mday, MAANDEN[lt.tm_mon - 1])
    return "%s %s" % (dag, time.strftime("%H:%M", lt))


def scherm_wandelingen(self):
    """Het wandelboekje: totalen en de lijst; de gekozen wandeling staat op het kaartje."""
    v = self.venster
    W, H = self.W, self.H
    lijst = laad(self)
    liggend = W > H
    self.knop((16, 16, 140, 72), "Terug", lambda: self.naar("kaart"), kleur=PANEEL)
    self.tekst("Wandelingen", self.f_groot, ZILVER, 176, 28)
    week, maand, alles = _week_maand(lijst)
    y = 104
    for label, m in (("Deze week", week), ("Deze maand", maand), ("Alles samen", alles)):
        self.tekst(label, self.f_klein, GRIJS, 20, y + 6)
        if liggend:
            self.tekst(km_tekst(m), self.f, GEEL, W // 2 - 24, y, rechts=True)
        else:
            self.tekst(km_tekst(m), self.f, GEEL, 260, y)
        y += 40
    if not lijst:
        self.tekst("Nog geen wandelingen.", self.f, ZILVER, 20, y + 20)
        for i, r in enumerate(self.breek("Kies Lopen op het kaartscherm en tik op %s." % maat_naam(self), self.f_klein, W - 40)):
            self.tekst(r, self.f_klein, GRIJS, 20, y + 70 + i * 30)
        return
    kijk = getattr(self, "kijk", None)
    if kijk not in lijst:
        kijk = self.kijk = lijst[0]
    # kaartje van de gekozen wandeling
    if liggend:
        gebied = pygame.Rect(W // 2, 104, W // 2 - 16, H - 120)
        lx, lb, ly = 16, W // 2 - 32, y + 10
    else:
        gebied = pygame.Rect(16, y + 6, W - 32, 330)
        lx, lb, ly = 16, W - 32, gebied.bottom + 14
    if kijk.get("punten"):
        _passend(self, kijk["punten"], gebied)
        oude_volg = self.volg
        self.volg = False
        self.teken_kaart(gebied, 0.5)
        self.volg = oude_volg
        pygame.draw.rect(v, SPOOR, gebied, 3, border_radius=4)
    # de lijst
    rij_h = 76
    plek = max(1, (H - ly - 10) // (rij_h + 8))
    start = getattr(self, "lijst_begin", 0)
    start = max(0, min(start, len(lijst) - plek))
    self.lijst_begin = start
    for x in lijst[start:start + plek]:
        gekozen = x is kijk
        r = (lx, ly, lb, rij_h)
        self.knop(r, "", lambda x=x: _kies(self, x), kleur=PAARS_D if gekozen else PANEEL, rand=SPOOR if gekozen else PAARS)
        self.tekst(datum_tekst(x["start"]), self.f_mid, ZILVER, lx + 16, ly + 10)
        self.tekst("%s  ·  %s" % (km_tekst(x["meters"]), duur_tekst(x["sec"])), self.f_klein, GEEL, lx + 16, ly + 44)
        ly += rij_h + 8
    if len(lijst) > plek:
        if start > 0:
            self.knop((lx + lb - 150, 104, 70, 60), "▲", lambda: setattr(self, "lijst_begin", start - plek), kleur=PANEEL)
        if start + plek < len(lijst):
            self.knop((lx + lb - 70, 104, 70, 60), "▼", lambda: setattr(self, "lijst_begin", start + plek), kleur=PANEEL)


def _kies(self, x):
    self.kijk = x
    self._spoor_px = None
    self._passend = None


def _passend(self, pts, gebied):
    """Zoom en midden zo kiezen dat de hele wandeling in het kaartje past."""
    sl = (id(pts), gebied.w, gebied.h)
    if getattr(self, "_passend", None) == sl:
        return
    self._passend = sl
    la = [p[0] for p in pts]
    lo = [p[1] for p in pts]
    for z in range(18, 9, -1):
        x0, y0 = geo.naar_pixel(max(la), min(lo), z)
        x1, y1 = geo.naar_pixel(min(la), max(lo), z)
        if x1 - x0 < gebied.w - 40 and y1 - y0 < gebied.h - 40:
            break
    self.zoom = z
    self._route_px = None
    self._spoor_px = None
    self.midden = ((x0 + x1) / 2, (y0 + y1) / 2)


# ------------------------------------------------------------------ naam van je hond (of maatje)
def naar_naam(self):
    self.naamtekst = self.inst.get("hond", "")
    self.naar("naam")
    self.toetsenbord()


def bewaar_naam(self):
    self.inst["hond"] = self.naamtekst.strip()[:20]
    self.bewaar()
    try:
        pygame.key.stop_text_input()
    except Exception:
        pass
    self.meld("Opgeslagen: %s" % maat_naam(self), 3)
    self.naar("instel")


def scherm_naam(self):
    W = self.W
    self.knop((16, 16, 140, 72), "Terug", lambda: self.naar("instel"), kleur=PANEEL)
    self.tekst("Naam van je hond", self.f, ZILVER, 176, 34)
    for i, r in enumerate(self.breek("Wandel je met je hond? Typ de naam, dan staat er bijvoorbeeld 'Wandelen met Max'. "
                                     "Leeg laten mag ook.", self.f_klein, W - 40)):
        self.tekst(r, self.f_klein, GRIJS, 20, 108 + i * 30)
    veld = pygame.Rect(16, 210, W - 32, 84)
    pygame.draw.rect(self.venster, (250, 250, 255), veld, border_radius=12)
    pygame.draw.rect(self.venster, GEEL, veld, 4, border_radius=12)
    knipper = "|" if int(time.time() * 2) % 2 else ""
    self.tekst(self.naamtekst + knipper, self.f_groot, ZWART, veld.x + 16, veld.y + 18, max_b=veld.w - 30)
    self.knoppen.append((veld, lambda: self.toetsenbord()))
    self.knop((16, 316, (W - 44) // 2, 86), "Opslaan", lambda: bewaar_naam(self), kleur=PAARS, rand=GEEL, tekstkleur=ZWART)
    self.knop((28 + (W - 44) // 2, 316, (W - 44) // 2, 86), "Leeg maken", lambda: setattr(self, "naamtekst", ""), kleur=PANEEL)
