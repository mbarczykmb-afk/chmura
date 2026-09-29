"""Nazwy miejsc bez internetu: najbliższa miejscowość (PL) lub kraj (za granicą)
oraz polska odmiana w miejscowniku: „w Olkuszu”, „we Wrocławiu”, „na Helu”, „we Włoszech”.

Dane: GeoNames (CC BY 4.0), przygotowane skryptem narzedzia/zbuduj_miejsca.py.
"""

from __future__ import annotations

import gzip
import math
import re
from functools import lru_cache
from pathlib import Path

PLIK = Path(__file__).parent / "dane" / "miejsca.tsv.gz"
_KOMORKA = 0.5  # stopnie
MAX_KM_PL = 25   # dalej od najbliższej miejscowości z listy — i tak podajemy ją, ale szukamy dalej niż 1 komórkę

# --- kraje (miejscownik z przyimkiem) -------------------------------------------
KRAJE = {
    "PL": "w Polsce", "HR": "w Chorwacji", "IT": "we Włoszech", "ES": "w Hiszpanii", "GR": "w Grecji",
    "EG": "w Egipcie", "TR": "w Turcji", "DE": "w Niemczech", "CZ": "w Czechach", "SK": "na Słowacji",
    "UA": "w Ukrainie", "HU": "na Węgrzech", "LT": "na Litwie", "LV": "na Łotwie", "BY": "na Białorusi",
    "AT": "w Austrii", "CH": "w Szwajcarii", "FR": "we Francji", "GB": "w Wielkiej Brytanii",
    "IE": "w Irlandii", "NL": "w Holandii", "BE": "w Belgii", "DK": "w Danii", "SE": "w Szwecji",
    "NO": "w Norwegii", "FI": "w Finlandii", "EE": "w Estonii", "PT": "w Portugalii", "BG": "w Bułgarii",
    "RO": "w Rumunii", "SI": "w Słowenii", "ME": "w Czarnogórze", "AL": "w Albanii",
    "BA": "w Bośni i Hercegowinie", "RS": "w Serbii", "MK": "w Macedonii Północnej", "CY": "na Cyprze",
    "MT": "na Malcie", "IS": "na Islandii", "US": "w USA", "CA": "w Kanadzie", "MX": "w Meksyku",
    "TN": "w Tunezji", "MA": "w Maroku", "TH": "w Tajlandii", "AE": "w Emiratach Arabskich",
    "IL": "w Izraelu", "JP": "w Japonii", "CN": "w Chinach", "IN": "w Indiach", "LK": "na Sri Lance",
    "ID": "w Indonezji", "VN": "w Wietnamie", "DO": "na Dominikanie", "CU": "na Kubie",
    "BR": "w Brazylii", "AR": "w Argentynie", "AU": "w Australii", "NZ": "w Nowej Zelandii",
    "ZA": "w RPA", "KE": "w Kenii", "TZ": "w Tanzanii", "MV": "na Malediwach", "GE": "w Gruzji",
    "AM": "w Armenii", "JO": "w Jordanii", "LU": "w Luksemburgu", "MC": "w Monako", "VA": "w Watykanie",
    "SM": "w San Marino", "AD": "w Andorze", "LI": "w Liechtensteinie", "RU": "w Rosji",
    "KZ": "w Kazachstanie", "MD": "w Mołdawii", "SG": "w Singapurze", "KR": "w Korei Południowej",
    "QA": "w Katarze", "OM": "w Omanie", "SA": "w Arabii Saudyjskiej", "CV": "na Wyspach Zielonego Przylądka",
    "XK": "w Kosowie", "GI": "na Gibraltarze", "FO": "na Wyspach Owczych", "GL": "na Grenlandii",
    "PE": "w Peru", "CL": "w Chile", "CO": "w Kolumbii", "CR": "w Kostaryce", "PH": "na Filipinach",
    "MY": "w Malezji", "KH": "w Kambodży", "NP": "w Nepalu", "UZ": "w Uzbekistanie", "AZ": "w Azerbejdżanie",
    "MU": "na Mauritiusie", "SC": "na Seszelach", "MG": "na Madagaskarze", "ZW": "w Zimbabwe",
    "NA": "w Namibii", "BW": "w Botswanie", "SN": "w Senegalu", "GH": "w Ghanie", "NG": "w Nigerii",
    "ET": "w Etiopii", "LB": "w Libanie", "KW": "w Kuwejcie", "BH": "w Bahrajnie", "IR": "w Iranie",
    "PK": "w Pakistanie", "MN": "w Mongolii", "TW": "na Tajwanie", "HK": "w Hongkongu",
}

