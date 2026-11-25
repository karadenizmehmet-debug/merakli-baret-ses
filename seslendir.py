#!/usr/bin/env python3
"""Meraklı Baret - doğal Türkçe seslendirme (Chatterbox Multilingual, MIT).

Kullanım:  python seslendir.py istekler/<ad>
Girdi:     istekler/<ad>/script.json
Çıktı:     istekler/<ad>/ses.wav, ses/NN.wav, zamanlar.json, agiz.json

script.json:
{
  "baslik": "Elmas",
  "cumleler": [
    {"metin": "Minecraft'ta elmas 5 dakikada bulunur.",   # altyazıda görünen
     "okunus": "Maynkraft'ta elmas beş dakikada bulunur.", # TTS'e giden (isteğe bağlı)
     "hiz": 1.0,          # 0.8-1.3, perdeyi bozmadan hızlandırır
     "duraklama": 0.25,   # cümleden sonra sessizlik (sn)
     "duygu": 0.6}        # 0.25 sakin ... 1.0 çok heyecanlı
  ]
}

Mehmet Karadeniz, 2026-2027
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 24000
SESLI = set("aeıioöuüAEIİOÖUÜâîû")


def hece_say(metin: str) -> int:
    return max(1, sum(1 for c in metin if c in SESLI))


def sayi_oku(metin: str) -> str:
    """Rakamları Türkçe okunuşa çevirir (TTS rakamları bazen yanlış okur)."""
    birler = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
    onlar = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]

    def uc(n):
        y, o, b = n // 100, (n // 10) % 10, n % 10
        s = ("" if y == 0 else ("yüz" if y == 1 else birler[y] + " yüz"))
        return " ".join(x for x in [s, onlar[o], birler[b]] if x)

    def oku(n):
        if n == 0:
            return "sıfır"
        parca = []
        for deger, ad in [(10**9, "milyar"), (10**6, "milyon"), (1000, "bin")]:
            if n >= deger:
                k = n // deger
                parca.append("bin" if (deger == 1000 and k == 1) else uc(k) + " " + ad)
                n %= deger
        if n:
            parca.append(uc(n))
        return " ".join(parca)

    metin = re.sub(r"(\d+)\s*°C", lambda m: m.group(1) + " derece", metin)
    metin = re.sub(r"(\d+)\s*km\b", lambda m: m.group(1) + " kilometre", metin)
    metin = re.sub(r"(\d+)[.,](\d+)", lambda m: oku(int(m.group(1))) + " virgül " + oku(int(m.group(2))), metin)
    return re.sub(r"\d+", lambda m: oku(int(m.group(0))), metin)


def kirp(wav: np.ndarray, esik_db=-42, pay=0.04) -> np.ndarray:
    if len(wav) == 0:
        return wav
    pencere = int(SR * 0.02)
    n = len(wav) // pencere
    if n == 0:
        return wav
    rms = np.sqrt(np.mean(wav[: n * pencere].reshape(n, pencere) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-12))
    aktif = np.where(db > esik_db)[0]
    if len(aktif) == 0:
        return wav
    bas = max(0, aktif[0] * pencere - int(pay * SR))
    son = min(len(wav), (aktif[-1] + 1) * pencere + int(pay * SR))
    return wav[bas:son]


def en_uzun_sessizlik(wav: np.ndarray) -> float:
    pencere = int(SR * 0.02)
    n = len(wav) // pencere
    if n == 0:
        return 0.0
    rms = np.sqrt(np.mean(wav[: n * pencere].reshape(n, pencere) ** 2, axis=1) + 1e-12)
    sessiz = 20 * np.log10(rms / (rms.max() + 1e-12)) < -40
    en, simdi = 0, 0
    for s in sessiz:
        simdi = simdi + 1 if s else 0
        en = max(en, simdi)
    return en * 0.02


def puanla(wav: np.ndarray, hece: int) -> float:
    """Küçük puan iyi. Konuşma hızı ~5.5 hece/sn civarı ve uzun boşluk yoksa iyi."""
    sure = len(wav) / SR
    if sure < 0.3:
        return 1e9
    hiz = hece / sure
    ceza = abs(hiz - 5.5)
    if hiz < 2.8 or hiz > 9.5:          # yutulmuş/uzatılmış kelime, halüsinasyon
        ceza += 50
    bosluk = en_uzun_sessizlik(wav)
    if bosluk > 0.7:
        ceza += 20 * bosluk
    return ceza


def tempo(wav: np.ndarray, hiz: float) -> np.ndarray:
    if abs(hiz - 1.0) < 0.01:
        return wav
    with tempfile.TemporaryDirectory() as t:
        g, c = Path(t, "g.wav"), Path(t, "c.wav")
        sf.write(g, wav, SR)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(g),
                        "-af", f"atempo={hiz:.3f}", str(c)], check=True)
        out, _ = sf.read(c, dtype="float32")
    return out


def son_islem(giris: Path, cikis: Path):
    filtre = ("highpass=f=70,"
              "equalizer=f=3000:t=q:w=1.2:g=2,"
              "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
              "loudnorm=I=-16:TP=-1.5:LRA=7")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(giris),
                    "-af", filtre, "-ar", str(SR), "-ac", "1", str(cikis)], check=True)


def kelime_zamanlari(metin: str, bas: float, son: float):
    kelimeler = metin.split()
    agirlik = [hece_say(k) + (0.6 if re.search(r"[,.!?;:]$", k) else 0) for k in kelimeler]
    toplam = sum(agirlik)
    t, cikti = bas, []
    for k, a in zip(kelimeler, agirlik):
        d = (son - bas) * a / toplam
        cikti.append({"kelime": k, "bas": round(t, 3), "son": round(t + d, 3)})
        t += d
    return cikti


def agiz_zarfi(wav: np.ndarray, fps=30):
    adim = SR // fps
    n = int(np.ceil(len(wav) / adim))
    rms = [float(np.sqrt(np.mean(wav[i * adim:(i + 1) * adim] ** 2) + 1e-12)) for i in range(n)]
    tepe = max(np.percentile(rms, 95), 1e-6)
    return [round(min(1.0, r / tepe), 3) for r in rms]


def main():
    istek = Path(sys.argv[1])
    ref = Path(os.environ.get("SES_REFERANS", Path(__file__).parent / "referans" / "baret.wav"))
    deneme = int(os.environ.get("SES_DENEME", "3"))
    senaryo = json.loads((istek / "script.json").read_text(encoding="utf-8"))
    cumleler = senaryo["cumleler"]

    import torch
    torch.set_num_threads(os.cpu_count() or 2)
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    print(f"Model yükleniyor... ({len(cumleler)} cümle, referans: {ref.name})", flush=True)
    model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    model.prepare_conditionals(str(ref), exaggeration=0.5)

    klasor = istek / "ses"
    klasor.mkdir(exist_ok=True)
    parcalar, zamanlar, t = [], [], 0.0
    for i, c in enumerate(cumleler):
        okunus = sayi_oku(c.get("okunus") or c["metin"])
        hece = hece_say(okunus)
        duygu = float(c.get("duygu", 0.55))
        en_iyi, en_puan = None, 1e18
        for d in range(deneme):
            torch.manual_seed(1000 * i + d)
            wav = model.generate(okunus, language_id="tr", exaggeration=duygu,
                                 cfg_weight=float(c.get("cfg", 0.5)), temperature=0.75)
            wav = kirp(wav.squeeze(0).numpy().astype("float32"))
            p = puanla(wav, hece)
            print(f"  [{i+1:02d}] deneme {d+1}: {len(wav)/SR:.2f} sn, puan {p:.2f}", flush=True)
            if p < en_puan:
                en_iyi, en_puan = wav, p
            if p < 1.5:
                break
        wav = tempo(en_iyi, float(c.get("hiz", 1.0)))
        sf.write(klasor / f"{i+1:02d}.wav", wav, SR)
        bas, son = t, t + len(wav) / SR
        zamanlar.append({"no": i + 1, "metin": c["metin"], "bas": round(bas, 3), "son": round(son, 3),
                         "kelimeler": kelime_zamanlari(c["metin"], bas, son)})
        dur = float(c.get("duraklama", 0.25))
        parcalar += [wav, np.zeros(int(SR * dur), dtype="float32")]
        t = son + dur

    ham = istek / "ses_ham.wav"
    sf.write(ham, np.concatenate(parcalar), SR)
    son_islem(ham, istek / "ses.wav")
    ham.unlink()
    final, _ = sf.read(istek / "ses.wav", dtype="float32")
    (istek / "zamanlar.json").write_text(json.dumps(
        {"sure": round(len(final) / SR, 3), "cumleler": zamanlar}, ensure_ascii=False, indent=1), encoding="utf-8")
    (istek / "agiz.json").write_text(json.dumps({"fps": 30, "deger": agiz_zarfi(final)}), encoding="utf-8")
    print(f"Bitti: {istek/'ses.wav'} ({len(final)/SR:.1f} sn)")


if __name__ == "__main__":
    main()
