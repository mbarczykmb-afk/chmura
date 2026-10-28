// ✈ Podróże — dziennik wypraw jako część Katalogatora: aplikacja (ui/podroze/) jest serwowana przez serwer programu pod /podroze/
// i pokazywana w ramce. Dane podróży leżą w folderze danych programu; tu: import z dotychczasowego folderu projektu, foldery
// ze zdjęciami i przekazywanie motywu do aplikacji.
"use strict";

const pod = {d: null, zaladowana: false, odpytuje: null};

// Motyw Katalogatora → aplikacja w ramce (katalogator-motyw.js): zmienne --kat-* i atrybut data-katalogator-motyw.
function motywPodrozy() {
  const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim();
  return {typ: "katalogator-motyw", motyw: cs.colorScheme.includes("dark") ? "dark" : "light",
          kolory: {"--kat-bg": v("--bg"), "--kat-panel": v("--panel"), "--kat-fg": v("--fg"), "--kat-mut": v("--mut"),
                   "--kat-lin": v("--lin"), "--kat-akc": v("--akc"), "--kat-akc-fg": v("--akc-fg")}};
}
function wyslijMotywPodrozy() {
  const r = $("podroze-ramka");
  if (pod.zaladowana && r.contentWindow) r.contentWindow.postMessage(motywPodrozy(), location.origin);
}
window.addEventListener("message", e => {   // aplikacja prosi o motyw po załadowaniu
  if (e.origin === location.origin && e.source === $("podroze-ramka").contentWindow && e.data && e.data.typ === "katalogator-gotowe")
    wyslijMotywPodrozy();
});
new MutationObserver(wyslijMotywPodrozy).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme", "style"]});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", wyslijMotywPodrozy);

const adresPodrozy = () => `/podroze/?t=${encodeURIComponent(TOKEN)}`;

function pokazRamkePodrozy() {
  const r = $("podroze-ramka");
  $("podroze-konfig").hidden = true; r.hidden = false;
  if (!pod.zaladowana) { r.src = adresPodrozy(); pod.zaladowana = true; }   // aplikacja zostaje załadowana między zakładkami
  const d = pod.d;
  $("podroze-opis").textContent = d && d.wyprawy ? `${d.wyprawy} wypraw · dane z ${dataCzas(d.zaimportowano)}` : "";
}
function pokazKonfiguracjePodrozy() {
  $("podroze-ramka").hidden = true; $("podroze-konfig").hidden = false;
  $("podroze-opis").textContent = "dane i zdjęcia";
  const t = $("podroze-konfig-tresc"); t.replaceChildren();
  t.append(sekcjaPodrozy(pod.d, async () => { await odswiezPodroze(); pokazKonfiguracjePodrozy(); }));
}
async function odswiezPodroze() { pod.d = await api("/api/podroze"); return pod.d; }

async function otworzPodroze() {
  $("pomoc-menu").hidden = true;
  zamknijUstawienia();
  if (!$("galeria-nakladka").hidden) { zamknijGalerie(); trybGalerii = false; }
  $("podroze-nakladka").hidden = false; trybPodroze = true; oznaczTryby();
  try { await odswiezPodroze(); } catch (e) { toast(e.message); return; }
  if (pod.d.ma_dane && !pod.d.import.trwa) pokazRamkePodrozy(); else pokazKonfiguracjePodrozy();
}