# --- polski miejscownik ----------------------------------------------------------
WYJATKI = {
    "Łódź": "w Łodzi", "Białystok": "w Białymstoku", "Bydgoszcz": "w Bydgoszczy", "Gniezno": "w Gnieźnie",
    "Zakopane": "w Zakopanem", "Wisła": "w Wiśle", "Hel": "na Helu", "Kielce": "w Kielcach",
    "Tychy": "w Tychach", "Sopot": "w Sopocie", "Kraków": "w Krakowie", "Warszawa": "w Warszawie",
    "Wrocław": "we Wrocławiu", "Włocławek": "we Włocławku", "Szczyrk": "w Szczyrku", "Opole": "w Opolu",
    "Busko-Zdrój": "w Busku-Zdroju", "Krynica-Zdrój": "w Krynicy-Zdroju", "Świnoujście": "w Świnoujściu",
    "Kazimierz Dolny": "w Kazimierzu Dolnym", "Bielsko-Biała": "w Bielsku-Białej",
    "Kędzierzyn-Koźle": "w Kędzierzynie-Koźlu", "Mielec": "w Mielcu", "Żywiec": "w Żywcu",
    "Sosnowiec": "w Sosnowcu", "Pruszcz Gdański": "w Pruszczu Gdańskim", "Łeba": "w Łebie",
    "Karpacz": "w Karpaczu", "Szklarska Poręba": "w Szklarskiej Porębie", "Ustrzyki Dolne": "w Ustrzykach Dolnych",
    "Polanica-Zdrój": "w Polanicy-Zdroju", "Kudowa-Zdrój": "w Kudowie-Zdroju", "Rabka-Zdrój": "w Rabce-Zdroju",
    "Chełm": "w Chełmie", "Legnica": "w Legnicy", "Łomża": "w Łomży", "Ełk": "w Ełku",
    "Limanowa": "w Limanowej", "Konstancin-Jeziorna": "w Konstancinie-Jeziornie",
}
_SLOWA = {"Zdrój": "Zdroju", "Sól": "Soli", "Wieś": "Wsi", "Łódź": "Łodzi"}
_NA = {"Hel", "Kasprowy Wierch", "Śnieżka", "Rysy", "Giewont"}
# Rzeczowniki, które wyglądają jak przymiotniki (w nazwach wieloczłonowych)
_RZECZOWNIKI = {"Dąbrowa", "Częstochowa", "Warszawa", "Rawa", "Mszana", "Środa", "Huta", "Ruda", "Wola",
                "Góra", "Góry", "Kalwaria", "Lipa", "Poręba", "Iława", "Mława", "Brzeg", "Wieś", "Sól"}
_PRZYM = re.compile(r"(ski|cki|dzki|ny|ły|owy|czy|wy|dni|ni)$|(ska|cka|dzka|[^iy]na|ła|owa|cza|nia|wa)$|(skie|ckie|dzkie|ne|łe|owe|cze)$")


def _czy_przymiotnik(w: str) -> bool:
    return w not in _RZECZOWNIKI and bool(_PRZYM.search(w))


def _przymiotnik(w: str, mnoga: bool) -> str:
    """Miejscownik przymiotnika: Nowy→Nowym, Zielona→Zielonej, Podlaska→Podlaskiej, Śląskie→Śląskich."""
    if w.endswith("a"):
        return w[:-1] + ("iej" if w.endswith(("ka", "ga")) else "ej")
    if w.endswith(("y", "i")):
        return w + "m"
    if w.endswith("e"):
        if mnoga:
            return w[:-1] + ("ch" if w.endswith("ie") else "ych")
        return w + "m"
    return w


