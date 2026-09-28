"""Rysuje ikonę Katalogatora: katalogator/dane/ikona.ico (Windows) i katalogator/ui/ikona.png (okno)."""

from pathlib import Path

from PIL import Image, ImageDraw

KORZEN = Path(__file__).resolve().parents[1]


def rysuj(r: int = 1024) -> Image.Image:
    im = Image.new("RGBA", (r, r), (0, 0, 0, 0))
    # tło: zaokrąglony kwadrat z pionowym gradientem
    grad = Image.new("RGBA", (r, r))
    g = ImageDraw.Draw(grad)
    for y in range(r):
        t = y / r
        g.line((0, y, r, y), fill=(int(58 - 20 * t), int(125 - 45 * t), int(235 - 45 * t), 255))
    maska = Image.new("L", (r, r), 0)
    ImageDraw.Draw(maska).rounded_rectangle((0, 0, r - 1, r - 1), radius=int(r * 0.22), fill=255)
    im.paste(grad, (0, 0), maska)
    d = ImageDraw.Draw(im)
    s = r / 1024
    # folder: zakładka + korpus
    d.rounded_rectangle((170 * s, 250 * s, 470 * s, 360 * s), radius=40 * s, fill=(255, 255, 255, 235))
    d.rounded_rectangle((150 * s, 310 * s, 874 * s, 800 * s), radius=60 * s, fill=(255, 255, 255, 255))
    # zdjęcie w folderze: niebo, słońce, góry
    x0, y0, x1, y1 = 250 * s, 400 * s, 774 * s, 720 * s
    d.rounded_rectangle((x0, y0, x1, y1), radius=28 * s, fill=(214, 233, 255, 255))
    d.ellipse((620 * s, 440 * s, 700 * s, 520 * s), fill=(255, 196, 61, 255))
    d.polygon([(x0, y1), (400 * s, 520 * s), (520 * s, y1)], fill=(52, 168, 110, 255))
    d.polygon([(420 * s, y1), (590 * s, 560 * s), (x1, y1)], fill=(31, 130, 85, 255))
    d.rounded_rectangle((x0, y0, x1, y1), radius=28 * s, outline=(47, 111, 219, 255), width=int(10 * s))
    return im


if __name__ == "__main__":
    duza = rysuj()
    (KORZEN / "katalogator" / "dane").mkdir(exist_ok=True)
    duza.resize((256, 256), Image.Resampling.LANCZOS).save(
        KORZEN / "katalogator" / "dane" / "ikona.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                             (128, 128), (256, 256)])
    duza.resize((192, 192), Image.Resampling.LANCZOS).save(KORZEN / "katalogator" / "ui" / "ikona.png")
    print("Zapisano ikonę.")