// Sekcja Podróży — w zakładce (gdy brak danych) i w Ustawieniach.
function sekcjaPodrozy(d, odswiez) {
  const s = sekcja("✈ Podróże — dziennik wypraw");
  const zmien = async (dane, komunikat) => {
    try { pod.d = await api("/api/podroze", dane); if (komunikat) toast(komunikat); }
    catch (e) { toast(e.message); }
    odswiez();
  };
  s.append(el("div", {className: "info", innerHTML: "Wyprawy z osi czasu Google, trasy GPS, szczyty, rezerwacje i zdjęcia — <b>jako część Katalogatora</b>, bez osobnego programu. " +
    "<b>Dane podróży zostają na tym komputerze</b> (folder danych programu) — Katalogator ich nie wysyła; zakładka nie jest dostępna przez most do domu ani przez telefon."}));

  // 📥 dane
  const imp = d.import || {};
  s.append(el("h4", {textContent: "Dane podróży", style: "margin:6px 0 0"}));
  s.append(wiersz(el("span", {className: d.ma_dane ? "ok" : "info", textContent: d.ma_dane
    ? `✓ ${d.wyprawy} wypraw, ${d.rozmiar_mb} MB · zaimportowano ${dataCzas(d.zaimportowano)}` : "Brak danych — zaimportuj je z dotychczasowego folderu projektu."}),
    d.ma_dane ? przyc("Otwórz Podróże", () => otworzPodroze(), "glowny") : null));
  const folder = el("input", {type: "text", value: d.folder_importu || "", id: "podroze-folder",
                              placeholder: d.podpowiedz || "C:\\…\\google-timeline-travels"});
  folder.onchange = () => zmien({folder_importu: folder.value.trim()});
  s.append(wiersz(etyk("Folder projektu"), folder,
    przyc("Wybierz…", () => otworzWyborFolderu("Folder z danymi Timeline Travels (z plikiem sample-trips.json)", d.folder_importu || "",
                                               f => zmien({folder_importu: f})))));
  if (!d.folder_importu && d.podpowiedz)
    s.append(wiersz(el("span", {className: "info", textContent: "Znaleziono projekt: " + d.podpowiedz}),
                    przyc("Użyj tego folderu", () => zmien({folder_importu: d.podpowiedz}), "glowny")));
  const pasek = imp.trwa ? el("div", {className: "info", textContent: `⏳ ${imp.komunikat} (${imp.zrobione} z ${imp.wszystkie})`}) : null;
  s.append(wiersz(przyc(d.ma_dane ? "↻ Importuj ponownie" : "▶ Importuj dane", () => zmien({akcja: "importuj", folder_importu: folder.value.trim()}), d.ma_dane ? "" : "glowny",
                       "Kopiuje sample-trips.json, zdjęcia dopasowane do wypraw i miniatury do folderu danych programu; oryginały zostają"),
                  d.ma_dane ? przyc("Usuń dane", async () => {
                    if (await oknoTak("Usunąć dane Podróży z Katalogatora?\n\nOryginalny folder projektu zostaje nietknięty — dane możesz zaimportować jeszcze raz.")) zmien({akcja: "usun-dane"}, "Usunięto dane Podróży.");
                  }) : null, pasek));
  if (imp.blad) s.append(el("div", {className: "zle", textContent: imp.blad}));
  else if (!imp.trwa && imp.komunikat) s.append(el("div", {className: "ok", textContent: imp.komunikat}));

  // 🖼 zdjęcia
  s.append(el("h4", {textContent: "Zdjęcia", style: "margin:10px 0 0"}));
  s.append(el("div", {className: "info", textContent: "Zakładka pokazuje zdjęcia tylko z tych folderów — to biblioteki Twoich projektów i foldery Przeglądarki. " +
    "Zdjęcie spoza nich nie zostanie pokazane."}));
  if (!d.korzenie.length) s.append(pustoEl("Brak folderów — ustaw bibliotekę w projekcie albo dodaj dysk w Przeglądarce."));
  for (const k of d.korzenie) {
    const dodatkowy = d.dodatkowe.includes(k);
    s.append(wiersz(sciezkaEl(k), dodatkowy ? przyc("✕", () => zmien({korzenie: d.dodatkowe.filter(x => x !== k)}), "", "Usuń dodatkowy folder") : el("span", {className: "info", textContent: "z programu"})));
  }
  s.append(wiersz(przyc("+ Dodaj folder ze zdjęciami…", () => otworzWyborFolderu("Dodatkowy folder ze zdjęciami podróży", "", f => {
    if (!d.dodatkowe.includes(f)) zmien({korzenie: [...d.dodatkowe, f]});
  }))));

  s.append(...sekcjaSlady(d, zmien));

  const sl = d.slady || {pobieranie: {}};
  if ((imp.trwa || sl.pobieranie.trwa) && !pod.odpytuje) {   // postęp importu i pobierania śladów: odświeżaj, aż się skończy
    pod.odpytuje = setInterval(async () => {
      try {
        const n = await api("/api/podroze"), trwa = n.import.trwa || (n.slady && n.slady.pobieranie.trwa);
        if (!trwa) { clearInterval(pod.odpytuje); pod.odpytuje = null; pod.zaladowana = false; }
        pod.d = n; odswiez();
      } catch (e) { clearInterval(pod.odpytuje); pod.odpytuje = null; }
    }, 900);
  }
  return s;
}