def _rzeczownik(w: str) -> str | None:
    """Miejscownik rzeczownika — nazwy miejscowości. None, gdy nie znamy reguły."""
    if w in _SLOWA:
        return _SLOWA[w]
    reguly = [
        # liczba mnoga
        (r"(ice|yce)$", lambda m: w[:-1] + "ach"), (r"ce$", lambda m: w[:-1] + "ach"),
        (r"(szcze|cze)$", lambda m: w[:-1] + "ach"),
        (r"(oje|aje)$", lambda m: w[:-1] + "ach"),
        (r"(ki|gi)$", lambda m: w[:-1] + "ach"), (r"(ny|ry|wy|ty|dy|by|py|my|sy|ły|chy)$", lambda m: w[:-1] + "ach"),
        # nijaki
        (r"(ko|go|cho)$", lambda m: w[:-1] + "u"), (r"wo$", lambda m: w[:-1] + "ie"),
        (r"sło$", lambda m: w[:-3] + "śle"), (r"(?<!r)zło$", lambda m: w[:-3] + "źle"),
        (r"sno$", lambda m: w[:-3] + "śnie"), (r"(?<!r)zno$", lambda m: w[:-3] + "źnie"),
        (r"no$", lambda m: w[:-1] + "ie"), (r"sto$", lambda m: w[:-3] + "ście"), (r"to$", lambda m: w[:-2] + "cie"),
        (r"ło$", lambda m: w[:-2] + "le"), (r"ro$", lambda m: w[:-2] + "rze"), (r"do$", lambda m: w[:-2] + "dzie"),
        (r"(mo|bo|po)$", lambda m: w[:-1] + "ie"),
        (r"(le|cie|ście|nie|rze|ie)$", lambda m: w[:-1] + "u"),
        (r"ne$", lambda m: w + "m"),
        # żeński -a
        (r"nia$", lambda m: w[:-1]), (r"ja$", lambda m: w[:-1] + "i"), (r"ia$", lambda m: w[:-1]),
        (r"ka$", lambda m: w[:-2] + "ce"), (r"ga$", lambda m: w[:-2] + "dze"), (r"cha$", lambda m: w[:-3] + "sze"),
        (r"sła$", lambda m: w[:-3] + "śle"), (r"ła$", lambda m: w[:-2] + "le"), (r"ra$", lambda m: w[:-2] + "rze"),
        (r"sta$", lambda m: w[:-3] + "ście"), (r"ta$", lambda m: w[:-2] + "cie"), (r"da$", lambda m: w[:-2] + "dzie"),
        (r"(ca|cza|sza|ża|rza|dża)$", lambda m: w[:-1] + "y"), (r"la$", lambda m: w[:-1] + "i"),
        (r"(na|wa|ba|pa|ma|fa|sa|za)$", lambda m: w[:-1] + "ie"),
        # męski
        (r"ów$", lambda m: w[:-2] + "owie"), (r"ław$", lambda m: w + "iu"), (r"w$", lambda m: w + "ie"),
        (r"ek$", lambda m: w[:-2] + "ku"), (r"iec$", lambda m: w[:-3] + "cu"), (r"ec$", lambda m: w[:-2] + "cu"),
        (r"(k|g|ch|sz|cz|ż|rz|dż|dz|l|j|c|h)$", lambda m: w + "u"),
        (r"ń$", lambda m: w[:-1] + "niu"), (r"ś$", lambda m: w[:-1] + "siu"), (r"ć$", lambda m: w[:-1] + "ciu"),
        (r"ź$", lambda m: w[:-1] + "ziu"),
        (r"st$", lambda m: w[:-2] + "ście"), (r"t$", lambda m: w[:-1] + "cie"), (r"d$", lambda m: w[:-1] + "dzie"),
        (r"r$", lambda m: w[:-1] + "rze"), (r"ł$", lambda m: w[:-1] + "le"),
        (r"(n|b|p|f|s|z)$", lambda m: w + "ie"), (r"m$", lambda m: w + "iu"),
    ]
    for wzor, f in reguly:
        m = re.search(wzor, w)
        if m:
            return f(m)
    return None


def _przyimek(fraza: str) -> str:
    """„we” przed w/f + spółgłoska (we Wrocławiu, we Władysławowie), inaczej „w”."""
    if re.match(r"[WwFf][^aąeęioóuyAĄEĘIOÓUY]", fraza):
        return "we"
    return "w"


def _mnoga(w: str) -> bool:
    return bool(re.search(r"(ice|yce|ce|cze|oje|ki|gi|ny|ry|wy|ty|dy|by|py|my|sy|ły|chy|ory|óry)$", w))


@lru_cache(maxsize=4096)
def miejscownik(nazwa: str) -> tuple[str, bool]:
    """Zwraca („w Olkuszu”, pewne?). Gdy reguła nieznana: („– Olkusz”, False)."""
    if nazwa in WYJATKI:
        return WYJATKI[nazwa], True
    czesci = re.split(r"(\s+|-)", nazwa)
    slowa = [c for c in czesci if c.strip(" -")]
    # „Kazimierz nad Wisłą”: odmieniamy tylko część przed przyimkiem
    reszta = ""
    for i, c in enumerate(czesci):
        if c in ("nad", "pod", "na", "przy", "k."):
            reszta = "".join(czesci[i - 1:]) if i else ""
            czesci = czesci[:i - 1]
            slowa = [c for c in czesci if c.strip(" -")]
            break
    wielo = len(slowa) > 1
    przym = {s_: wielo and _czy_przymiotnik(s_) for s_ in slowa}
    glowne = [s_ for s_ in slowa if not przym[s_]]
    mnoga = bool(glowne) and _mnoga(glowne[0])
    wynik, pewne = [], True
    for c in czesci:
        if not c.strip(" -"):
            wynik.append(c)
        elif przym[c]:
            wynik.append(_przymiotnik(c, mnoga))
        else:
            r = _rzeczownik(c)
            if r is None:
                pewne, r = False, c
            wynik.append(r)
    fr = "".join(wynik) + reszta
    if not pewne:
        return f"– {nazwa}", False
    przyimek = "na" if nazwa in _NA else _przyimek(fr)
    return f"{przyimek} {fr}", True


