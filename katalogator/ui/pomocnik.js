// 📖 Pomoc: tematy dla każdej zakładki z przykładami (nowy projekt / istniejący / zmienione foldery), skróty klawiszy,
// pytania. Otwierana z menu „?” albo klawiszem F1 — od razu na temacie zakładki, na której jesteś.
// Treść jest stała (pisana tutaj), więc wstawiamy ją jako HTML.
"use strict";

const POMOC = [
  {id: "start", ik: "🚀", tyt: "Pierwsze kroki", tresc: `
<p>Katalogator ma trzy główne zakładki u góry okna:</p>
<ul>
  <li><b>🔭 Przeglądarka</b> — oglądanie: oś czasu, mapa, osoby, albumy, „Tego dnia”. Niczego sama nie przenosi.</li>
  <li><b>🗂 Porządkowanie</b> — kopiuje albo przenosi zdjęcia i filmy do jednej biblioteki: <code>Rok → Miesiąc → Miejsce</code>.</li>
  <li><b>🧹 Sprzątanie</b> — duplikaty i śmieci w istniejących folderach, bez kopiowania i bez nowego drzewa.</li>
</ul>
<p>Do tego <b>🛟 Odzyskiwanie</b> usuniętych plików (menu <b>?</b>) i <b>📱 telefon</b> jako pilot i przeglądarka.</p>
<div class="pm-rada"><b>Od czego zacząć?</b> Masz zdjęcia porozrzucane po dyskach → <a data-pm="porzadkowanie">Porządkowanie</a>.
Chcesz tylko odchudzić folder → <a data-pm="sprzatanie">Sprzątanie</a>. Chcesz oglądać → <a data-pm="przegladarka">Przeglądarka</a>.</div>
<p>Każdą decyzję można cofnąć: przycisk <b>↶ Cofnij</b> w komunikacie na dole, a całe porządkowanie — <b>Cofnij porządkowanie</b>.
Usuwane pliki trafiają najpierw do kosza programu (<i>Odłożone</i>).</p>
<p>Najedź myszką na dowolny przycisk — pojawi się podpowiedź, co robi (i jaki ma skrót klawisza).</p>`},

  {id: "przegladarka", ik: "🔭", tyt: "Przeglądarka", tresc: `
<p>Zdjęcia i filmy z biblioteki i z dowolnych dysków. Widoki na pasku: <b>Oś czasu</b>, <b>Mapa</b>, <b>Kolekcje</b>
(ulubione i albumy), <b>Foldery</b>, <b>Osoby</b>, <b>Serie</b>, <b>🕰 Tego dnia</b> (ta sama data w różnych latach albo
to samo miejsce w różnym czasie).</p>
<ul>
  <li><b>Kliknięcie</b> miniatury — duży podgląd; strzałki ← → przełączają, Esc zamyka.</li>
  <li><b>Ctrl+klik / Shift+klik</b> albo przeciągnięcie myszą po pustym miejscu — zaznaczanie wielu; na dole pasek akcji
  (data, miejsce, typ, album, porównaj, eksport, nazwy, ZIP, usuń).</li>
  <li><b>📍 Miejsce</b> — kliknij na mapie albo wybierz z „Znanych miejsc”. <b>📅 Data</b> — gdy aparat miał zły zegar.</li>
  <li><b>Typ: 📷 Zdjęcie / 📄 Dokument</b> — w uporządkowanej bibliotece plik od razu przenosi się do właściwego folderu.</li>
  <li><b>✏ Edycja</b> (przełącznik na pasku) — obrót, kadrowanie, kolory; zapis jako kopia albo w miejsce oryginału.</li>
  <li><b>Wyszukiwarka</b> rozumie miejscowości, kraje, lata, miesiące, imiona osób i fragmenty nazw — a także
  <b>tekst z dokumentów</b> (np. „faktura”, „PESEL”), jeśli zdjęcie było analizowane w Porządkowaniu lub Sprzątaniu.</li>
</ul>
<h4>Nowy projekt</h4>
<p>Dodaj folder (np. <code>D:\\Telefon\\DCIM</code>) i poczekaj na skan — pierwszy trwa najdłużej, kolejne czytają tylko zmiany.</p>
<p class="pm-prz">Przykład: z telefonu przyszło 3 000 zdjęć. Na osi czasu widać szczyt w lipcu 2022 — klik w słupek pokazuje wakacje.</p>
<h4>Istniejący projekt</h4>
<p>Po uruchomieniu wszystko jest od razu (baza z poprzedniego skanu). Przeglądarka sama odświeża bibliotekę co kilka godzin.</p>
<h4>Foldery się zmieniły</h4>
<p>Przeskanuj folder jeszcze raz. Zdjęcia, których już tam nie ma, znikają z listy, przeniesione pojawiają się w nowym
miejscu. <b>Ulubione i albumy</b> program odnajduje sam (po nazwie, rozmiarze i dacie zdjęcia).
Wyłączony dysk sieciowy niczego nie kasuje — po jego włączeniu wystarczy skan.</p>
<p class="pm-prz">Przykład: przeniosłeś <code>E:\\Stare zdjęcia\\2019</code> do <code>E:\\Archiwum\\2019</code> — po skanie album „Święta 2019” dalej ma swoje zdjęcia.</p>`},

  {id: "porzadkowanie", ik: "🗂", tyt: "Porządkowanie", tresc: `
<p>Kopiuje albo przenosi pliki ze <b>źródeł</b> do <b>miejsca docelowego</b> (biblioteki). Każda kopia jest sprawdzana,
a <b>Cofnij porządkowanie</b> przywraca stan sprzed.</p>
<ol>
  <li><b>Źródła</b> — foldery do uporządkowania; przy każdym <b>K</b> (kopiuj) albo <b>P</b> (przenieś).</li>
  <li><b>Miejsce docelowe</b> — np. <code>Z:\\Uporządkowane</code>.</li>
  <li><b>Skanuj</b> → <b>Duplikaty</b> → zakładki <b>Dokumenty</b>, <b>Podobne</b>, <b>Nie z aparatu</b> (klawisze
  <kbd>1</kbd> zdjęcie, <kbd>2</kbd> dokument, <kbd>3</kbd> śmieci). Zdjęcia podobne do dokumentów program
  <b>czyta (OCR)</b>: odczytany tekst potwierdza dokument albo go wyklucza, a jego początek widać pod miniaturą.</li>
  <li><b>🌳 Drzewo</b> — tu widzisz, gdzie trafi każdy plik; zmieniaj nazwy folderów (ta sama nazwa = scalenie),
  oznaczaj „✓ Przejrzany”.</li>
  <li><b>Uporządkuj pliki…</b> — kopiowanie / przenoszenie. Przy setkach GB przez sieć najlepiej na noc.</li>
</ol>
<h4>Nowy projekt</h4>
<p class="pm-prz">Przykład: źródła <code>D:\\Telefon\\DCIM</code> (K) i <code>E:\\Stare zdjęcia</code> (K), cel
<code>Z:\\Uporządkowane</code>. Skan, duplikaty, przejrzenie dokumentów, Drzewo, <i>Uporządkuj pliki…</i></p>
<h4>Istniejący projekt</h4>
<p><b>Skanuj ponownie (tylko zmiany)</b> — pliki, które już są w bibliotece, plan pokazuje jako
„już w miejscu docelowym” i nie kopiuje ich drugi raz. Przejrzyj w Drzewie tylko nowe foldery.</p>
<h4>Foldery się zmieniły — doskanuj jeden folder i porównaj z biblioteką</h4>
<ol>
  <li>Ustaw ten folder jako źródło (stare źródło, którego już nie ma, usuń z listy). Miejsce docelowe zostaw.</li>
  <li><b>Skanuj</b> — czytany jest tylko ten folder, biblioteki nie skanujesz od nowa.</li>
  <li>W propozycji każdy plik ma stan: <b>„już jest: …”</b> (identyczny plik jest w bibliotece — pominięty),
  <b>nowy</b> (trafi do drzewa) albo <b>już w miejscu docelowym</b> (folder leży w samej bibliotece).</li>
  <li>Chcesz tylko sprawdzić? Nic więcej nie klikaj. Chcesz dołożyć nowe? <i>Uporządkuj pliki…</i></li>
</ol>
<p class="pm-prz">Przykład: <code>E:\\Archiwum\\2019</code> — 800 plików „już jest”, 40 nowych (wakacje). Porządkujesz tylko te 40.</p>
<p><b>Najpierw skopiowałeś, teraz chcesz przenieść?</b> Przełącz źródło z K na P i kliknij <i>Uporządkuj pliki…</i> —
program usunie tylko oryginały, które po porównaniu z kopią już są w bibliotece.</p>`},

  {id: "sprzatanie", ik: "🧹", tyt: "Sprzątanie", tresc: `
<p>Porządek <b>na miejscu</b>: nic nie jest kopiowane, nie powstaje nowe drzewo. Zakładki: <b>Raport</b>,
<b>Duplikaty</b>, <b>🗑 Śmieci</b> (puste pliki, tymczasowe, skróty, miniatury), <b>Podobne</b> (serie i nieostre).</p>
<p>Odłożone pliki trafiają do kosza programu — możesz je przywrócić; na stałe znikają dopiero po potwierdzeniu.</p>
<h4>Nowy projekt</h4>
<p>Projekt sprzątania tworzysz przy otwartym projekcie typu Sprzątanie (nowy projekt dziedziczy tryb bieżącego).
Dodaj folder, <b>Skanuj</b>, zobacz <b>Raport</b>, potem <b>Duplikaty</b> i <b>Śmieci</b>.</p>
<p class="pm-prz">Przykład: w <code>E:\\Stare zdjęcia</code> 800 kopii z pendrive’a i 1 200 plików <code>Thumbs.db</code>.</p>
<h4>Istniejący projekt</h4>
<p><b>Skanuj ponownie (tylko zmiany)</b>, potem w Duplikatach <b>Szukaj ponownie</b>.</p>
<h4>Foldery się zmieniły</h4>
<p>Zawsze najpierw skan — duplikaty liczone są na nowo, więc nie odłożysz „kopii”, która jest już jedynym egzemplarzem.</p>`},

  {id: "odzysk", ik: "🛟", tyt: "Odzyskiwanie", tresc: `
<p>Menu <b>?</b> → <b>Odzyskaj usunięte pliki</b>. Program szuka po kolei: kosze Windows (na wszystkich dyskach),
kosz programu, kopia zapasowa, a na końcu cały dysk / pendrive (Windows File Recovery).</p>
<ul>
  <li>Odzyskane pliki zapisuj <b>na inny dysk</b> niż ten, z którego odzyskujesz (domyślnie folder
  <code>Odzyskane_Katalogator</code>).</li>
  <li>Filmy po odzyskaniu bywają uszkodzone — <b>🛠 Naprawa filmów</b> próbuje je przepisać albo odbudować indeks
  z „wzorca” (działającego filmu z tego samego telefonu / programu).</li>
</ul>
<p class="pm-prz">Przykład: sformatowana karta <code>F:</code> → cały dysk, tylko JPG i MP4, zapis do
<code>D:\\Odzyskane_Katalogator</code>, potem naprawa filmów i obejrzenie w Przeglądarce.</p>`},

  {id: "projekty", ik: "⭐", tyt: "Projekty i nowe pliki", tresc: `
<p>Przycisk z nazwą projektu u góry — osobne źródła, cel, notatki i dziennik. Przełączanie projektów niczego nie kasuje.</p>
<ul>
  <li><b>Nowe pliki</b> (folder przychodzący) — np. zrzuty z telefonu: <i>Sprawdź nowe pliki</i> →
  <i>Przenieś do biblioteki</i>; opcjonalnie codziennie o wybranej godzinie.</li>
  <li><b>Kopia zapasowa</b> biblioteki i sprawdzanie, czy pliki nie są uszkodzone — w ⚙ Ustawieniach.</li>
</ul>`},

  {id: "telefon", ik: "📱", tyt: "Telefon", tresc: `
<p>Przycisk 📱 w nagłówku: kod QR + PIN. Telefon w tej samej sieci Wi-Fi (albo przez Tailscale — z każdego miejsca)
widzi postęp prac, może uruchamiać kroki projektu i przeglądać bibliotekę. Ukryte albumy (np. „Praca”) na telefonie
się nie pokazują. Działa, dopóki Katalogator jest otwarty.</p>`},

  {id: "most", ik: "🌍", tyt: "Most do domu (praca)", tresc: `
<p>Biblioteka z domu na innym komputerze, np. w pracy — <b>bez Tailscale i bez VPN-u na tamtym komputerze</b>.</p>
<ol>
  <li><b>W domu</b>: ⚙ Ustawienia → <b>🌍 Most do domu → Włącz most</b>. Potrzebny jest Tailscale na komputerze w domu.
  Za pierwszym razem Tailscale poprosi o zgodę na Funnel (link w okienku) — zatwierdź i kliknij „Włącz most” jeszcze raz.</li>
  <li>Skopiuj <b>link</b> (adres <code>https://….ts.net/#k=…</code> z kluczem).</li>
  <li><b>W pracy</b>: Katalogator → ⚙ Ustawienia → <b>🌍 Zdalna biblioteka</b> → wklej link → Zapisz. Biblioteka otwiera się
  przyciskiem <b>🌍 Dom</b> u góry (albo od razu po starcie — „Po uruchomieniu: 🌍 Biblioteka w domu”).
  Link działa też w zwykłej przeglądarce, bez instalowania czegokolwiek.</li>
</ol>
<p>Przez most można <b>tylko oglądać</b> — bez usuwania, pilota i pełnego programu. Wejście tylko z kluczem (PIN telefonu
nie działa). Gdy klucz trafi do niewłaściwej osoby: <b>Nowy klucz</b>. Komputer w domu musi być włączony.</p>`},

  {id: "ustawienia", ik: "⚙", tyt: "Ustawienia", tresc: `
<p>Zakładka <b>Ustawienia</b> u góry (albo ⚙) zbiera wszystkie ustawienia w jednym miejscu — każde można tu zmienić:</p>
<ul>
  <li><b>Program</b> — wygląd, co pokazać po starcie, start z Windows, telefon, most do domu, aktualizacje, kopia zapasowa.</li>
  <li><b>Projekt</b> — ustawienia bieżącego projektu: nazwa, notatki, źródła (K — kopiuj / P — przenieś), biblioteka
    (Dokąd), „Mieszkam w”, foldery przychodzące i godzina codziennego sprawdzania. Inny projekt ma własne.</li>
  <li><b>Przeglądarka</b> — dyski i foldery (zestawy), samoczynne odświeżanie, zapamiętany wygląd (kolejność, rodzaj,
    wykres, panele) — zmiany wyglądu widać po następnym otwarciu Przeglądarki.</li>
  <li><b>Porządkowanie i Sprzątanie</b> — opcje zakładek: schowany pasek, podpowiedzi, usuwanie duplikatów na stałe,
    Podobne po jednej grupie, widok „Nie z aparatu”.</li>
</ul>
<p>Spis po lewej przenosi do wybranej części. Wyjście: kliknij inną zakładkę u góry.</p>`},
  {id: "klawisze", ik: "⌨", tyt: "Skróty klawiszy", tresc: `
<table class="pm-tab">
<tr><th colspan="2">Wszędzie</th></tr>
<tr><td><kbd>F1</kbd></td><td>ta pomoc</td></tr>
<tr><th colspan="2">Przeglądarka — duży podgląd</th></tr>
<tr><td><kbd>←</kbd> <kbd>→</kbd></td><td>poprzednie / następne</td></tr>
<tr><td><kbd>Esc</kbd></td><td>zamknij</td></tr>
<tr><td><kbd>+</kbd> <kbd>-</kbd> <kbd>0</kbd></td><td>powiększ / pomniejsz / cały obraz</td></tr>
<tr><td><kbd>F</kbd></td><td>ulubione</td></tr>
<tr><td><kbd>L</kbd></td><td>miejsce (lokalizacja)</td></tr>
<tr><td><kbd>D</kbd></td><td>zdjęcie ⇄ dokument</td></tr>
<tr><td><kbd>E</kbd></td><td>edycja (w trybie Edycja); w edytorze <kbd>C</kbd> kadrowanie, spacja — porównanie z oryginałem</td></tr>
<tr><td><kbd>I</kbd></td><td>właściwości (folder, EXIF, histogram)</td></tr>
<tr><td><kbd>P</kbd></td><td>pokaz slajdów</td></tr>
<tr><td><kbd>Delete</kbd></td><td>usuń (do kosza programu)</td></tr>
<tr><th colspan="2">Przeglądarka — siatka</th></tr>
<tr><td><kbd>Ctrl+A</kbd></td><td>zaznacz wszystko</td></tr>
<tr><th colspan="2">Porównanie serii</th></tr>
<tr><td><kbd>1</kbd>–<kbd>4</kbd></td><td>zostaw / odrzuć ujęcie</td></tr>
<tr><td><kbd>Enter</kbd></td><td>zatwierdź</td></tr>
<tr><th colspan="2">Porządkowanie — Dokumenty, Podobne, Nie z aparatu</th></tr>
<tr><td><kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd></td><td>zdjęcie / dokument / śmieci (i od razu następne)</td></tr>
<tr><td>strzałki, spacja</td><td>przechodzenie, powiększenie</td></tr>
</table>`},

  {id: "pytania", ik: "❓", tyt: "Pytania i problemy", tresc: `
<h4>Czy skan usuwa moje zdjęcia?</h4>
<p>Nie. Skan tylko czyta. Z listy programu znikają wpisy plików, których już nie ma w skanowanym miejscu.</p>
<h4>Przeniosłem foldery ręcznie — muszę skanować wszystko od nowa?</h4>
<p>Nie — <b>Skanuj ponownie (tylko zmiany)</b>. Przeczytane zostaną tylko nowe i zmienione pliki.</p>
<h4>W raporcie są „pliki z nieczytelnymi metadanymi”</h4>
<p>Przy każdym takim pliku jest powód, np. „same zera” (plik uszkodzony przy kopiowaniu lub odzyskiwaniu),
„uszkodzony JPEG” albo „film nie daje się odczytać”. Otwórz go w Eksploratorze — jeśli się nie otwiera,
oryginał jest uszkodzony. Pliki z błędem są czytane jeszcze raz przy każdym skanie.</p>
<h4>Coś nie działa</h4>
<p>Menu <b>?</b> → <b>Zgłoś problem / wyślij raport…</b> — raport (bez zawartości plików) do skopiowania lub
zapisania. Dziennik błędów: <code>%LOCALAPPDATA%\\Katalogator\\logi\\katalogator.log</code>.</p>`},
];

