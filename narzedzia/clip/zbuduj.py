"""Budowa modelu wyszukiwania po treści (CLIP) dla Katalogatora — uruchamiana w CI (torch, transformers,
sentence-transformers, dostęp do Hugging Face).

Wynik (w folderze z argumentu):
  clip-obraz-int8.onnx  — koder obrazu CLIP ViT-B/32 (pixel_values 224×224 → image_embeds 512, znormalizowane)
  clip-tekst-int8.onnx  — wielojęzyczny koder tekstu sentence-transformers/clip-ViT-B-32-multilingual-v1
                           (input_ids, attention_mask → embedding 512, znormalizowany)
  clip-slownik.txt      — słownik WordPiece
  clip-sumy.json        — SHA-256 plików
Sprawdzenia: tokenizacja z katalogator/tresc.py = tokenizer HF; ONNX ≈ oryginał (cosinus > 0,98);
dopasowanie tekst↔obraz na syntetycznych obrazach (polskie hasła).
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from onnxruntime.quantization import QuantType, quantize_dynamic
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, CLIPVisionModelWithProjection

KORZEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KORZEN))
from katalogator import tresc  # noqa: E402

cel = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
cel.mkdir(parents=True, exist_ok=True)
torch.set_grad_enabled(False)


def eksport(modul, wejscia, nazwy_we, nazwy_wy, osie, plik):
    opcje = dict(input_names=nazwy_we, output_names=nazwy_wy, dynamic_axes=osie, opset_version=17, do_constant_folding=True)
    try:
        torch.onnx.export(modul, wejscia, str(plik), dynamo=False, **opcje)
    except TypeError:
        torch.onnx.export(modul, wejscia, str(plik), **opcje)


# --- obraz ---
wizja = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-base-patch32").eval()


class Obraz(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, pixel_values):
        return F.normalize(self.m(pixel_values=pixel_values).image_embeds, dim=1)


fp32_o = cel / "clip-obraz-fp32.onnx"
eksport(Obraz(wizja), (torch.randn(1, 3, 224, 224),), ["pixel_values"], ["wektor"],
        {"pixel_values": {0: "n"}, "wektor": {0: "n"}}, fp32_o)
quantize_dynamic(str(fp32_o), str(cel / tresc.PLIKI[0]), weight_type=QuantType.QInt8, per_channel=True)

# --- tekst (wielojęzyczny, ta sama przestrzeń co obraz) ---
st = SentenceTransformer("sentence-transformers/clip-ViT-B-32-multilingual-v1", device="cpu").eval()
tok = AutoTokenizer.from_pretrained("sentence-transformers/clip-ViT-B-32-multilingual-v1")
transformer, pooling, dense = st[0].auto_model, st[1], st[2]


class Tekst(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.t, self.d = transformer, dense

    def forward(self, input_ids, attention_mask):
        h = self.t(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        m = attention_mask.unsqueeze(-1).float()
        sr = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)               # mean pooling jak w sentence-transformers
        return F.normalize(self.d({"sentence_embedding": sr})["sentence_embedding"], dim=1)


fp32_t = cel / "clip-tekst-fp32.onnx"
ids = torch.tensor([tok("pies na plaży")["input_ids"]])
eksport(Tekst().eval(), (ids, torch.ones_like(ids)), ["input_ids", "attention_mask"], ["wektor"],
        {"input_ids": {0: "n", 1: "t"}, "attention_mask": {0: "n", 1: "t"}, "wektor": {0: "n"}}, fp32_t)
quantize_dynamic(str(fp32_t), str(cel / tresc.PLIKI[1]), weight_type=QuantType.QInt8, per_channel=True)
slownik = sorted(tok.get_vocab().items(), key=lambda kv: kv[1])
assert [i for _, i in slownik] == list(range(len(slownik)))
(cel / tresc.PLIKI[2]).write_text("\n".join(t for t, _ in slownik) + "\n", encoding="utf-8")

# --- sprawdzenia ---
moj = tresc.Tokenizer(cel / tresc.PLIKI[2])
for z in ("pies na plaży", "Tort urodzinowy z świeczkami!", "Zdjęcie: Kraków, rynek (2019)", "śnieg w górach",
          "ŻÓŁTY samochód", "kot", "zachód słońca nad morzem", "dzieci grają w piłkę", "日本の桜", "naïve café"):
    hf = tok(z, truncation=True, max_length=tresc.MAKS_TOKENOW)["input_ids"]
    assert moj.koduj(z)[0] == hf, (z, moj.koduj(z)[0], hf)
print("tokenizacja: zgodna z HF")

tresc.KATALOG_MODELI = cel.parent
(cel.parent / "clip").mkdir(exist_ok=True)
for n in tresc.PLIKI:
    (cel.parent / "clip" / n).write_bytes((cel / n).read_bytes())
for z in ("pies na plaży", "śnieg w górach", "a red car"):
    oryg = st.encode([z], normalize_embeddings=True)[0]
    nasz = tresc.wektor_tekstu(z)
    cos = float(np.dot(oryg, nasz))
    print(f"tekst „{z}”: cos(ONNX int8, oryginał) = {cos:.4f}")
    assert cos > 0.98

from PIL import Image  # noqa: E402
obrazy = {"czerwony": (220, 20, 20), "niebieski": (20, 40, 220), "zielony": (20, 180, 40)}
for nazwa, kolor in obrazy.items():
    Image.new("RGB", (320, 240), kolor).save(cel.parent / f"{nazwa}.jpg")
wek = tresc.wektory_obrazow([str(cel.parent / f"{n}.jpg") for n in obrazy])
for i, (nazwa, haslo) in enumerate((("czerwony", "czerwony kolor"), ("niebieski", "niebieski kolor"), ("zielony", "zielony kolor"))):
    t = tresc.wektor_tekstu(haslo)
    oceny = [float(np.dot(w.astype(np.float32), t)) for w in wek]
    print(f"„{haslo}”: {['%.3f' % o for o in oceny]}")
    assert int(np.argmax(oceny)) == i, (haslo, oceny)
# obraz: ONNX int8 vs oryginał
from transformers import CLIPImageProcessor  # noqa: E402
proc = CLIPImageProcessor.from_pretrained("openai/clip-vit-base-patch32")
x = proc(images=Image.open(cel.parent / "czerwony.jpg"), return_tensors="pt")["pixel_values"]
oryg = F.normalize(wizja(pixel_values=x).image_embeds, dim=1)[0].numpy()
cos = float(np.dot(oryg, wek[0].astype(np.float32)))
print(f"obraz: cos(ONNX int8, oryginał) = {cos:.4f}")
assert cos > 0.97

for p in (fp32_o, fp32_t):
    p.unlink()
sumy = {n: hashlib.sha256((cel / n).read_bytes()).hexdigest() for n in tresc.PLIKI}
(cel / "clip-sumy.json").write_text(json.dumps(sumy, indent=1), encoding="utf-8")
print(json.dumps(sumy, indent=1))
for n in tresc.PLIKI:
    print(n, round((cel / n).stat().st_size / 1e6, 1), "MB")