# --- wyszukiwanie najbliższego miejsca -------------------------------------------------

@lru_cache(maxsize=1)
def _siatka() -> dict:
    siatka: dict[tuple[int, int], list] = {}
    with gzip.open(PLIK, "rt", encoding="utf-8") as f:
        for linia in f:
            cz = linia.rstrip("\n").split("\t")
            if len(cz) < 3:
                continue
            lat, lon = float(cz[0]), float(cz[1])
            nazwa = cz[3] if len(cz) > 3 and cz[3] else None
            klucz = (int(math.floor(lat / _KOMORKA)), int(math.floor(lon / _KOMORKA)))
            siatka.setdefault(klucz, []).append((lat, lon, cz[2], nazwa))
    return siatka


def _odl(lat1, lon1, lat2, lon2) -> float:
    return math.hypot((lat1 - lat2) * 111.2, (lon1 - lon2) * 111.2 * math.cos(math.radians(lat1)))


def najblizsze(lat: float, lon: float) -> tuple[str, str | None]:
    """(kod_kraju, nazwa_miejscowości_PL albo None)."""
    siatka = _siatka()
    kl = (int(math.floor(lat / _KOMORKA)), int(math.floor(lon / _KOMORKA)))
    najlepszy, naj_pl = None, None
    for promien in range(0, 6):
        for dy in range(-promien, promien + 1):
            for dx in range(-promien, promien + 1):
                if max(abs(dy), abs(dx)) != promien:
                    continue
                for p in siatka.get((kl[0] + dy, kl[1] + dx), ()):
                    d = _odl(lat, lon, p[0], p[1])
                    if najlepszy is None or d < najlepszy[0]:
                        najlepszy = (d, p)
                    if p[2] == "PL" and p[3] and (naj_pl is None or d < naj_pl[0]):
                        naj_pl = (d, p)
        if najlepszy and najlepszy[0] < (promien) * _KOMORKA * 111.2 * 0.5 and (
                najlepszy[1][2] != "PL" or naj_pl):
            break
    if najlepszy is None:
        return "", None
    kraj = najlepszy[1][2]
    if kraj == "PL" and naj_pl:
        return "PL", naj_pl[1][3]
    return kraj, None


@lru_cache(maxsize=65536)
def _etykieta_zaokr(lat: float, lon: float) -> str:
    kraj, nazwa = najblizsze(lat, lon)
    if kraj == "PL" and nazwa:
        return nazwa
    return "@" + (kraj or "?")


def etykieta(lat: float, lon: float) -> str:
    """Identyfikator miejsca: nazwa miejscowości (PL) albo „@KOD” kraju."""
    return _etykieta_zaokr(round(lat, 3), round(lon, 3))


def fraza(etyk: str) -> str:
    """„w Olkuszu”, „we Włoszech”, „– Brzeszcze” (gdy nie wiemy jak odmienić)."""
    if etyk.startswith("@"):
        return KRAJE.get(etyk[1:], "za granicą")
    return miejscownik(etyk)[0]


