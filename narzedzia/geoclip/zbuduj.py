"""Budowa modelu GeoCLIP dla Katalogatora (uruchamiana w CI — potrzebuje torch, transformers, geoclip i dostępu do Hugging Face).

Wynik (w folderze z argumentu):
  geoclip-obraz-int8.onnx  — obraz 224×224 (wejście `pixel_values`) → znormalizowana cecha 512 (wyjście `cecha`)
  geoclip-galeria.npz      — cechy 100 tys. miejsc (fp16, znormalizowane), ich współrzędne i skala logitów
  geoclip-sumy.json        — SHA-256 obu plików
Na końcu porównuje przewidywania wersji ONNX (z przetwarzaniem obrazu z katalogator/geoclip.py) z oryginałem.
"""
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from geoclip import GeoCLIP
from onnxruntime.quantization import QuantType, quantize_dynamic

KORZEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KORZEN))
from katalogator import geoclip as kg  # noqa: E402

cel = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
cel.mkdir(parents=True, exist_ok=True)
torch.set_grad_enabled(False)
model = GeoCLIP().eval()


class Obraz(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, pixel_values):
        return F.normalize(self.m.image_encoder(pixel_values), dim=1)


fp32 = cel / "geoclip-obraz-fp32.onnx"
torch.onnx.export(Obraz(model), torch.randn(1, 3, 224, 224), str(fp32), input_names=["pixel_values"], output_names=["cecha"],
                  dynamic_axes={"pixel_values": {0: "n"}, "cecha": {0: "n"}}, opset_version=17, do_constant_folding=True)
int8 = cel / kg.PLIK_MODELU
quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)

gal = model.gps_gallery.float()
cechy = torch.cat([F.normalize(model.location_encoder(gal[i:i + 10000]), dim=1) for i in range(0, len(gal), 10000)])
np.savez_compressed(cel / kg.PLIK_GALERII, cechy=cechy.numpy().astype(np.float16), gps=gal.numpy().astype(np.float32),
                    skala=np.float32(model.logit_scale.exp().item()))

# --- sprawdzenie: ta sama odpowiedź co oryginał ---
import onnxruntime as ort  # noqa: E402
obrazy = [Path(__import__("geoclip").__file__).parent / "images" / "Kauai.png"]
for i, url in enumerate(("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a8/Tour_Eiffel_Wikimedia_Commons.jpg/640px-Tour_Eiffel_Wikimedia_Commons.jpg",
                         "https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/Empire_State_Building_%28aerial_view%29.jpg/640px-Empire_State_Building_%28aerial_view%29.jpg")):
    try:
        p = cel / f"test{i}.jpg"
        zad = urllib.request.Request(url, headers={"User-Agent": "Katalogator-CI/1.0 (model build)"})
        p.write_bytes(urllib.request.urlopen(zad, timeout=30).read())
        obrazy.append(p)
    except Exception as e:  # noqa: BLE001 — obraz z sieci jest dodatkiem
        print("pominięto obraz testowy:", e)

g = kg.Galeria(cel / kg.PLIK_GALERII)
sesja32 = ort.InferenceSession(str(fp32), providers=["CPUExecutionProvider"])
sesja8 = ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"])


def km(a, b):
    r = math.radians
    h = math.sin(r(b[0] - a[0]) / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(r(b[1] - a[1]) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


zle = 0
for p in obrazy:
    gps, prob = model.predict(str(p), top_k=3)
    oryg = [float(x) for x in gps[0]]
    px = kg.przygotuj(p)[None]
    c32 = sesja32.run(None, {"pixel_values": px})[0][0]
    c8 = sesja8.run(None, {"pixel_values": px})[0][0]
    pod = float(np.dot(c32, c8) / (np.linalg.norm(c32) * np.linalg.norm(c8)))
    nasz = g.najlepsze(c8, 3)[0]
    d = km(oryg, (nasz[0], nasz[1]))
    print(f"{p.name}: oryginał {oryg} p={float(prob[0]):.3f} | ONNX int8 {nasz} | {d:.1f} km | podobieństwo fp32/int8 {pod:.4f}")
    if d > 150 or pod < 0.95:
        zle += 1
fp32.unlink()
for p in cel.glob("test*.jpg"):
    p.unlink()
sumy = {n: hashlib.sha256((cel / n).read_bytes()).hexdigest() for n in (kg.PLIK_MODELU, kg.PLIK_GALERII)}
sumy["rozmiary"] = {n: (cel / n).stat().st_size for n in (kg.PLIK_MODELU, kg.PLIK_GALERII)}
(cel / "geoclip-sumy.json").write_text(json.dumps(sumy, indent=2), encoding="utf-8")
print(json.dumps(sumy, indent=2))
sys.exit(1 if zle else 0)
