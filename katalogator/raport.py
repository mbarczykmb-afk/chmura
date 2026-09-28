"""Raport ze skanu: podsumowanie w konsoli i plik HTML."""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime

NAZWY_RODZAJOW = {
    "zdjecie": "Zdjęcia", "film": "Filmy", "muzyka": "Muzyka",
    "towarzyszacy": "Pliki towarzyszące (napisy, .xmp)", "inne": "Pozostałe pliki",
}
NAZWY_ZRODEL = {
    "exif": "z aparatu (EXIF)", "film": "z metadanych filmu",
    "nazwa": "z nazwy pliku", "plik": "z daty pliku — do sprawdzenia",
}


def rozmiar_txt(b: float) -> str:
    for j in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or j == "TB":
            return f"{b:.0f} {j}" if j in ("B", "KB") else f"{b:.1f} {j}"
        b /= 1024
    return ""


def zbierz(db: sqlite3.Connection) -> dict:
    q = lambda sql, *a: db.execute(sql, a).fetchall()
    d: dict = {"utworzono": datetime.now().strftime("%Y-%m-%d %H:%M")}
    d["korzenie"] = q("SELECT korzen, COUNT(*) n, COALESCE(SUM(rozmiar),0) b FROM pliki GROUP BY korzen")
    d["rodzaje"] = q("SELECT rodzaj, COUNT(*) n, SUM(rozmiar) b FROM pliki GROUP BY rodzaj ORDER BY b DESC")
    d["media"] = {}
    for rodz in ("zdjecie", "film"):
        wsz = q("SELECT COUNT(*) n, SUM(lat IS NOT NULL) gps FROM pliki WHERE rodzaj=?", rodz)[0]
        d["media"][rodz] = {
            "n": wsz["n"], "gps": wsz["gps"] or 0,
            "zrodla": q("SELECT zrodlo_daty z, COUNT(*) n FROM pliki WHERE rodzaj=? GROUP BY z ORDER BY n DESC", rodz),
            "lata": q(
                "SELECT substr(data,1,4) rok, COUNT(*) n, SUM(lat IS NOT NULL) gps, SUM(rozmiar) b "
                "FROM pliki WHERE rodzaj=? GROUP BY rok ORDER BY rok", rodz),
            "aparaty": q(
                "SELECT COALESCE(aparat,'(brak informacji)') a, COUNT(*) n FROM pliki "
                "WHERE rodzaj=? GROUP BY a ORDER BY n DESC LIMIT 8", rodz),
        }
    m = q("SELECT COUNT(*) n, SUM(wykonawca IS NOT NULL AND album IS NOT NULL) tag, "
          "COUNT(DISTINCT wykonawca) wyk, COUNT(DISTINCT wykonawca||'/'||album) alb "
          "FROM pliki WHERE rodzaj='muzyka'")[0]
    d["muzyka"] = dict(m)
    # Foldery pierwszego poziomu dla pozostałych plików (np. "Praca").
    d["inne_foldery"] = q(
        "SELECT CASE WHEN instr(replace(wzgledna,'\\','/'),'/')>0 "
        "THEN substr(replace(wzgledna,'\\','/'),1,instr(replace(wzgledna,'\\','/'),'/')-1) "
        "ELSE '(pliki luzem)' END f, COUNT(*) n, SUM(rozmiar) b "
        "FROM pliki WHERE rodzaj IN ('inne','towarzyszacy') GROUP BY f ORDER BY b DESC LIMIT 25")
    d["rozszerzenia_inne"] = q(
        "SELECT rozszerzenie e, COUNT(*) n, SUM(rozmiar) b FROM pliki WHERE rodzaj='inne' "
        "GROUP BY e ORDER BY b DESC LIMIT 12")
    kand = q(
        "SELECT COUNT(*) grupy, COALESCE(SUM(n-1),0) nadmiar, COALESCE(SUM((n-1)*rozmiar),0) b FROM "
        "(SELECT rozmiar, COUNT(*) n FROM pliki WHERE rozmiar > 0 GROUP BY rozmiar HAVING n > 1)")[0]
    d["duplikaty"] = dict(kand)
    d["bledy"] = q("SELECT wzgledna, blad FROM pliki WHERE blad IS NOT NULL LIMIT 10")
    d["n_bledow"] = q("SELECT COUNT(*) n FROM pliki WHERE blad IS NOT NULL")[0]["n"]
    d["pominiete"] = q(
        "SELECT korzen, pominiete_pliki p, pominiete_foldery f, bledy_dostepu e FROM skany s "
        "WHERE id = (SELECT MAX(id) FROM skany WHERE korzen = s.korzen)")
    return d