# --- miejsce z nazwy folderu (zdjęcia bez GPS, np. „2004 Zakopane”, „Wakacje Hel”, „Chorwacja 2019”) ----------
KRAJE_NAZWY = {
    "włochy": "IT", "chorwacja": "HR", "hiszpania": "ES", "grecja": "GR", "egipt": "EG", "turcja": "TR",
    "niemcy": "DE", "czechy": "CZ", "słowacja": "SK", "ukraina": "UA", "węgry": "HU", "litwa": "LT",
    "łotwa": "LV", "austria": "AT", "szwajcaria": "CH", "francja": "FR", "anglia": "GB", "londyn": "GB",
    "irlandia": "IE", "holandia": "NL", "belgia": "BE", "dania": "DK", "szwecja": "SE", "norwegia": "NO",
    "finlandia": "FI", "estonia": "EE", "portugalia": "PT", "bułgaria": "BG", "rumunia": "RO",
    "słowenia": "SI", "czarnogóra": "ME", "albania": "AL", "serbia": "RS", "cypr": "CY", "malta": "MT",
    "islandia": "IS", "usa": "US", "tunezja": "TN", "maroko": "MA", "tajlandia": "TH", "dubaj": "AE",
    "izrael": "IL", "japonia": "JP", "chiny": "CN", "indie": "IN", "wietnam": "VN", "dominikana": "DO",
    "kuba": "CU", "gruzja": "GE", "madera": "PT", "kreta": "GR", "rodos": "GR", "korfu": "GR",
    "zakynthos": "GR", "teneryfa": "ES", "majorka": "ES", "sycylia": "IT", "rzym": "IT", "paryż": "FR",
    "praga": "CZ", "wiedeń": "AT", "berlin": "DE", "barcelona": "ES", "wenecja": "IT", "budapeszt": "HU",
    "wilno": "LT", "lwów": "UA", "zanzibar": "TZ", "malediwy": "MV", "kanada": "CA", "meksyk": "MX",
}
# jednowyrazowe nazwy miejscowości, które są też zwykłymi słowami — z nazwy folderu ich nie bierzemy
_ZWYKLE_SLOWA = {"góra", "wola", "dom", "las", "ruda", "huta", "środa", "rawa", "zdjęcia", "wakacje", "ferie",
                 "morze", "góry", "kolonia", "osiedle", "nowa", "nowe", "stare", "most", "brzeg", "wieś", "sól",
                 "zdrój", "gród", "kamień", "łąka", "piła", "jawor", "lipiec", "maj", "marzec"}
_MIN_LUDNOSC = 2500
# małe, ale popularne miejsca wyjazdów — rozpoznawane mimo małej liczby mieszkańców
_TURYSTYCZNE = {"hel", "jurata", "chałupy", "dębki", "rewal", "rowy", "mielno", "sarbinowo", "pobierowo",
                "krynica morska", "jastrzębia góra", "białka tatrzańska", "bukowina tatrzańska", "poronin",
                "kościelisko", "wetlina", "cisna", "polańczyk", "solina", "szczawnica", "łeba", "jastarnia",
                "karpacz", "mikołajki", "ustka", "władysławowo", "międzyzdroje", "świeradów-zdrój", "korbielów",
                "zawoja", "rabka-zdrój", "ustrzyki dolne", "szklarska poręba", "krynica-zdrój", "ełk"}


@lru_cache(maxsize=1)
def _indeks_nazw() -> dict[str, str]:
    """„zakopane” -> „Zakopane” (także bez polskich liter: „krakow” -> „Kraków”)."""
    ind: dict[str, tuple[int, str]] = {}
    with gzip.open(PLIK, "rt", encoding="utf-8") as f:
        for linia in f:
            cz = linia.rstrip("\n").split("\t")
            if len(cz) < 5 or cz[2] != "PL" or not cz[3]:
                continue
            try:
                lud = int(cz[4])
            except ValueError:
                continue
            if (lud < _MIN_LUDNOSC and cz[3].lower() not in _TURYSTYCZNE) or cz[3].lower() in _ZWYKLE_SLOWA:
                continue
            for k in {cz[3].lower(), _bez_ogonkow(cz[3].lower())}:
                if k not in ind or ind[k][0] < lud:
                    ind[k] = (lud, cz[3])
    return {k: v[1] for k, v in ind.items()}


def _bez_ogonkow(s: str) -> str:
    return s.translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


_SLOWO = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)?")


def z_folderu(sciezka_wzgledna: str) -> str | None:
    """Etykieta miejsca (jak etykieta()) z nazw folderów — od najbliższego pliku w górę; None, gdy brak."""
    ind = _indeks_nazw()
    czesci = re.split(r"[\\/]+", sciezka_wzgledna)[:-1]
    for folder in reversed(czesci):
        slowa = _SLOWO.findall(folder)
        for dl in (3, 2, 1):  # najpierw dłuższe nazwy: „Szklarska Poręba”, „Bielsko-Biała”
            for i in range(len(slowa) - dl + 1):
                fraza_ = " ".join(slowa[i:i + dl]).lower()
                if fraza_ in KRAJE_NAZWY and dl == 1:
                    return "@" + KRAJE_NAZWY[fraza_]
                if dl == 1 and len(fraza_) < 4 and fraza_ not in _TURYSTYCZNE:
                    continue
                trafienie = ind.get(fraza_) or ind.get(_bez_ogonkow(fraza_))
                if trafienie:
                    return trafienie
    return None