const pm = {okno: null, temat: "start"};

function trybPomocy() {  // temat dla bieżącej zakładki
  if (typeof $ === "function" && $("galeria-nakladka") && !$("galeria-nakladka").hidden) return "przegladarka";
  const b = document.querySelector(".tryby button.akt");
  return {przegladarka: "przegladarka", porzadkowanie: "porzadkowanie", sprzatanie: "sprzatanie",
          ustawienia: "ustawienia"}[b && b.dataset.tryb] || "start";
}

function zbudujPomoc() {
  const n = document.createElement("div"); n.id = "pomoc-okno"; n.className = "pm-tlo"; n.hidden = true;
  n.setAttribute("role", "dialog"); n.setAttribute("aria-label", "Pomoc");
  n.innerHTML = `<div class="pm-okno">
    <div class="pm-gora"><b>📖 Pomoc</b>
      <input type="search" id="pm-szukaj" placeholder="🔍 Szukaj w pomocy: duplikaty, przenieść, telefon…" autocomplete="off">
      <button id="pm-zamknij" title="Zamknij (Esc)">✕</button></div>
    <div class="pm-srodek"><nav id="pm-lista"></nav><div id="pm-tresc" tabindex="-1"></div></div>
    <div class="pm-dol"><label><input type="checkbox" id="pm-podp"> Pokazuj podpowiedzi po najechaniu myszką</label>
      <span class="pm-info">F1 — pomoc do zakładki, na której jesteś</span></div></div>`;
  document.body.append(n);
  const css = document.createElement("style");
  css.textContent = `
.pm-tlo{position:fixed;inset:0;z-index:3000;background:rgba(6,10,21,.45);display:flex;align-items:center;justify-content:center;padding:16px}
.pm-tlo[hidden]{display:none}
.pm-okno{background:var(--panel,#fff);color:var(--fg,#0f172a);border:1px solid var(--lin,#e1e7f0);border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.3);
  width:min(980px,100%);height:min(720px,100%);display:flex;flex-direction:column;overflow:hidden}
.pm-gora{display:flex;gap:12px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--lin,#e1e7f0)}
.pm-gora b{font-size:17px;white-space:nowrap}
#pm-szukaj{flex:1;min-width:0;padding:8px 12px;border-radius:999px;border:1px solid var(--lin,#e1e7f0);background:var(--bg,#f3f6fb);color:inherit;font-size:14px}
#pm-zamknij{border:0;background:none;font-size:18px;color:var(--mut,#5b6b86);border-radius:8px;width:34px;height:34px;cursor:pointer}
.pm-srodek{flex:1;display:flex;min-height:0}
#pm-lista{width:210px;flex:none;border-right:1px solid var(--lin,#e1e7f0);padding:8px;overflow:auto;display:flex;flex-direction:column;gap:2px}
#pm-lista button{display:flex;gap:8px;align-items:center;text-align:left;border:0;background:none;color:inherit;padding:8px 10px;border-radius:9px;font-size:14px;cursor:pointer}
#pm-lista button:hover{background:var(--hover,#f1f5ff)}
#pm-lista button.akt{background:var(--akc-miekki,#e9f0ff);color:var(--akc,#2563eb);font-weight:600}
#pm-lista button small{margin-left:auto;font-size:11px;color:var(--mut,#5b6b86)}
#pm-tresc{flex:1;overflow:auto;padding:18px 24px 28px;font-size:14.5px;line-height:1.6;outline:none}
#pm-tresc h3{margin:0 0 10px;font-size:20px}
#pm-tresc h4{margin:18px 0 4px;font-size:15px}
#pm-tresc ul,#pm-tresc ol{padding-left:22px;margin:6px 0}
#pm-tresc li{margin:3px 0}
#pm-tresc code{background:var(--bg,#f3f6fb);border:1px solid var(--lin,#e1e7f0);border-radius:5px;padding:0 4px;font-size:13px}
#pm-tresc a[data-pm]{color:var(--akc,#2563eb);cursor:pointer;text-decoration:underline}
#pm-tresc kbd{display:inline-block;min-width:18px;padding:0 6px;border-radius:5px;border:1px solid var(--lin,#e1e7f0);border-bottom-width:2px;
  background:var(--bg,#f3f6fb);font:600 12px/20px system-ui,sans-serif;text-align:center}
#pm-tresc mark{background:#fde68a;color:#111;border-radius:3px}
.pm-prz{border-left:3px solid var(--akc,#2563eb);background:var(--akc-miekki,#e9f0ff);padding:7px 12px;border-radius:0 9px 9px 0}
.pm-rada{background:var(--akc-miekki,#e9f0ff);padding:10px 14px;border-radius:10px;margin:10px 0}
.pm-tab{border-collapse:collapse;width:100%}
.pm-tab td,.pm-tab th{padding:5px 8px;border-bottom:1px solid var(--lin,#e1e7f0);text-align:left;vertical-align:top}
.pm-tab th{padding-top:14px;font-size:13px;color:var(--mut,#5b6b86)}
.pm-tab td:first-child{white-space:nowrap;width:1%}
.pm-dol{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:10px 14px;border-top:1px solid var(--lin,#e1e7f0);font-size:13px}
.pm-info{color:var(--mut,#5b6b86)}
.pm-brak{color:var(--mut,#5b6b86)}
@media (max-width:700px){.pm-srodek{flex-direction:column} #pm-lista{width:auto;flex-direction:row;overflow-x:auto;border-right:0;border-bottom:1px solid var(--lin,#e1e7f0)}
  #pm-lista button{white-space:nowrap} #pm-lista button small{display:none} .pm-info{display:none}}`;
  document.head.append(css);
  n.addEventListener("click", e => {
    if (e.target === n) zamknijPomoc();
    const a = e.target.closest("a[data-pm]"); if (a) { e.preventDefault(); pokazTemat(a.dataset.pm); }
  });
  n.querySelector("#pm-zamknij").onclick = zamknijPomoc;
  n.querySelector("#pm-szukaj").oninput = rysujListe;
  const cb = n.querySelector("#pm-podp");
  cb.checked = !window.podpowiedzi || window.podpowiedzi.wlaczone();
  cb.onchange = () => window.podpowiedzi && window.podpowiedzi.ustaw(cb.checked);
  pm.okno = n;
}