def _proc(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "—"


def tekst(d: dict) -> str:
    w = [f"RAPORT KATALOGATORA ({d['utworzono']})", ""]
    for k in d["korzenie"]:
        w.append(f"Folder: {k['korzen']} — {k['n']} plików, {rozmiar_txt(k['b'])}")
    w.append("")
    for r in d["rodzaje"]:
        w.append(f"  {NAZWY_RODZAJOW.get(r['rodzaj'], r['rodzaj']):38} {r['n']:>8}  {rozmiar_txt(r['b']):>10}")
    for rodz, nazwa in (("zdjecie", "ZDJĘCIA"), ("film", "FILMY")):
        m = d["media"][rodz]
        if not m["n"]:
            continue
        w += ["", f"{nazwa}: {m['n']}, z lokalizacją GPS: {m['gps']} ({_proc(m['gps'], m['n'])})", "  Data:"]
        for z in m["zrodla"]:
            w.append(f"    {NAZWY_ZRODEL.get(z['z'], z['z']):34} {z['n']:>8}")
        w.append("  Lata (plików / z GPS):")
        for r in m["lata"]:
            w.append(f"    {r['rok'] or '?':6} {r['n']:>7} / {r['gps'] or 0:<7} {rozmiar_txt(r['b'] or 0):>10}")
    mz = d["muzyka"]
    if mz["n"]:
        w += ["", f"MUZYKA: {mz['n']} utworów, z tagami wykonawca+album: {mz['tag'] or 0} "
                  f"({_proc(mz['tag'] or 0, mz['n'])}), albumów: {mz['alb']}"]
    if d["inne_foldery"]:
        w += ["", "POZOSTAŁE PLIKI — foldery główne:"]
        for f in d["inne_foldery"]:
            w.append(f"    {f['f'][:40]:40} {f['n']:>7}  {rozmiar_txt(f['b']):>10}")
    du = d["duplikaty"]
    w += ["", f"MOŻLIWE DUPLIKATY (identyczny rozmiar, do potwierdzenia sumą kontrolną): "
              f"{du['nadmiar']} plików, do {rozmiar_txt(du['b'])}"]
    for p in d["pominiete"]:
        w.append(f"Pominięto śmieci: {p['p']} plików, {p['f']} folderów (.wdmc, Thumbs.db...); "
                 f"błędy dostępu: {p['e']}")
    if d["n_bledow"]:
        w.append(f"Plików z nieczytelnymi metadanymi: {d['n_bledow']} (zob. raport HTML)")
    return "\n".join(w)


def _tabela(naglowki, wiersze) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in naglowki)
    tr = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in wiersze
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def _slupki(lata) -> str:
    if not lata:
        return ""
    mx = max(r["n"] for r in lata) or 1
    wiersze = []
    for r in lata:
        gps = r["gps"] or 0
        wiersze.append(
            f"<div class='rok'><span>{html.escape(r['rok'] or '?')}</span>"
            f"<div class='bar'><i style='width:{100 * r['n'] / mx:.1f}%'>"
            f"<b style='width:{100 * gps / r['n'] if r['n'] else 0:.1f}%'></b></i></div>"
            f"<em>{r['n']} <small>({gps} z GPS)</small></em></div>"
        )
    return "<div class='lata'>" + "".join(wiersze) + "</div>"


