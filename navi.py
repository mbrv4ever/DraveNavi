# -*- coding: utf-8 -*-
# DraveNavi - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""navi.py - DraveNavi: navigeren met grote pijlen, veel contrast en Leon die praat.

Schermen: kaart (waar ben ik), zoeken (waar wil ik heen), nav (onderweg), instellingen.
Lopen, fietsen en auto. Routes via openrouteservice (met sleutel) of de gratis OSRM-testserver.
"""
import io
import json
import math
import os
import sys
import time

import pygame

import geo
import gps as gpsmod
import netwerk
import verkeer
import wandel

VERSIE = "1.0.4"
ANDROID = gpsmod.ANDROID
HIER = os.path.dirname(os.path.abspath(__file__))

ZWART = (10, 8, 16)
PANEEL = (24, 18, 38)
PAARS = (150, 90, 230)
PAARS_D = (70, 40, 120)
ZILVER = (226, 226, 236)
GRIJS = (140, 136, 156)
GEEL = (255, 222, 60)
ROOD = (220, 60, 60)
GROEN = (70, 200, 110)
ROUTE = (190, 120, 255)

VERVOER = [("lopen", "Lopen"), ("fietsen", "Fiets"), ("auto", "Auto")]
DREMPELS = {"lopen": (150, 50, 15), "fietsen": (300, 100, 30), "auto": (800, 300, 80)}
AFWIJK = {"lopen": 30, "fietsen": 40, "auto": 55}
ZOOM_NAV = {"lopen": 17, "fietsen": 16, "auto": 16}
AFSTAND_CLIPS = [(50, "m50"), (100, "m100"), (200, "m200"), (300, "m300"), (400, "m400"), (500, "m500"),
                 (800, "m800"), (1000, "km1"), (2000, "km2"), (5000, "km5")]
SOORT_CLIP = {0: "links", 1: "rechts", 2: "scherp_links", 3: "scherp_rechts", 4: "flauw_links", 5: "flauw_rechts",
              6: "rechtdoor", 9: "omkeren", 10: "bestemming", 12: "houd_links", 13: "houd_rechts"}
SOORT_TEKST = {0: "Linksaf", 1: "Rechtsaf", 2: "Scherp linksaf", 3: "Scherp rechtsaf", 4: "Flauw links",
               5: "Flauw rechts", 6: "Rechtdoor", 7: "Rotonde", 9: "Keer om", 10: "Bestemming",
               12: "Links aanhouden", 13: "Rechts aanhouden"}


def data_map():
    if ANDROID:
        basis = os.environ.get("ANDROID_PRIVATE") or HIER
    else:
        basis = HIER                      # pc: naast de app (D:), niet op C:
    p = os.path.join(basis, "DraveNavi-data")
    os.makedirs(p, exist_ok=True)
    return p


def lees_sleutel(data):
    """De openrouteservice-sleutel: sleutel.txt in de app-map, of (telefoon) in Android/data/.../files."""
    plekken = [os.path.join(data, "sleutel.txt"), os.path.join(HIER, "sleutel.txt")]
    if ANDROID:
        try:
            from jnius import autoclass
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            plekken.insert(0, os.path.join(act.getExternalFilesDir(None).getAbsolutePath(), "sleutel.txt"))
        except Exception:
            pass
    for p in plekken:
        try:
            with open(p, encoding="utf-8") as f:
                s = f.read().strip()
            if len(s) > 20:
                return s
        except Exception:
            pass
    return ""


def scherm_aan_houden():
    if not ANDROID:
        return
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        @run_on_ui_thread
        def zet():
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            act.getWindow().addFlags(128)          # FLAG_KEEP_SCREEN_ON
        zet()
    except Exception:
        pass


class Stem:
    """Leon: vaste zinnetjes achter elkaar afspelen."""

    def __init__(self):
        self.aan = True
        self.clips = {}
        self.rij = []
        self.kanaal = None
        try:
            pygame.mixer.init(22050, -16, 1, 1024)
            map_ = os.path.join(HIER, "stem")
            for f in os.listdir(map_):
                if f.endswith(".wav"):
                    self.clips[f[:-4]] = pygame.mixer.Sound(os.path.join(map_, f))
        except Exception:
            self.clips = {}

    def zeg(self, *delen, voorrang=False):
        if not self.aan:
            return
        delen = [d for d in delen if d in self.clips]
        if voorrang:
            self.rij = []
            if self.kanaal:
                self.kanaal.stop()
        self.rij.extend(delen)

    def update(self):
        nu = time.time()
        if self.kanaal is not None and self.kanaal.get_busy():
            self.vrij = nu + 0.15                 # na elk stukje even ademhalen
            return
        if self.rij and nu >= getattr(self, "vrij", 0):
            self.kanaal = self.clips[self.rij.pop(0)].play()
            self.vrij = nu + 0.3


class Navi:
    def __init__(self):
        pygame.init()
        self.data = data_map()
        self.inst = {"stijl": "donker", "stem": True, "vervoer": "lopen", "recent": []}
        try:
            with open(os.path.join(self.data, "instellingen.json"), encoding="utf-8") as f:
                self.inst.update(json.load(f))
        except Exception:
            pass
        if ANDROID:
            info = pygame.display.Info()
            pw, ph = max(1, info.current_w), max(1, info.current_h)
            self.W = 540
            self.H = int(540 * max(pw, ph) / min(pw, ph))
            self.venster = pygame.display.set_mode((self.W, self.H), pygame.FULLSCREEN | pygame.SCALED)
        else:
            self.W, self.H = 540, 1040
            self.venster = pygame.display.set_mode((self.W, self.H))
        self.echt = self.venster                 # het echte (staande) scherm
        self.PW, self.PH = self.W, self.H
        self.lig = pygame.Surface((self.PH, self.PW)).convert()   # tekenvel voor liggend
        self.draai = int(self.inst.get("draai", 0))             # 0 = staand, 90 en 270 = liggend
        pygame.display.set_caption("DraveNavi")
        try:
            pygame.display.set_icon(pygame.image.load(os.path.join(HIER, "icon.png")))
        except Exception:
            pass
        fb = os.path.join(HIER, "assets", "DejaVuSans-Bold.ttf")
        fr = os.path.join(HIER, "assets", "DejaVuSans.ttf")
        self.f_reus = pygame.font.Font(fb, 70)
        self.f_groot = pygame.font.Font(fb, 40)
        self.f = pygame.font.Font(fb, 28)
        self.f_mid = pygame.font.Font(fb, 23)
        self.f_klein = pygame.font.Font(fr, 21)
        self.f_mini = pygame.font.Font(fr, 15)
        self.klok = pygame.time.Clock()
        self.stem = Stem()
        self.stem.aan = self.inst.get("stem", True)
        self.gps = gpsmod.Gps()
        self.tegels = netwerk.Tegels(os.path.join(self.data, "tegels"), self.inst.get("stijl", "donker"))
        self.plaatjes = {}
        self.planner = netwerk.Planner(lees_sleutel(self.data))
        self.verkeer = verkeer.Verkeer()
        self.files = verkeer.Files(os.path.join(HIER, "meetpunten.csv"))
        self.verkeer.ververs(0)                 # meteen ophalen, dan is het klaar voor de eerste route
        self.scherm = "kaart"
        self.zoom = 16
        self.midden = None             # wereldpixels (x, y) op self.zoom
        self.volg = True
        self.knoppen = []
        self.sleep = None
        self.zoektekst = ""
        self.resultaten = []
        self.bezig = None              # tekst als er iets berekend wordt
        self.melding = None            # (tekst, tot)
        self.route = None
        self.doel = None
        self.nav = {}
        self.tijd = 0.0
        self.stop = False
        self._route_px = None
        self.gps.start()
        scherm_aan_houden()
        self.stem.zeg("welkom")

    # ------------------------------------------------------------ hulp
    def bewaar(self):
        try:
            with open(os.path.join(self.data, "instellingen.json"), "w", encoding="utf-8") as f:
                json.dump(self.inst, f)
        except Exception:
            pass

    def meld(self, tekst, s=3.0):
        self.melding = (tekst, time.time() + s)

    def tekst(self, t, font, kleur, x, y, midden=False, rechts=False, max_b=None):
        if max_b:
            while font.size(t)[0] > max_b and len(t) > 3:
                t = t[:-4] + "..."
        img = font.render(t, True, kleur)
        r = img.get_rect()
        if midden:
            r.midtop = (x, y)
        elif rechts:
            r.topright = (x, y)
        else:
            r.topleft = (x, y)
        self.venster.blit(img, r)
        return r

    def knop(self, rect, label, actie, kleur=PAARS_D, rand=PAARS, font=None, tekstkleur=ZILVER):
        r = pygame.Rect(rect)
        pygame.draw.rect(self.venster, kleur, r, border_radius=14)
        pygame.draw.rect(self.venster, rand, r, 3, border_radius=14)
        if label:
            f = font or self.f
            img = f.render(label, True, tekstkleur)
            self.venster.blit(img, img.get_rect(center=r.center))
        self.knoppen.append((r, actie))
        return r

    @staticmethod
    def meters(m):
        if m >= 10000:
            return "%d km" % round(m / 1000)
        if m >= 1000:
            return ("%.1f km" % (m / 1000)).replace(".", ",")
        if m >= 100:
            return "%d m" % (round(m / 50) * 50)
        return "%d m" % max(0, round(m / 10) * 10)

    # ------------------------------------------------------------ kaart
    def plek(self):
        return self.gps.plek

    def zet_midden(self, lat, lon):
        self.midden = geo.naar_pixel(lat, lon, self.zoom)

    def wissel_zoom(self, nieuw):
        nieuw = max(5, min(20, nieuw))
        if self.midden:
            lat, lon = geo.van_pixel(self.midden[0], self.midden[1], self.zoom)
            self.zoom = nieuw
            self.zet_midden(lat, lon)
        else:
            self.zoom = nieuw
        self._route_px = None
        self.sleep_start = None

    def tegel_beeld(self, z, x, y):
        s = self.tegels.stijl
        k = (s, z, x, y)
        if k in self.plaatjes:
            return self.plaatjes[k]
        bron = ("osm", z, x, y)
        if bron in self.tegels.klaar:
            data = self.tegels.klaar.pop(bron)
            img = None
            if data:
                try:
                    img = pygame.image.load(io.BytesIO(data), "t.png").convert()
                    if s == "donker":        # rustiger voor de ogen: de kaart gedimd, met een paarse gloed
                        img.fill((160, 152, 178), special_flags=pygame.BLEND_MULT)
                except Exception:
                    img = None
            if img is not None:
                self.plaatjes[k] = img
                if len(self.plaatjes) > 120:
                    del self.plaatjes[next(iter(self.plaatjes))]
            return img
        self.tegels.vraag(z, x, y)
        return None

    def teken_kaart(self, gebied, vooruit=0.5):
        v = self.venster
        pygame.draw.rect(v, (26, 24, 34) if self.tegels.stijl == "donker" else (220, 220, 214), gebied)
        p = self.plek()
        if p and not getattr(self, "eerste_fix", False):      # eerste GPS-plek: inzoomen op jezelf
            self.eerste_fix = True
            if self.zoom < 13:
                self.zoom = 16
                self._route_px = None
        if self.volg and p:
            self.zet_midden(*p)
        if not self.midden:
            self.zet_midden(52.1, 5.3)
            self.zoom = 8
        cx, cy = self.midden
        ox = gebied.x + gebied.w / 2 - cx
        oy = gebied.y + gebied.h * vooruit - cy
        tz = min(18, self.zoom)                 # boven zoom 18: dezelfde tegels, maar groter getekend
        T = 256 * 2 ** (self.zoom - tz)
        n = 2 ** tz
        x0 = int(math.floor((cx - gebied.w / 2) / T))
        x1 = int(math.floor((cx + gebied.w / 2) / T))
        y0 = int(math.floor((cy - gebied.h * vooruit) / T))
        y1 = int(math.floor((cy + gebied.h * (1 - vooruit)) / T))
        oud = v.get_clip()
        v.set_clip(gebied)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if 0 <= ty < n:
                    img = self.tegel_beeld(tz, tx % n, ty)
                    sx, sy = tx * T + ox, ty * T + oy
                    if img and T != 256:
                        k = ("groot", T, tz, tx % n, ty, self.tegels.stijl)
                        grote = self.__dict__.setdefault("grote", {})
                        groot = grote.get(k)
                        if groot is None:
                            groot = pygame.transform.smoothscale(img, (T, T))
                            grote[k] = groot
                            if len(grote) > (24 if T == 512 else 10):
                                del grote[next(iter(grote))]
                        img = groot
                    if img:
                        v.blit(img, (sx, sy))
                    else:
                        pygame.draw.rect(v, (38, 34, 50) if self.tegels.stijl == "donker" else (200, 200, 196),
                                         (sx + 1, sy + 1, T - 2, T - 2))
        # route
        if self.route:
            if self._route_px is None or self._route_px[0] != self.zoom:
                self._route_px = (self.zoom, [geo.naar_pixel(a, b, self.zoom) for a, b in self.route.punten])
            pts = [(x + ox, y + oy) for x, y in self._route_px[1]]
            if len(pts) > 1:
                pygame.draw.lines(v, (30, 10, 50), False, pts, 16)
                pygame.draw.lines(v, ROUTE, False, pts, 10)
            if self.doel:
                dx, dy = geo.naar_pixel(self.doel[0], self.doel[1], self.zoom)
                self.vlag(v, dx + ox, dy + oy)
            for _, b in (self.nav or {}).get("verkeer", [])[:25]:
                q = b["punten"][len(b["punten"]) // 2]
                bx, by = geo.naar_pixel(q[0], q[1], self.zoom)
                self.verkeersteken(v, bx + ox, by + oy, b["soort"])
        wandel.teken_spoor(self, ox, oy)
        # jijzelf
        if p:
            px, py = geo.naar_pixel(p[0], p[1], self.zoom)
            px, py = px + ox, py + oy
            if self.gps.nauwkeurig and self.gps.nauwkeurig > 15:
                straal = self.gps.nauwkeurig / (40075016.0 * math.cos(math.radians(p[0])) / (256 * 2 ** self.zoom))
                if straal < 400:
                    s = pygame.Surface((int(straal * 2) + 2, int(straal * 2) + 2), pygame.SRCALPHA)
                    pygame.draw.circle(s, (255, 222, 60, 50), (int(straal) + 1, int(straal) + 1), int(straal))
                    v.blit(s, (px - straal, py - straal))
            if self.gps.koers is not None:
                h = math.radians(self.gps.koers)
                punt = [(px + math.sin(h) * 30, py - math.cos(h) * 30),
                        (px + math.sin(h + 2.5) * 18, py - math.cos(h + 2.5) * 18),
                        (px + math.sin(h - 2.5) * 18, py - math.cos(h - 2.5) * 18)]
                pygame.draw.polygon(v, ZWART, punt)
                pygame.draw.polygon(v, GEEL, [((a - px) * 0.8 + px, (b - py) * 0.8 + py) for a, b in punt])
            pygame.draw.circle(v, ZWART, (int(px), int(py)), 16)
            pygame.draw.circle(v, GEEL, (int(px), int(py)), 12)
        # bron (verplicht)
        img = self.f_mini.render("© OpenStreetMap-bijdragers", True, GRIJS if self.tegels.stijl == "donker" else (60, 60, 60))
        v.blit(img, (gebied.right - img.get_width() - 6, gebied.bottom - img.get_height() - 4))
        v.set_clip(oud)
        self.kaart_gebied = gebied

    @staticmethod
    def verkeersteken(v, x, y, soort):
        x, y = int(x), int(y)
        if soort == "dicht":                 # rood rond bord met witte balk
            pygame.draw.circle(v, ZWART, (x, y), 19)
            pygame.draw.circle(v, ROOD, (x, y), 16)
            pygame.draw.rect(v, (255, 255, 255), (x - 10, y - 3, 20, 6))
        else:                                # oranje driehoek met uitroepteken (file en ongeluk: rood)
            kl = (255, 150, 30) if soort not in ("ongeluk", "file") else ROOD
            pygame.draw.polygon(v, ZWART, [(x, y - 22), (x - 21, y + 15), (x + 21, y + 15)])
            pygame.draw.polygon(v, kl, [(x, y - 17), (x - 16, y + 12), (x + 16, y + 12)])
            pygame.draw.rect(v, ZWART, (x - 2, y - 7, 4, 11))
            pygame.draw.rect(v, ZWART, (x - 2, y + 6, 4, 4))

    @staticmethod
    def vlag(v, x, y):
        pygame.draw.line(v, ZWART, (x, y), (x, y - 44), 6)
        pygame.draw.line(v, ZILVER, (x, y), (x, y - 44), 3)
        for i in range(3):
            for j in range(2):
                kl = ZWART if (i + j) % 2 else ZILVER
                pygame.draw.rect(v, kl, (x + 2 + i * 9, y - 44 + j * 9, 9, 9))
        pygame.draw.circle(v, ROOD, (int(x), int(y)), 6)

    # ------------------------------------------------------------ pijlen
    def teken_pijl(self, soort, afslag, rect, kleur=GEEL):
        v = self.venster
        cx, cy = rect.centerx, rect.centery
        s = min(rect.w, rect.h) / 2 * 0.9
        dik = max(10, int(s * 0.22))
        if soort == 10:
            self.vlag(v, cx - s * 0.2, cy + s * 0.6)
            return
        if soort in (7, 8):
            pygame.draw.circle(v, kleur, (cx, int(cy - s * 0.15)), int(s * 0.45), dik // 2 + 2)
            pygame.draw.line(v, kleur, (cx, cy + s * 0.3), (cx, cy + s * 0.9), dik)
            if afslag:
                img = self.f_groot.render(str(afslag), True, kleur)
                v.blit(img, img.get_rect(center=(cx, int(cy - s * 0.15))))
            return
        if soort == 9:
            r = s * 0.35
            pygame.draw.line(v, kleur, (cx + r, cy + s * 0.9), (cx + r, cy - s * 0.2), dik)
            pygame.draw.arc(v, kleur, (cx - r - dik / 2, cy - s * 0.2 - r - dik / 2, 2 * r + dik, 2 * r + dik), 0, math.pi, dik)
            punt_x, punt_y, hoek = cx - r, cy - s * 0.1, 180
        else:
            hoek = {0: -90, 1: 90, 2: -135, 3: 135, 4: -40, 5: 40, 6: 0, 11: 0, 12: -25, 13: 25}.get(soort, 0)
            onder = (cx, cy + s * 0.9)
            knik = (cx, cy + s * 0.05)
            h = math.radians(hoek)
            lengte = s * 0.75
            punt_x, punt_y = knik[0] + math.sin(h) * lengte, knik[1] - math.cos(h) * lengte
            pygame.draw.line(v, kleur, onder, knik, dik)
            pygame.draw.circle(v, kleur, (int(knik[0]), int(knik[1])), dik // 2)
            pygame.draw.line(v, kleur, knik, (punt_x - math.sin(h) * dik, punt_y + math.cos(h) * dik), dik)
        h = math.radians(hoek)
        kop = s * 0.42
        p1 = (punt_x + math.sin(h) * kop * 0.5, punt_y - math.cos(h) * kop * 0.5)
        p2 = (punt_x + math.sin(h + 2.3) * kop * 0.7, punt_y - math.cos(h + 2.3) * kop * 0.7)
        p3 = (punt_x + math.sin(h - 2.3) * kop * 0.7, punt_y - math.cos(h - 2.3) * kop * 0.7)
        pygame.draw.polygon(v, kleur, [p1, p2, p3])

    # ------------------------------------------------------------ schermen
    def nu_draai(self):
        """Het zoekscherm blijft staand (het Android-toetsenbord draait niet mee)."""
        return self.draai

    def kies_vel(self):
        if self.nu_draai():
            self.venster, self.W, self.H = self.lig, self.PH, self.PW
        else:
            self.venster, self.W, self.H = self.echt, self.PW, self.PH

    def naar_vel(self, pos):
        """Aanraakplek op het echte scherm -> plek op het tekenvel."""
        wx, wy = pos
        d = self.nu_draai()
        if d == 90:
            return self.PH - wy, wx
        if d == 270:
            return wy, self.PW - wx
        return wx, wy

    def teken(self):
        self.knoppen = []
        self.kies_vel()
        v = self.venster
        v.fill(ZWART)
        getattr(self, "scherm_" + self.scherm)()
        if self.bezig:
            self.paneel(self.bezig, PAARS)
        elif self.melding and time.time() < self.melding[1]:
            self.paneel(self.melding[0], GEEL)
        d = self.nu_draai()
        if d:
            self.echt.blit(pygame.transform.rotate(self.lig, 90 if d == 90 else -90), (0, 0))
        pygame.display.flip()

    def paneel(self, tekst, rand):
        r = pygame.Rect(30, self.H // 2 - 60, self.W - 60, 120)
        pygame.draw.rect(self.venster, PANEEL, r, border_radius=16)
        pygame.draw.rect(self.venster, rand, r, 4, border_radius=16)
        regels = self.breek(tekst, self.f, r.w - 30)
        y = r.centery - len(regels) * 17
        for t in regels:
            self.tekst(t, self.f, ZILVER, r.centerx, y, midden=True)
            y += 34

    def breek(self, tekst, font, breed):
        woorden, regels, nu = tekst.split(), [], ""
        for w in woorden:
            if font.size((nu + " " + w).strip())[0] <= breed:
                nu = (nu + " " + w).strip()
            else:
                regels.append(nu)
                nu = w
        if nu:
            regels.append(nu)
        return regels or [""]

    def gps_tekst(self):
        st = self.gps.status
        if st == "geen_toestemming":
            return "Geen toestemming voor je locatie", ROOD
        if st in ("wacht", "fout") or not self.gps.plek:
            return "GPS zoeken...", GEEL
        if self.gps.oud() > 20:
            return "GPS-signaal kwijt", ROOD
        return "GPS: %d m nauwkeurig" % (self.gps.nauwkeurig or 0), GROEN



def _teken_kaartscherm(self):
    v = self.venster
    W, H = self.W, self.H
    self.teken_kaart(pygame.Rect(0, 0, W, H), 0.5)
    # boven: zoeken en vervoer
    liggend = W > H
    zb = int(W * 0.5) if liggend else W - 32
    self.knop((16, 16, zb, 84), "Waar wil je heen?", lambda: self.naar_zoeken(), kleur=PANEEL, font=self.f_groot)
    bx = zb + 32 if liggend else 16
    by, bh = (16, 84) if liggend else (112, 70)
    bw = (W - bx - 16 - 2 * 12) // 3
    for sleutel, label in VERVOER:
        gekozen = self.inst["vervoer"] == sleutel
        self.knop((bx, by, bw, bh), label, lambda s=sleutel: self.kies_vervoer(s),
                  kleur=PAARS if gekozen else PANEEL, rand=GEEL if gekozen else PAARS,
                  tekstkleur=ZWART if gekozen else ZILVER)
        bx += bw + 12
    # wandelen (bij Lopen), of terug naar de wandeling die al loopt
    wx, wy, ww = (zb + 32, 112, W - zb - 48) if liggend else (16, 194, min(W - 140, 380))
    if getattr(self, "wandeling", None):
        self.knop((wx, wy, ww, 70), "Terug naar de wandeling", lambda: self.naar("wandel"), kleur=(90, 50, 10),
                  rand=GEEL, font=self.f_mid)
    elif self.inst["vervoer"] == "lopen":
        wandel.knop_op_kaart(self, wx, wy, ww)
    # rechts: zoom en 'mij'
    self.knop((W - 96, H - 404, 80, 80), "+", lambda: self.wissel_zoom(self.zoom + 1), kleur=PANEEL, font=self.f_groot)
    self.knop((W - 96, H - 312, 80, 80), "-", lambda: self.wissel_zoom(self.zoom - 1), kleur=PANEEL, font=self.f_groot)
    self.knop((W - 96, H - 220, 80, 80), "", lambda: self.volg_mij(), kleur=GEEL if self.volg else PANEEL)
    r = self.knoppen[-1][0]
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 18, 5)
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 6)
    # onder: status en instellingen
    pygame.draw.rect(v, PANEEL, (0, H - 120, W, 120))
    pygame.draw.line(v, PAARS, (0, H - 120), (W, H - 120), 3)
    t, kl = self.gps_tekst()
    self.tekst(t, self.f, kl, 20, H - 104)
    self.tekst("Route: " + ("openrouteservice" if self.planner.heeft_sleutel() else "gratis testserver (alleen auto)"),
               self.f_klein, GRIJS, 20, H - 62, max_b=W - 150)
    self.knop((W - 130, H - 108, 114, 92), "Menu", lambda: self.naar("instel"), kleur=PAARS_D)


def _teken_zoek(self):
    v = self.venster
    W, H = self.W, self.H
    liggend = W > H
    LB = int(W * 0.44) if liggend else W - 32          # breedte van het linkerdeel
    self.knop((16, 16, 140, 72), "Terug", lambda: self.naar("kaart"), kleur=PANEEL)
    self.tekst("Waar wil je heen?", self.f, ZILVER, 172, 34)
    vak = pygame.Rect(16, 104, LB, 80)
    pygame.draw.rect(v, (250, 250, 250), vak, border_radius=12)
    pygame.draw.rect(v, GEEL, vak, 4, border_radius=12)
    t = self.zoektekst + ("|" if int(self.tijd * 2) % 2 == 0 else " ")
    while self.f_groot.size(t)[0] > vak.w - 24 and len(t) > 1:
        t = t[1:]
    self.tekst(t, self.f_groot, ZWART, vak.x + 14, vak.y + 16)
    self.knoppen.append((vak, lambda: self.toetsenbord()))
    self.knop((16, 198, LB, 76), "Zoeken", lambda: self.zoek_nu(), kleur=PAARS, rand=GEEL, tekstkleur=ZWART)
    lx = LB + 40 if liggend else 16
    lw = W - lx - 16
    y = 16 if liggend else 292
    lijst = self.resultaten if self.resultaten else [dict(r, recent=True) for r in self.inst.get("recent", [])]
    if not self.resultaten and lijst:
        self.tekst("Eerder gezocht:", self.f_klein, GRIJS, lx + 4, y)
        y += 34
    if liggend:
        self.tekst("Tip: zoek je adres voor je wegrijdt.", self.f_klein, GRIJS, 20, 290)
    for r in lijst[:7]:
        if y + 96 > H - 10:
            break
        regels = self.breek(r["naam"], self.f_klein, lw - 40)[:2]
        knop = self.knop((lx, y, lw, 92), "", lambda r=r: self.kies_doel(r), kleur=PANEEL)
        self.tekst(regels[0], self.f, ZILVER, knop.x + 18, knop.y + 12, max_b=knop.w - 36)
        if len(regels) > 1:
            self.tekst(" ".join(regels[1:]), self.f_klein, GRIJS, knop.x + 18, knop.y + 54, max_b=knop.w - 36)
        if self.plek():
            d = geo.afstand(self.plek(), (r["lat"], r["lon"]))
            self.tekst(self.meters(d), self.f_klein, GEEL, knop.right - 16, knop.y + 54, rechts=True)
        y += 104


def _teken_nav(self):
    if self.W > self.H:
        return _teken_nav_liggend(self)
    v = self.venster
    W, H = self.W, self.H
    n = self.nav
    boven = pygame.Rect(0, 0, W, 300)
    self.teken_kaart(pygame.Rect(0, boven.bottom, W, H - boven.bottom - 150), 0.62)
    pygame.draw.rect(v, PANEEL, boven)
    pygame.draw.line(v, GEEL, (0, boven.bottom), (W, boven.bottom), 4)
    st, m = n.get("stap"), n.get("tot", 0)
    soort = st["soort"] if st else 10
    self.teken_pijl(soort, st.get("afslag") if st else None, pygame.Rect(14, 14, 210, 200))
    self.tekst(self.meters(m), self.f_reus, ZILVER, W - 20, 30, rechts=True)
    self.tekst(SOORT_TEKST.get(soort, ""), self.f, GEEL, W - 20, 122, rechts=True)
    naam = (st or {}).get("naam") or ""
    if naam in ("", "-"):
        naam = "Bestemming" if soort == 10 else ""
    self.tekst(naam, self.f_groot, ZILVER, 20, 232, max_b=W - 40)
    onder = pygame.Rect(0, H - 150, W, 150)
    pygame.draw.rect(v, PANEEL, onder)
    pygame.draw.line(v, PAARS, (0, onder.y), (W, onder.y), 3)
    rest = n.get("rest", 0)
    snel = {"lopen": 1.3, "fietsen": 4.6, "auto": 13.0}[self.route.profiel] if self.route else 1.3
    if self.route and self.route.totaal_m > 0:
        snel = self.route.totaal_m / max(1, self.route.totaal_s)
    sec = rest / max(0.5, snel)
    aankomst = time.strftime("%H:%M", time.localtime(time.time() + sec))
    self.tekst("Aankomst " + aankomst, self.f_groot, ZILVER, 20, onder.y + 20)
    self.tekst("%s   %d min" % (self.meters(rest), round(sec / 60)), self.f, GEEL, 20, onder.y + 82)
    self.knop((W - 150, onder.y + 22, 134, 106), "Stop", lambda: self.stop_nav(), kleur=ROOD, rand=ZILVER)
    kaart_onder = onder.y - 16
    self.knop((W - 100, kaart_onder - 270, 84, 84), "+", lambda: self.wissel_zoom(self.zoom + 1), kleur=PANEEL, font=self.f_groot)
    self.knop((W - 100, kaart_onder - 176, 84, 84), "-", lambda: self.wissel_zoom(self.zoom - 1), kleur=PANEEL, font=self.f_groot)
    self.knop((W - 100, kaart_onder - 82, 84, 76), "", lambda: self.volg_mij(), kleur=GEEL if self.volg else PANEEL)
    r = self.knoppen[-1][0]
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 18, 5)
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 6)
    if self.gps.oud() > 20:
        self.tekst("GPS-signaal kwijt", self.f, ROOD, W // 2, boven.bottom + 16, midden=True)
    else:
        _verkeersregel(self, pygame.Rect(12, boven.bottom + 12, W - 24, 56))


VERKEER_TEKST = {"dicht": "Weg afgesloten", "werk": "Werk aan de weg", "obstakel": "Let op, obstakel",
                 "ongeluk": "Ongeluk", "file": "File"}


def _verkeersregel(self, r):
    """Een balk met het eerstvolgende verkeersbericht op de route ('Werk aan de weg over 2,3 km')."""
    lijst = self.nav.get("verkeer") or []
    if not lijst:
        return
    m, b = lijst[0]
    over = m - self.nav.get("langs", 0)
    if over < 0 or over > 20000:
        return
    pygame.draw.rect(self.venster, ZWART, r, border_radius=12)
    pygame.draw.rect(self.venster, ROOD if b["soort"] in ("dicht", "ongeluk", "file") else (255, 150, 30), r, 3, border_radius=12)
    self.verkeersteken(self.venster, r.x + 34, r.centery + 2, b["soort"])
    afst = self.tekst("over " + self.meters(over), self.f, GEEL, r.right - 14, r.y + 12, rechts=True)
    wat = VERKEER_TEKST.get(b["soort"], "Let op")
    if b["soort"] == "file" and b.get("lengte"):
        wat = "File %s" % self.meters(max(500, b["lengte"]))
    ruimte = afst.x - (r.x + 66) - 12
    f = self.f if self.f.size(wat)[0] <= ruimte else self.f_mid
    self.tekst(wat, f, ZILVER, r.x + 66, r.y + (12 if f is self.f else 15), max_b=ruimte)


def _reis(self):
    n = self.nav
    rest = n.get("rest", 0)
    snel = {"lopen": 1.3, "fietsen": 4.6, "auto": 13.0}[self.route.profiel] if self.route else 1.3
    if self.route and self.route.totaal_m > 0:
        snel = self.route.totaal_m / max(1, self.route.totaal_s)
    sec = rest / max(0.5, snel)
    return rest, sec, time.strftime("%H:%M", time.localtime(time.time() + sec))


def _zoomknoppen(self, x, onderkant):
    v = self.venster
    self.knop((x, onderkant - 270, 84, 84), "+", lambda: self.wissel_zoom(self.zoom + 1), kleur=PANEEL, font=self.f_groot)
    self.knop((x, onderkant - 176, 84, 84), "-", lambda: self.wissel_zoom(self.zoom - 1), kleur=PANEEL, font=self.f_groot)
    self.knop((x, onderkant - 82, 84, 76), "", lambda: self.volg_mij(), kleur=GEEL if self.volg else PANEEL)
    r = self.knoppen[-1][0]
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 18, 5)
    pygame.draw.circle(v, ZWART if self.volg else GEEL, r.center, 6)


def _teken_nav_liggend(self):
    v = self.venster
    W, H = self.W, self.H
    n = self.nav
    P = 440
    self.teken_kaart(pygame.Rect(P, 0, W - P, H), 0.6)
    pygame.draw.rect(v, PANEEL, (0, 0, P, H))
    pygame.draw.line(v, GEEL, (P, 0), (P, H), 4)
    st, m = n.get("stap"), n.get("tot", 0)
    soort = st["soort"] if st else 10
    self.teken_pijl(soort, st.get("afslag") if st else None, pygame.Rect(10, 10, 180, 170))
    self.tekst(self.meters(m), self.f_reus, ZILVER, P - 16, 24, rechts=True)
    self.tekst(SOORT_TEKST.get(soort, ""), self.f, GEEL, P - 16, 112, rechts=True)
    naam = (st or {}).get("naam") or ""
    if naam in ("", "-"):
        naam = "Bestemming" if soort == 10 else ""
    self.tekst(naam, self.f_groot, ZILVER, 16, 192, max_b=P - 32)
    pygame.draw.line(v, PAARS, (16, 254), (P - 16, 254), 2)
    rest, sec, aankomst = _reis(self)
    self.tekst("Aankomst " + aankomst, self.f_groot, ZILVER, 16, 268)
    self.tekst("%s   %d min" % (self.meters(rest), round(sec / 60)), self.f, GEEL, 16, 326)
    self.knop((16, H - 118, P - 32, 100), "Stop", lambda: self.stop_nav(), kleur=ROOD, rand=ZILVER)
    _zoomknoppen(self, W - 100, H - 16)
    if self.gps.oud() > 20:
        self.tekst("GPS-signaal kwijt", self.f, ROOD, P + (W - P) // 2, 16, midden=True)
    else:
        _verkeersregel(self, pygame.Rect(P + 12, 12, W - P - 24, 56))


def _wissel_draai(self):
    self.draai = {0: 90, 90: 270, 270: 0}[self.draai]
    self.inst["draai"] = self.draai
    self.bewaar()


def _teken_instel(self):
    W, H = self.W, self.H
    self.knop((16, 16, 140, 72), "Terug", lambda: self.naar("kaart"), kleur=PANEEL)
    self.tekst("Menu", self.f_groot, ZILVER, 176, 28)
    y = 112
    liggend = W > H
    rijen = [
        ("Scherm: " + {0: "staand", 90: "liggend", 270: "liggend omgekeerd"}[self.draai], self.wissel_draai),
        ("Kaart: " + ("donker" if self.tegels.stijl == "donker" else "licht"), self.wissel_stijl),
        ("Leon praat: " + ("aan" if self.stem.aan else "uit"), self.wissel_stem),
        ("Snelwegen (auto): " + ("vermijden" if self.inst.get("geen_snelweg") else "gebruiken"), self.wissel_snelweg),
        ("Leon testen", lambda: self.stem.zeg("over", "m200", "links", voorrang=True)),
        ("Wandelingen", lambda: self.naar("wandelingen")),
        ("Naam hond: " + (self.inst.get("hond") or "geen"), lambda: wandel.naar_naam(self)),
        ("\u2665 Doneren (de app is gratis)", self.doneer),
    ]
    if self.route:
        rijen.append(("Demo-rit " + ("stoppen" if self.gps.demo else "starten"), self.wissel_demo))
    if liggend:                                   # liggend: twee kolommen, zodat alles op het scherm past
        kb = (W - 48) // 2
        per = (len(rijen) + 1) // 2
        rh = 64 if per > 3 else 72
        for i, (label, actie) in enumerate(rijen):
            self.knop((16 + (i // per) * (kb + 16), y + (i % per) * (rh + 10), kb, rh), label, actie, kleur=PANEEL)
        y += per * (rh + 10) + 6
    else:
        kb = W - 32
        rh, stap = (86, 102) if len(rijen) <= 6 else (74, 86) if len(rijen) <= 7 else (66, 76)   # meer knoppen: lager
        for label, actie in rijen:
            self.knop((16, y, kb, rh), label, actie, kleur=PANEEL)
            y += stap
        y += 10
    tx = 20
    sl = self.planner.heeft_sleutel()
    regels = [("Route-dienst: " + ("openrouteservice (eigen sleutel)" if sl else "gratis OSRM-testserver"), ZILVER),
              ("Zonder sleutel kan alleen de auto. Zet de sleutel in sleutel.txt (zie de snelgids)." if not sl else
               "Lopen, fietsen en auto kunnen allemaal.", GRIJS),
              ("Kaart: OpenStreetMap-bijdragers. Stem: Leon.", GRIJS),
              ("DraveNavi %s  -  Dravenlock (Roger & Claudio)" % VERSIE, PAARS)]
    if liggend:
        regels = [(regels[0][0] + "   ·   " + regels[2][0], GRIJS), regels[3]]
    for t, kl in regels:
        for regel in self.breek(t, self.f_klein, (W - tx - 20)):
            self.tekst(regel, self.f_klein, kl, tx, y)
            y += 30
        y += 8


Navi.scherm_kaart = _teken_kaartscherm
Navi.scherm_zoek = _teken_zoek
Navi.scherm_nav = _teken_nav
Navi.scherm_instel = _teken_instel
Navi.scherm_wandel = wandel.scherm_wandel
Navi.scherm_wandelingen = wandel.scherm_wandelingen
Navi.scherm_naam = wandel.scherm_naam


# ------------------------------------------------------------------ acties en het navigeren
def _naar(self, scherm):
    self.scherm = scherm
    if scherm not in ("zoek", "naam"):
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass


def _naar_zoeken(self):
    self.naar("zoek")
    self.resultaten = []
    if not self.draai:                 # liggend (in de auto): toetsenbord pas als je op het vak tikt
        self.toetsenbord()


def _toetsenbord(self):
    try:
        pygame.key.start_text_input()
        if not self.draai:
            pygame.key.set_text_input_rect(pygame.Rect(16, 104, self.W - 32, 80))
    except Exception:
        pass


def _zoek_nu(self):
    t = self.zoektekst.strip()
    if len(t) < 2:
        self.meld("Typ eerst een adres of plaats.")
        return
    try:
        pygame.key.stop_text_input()
    except Exception:
        pass
    self.bezig = "Zoeken..."
    self.planner.zoek(t, self.plek())


def _kies_vervoer(self, s):
    self.inst["vervoer"] = s
    self.bewaar()
    self.stem.zeg({"lopen": "lopen", "fietsen": "fietsen", "auto": "auto"}[s], voorrang=True)
    if s != "auto" and not self.planner.heeft_sleutel():
        self.meld("Zonder sleutel kan alleen de auto. Lopen en fietsen komen met de sleutel.", 5)


def _kies_doel(self, r):
    self.vermijd = None
    if not self.plek():
        self.meld("Nog geen GPS. Wacht even tot je plek bekend is.")
        return
    self.doel = (r["lat"], r["lon"])
    self.doel_naam = r["naam"]
    recent = [x for x in self.inst.get("recent", []) if x.get("naam") != r["naam"]]
    self.inst["recent"] = [dict(naam=r["naam"], lat=r["lat"], lon=r["lon"])] + recent[:5]
    self.bewaar()
    self.bereken()


def _bereken(self, opnieuw=False):
    vervoer = self.inst["vervoer"]
    if not self.planner.heeft_sleutel():
        vervoer = "auto"
    self.bezig = None if opnieuw else "Route berekenen..."
    if not opnieuw:
        self.stem.zeg("berekenen", voorrang=True)
    self.nav_opnieuw = opnieuw
    self.laatst_berekend = time.time()
    self.planner.route(self.plek(), self.doel, vervoer, getattr(self, "vermijd", None) if opnieuw and vervoer == "auto" else None,
                       geen_snelweg=bool(self.inst.get("geen_snelweg")) and vervoer == "auto")


def _start_nav(self, route):
    self.route = route
    self._route_px = None
    oud = self.nav or {}
    self.nav = dict(gezegd={}, af_sinds=None, aangekomen=None, gps_weg=False, stap=None, tot=0, rest=route.totaal_m,
                    omweg=oud.get("omweg") if getattr(self, "nav_opnieuw", False) else False,
                    gewaarschuwd=oud.get("gewaarschuwd", set()) if getattr(self, "nav_opnieuw", False) else set())
    self.volg = True
    self.wissel_zoom(ZOOM_NAV.get(route.profiel, 16))
    self.naar("nav")
    if not getattr(self, "nav_opnieuw", False):
        self.stem.zeg("route_klaar")


def _stop_nav(self):
    self.route = None
    self.doel = None
    self.gps.stop_demo()
    self.naar("kaart")
    self.stem.zeg("gestopt", voorrang=True)


def _volg_mij(self):
    self.volg = True
    if not self.plek():
        self.meld("Nog geen GPS-plek.")


def _wissel_stijl(self):
    self.tegels.stijl = "licht" if self.tegels.stijl == "donker" else "donker"
    self.inst["stijl"] = self.tegels.stijl
    self.plaatjes.clear()
    self.__dict__.get("grote", {}).clear()
    self.bewaar()


def _wissel_stem(self):
    self.stem.aan = not self.stem.aan
    self.inst["stem"] = self.stem.aan
    self.bewaar()


def _doneer(self):
    """DraveNavi is gratis (donationware): de doneerpagina openen in de browser van de telefoon."""
    url = "https://paypal.me/roger076"
    try:
        from jnius import autoclass
        I = autoclass("android.content.Intent")
        i = I(I.ACTION_VIEW, autoclass("android.net.Uri").parse(url))
        i.addFlags(0x10000000)
        autoclass("org.kivy.android.PythonActivity").mActivity.startActivity(i)
    except Exception:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    self.meld("Dank je wel! De doneerpagina gaat open.", 4)


def _wissel_snelweg(self):
    self.inst["geen_snelweg"] = not self.inst.get("geen_snelweg", False)
    self.bewaar()
    if self.inst["geen_snelweg"]:
        self.meld("Auto: ik vermijd snelwegen. Geldt voor de volgende route." if self.planner.heeft_sleutel()
                  else "Snelwegen vermijden werkt alleen met de sleutel (zie de snelgids).", 5)
    else:
        self.meld("Auto: snelwegen mogen weer. Geldt voor de volgende route.", 4)


def _wissel_demo(self):
    if self.gps.demo:
        self.gps.stop_demo()
    elif self.route:
        v = {"lopen": 5.0, "fietsen": 9.0, "auto": 22.0}.get(self.route.profiel, 10.0)
        self.gps.start_demo(self.route.punten, v)
        self.naar("nav")


def _nav_update(self):
    """Elke beurt: waar ben ik op de route, wat komt er, moet Leon iets zeggen, ben ik afgeweken?"""
    n, r, p = self.nav, self.route, self.plek()
    if not r or not p:
        return
    weg = self.gps.oud() > 20
    if weg and not n["gps_weg"]:
        n["gps_weg"] = True
        self.stem.zeg("gps_kwijt")
    elif not weg and n["gps_weg"]:
        n["gps_weg"] = False
        self.stem.zeg("gps_terug")
    if weg:
        return
    afstand, langs = r.plek(p)
    n["rest"] = r.rest(langs)
    n["langs"] = langs
    _verkeer_update(self, r, langs)
    st, tot = r.volgende_stap(langs)
    if st is None:
        st = dict(soort=10, naam=getattr(self, "doel_naam", ""), afslag=None, start=len(r.punten) - 1)
    n["stap"], n["tot"] = st, tot
    # aangekomen?
    if n["rest"] < (15 if r.profiel == "lopen" else 25):
        if not n["aangekomen"]:
            n["aangekomen"] = time.time()
            self.stem.zeg("aangekomen", voorrang=True)
        elif time.time() - n["aangekomen"] > 6:
            self.route = None
            self.doel = None
            self.gps.stop_demo()
            self.naar("kaart")
        return
    # afgeweken?
    if afstand > AFWIJK.get(r.profiel, 40) and (self.gps.nauwkeurig or 0) < 60:
        if n["af_sinds"] is None:
            n["af_sinds"] = time.time()
        elif time.time() - n["af_sinds"] > 6 and time.time() - getattr(self, "laatst_berekend", 0) > 15:
            n["af_sinds"] = None
            self.stem.zeg("afwijken", voorrang=True)
            self.bereken(opnieuw=True)
            return
    else:
        n["af_sinds"] = None
    # Leon: aankondigen bij de drempels
    sleutel = (st.get("start"), st.get("soort"))
    al = n["gezegd"].setdefault(sleutel, set())
    ver, mid, dichtbij = DREMPELS.get(r.profiel, DREMPELS["lopen"])
    clip = ("rotonde%d" % max(1, min(6, st.get("afslag") or 1))) if st["soort"] in (7, 8) else SOORT_CLIP.get(st["soort"], "rechtdoor")
    if tot <= dichtbij and "nu" not in al:
        al.update(("nu", "mid", "ver"))
        if st["soort"] == 10:
            self.stem.zeg("bijna")
        else:
            self.stem.zeg("nu", clip, voorrang=True)
    elif tot <= mid and "mid" not in al and tot > dichtbij * 1.5:
        al.update(("mid", "ver"))
        self.stem.zeg("over", afstand_clip(tot), clip, voorrang=True)
    elif tot <= ver and "ver" not in al and tot > mid * 1.5:
        al.add("ver")
        self.stem.zeg("over", afstand_clip(tot), clip)


def afstand_clip(m):
    beste = min(AFSTAND_CLIPS, key=lambda a: abs(a[0] - m))
    return beste[1]


def _verwerk_antwoorden(self):
    try:
        while True:
            soort, res = self.planner.antwoord.get_nowait()
            self.bezig = None
            if soort == "zoek":
                self.resultaten = res
                if not res:
                    self.meld("Niets gevonden. Probeer het anders te schrijven.", 4)
            elif soort == "route":
                self.start_nav(res)
            else:
                if "route" in res:
                    self.stem.zeg("geen_route" if "40" in res or "HTTP" in res else "geen_internet", voorrang=True)
                self.meld("Dat lukte niet. Is er internet?", 4)
                self.fout = res
    except Exception:
        pass


def _klik(self, pos):
    for r, actie in reversed(self.knoppen):
        if r.collidepoint(pos):
            actie()
            return True
    return False


def _toets(self, e):
    if e.key in (pygame.K_AC_BACK, pygame.K_ESCAPE):
        if self.scherm in ("zoek", "instel", "wandel", "wandelingen"):
            self.naar("kaart")
        elif self.scherm == "naam":
            self.naar("instel")
        elif self.scherm == "nav":
            self.naar("kaart")
        else:
            self.stop = True
    elif self.scherm == "naam":
        if e.key == pygame.K_BACKSPACE:
            self.naamtekst = self.naamtekst[:-1]
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            wandel.bewaar_naam(self)
    elif self.scherm == "zoek":
        if e.key == pygame.K_BACKSPACE:
            self.zoektekst = self.zoektekst[:-1]
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.zoek_nu()


def _run(self):
    self.sleep_start = None
    while not self.stop:
        dt = self.klok.tick(30) / 1000.0
        self.tijd += dt
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.stop = True
            elif e.type == pygame.KEYDOWN:
                self.toets(e)
            elif e.type == pygame.TEXTINPUT and self.scherm == "zoek":
                self.zoektekst = (self.zoektekst + e.text)[:60]
            elif e.type == pygame.TEXTINPUT and self.scherm == "naam":
                self.naamtekst = (self.naamtekst + e.text)[:20]
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self.sleep_start = (self.naar_vel(e.pos), self.midden, False)
            elif e.type == pygame.MOUSEMOTION and self.sleep_start and e.buttons[0] and len(getattr(self, "vingers", {})) < 2:
                (sx, sy), m0, _ = self.sleep_start
                ex, ey = self.naar_vel(e.pos)
                dx, dy = ex - sx, ey - sy
                if abs(dx) + abs(dy) > 18 and m0 and getattr(self, "kaart_gebied", None) and \
                        self.kaart_gebied.collidepoint((sx, sy)) and not any(r.collidepoint((sx, sy)) for r, _ in self.knoppen):
                    self.volg = False
                    self.midden = (m0[0] - dx, m0[1] - dy)
                    self.sleep_start = ((sx, sy), m0, True)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                if self.sleep_start and not self.sleep_start[2]:
                    self.klik(self.naar_vel(e.pos))
                self.sleep_start = None
            elif e.type == pygame.MOUSEWHEEL:
                self.wissel_zoom(self.zoom + (1 if e.y > 0 else -1))
            elif e.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
                self.knijp(e)
        self.gps.update()
        self.verwerk_antwoorden()
        wandel.wandel_update(self)
        if self.route and self.scherm in ("nav", "kaart"):
            self.nav_update()
        self.stem.update()
        self.teken()
    pygame.quit()


for _naam, _f in list(globals().items()):
    if _naam.startswith("_") and callable(_f) and _naam[1:] in (
            "naar", "naar_zoeken", "toetsenbord", "zoek_nu", "kies_vervoer", "kies_doel", "bereken", "start_nav",
            "stop_nav", "volg_mij", "wissel_draai", "wissel_stijl", "wissel_stem", "wissel_snelweg", "doneer", "wissel_demo", "nav_update",
            "verwerk_antwoorden", "klik", "toets", "run"):
        setattr(Navi, _naam[1:], _f)


def main():
    Navi().run()


if __name__ == "__main__":
    main()


def _knijp(self, e):
    """Twee vingers uit elkaar = inzoomen, naar elkaar = uitzoomen."""
    vingers = getattr(self, "vingers", {})
    self.vingers = vingers
    if e.type == pygame.FINGERUP:
        vingers.pop(e.finger_id, None)
        if len(vingers) < 2:
            self.knijp_start = None
        return
    vingers[e.finger_id] = (e.x * self.PW, e.y * self.PH)
    if len(vingers) >= 2:
        self.sleep_start = None                 # knijpen is geen slepen (anders schiet de kaart weg)
        (ax, ay), (bx, by) = list(vingers.values())[:2]
        d = math.hypot(ax - bx, ay - by)
        if not getattr(self, "knijp_start", None):
            self.knijp_start = d
        elif d > self.knijp_start * 1.45:
            self.wissel_zoom(self.zoom + 1)
            self.knijp_start = d
        elif d < self.knijp_start / 1.45:
            self.wissel_zoom(self.zoom - 1)
            self.knijp_start = d


Navi.knijp = _knijp


WAARSCHUW = {"auto": 2500, "fietsen": 600, "lopen": 0}


def punt_op(r, m):
    """Het punt op de route op m meter vanaf het begin."""
    import bisect
    i = max(0, min(len(r.punten) - 2, bisect.bisect_right(r.cum, m) - 1))
    a, b = r.punten[i], r.punten[i + 1]
    t = 0 if r.cum[i + 1] == r.cum[i] else (m - r.cum[i]) / (r.cum[i + 1] - r.cum[i])
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
VERKEER_CLIP = {"dicht": "let_dicht", "werk": "let_werk", "obstakel": "let_werk", "ongeluk": "let_ongeluk", "file": "let_file"}


def _verkeer_update(self, r, langs):
    n = self.nav
    if r.profiel == "lopen":
        return
    self.verkeer.ververs(300)
    nu = time.time()
    if nu - n.get("verkeer_tijd", 0) > 8 or n.get("verkeer_versie") != self.verkeer.tijd:
        n["verkeer_tijd"], n["verkeer_versie"] = nu, self.verkeer.tijd
        n["verkeer"] = self.verkeer.op_route(r, langs)
        if r.profiel == "auto":                   # files uit de snelheidsmetingen
            self.files.zet_route(r)
            self.files.ververs(180)
            for a, b, v in self.files.files:
                if b >= langs:
                    n["verkeer"].append((a, dict(soort="file", punten=[punt_op(r, a)], lengte=b - a, snel=v)))
            n["verkeer"].sort(key=lambda x: x[0])
        # afgesloten weg op de route? (auto, met sleutel): een keer een omweg zoeken
        dicht = [x for x in n["verkeer"] if x[1]["soort"] == "dicht"]
        if dicht and r.profiel == "auto" and self.planner.heeft_sleutel() and not n.get("omweg") and self.doel:
            n["omweg"] = True
            self.vermijd = verkeer.vermijd_vlakken(dicht)
            self.stem.zeg("let_dicht", "berekenen", voorrang=True)
            self.meld("Weg afgesloten op je route. Ik zoek een omweg.", 5)
            self.nav_opnieuw = True
            self.laatst_berekend = nu
            self.planner.route(self.plek(), self.doel, "auto", self.vermijd,
                               geen_snelweg=bool(self.inst.get("geen_snelweg")))
            return
    # Leon waarschuwt een keer voor het eerstvolgende bericht dichtbij
    lijst = n.get("verkeer") or []
    if lijst and nu - n.get("laatst_gewaarschuwd", 0) > 60:
        m, b = lijst[0]
        over = m - langs
        sleutel = (b["soort"], round(b["punten"][0][0], 4), round(b["punten"][0][1], 4))
        grens = 5000 if b["soort"] == "file" else WAARSCHUW.get(r.profiel, 0)
        if 0 <= over <= grens and sleutel not in n.setdefault("gewaarschuwd", set()):
            n["gewaarschuwd"].add(sleutel)
            n["laatst_gewaarschuwd"] = nu
            self.stem.zeg(VERKEER_CLIP.get(b["soort"], "let_werk"))