const pmTekst = html => { const d = document.createElement("div"); d.innerHTML = html; return d.textContent.toLowerCase(); };
function rysujListe() {
  const q = pm.okno.querySelector("#pm-szukaj").value.trim().toLowerCase();
  const l = pm.okno.querySelector("#pm-lista"); l.replaceChildren();
  const pasujace = POMOC.filter(t => !q || t.tyt.toLowerCase().includes(q) || pmTekst(t.tresc).includes(q));
  for (const t of pasujace) {
    const b = document.createElement("button"); b.className = t.id === pm.temat ? "akt" : "";
    b.innerHTML = `<span>${t.ik}</span><span></span>`; b.children[1].textContent = t.tyt;
    if (q) { const n = pmTekst(t.tresc).split(q).length - 1; if (n) { const s = document.createElement("small"); s.textContent = n; b.append(s); } }
    b.onclick = () => pokazTemat(t.id);
    l.append(b);
  }
  if (q && pasujace.length && !pasujace.some(t => t.id === pm.temat)) return pokazTemat(pasujace[0].id);
  if (!pasujace.length) {
    pm.okno.querySelector("#pm-tresc").innerHTML = '<p class="pm-brak">Nic nie znaleziono. Spróbuj innego słowa — np. „skan”, „album”, „cofnij”.</p>';
    return;
  }
  rysujTresc();
}
function rysujTresc() {
  const t = POMOC.find(x => x.id === pm.temat) || POMOC[0];
  const el = pm.okno.querySelector("#pm-tresc");
  el.innerHTML = `<h3>${t.ik} ${t.tyt}</h3>` + t.tresc;
  const q = pm.okno.querySelector("#pm-szukaj").value.trim();
  if (q.length > 1) {  // podświetlenie szukanego słowa w treści
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), wezly = [];
    while (w.nextNode()) wezly.push(w.currentNode);
    const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    let pierwszy = null;
    for (const node of wezly) {
      if (!re.test(node.data)) continue; re.lastIndex = 0;
      const f = document.createDocumentFragment(); let ost = 0;
      node.data.replace(re, (m, i) => { f.append(node.data.slice(ost, i)); const k = document.createElement("mark"); k.textContent = m; f.append(k); pierwszy = pierwszy || k; ost = i + m.length; });
      f.append(node.data.slice(ost)); node.replaceWith(f);
    }
    if (pierwszy) pierwszy.scrollIntoView({block: "center"});
  } else el.scrollTop = 0;
}
function pokazTemat(id) {
  if (!POMOC.some(t => t.id === id)) return;
  pm.temat = id;
  const sz = pm.okno.querySelector("#pm-szukaj");
  const q = sz.value.trim().toLowerCase(), t = POMOC.find(x => x.id === id);
  if (q && !(t.tyt.toLowerCase().includes(q) || pmTekst(t.tresc).includes(q))) sz.value = "";  // link do tematu spoza wyników
  rysujListe();
}
function otworzPomoc(temat) {
  if (!pm.okno) zbudujPomoc();
  if ($("pomoc-menu")) $("pomoc-menu").hidden = true;
  pm.temat = temat || trybPomocy();
  pm.okno.querySelector("#pm-szukaj").value = "";
  pm.okno.querySelector("#pm-podp").checked = !window.podpowiedzi || window.podpowiedzi.wlaczone();
  pm.okno.hidden = false; rysujListe();
  setTimeout(() => pm.okno.querySelector("#pm-szukaj").focus(), 30);
}
function zamknijPomoc() { if (pm.okno) pm.okno.hidden = true; }

if ($("m-pomoc")) $("m-pomoc").onclick = e => { e.stopPropagation(); otworzPomoc(); };
document.addEventListener("keydown", e => {
  if (e.key === "F1") { e.preventDefault(); otworzPomoc(); }
  else if (e.key === "Escape" && pm.okno && !pm.okno.hidden) { e.stopPropagation(); zamknijPomoc(); }
}, true);
// z Przeglądarki (iframe): F1 albo „📖 Pomoc” w menu ⋯
window.addEventListener("message", e => {
  if (typeof e.data === "string" && e.data.startsWith("pomoc")) otworzPomoc(e.data.split(":")[1] || "przegladarka");
});
// jednorazowo po aktualizacji: gdzie jest pomoc
setTimeout(() => {
  try {
    if (localStorage.getItem("kat_pomoc_info")) return;
    localStorage.setItem("kat_pomoc_info", "1");
  } catch (e) { return; }
  if (typeof toast === "function") toast("📖 Pomoc jest pod klawiszem F1 (i w menu ?). Najedź myszką na przycisk — zobaczysz, co robi.");
}, 4000);
