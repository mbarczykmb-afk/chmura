import pytest

from katalogator import miejsca

ODMIANA = [
    ("Olkusz", "w Olkuszu"), ("Gdańsk", "w Gdańsku"), ("Poznań", "w Poznaniu"), ("Toruń", "w Toruniu"),
    ("Lublin", "w Lublinie"), ("Radom", "w Radomiu"), ("Tarnów", "w Tarnowie"), ("Katowice", "w Katowicach"),
    ("Siedlce", "w Siedlcach"), ("Suwałki", "w Suwałkach"), ("Puławy", "w Puławach"), ("Gdynia", "w Gdyni"),
    ("Częstochowa", "w Częstochowie"), ("Ustka", "w Ustce"), ("Wieliczka", "w Wieliczce"),
    ("Władysławowo", "we Władysławowie"), ("Jastarnia", "w Jastarni"), ("Zamość", "w Zamościu"),
    ("Kalisz", "w Kaliszu"), ("Elbląg", "w Elblągu"), ("Olsztyn", "w Olsztynie"), ("Kołobrzeg", "w Kołobrzegu"),
    ("Nowy Sącz", "w Nowym Sączu"), ("Nowy Targ", "w Nowym Targu"), ("Zielona Góra", "w Zielonej Górze"),
    ("Gorzów Wielkopolski", "w Gorzowie Wielkopolskim"), ("Biała Podlaska", "w Białej Podlaskiej"),
    ("Stalowa Wola", "w Stalowej Woli"), ("Ciechocinek", "w Ciechocinku"), ("Kłodzko", "w Kłodzku"),
    ("Legionowo", "w Legionowie"), ("Międzyzdroje", "w Międzyzdrojach"), ("Mikołajki", "w Mikołajkach"),
    ("Giżycko", "w Giżycku"), ("Augustów", "w Augustowie"), ("Sandomierz", "w Sandomierzu"),
    ("Kazimierz Dolny", "w Kazimierzu Dolnym"), ("Świnoujście", "w Świnoujściu"), ("Łeba", "w Łebie"),
    ("Krynica Morska", "w Krynicy Morskiej"), ("Bukowina Tatrzańska", "w Bukowinie Tatrzańskiej"),
    ("Nowa Sól", "w Nowej Soli"), ("Chorzów", "w Chorzowie"), ("Wadowice", "w Wadowicach"),
    ("Oświęcim", "w Oświęcimiu"), ("Brzeszcze", "w Brzeszczach"), ("Bochnia", "w Bochni"),
    ("Limanowa", "w Limanowej"), ("Jasło", "w Jaśle"), ("Krosno", "w Krośnie"), ("Sanok", "w Sanoku"),
    ("Przemyśl", "w Przemyślu"), ("Wągrowiec", "w Wągrowcu"), ("Łańcut", "w Łańcucie"), ("Sopot", "w Sopocie"),
    ("Hel", "na Helu"), ("Opole", "w Opolu"), ("Jelenia Góra", "w Jeleniej Górze"),
    ("Dąbrowa Górnicza", "w Dąbrowie Górniczej"), ("Ruda Śląska", "w Rudzie Śląskiej"),
    ("Piekary Śląskie", "w Piekarach Śląskich"), ("Tarnowskie Góry", "w Tarnowskich Górach"),
    ("Skarżysko-Kamienna", "w Skarżysku-Kamiennej"), ("Ostrów Wielkopolski", "w Ostrowie Wielkopolskim"),
    ("Grudziądz", "w Grudziądzu"), ("Inowrocław", "w Inowrocławiu"), ("Wałbrzych", "w Wałbrzychu"),
    ("Kutno", "w Kutnie"), ("Piła", "w Pile"), ("Wejherowo", "w Wejherowie"), ("Iława", "w Iławie"),
    ("Ostróda", "w Ostródzie"), ("Nysa", "w Nysie"), ("Zgierz", "w Zgierzu"), ("Zabrze", "w Zabrzu"),
    ("Rybnik", "w Rybniku"), ("Zawiercie", "w Zawierciu"), ("Bolesławiec", "w Bolesławcu"),
    ("Szczawnica", "w Szczawnicy"), ("Jaworzno", "w Jaworznie"), ("Kęty", "w Kętach"), ("Pszczyna", "w Pszczynie"),
    ("Łódź", "w Łodzi"), ("Zakopane", "w Zakopanem"), ("Wrocław", "we Wrocławiu"), ("Busko-Zdrój", "w Busku-Zdroju"),
    ("Lądek-Zdrój", "w Lądku-Zdroju"), ("Strzelce Opolskie", "w Strzelcach Opolskich"),
]


@pytest.mark.parametrize("nazwa,oczek", ODMIANA)
def test_odmiana(nazwa, oczek):
    assert miejsca.miejscownik(nazwa)[0] == oczek


def test_nieznana_forma_bez_odmiany():
    wynik, pewne = miejsca.miejscownik("Xyzqq")
    assert wynik.startswith("w ") or wynik == "– Xyzqq"


@pytest.mark.parametrize("lat,lon,oczek", [
    (50.2811, 19.5625, "Olkusz"),        # rynek w Olkuszu
    (52.2297, 21.0122, "Warszawa"),      # centrum
    (52.1850, 21.0280, "Warszawa"),      # Mokotów -> Warszawa
    (54.6080, 18.8010, "Hel"),
    (49.2992, 19.9496, "Zakopane"),
    (54.4416, 18.5601, "Sopot"),
    (50.0647, 19.9450, "Kraków"),
])
def test_miejscowosci_pl(lat, lon, oczek):
    assert miejsca.etykieta(lat, lon) == oczek


@pytest.mark.parametrize("lat,lon,fraza", [
    (41.9028, 12.4964, "we Włoszech"), (43.5081, 16.4402, "w Chorwacji"), (50.0755, 14.4378, "w Czechach"),
    (27.2579, 33.8116, "w Egipcie"), (48.8566, 2.3522, "we Francji"), (49.0, 20.3, "na Słowacji"),
])
def test_kraje(lat, lon, fraza):
    assert miejsca.fraza(miejsca.etykieta(lat, lon)) == fraza