// 🥾 Ślady GPS wypraw ze Stravy i Intervals.icu — zamiast prostych kresek tam, gdzie Google zapisał tylko początek i koniec.
function sekcjaSlady(d, zmien) {
  const sl = d.slady || {klucze: {}, pobieranie: {}}, p = sl.pobieranie || {}, wyniki = [];
  const pole = (etykieta, nazwa, ustawione, podpowiedz, haslo) => {
    const i = el("input", {type: haslo ? "password" : "text", autocomplete: "off", placeholder: ustawione ? "zapisany — wpisz, aby zmienić" : podpowiedz});
    i.onchange = () => { if (i.value.trim()) zmien({slady: {klucze: {[nazwa]: i.value.trim()}}}, "Zapisano na tym komputerze."); };
    return wiersz(etyk(etykieta), i);
  };
  wyniki.push(el("h4", {textContent: "Ślady GPS (Strava / Intervals.icu)", style: "margin:10px 0 0"}));
  wyniki.push(el("div", {className: "info", innerHTML: "Prawdziwy ślad z aktywności z dni wypraw — na mapie zamiast prostych kresek. " +
    "<b>Klucze zostają tylko na tym komputerze</b>; program łączy się wyłącznie ze strava.com i intervals.icu. Najpierw próbuje Intervals.icu (klucz się nie zmienia), Stravę — gdy tam śladu nie ma."}));
  wyniki.push(pole("Intervals.icu — identyfikator", "intervals_athlete_id", sl.klucze.intervals, "np. i123456", false));
  wyniki.push(pole("Intervals.icu — klucz API", "intervals_api_key", sl.klucze.intervals, "Ustawienia → Developer Settings", true));
  wyniki.push(pole("Strava — Client ID", "strava_client_id", sl.klucze.strava, "z aplikacji API Stravy", false));
  wyniki.push(pole("Strava — Client Secret", "strava_client_secret", sl.klucze.strava, "", true));
  wyniki.push(pole("Strava — Refresh Token", "strava_refresh_token", sl.klucze.strava, "", true));
  const kopia = el("input", {type: "text", id: "slady-kopia", placeholder: "C:\\…\\kopia-szczyty.json — kopia zapasowa aplikacji Szczyty"});
  wyniki.push(wiersz(etyk("Wczytaj klucze z kopii"), kopia,
    przyc("Wczytaj", () => { if (kopia.value.trim()) zmien({slady: {akcja: "klucze-z-kopii", plik: kopia.value.trim()}}, "Wczytano klucze z kopii."); },
          "", "Kopiuje klucze Stravy i Intervals.icu z pliku kopii aplikacji Szczyty; nic nie jest pokazywane ani wysyłane")));
  const stanKluczy = `${sl.klucze.intervals ? "Intervals.icu ✓" : "Intervals.icu —"}  ·  ${sl.klucze.strava ? "Strava ✓" : "Strava —"}`;
  wyniki.push(wiersz(el("span", {className: "info", textContent: stanKluczy}),
    (sl.klucze.intervals || sl.klucze.strava) ? przyc("Usuń klucze", async () => {
      if (await oknoTak("Usunąć zapisane klucze Stravy i Intervals.icu z tego komputera?")) zmien({slady: {akcja: "usun-klucze"}}, "Usunięto klucze.");
    }) : null));
  wyniki.push(wiersz(
    p.trwa ? przyc("■ Przerwij", () => zmien({slady: {akcja: "przerwij"}})) :
      przyc(sl.ze_sladem ? "↻ Pobierz nowe ślady" : "⬇ Pobierz ślady wypraw", () => zmien({slady: {akcja: "pobierz"}}), sl.ze_sladem ? "" : "glowny",
            "Pobiera ślady aktywności z dni wypraw i zapamiętuje je na komputerze; można przerwać i wznowić"),
    sl.aktywnosci ? el("span", {className: "info", textContent: `${sl.ze_sladem} śladów z ${sl.aktywnosci} aktywności · ${sl.rozmiar_mb} MB`}) : null,
    sl.aktywnosci && !p.trwa ? przyc("Usuń ślady", async () => {
      if (await oknoTak("Usunąć pobrane ślady GPS? Klucze zostają, ślady można pobrać jeszcze raz.")) zmien({slady: {akcja: "usun"}}, "Usunięto ślady.");
    }) : null));
  if (p.trwa) wyniki.push(el("div", {className: "info", textContent: `⏳ ${p.komunikat}${p.wszystkie ? ` (${p.zrobione} z ${p.wszystkie})` : ""}`}));
  else if (p.blad) wyniki.push(el("div", {className: "zle", textContent: p.blad}));
  else if (p.komunikat) wyniki.push(el("div", {className: "ok", textContent: p.komunikat}));
  return wyniki;
}

$("podroze-odswiez").onclick = () => { const r = $("podroze-ramka"); if (pod.zaladowana) r.src = adresPodrozy(); };
$("podroze-przegladarka").onclick = () => window.open(adresPodrozy(), "_blank");
$("podroze-ust").onclick = async () => { try { await odswiezPodroze(); } catch (e) { toast(e.message); } pokazKonfiguracjePodrozy(); };
