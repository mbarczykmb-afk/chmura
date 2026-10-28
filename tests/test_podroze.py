"""✈ Podróże: uruchamianie serwera projektu Timeline Travels (node), wykrywanie już działającego i adapter motywu."""
import socket

import pytest

from katalogator import podroze

pytestmark = pytest.mark.skipif(podroze.node() is None, reason="brak Node.js")

SERVER_JS = """const http=require('http'),fs=require('fs');
http.createServer((q,s)=>{s.writeHead(200,{'Content-Type':'text/html'});s.end(fs.readFileSync('index.html'))})
.listen(process.env.PORT||8080,'127.0.0.1');"""
INDEX = "<!doctype html><html><head><title>Podróże</title></head><body>Tatry</body></html>"


def _wolny_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def projekt(tmp_path):
    k = tmp_path / "google-timeline-travels"
    k.mkdir()
    (k / "server.js").write_text(SERVER_JS, encoding="utf-8")
    (k / "index.html").write_text(INDEX, encoding="utf-8")
    yield {"folder": str(k), "port": _wolny_port(), "auto": True}
    podroze.zatrzymaj()


def test_walidacja_folderu(tmp_path):
    assert podroze.sprawdz_folder("") and podroze.sprawdz_folder(str(tmp_path / "brak"))
    assert "server.js" in podroze.sprawdz_folder(str(tmp_path))
    assert podroze.port_poprawny("8080") == 8080 and podroze.port_poprawny(80) is None
    assert podroze.port_poprawny("abc") is None and podroze.port_poprawny(70000) is None


def test_start_stop_serwera(projekt):
    assert not podroze.stan(projekt)["dziala"]
    w = podroze.uruchom(projekt)
    assert w == {"ok": True, "zewnetrzny": False}
    s = podroze.stan(projekt)
    assert s["dziala"] and s["wlasny"] and not s["zewnetrzny"] and s["adres"].endswith(f":{projekt['port']}/")
    assert podroze.uruchom(projekt)["ok"]  # drugi start niczego nie dubluje
    podroze.zatrzymaj()
    assert not podroze.stan(projekt)["dziala"]


def test_serwer_uruchomiony_samodzielnie_nie_jest_zatrzymywany(projekt):
    import subprocess
    p = subprocess.Popen([podroze.node(), "server.js"], cwd=projekt["folder"], env={"PORT": str(projekt["port"]), **__import__("os").environ})
    try:
        for _ in range(50):
            if podroze.dziala(projekt["port"]):
                break
            __import__("time").sleep(0.1)
        w = podroze.uruchom(projekt)
        assert w == {"ok": True, "zewnetrzny": True}
        assert podroze.stan(projekt)["zewnetrzny"]
        podroze.zatrzymaj()  # cudzego serwera nie ruszamy
        assert podroze.dziala(projekt["port"])
    finally:
        p.kill()
        p.wait()


def test_bledy_startu(projekt, tmp_path, monkeypatch):
    assert "server.js" in podroze.uruchom({**projekt, "folder": str(tmp_path)})["blad"]
    monkeypatch.setattr(podroze, "node", lambda: None)
    assert "Node.js" in podroze.uruchom(projekt)["blad"]
    monkeypatch.undo()
    (tmp_path / "pad").mkdir()
    (tmp_path / "pad" / "server.js").write_text("process.exit(3)", encoding="utf-8")
    assert "kod 3" in podroze.uruchom({"folder": str(tmp_path / "pad"), "port": _wolny_port()})["blad"]


def test_adapter_dopisuje_i_usuwa_jedna_linie(projekt):
    from pathlib import Path
    k = Path(projekt["folder"])
    assert not podroze.stan(projekt)["adapter"]
    assert podroze.zainstaluj_adapter(projekt["folder"]) == {"ok": True, "juz": False}
    html = (k / "index.html").read_text(encoding="utf-8")
    assert html.count("katalogator-motyw.js") == 1 and html.index("katalogator-motyw") < html.index("</head>")
    assert (k / "index.html.katalogator.bak").read_text(encoding="utf-8") == INDEX      # kopia oryginału
    assert (k / "katalogator-motyw.css").is_file() and (k / "katalogator-fonty").is_dir()
    assert podroze.stan(projekt)["adapter"]
    assert podroze.zainstaluj_adapter(projekt["folder"]) == {"ok": True, "juz": True}   # drugi raz — bez zmian
    assert (k / "index.html").read_text(encoding="utf-8").count("katalogator-motyw.js") == 1
    assert podroze.usun_adapter(projekt["folder"]) == {"ok": True}
    assert (k / "index.html").read_text(encoding="utf-8") == INDEX
    assert not (k / "katalogator-motyw.js").exists() and not (k / "katalogator-fonty").exists()
    assert not podroze.stan(projekt)["adapter"]


def test_adapter_bez_znacznika_head(projekt):
    from pathlib import Path
    (Path(projekt["folder"]) / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
    assert "</head>" in podroze.zainstaluj_adapter(projekt["folder"])["blad"]
