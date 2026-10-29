# -*- coding: utf-8 -*-
# DraveNavi - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""maak_stem_wandel.py - Leon spreekt de wandel-zinnetjes in. Draai: py -3.10 maak_stem_wandel.py -> map stem"""
import os
import wave

import numpy as np

GETAL = ["", "een", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien"]
ZINNEN = {"w_start": "Veel plezier met wandelen!", "w_je_hebt": "Je hebt nu", "w_gelopen": "gelopen.",
          "w_klaar": "Lekker gewandeld! De wandeling is bewaard."}
for h in range(1, 21):                       # halve kilometers tot 10 km
    km, half = divmod(h, 2)
    if km == 0:
        t = "een halve kilometer"
    elif km == 1 and half:
        t = "anderhalve kilometer"
    elif half:
        t = "%s en een halve kilometer" % GETAL[km]
    else:
        t = "%s kilometer" % ("een" if km == 1 else GETAL[km])
    ZINNEN["w_km%d" % h] = t


def main():
    from neuvoice import TTS
    uit = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stem")
    os.makedirs(uit, exist_ok=True)
    tts = TTS(auto_download=True)
    namen = list(getattr(tts, "voice_style_names", []) or [])
    stijl = tts.get_voice_style("Leon" if "Leon" in namen else namen[0])
    sr = int(getattr(tts, "sample_rate", 44100) or 44100)
    for sleutel, tekst in ZINNEN.items():
        wav, _ = tts.synthesize(tekst, voice_style=stijl, total_steps=10, speed=0.88, lang="nl")
        x = np.asarray(wav, dtype=np.float32).flatten()
        drempel = 0.01 * (np.max(np.abs(x)) or 1)
        waar = np.where(np.abs(x) > drempel)[0]
        if len(waar):
            x = x[max(0, waar[0] - int(sr * 0.02)): waar[-1] + int(sr * 0.06)]
        x = np.concatenate([np.zeros(int(sr * 0.08), np.float32), x, np.zeros(int(sr * 0.06), np.float32)])
        n = int(len(x) * 22050 / sr)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        x = x / (np.max(np.abs(x)) or 1) * 0.9
        with wave.open(os.path.join(uit, sleutel + ".wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes((x * 32767).astype("<i2").tobytes())
    print("KLAAR", len(ZINNEN))


if __name__ == "__main__":
    main()