def html_raport(d: dict) -> str:
    sekcje = []
    kafle = "".join(
        f"<div class='kafel'><small>{html.escape(NAZWY_RODZAJOW.get(r['rodzaj'], r['rodzaj']))}</small>"
        f"<strong>{r['n']}</strong><span>{rozmiar_txt(r['b'])}</span></div>"
        for r in d["rodzaje"]
    )
    sekcje.append(f"<div class='kafle'>{kafle}</div>")
    for rodz, nazwa in (("zdjecie", "Zdjęcia"), ("film", "Filmy")):
        m = d["media"][rodz]
        if not m["n"]:
            continue
        sekcje.append(
            f"<h2>{nazwa}</h2><p>{m['n']} plików · z lokalizacją GPS: <b>{m['gps']}</b> "
            f"({_proc(m['gps'], m['n'])}) — tylko te dostaną nazwę miejscowości od razu.</p>"
            + _slupki(m["lata"])
            + "<h3>Skąd data</h3>"
            + _tabela(["Źródło", "Plików"], [(NAZWY_ZRODEL.get(z["z"], z["z"]), z["n"]) for z in m["zrodla"]])
            + "<h3>Urządzenia</h3>"
            + _tabela(["Aparat / telefon", "Plików"], [(a["a"], a["n"]) for a in m["aparaty"]])
        )
    mz = d["muzyka"]
    if mz["n"]:
        sekcje.append(
            f"<h2>Muzyka</h2><p>{mz['n']} utworów · z tagami wykonawca+album: {mz['tag'] or 0} "
            f"({_proc(mz['tag'] or 0, mz['n'])}) · wykonawców: {mz['wyk']} · albumów: {mz['alb']}</p>"
        )
    if d["inne_foldery"]:
        sekcje.append(
            "<h2>Pozostałe pliki</h2><p>Zostaną skopiowane z zachowaniem tych nazw folderów.</p>"
            + _tabela(["Folder", "Plików", "Rozmiar"],
                      [(f["f"], f["n"], rozmiar_txt(f["b"])) for f in d["inne_foldery"]])
            + "<h3>Najwięcej miejsca zajmują typy</h3>"
            + _tabela(["Rozszerzenie", "Plików", "Rozmiar"],
                      [(e["e"] or "(brak)", e["n"], rozmiar_txt(e["b"])) for e in d["rozszerzenia_inne"]])
        )
    du = d["duplikaty"]
    info = [
        f"Możliwe duplikaty (identyczny rozmiar): <b>{du['nadmiar']}</b> plików, "
        f"do odzyskania do <b>{rozmiar_txt(du['b'])}</b> — potwierdzimy sumą kontrolną w etapie 2."
    ]
    for p in d["pominiete"]:
        info.append(f"Pominięte śmieci w {html.escape(p['korzen'])}: {p['p']} plików, {p['f']} folderów; "
                    f"błędy dostępu: {p['e']}.")
    sekcje.append("<h2>Porządki</h2>" + "".join(f"<p>{i}</p>" for i in info))
    if d["bledy"]:
        sekcje.append(f"<h3>Nieczytelne metadane ({d['n_bledow']})</h3>"
                      + _tabela(["Plik", "Błąd"], [(b["wzgledna"], b["blad"]) for b in d["bledy"]]))
    zrodla = "".join(
        f"<li>{html.escape(k['korzen'])} — {k['n']} plików, {rozmiar_txt(k['b'])}</li>" for k in d["korzenie"])
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Raport katalogatora</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1d1d1f;--mut:#6b6b70;--kar:#fff;--lin:#e3e3e0;--akc:#2f6fdb;--gps:#1f9d6b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16171a;--fg:#ececef;--mut:#9a9aa2;--kar:#1f2024;--lin:#2e2f35;--akc:#6d9df0;--gps:#3cc28c}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:24px;margin:0 0 4px}} h2{{margin-top:36px;font-size:19px}} h3{{font-size:15px;color:var(--mut)}}
.mut{{color:var(--mut)}} ul{{padding-left:18px}}
.kafle{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:20px}}
.kafel{{background:var(--kar);border:1px solid var(--lin);border-radius:10px;padding:12px}}
.kafel small{{display:block;color:var(--mut)}} .kafel strong{{font-size:22px;display:block}}
table{{border-collapse:collapse;width:100%;background:var(--kar);border:1px solid var(--lin);border-radius:8px;overflow:hidden}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--lin)}} th{{color:var(--mut);font-weight:500}}
td:not(:first-child),th:not(:first-child){{text-align:right;font-variant-numeric:tabular-nums}}
.lata{{display:grid;gap:4px}} .rok{{display:grid;grid-template-columns:48px 1fr 150px;gap:8px;align-items:center}}
.bar{{height:14px}} .bar i{{display:block;height:100%;background:var(--akc);border-radius:3px;opacity:.85}}
.bar b{{display:block;height:100%;background:var(--gps);border-radius:3px}}
.rok em{{font-style:normal;font-variant-numeric:tabular-nums}} .rok small{{color:var(--mut)}}
.leg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px}}
</style></head><body><main>
<h1>Raport ze skanowania</h1><p class="mut">{d['utworzono']}</p><ul>{zrodla}</ul>
<p class="leg mut">Wykresy lat:<i style="background:var(--akc)"></i>wszystkie<i style="background:var(--gps)"></i>z GPS</p>
{''.join(sekcje)}
</main></body></html>"""
