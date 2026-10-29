# -*- coding: utf-8 -*-
# DraveNavi - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""maak_stem.py - laat Leon (neuvoice) alle vaste navigatiezinnen inspreken.

Draai op de pc met:  py -3.10 maak_stem.py
De wav-bestanden komen in de map 'stem' naast dit script (22050 Hz, mono, 16 bit).
De app op de telefoon plakt ze achter elkaar: "Over" + "200 meter" + "sla linksaf".
"""
import os
import sys
import wave

import numpy as np

ZINNEN = {
    # opbouwblokjes
    "over": "Over",
    "nu": "Nu,",
    "en_dan": "en daarna,",
    "m50": "50 meter,", "m100": "100 meter,", "m200": "200 meter,", "m300": "300 meter,",
    "m400": "400 meter,", "m500": "500 meter,", "m800": "800 meter,",
    "km1": "een kilometer,", "km2": "twee kilometer,", "km5": "vijf kilometer,",
    # afslagen (openrouteservice-soorten)
    "links": "sla linksaf.", "rechts": "sla rechtsaf.",
    "scherp_links": "sla scherp linksaf.", "scherp_rechts": "sla scherp rechtsaf.",
    "flauw_links": "ga flauw naar links.", "flauw_rechts": "ga flauw naar rechts.",
    "rechtdoor": "ga rechtdoor.", "omkeren": "keer om.",
    "houd_links": "houd links aan.", "houd_rechts": "houd rechts aan.",
    "rotonde1": "neem op de rotonde de eerste afslag.", "rotonde2": "neem op de rotonde de tweede afslag.",
    "rotonde3": "neem op de rotonde de derde afslag.", "rotonde4": "neem op de rotonde de vierde afslag.",
    "rotonde5": "neem op de rotonde de vijfde afslag.", "rotonde6": "neem op de rotonde de zesde afslag.",
    "bestemming": "ben je op je bestemming.",
    # hele zinnen
    "welkom": "Welkom bij Dreev Navie. Waar wil je heen?",
    "berekenen": "Ik bereken de route.",
    "route_klaar": "De route is klaar. We gaan op pad.",
    "volg_weg": "Volg de weg.",
    "afwijken": "Je wijkt af van de route. Ik bereken een nieuwe route.",
    "bijna": "Je bent er bijna.",
    "aangekomen": "Je bent aangekomen op je bestemming.",
    "gps_kwijt": "Ik heb geen GPS-signaal.",
    "gps_terug": "Het GPS-signaal is terug.",
    "geen_route": "Ik kan geen route vinden.",
    "geen_internet": "Er is geen internet. Ik probeer het zo opnieuw.",
    "gestopt": "De navigatie is gestopt.",
    "let_file": "Let op: er staat file op je route.",
    "let_werk": "Let op: er zijn wegwerkzaamheden op je route.",
    "let_dicht": "Let op: er is een weg afgesloten op je route.",
    "let_ongeluk": "Let op: er is een ongeluk gebeurd op je route.",
    "flitser": "Let op: snelheidscontrole.",
    "lopen": "Lopen.", "fietsen": "Fietsen.", "auto": "Auto.",
}


def spreekbaar(t):
    return t.replace("GPS", "gee pee es")


def main():
    from neuvoice import TTS
    uit = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stem")
    os.makedirs(uit, exist_ok=True)
    tts = TTS(auto_download=True)
    namen = list(getattr(tts, "voice_style_names", []) or [])
    stem = "Leon" if "Leon" in namen else (namen[0] if namen else None)
    stijl = tts.get_voice_style(stem)
    sr = int(getattr(tts, "sample_rate", 44100) or 44100)
    print("stem:", stem, "sample rate:", sr)
    for sleutel, tekst in ZINNEN.items():
        wav, _ = tts.synthesize(spreekbaar(tekst), voice_style=stijl, total_steps=10, speed=0.88, lang="nl")
        x = np.asarray(wav, dtype=np.float32).flatten()
        # stilte aan begin en eind weg, dan naar 22050 Hz
        drempel = 0.01 * (np.max(np.abs(x)) or 1)
        waar = np.where(np.abs(x) > drempel)[0]
        if len(waar):
            x = x[max(0, waar[0] - int(sr * 0.02)): waar[-1] + int(sr * 0.06)]
            x = np.concatenate([np.zeros(int(sr * 0.12), np.float32), x, np.zeros(int(sr * 0.10), np.float32)])
        if sr != 22050:
            n = int(len(x) * 22050 / sr)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        x = x / (np.max(np.abs(x)) or 1) * 0.9
        with wave.open(os.path.join(uit, sleutel + ".wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes((x * 32767).astype("<i2").tobytes())
        print("ok", sleutel, round(len(x) / 22050, 2), "s")
    print("KLAAR", len(ZINNEN), "zinnen")


if __name__ == "__main__":
    sys.exit(main())
