import json
import time

import pytest

from katalogator import projekty
from katalogator.aplikacja import Stan
from test_aplikacja import app  # noqa: F401
from test_aplikacja_plan import _czekaj
from test_katalogator import _drzewo


def test_migracja_ze_starej_wersji(tmp_path):
    (tmp_path / "ustawienia.json").write_text(json.dumps({"zrodla": ["Z:/Zdj"], "cel": "Z:/Cel"}), encoding="utf-8")
    (tmp_path / "katalog.db").write_bytes(b"")
    st = Stan(tmp_path)
    assert st.projekt["nazwa"] == "Mój pierwszy projekt" and st.ustawienia["cel"]
    assert (tmp_path / "projekty" / st.pid / "katalog.db").exists() and not (tmp_path / "katalog.db").exists()
    # kolejne uruchomienie otwiera ten sam projekt
    assert Stan(tmp_path).pid == st.pid


def test_projekty_sa_rozdzielone(tmp_path):
    st = Stan(tmp_path)
    a = st.pid
    st.zapisz_ustawienia({"zrodla": [str(tmp_path / "A")], "cel": str(tmp_path / "CelA")})
    b = st.projekty.nowy("Zdjęcia rodziców")
    assert st.otworz_projekt(b) is None
    assert st.ustawienia == {"zrodla": [], "cel": ""} and st.baza != st.projekty.baza(a)
    st.zapisz_ustawienia({"zrodla": [str(tmp_path / "B")], "cel": ""})
    st.otworz_projekt(a)
    assert st.ustawienia["zrodla"][0]["sciezka"].endswith("A")
    assert Stan(tmp_path).pid == a  # zapamiętany ostatni
    assert "blad" in st.zmien_projekt({"nazwa": " "})
    assert st.zmien_projekt({"nazwa": "Mój dysk", "notatki": "Zostało: filmy 2019"})["notatki"].startswith("Zostało")
    assert [p["nazwa"] for p in st.projekty.lista()][0] == "Mój dysk"
    st.usun_projekt(a)  # usunięcie bieżącego przełącza na inny
    assert st.pid == b and not (tmp_path / "projekty" / a).exists()
    with pytest.raises(ValueError):
        st.projekty.wczytaj("../../etc")


def test_api_projektow_dziennik_przejrzane(app, tmp_path):  # noqa: F811
    api, _, stan = app
    k = _drzewo(tmp_path)
    cel = tmp_path / "cel"; cel.mkdir()
    api("/api/ustawienia", {"zrodla": [{"sciezka": str(k), "tryb": "kopiuj"}], "cel": str(cel)})
    api("/api/skanuj", {}); _czekaj(api, "skan")
    api("/api/plan/generuj", {}); _czekaj(api, "plan")
    d = json.loads(api("/api/plan/drzewo")[1])
    folder = next(f["sciezka"] for f in d["foldery"] if f["nowe"])
    api("/api/plan/przejrzany", {"folder": folder, "wartosc": True})
    assert json.loads(api("/api/plan/drzewo")[1])["przejrzane"] == [folder]
    wpisy = json.loads(api("/api/projekt/dziennik")[1])["wpisy"]
    assert {w["typ"] for w in wpisy} >= {"skan", "plan"}
    lista = json.loads(api("/api/projekty")[1])
    st = next(p for p in lista["projekty"] if p["id"] == lista["biezacy"])["statystyki"]
    assert st["pliki"] >= 6 and st["przejrzane"] == 1 and st["foldery"] >= 2
    s = json.loads(api("/api/projekty/nowy", {"nazwa": "Drugi"})[1])
    assert s["projekt"]["nazwa"] == "Drugi" and not s["ma_wyniki"] and s["zrodla"] == []
    s = json.loads(api("/api/projekty/otworz", {"id": lista["biezacy"]})[1])
    assert s["ma_wyniki"] and s["plan"]
