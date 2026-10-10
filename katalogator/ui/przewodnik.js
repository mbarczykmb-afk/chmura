// Przewodnik krok po kroku (zwijane sekcje lewej kolumny), przeglądanie z klawiatury, ekran powitalny.
"use strict";

// ---------- 1. lewa kolumna jako przewodnik ----------
const PRZEW_KLUCZE = ["projekt", "zrodla", "cel", "skan", "dup", "analiza", "plan", "przych", "usun"];
const sprzatanie = () => !!(stan && stan.projekt && stan.projekt.typ === "sprzatanie");
const przew = {sekcje: {}, krok: null, reczne: new Map()};

(function budujPrzewodnik() {
  const sekcje = document.querySelectorAll("main > div:first-child > section");
  sekcje.forEach((s, i) => {
    const klucz = PRZEW_KLUCZE[i];
    if (!klucz) return;
    s.classList.add("przew"); s.dataset.klucz = klucz;
    const h = s.querySelector("h2");
    const tresc = document.createElement("div"); tresc.className = "tresc";
    while (h.nextSibling) tresc.append(h.nextSibling);
    const stre = document.createElement("div"); stre.className = "streszczenie";
    h.insertAdjacentElement("afterend", stre); s.append(tresc);
    h.tabIndex = 0; h.setAttribute("role", "button");
    h.title = "Kliknij, aby rozwinąć albo zwinąć";
    const przelacz = () => { przew.reczne.set(klucz, s.classList.contains("zwiniety")); ukladPrzewodnika(); };
    h.onclick = przelacz;
    h.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); przelacz(); } };
    stre.onclick = przelacz;
    przew.sekcje[klucz] = s;
  });
})();

function krokBiezacy() {
  const z = stan.zad || {};
  if (stan.skan && stan.skan.trwa) return ["skan"];
  if (stan.dup && stan.dup.trwa) return ["dup"];
  if (z.analiza && z.analiza.trwa) return ["analiza"];
  if (z.usuwanie && z.usuwanie.trwa) return ["usun"];
  if (sprzatanie()) {  // Sprzątanie: foldery → skan → duplikaty i śmieci → usuwanie
    if (!stan.zrodla || !stan.zrodla.length) return ["zrodla"];
    if (!stan.ma_wyniki) return ["skan"];
    return ["dup", "usun"];
  }
  if (!stan.zrodla || !stan.zrodla.length || !stan.cel) return ["zrodla", "cel"];
  if (!stan.ma_wyniki) return ["skan"];
  if (!stan.plan) return ["dup", "analiza", "plan"];
  return ["plan"];
}

const nazwaFolderu = p => (p || "").split(/[\\/]/).filter(Boolean).pop() || p;
const liczba = n => (n || 0).toLocaleString("pl-PL");

function streszczenia() {
  const s = stan, o = {};
  o.projekt = $("proj-postep-opis") ? $("proj-postep-opis").textContent : "";
  o.zrodla = s.zrodla && s.zrodla.length
    ? "✓ " + s.zrodla.map(z => nazwaFolderu(z.sciezka) + (sprzatanie() ? "" : ` (${z.tryb === "przenies" ? "P" : "K"})`)).join(", ")
    : "Nie wybrano folderów";
  o.cel = s.cel ? "✓ " + nazwaFolderu(s.cel) : "Nie wybrano miejsca docelowego";
  o.skan = s.skan && s.skan.trwa ? "⏳ Trwa skanowanie…" :
    (s.ma_wyniki ? `✓ Zeskanowano ${liczba(s.plikow)} plików` : "Jeszcze nie skanowano");
  o.dup = s.dup && s.dup.trwa ? "⏳ Szukam…" : (s.duplikaty
    ? (s.duplikaty.nadmiar ? `✓ ${liczba(s.duplikaty.nadmiar)} zbędnych kopii · ${rozmiar(s.duplikaty.bajty)}` : "✓ Brak duplikatów")
    : "Nie szukano (opcjonalnie)");
  o.analiza = s.analiza
    ? `✓ ${liczba(s.analiza.przeanalizowane)} zdjęć · dokumenty: ${s.analiza.dokumenty} · podobne: ${s.analiza.podobne_grupy}`
    : "Nie analizowano (opcjonalnie)";
  const p = s.plan;
  const zostalo = p ? p.kopiuj + p.przenies + (p.oryginaly || 0) : 0;
  o.plan = p ? (p.zrobione ? `✓ Uporządkowano ${liczba(p.zrobione)} plików` + (zostalo ? ` · zostało ${liczba(zostalo)}` : "")
                           : `✓ Propozycja: ${liczba(zostalo)} plików do uporządkowania`)
             : "Propozycja jeszcze nie utworzona";
  const odl = window.odlozoneStan;
  o.usun = odl && odl.plikow ? `${liczba(odl.plikow)} odłożonych · ${rozmiar(odl.bajty)} do usunięcia` : "Nic nie odłożono";
  const pr = (s.projekt && s.projekt.przychodzace) || [];
  o.przych = pr.length ? `${pr.length} folder(y) przychodzące` + (s.projekt.harmonogram ? " · codziennie automatycznie" : "")
                       : "Opcjonalnie — np. zrzuty z telefonu";
  return o;
}

function ukladPrzewodnika() {
  if (!stan || !stan.zrodla) return;
  const krok = krokBiezacy(), klucz = krok.join(",");
  if (klucz !== przew.krok) { przew.krok = klucz; przew.reczne.clear(); }  // nowy krok — ręczne wybory od nowa
  const stre = streszczenia();
  for (const [k, s] of Object.entries(przew.sekcje)) {
    const otwarta = przew.reczne.has(k) ? przew.reczne.get(k) : krok.includes(k);
    s.classList.toggle("zwiniety", !otwarta);
    s.classList.toggle("biezacy", krok.includes(k));
    s.querySelector(".streszczenie").textContent = stre[k] || "";
    s.querySelector("h2").setAttribute("aria-expanded", String(otwarta));
  }
}
naStan.push(ukladPrzewodnika);

function otworzSekcje(klucze) {
  klucze.forEach(k => przew.reczne.set(k, true));
  ukladPrzewodnika();
  const s = przew.sekcje[klucze[0]];
  if (s) s.scrollIntoView({behavior: "smooth", block: "start"});
}
$("k1").classList.add("klik"); $("k1").onclick = () => otworzSekcje(sprzatanie() ? ["zrodla"] : ["zrodla", "cel"]);
$("k2").classList.add("klik"); $("k2").onclick = () => { otworzSekcje(["skan", "dup", "analiza"]); pokazZakladke("raport"); };
{
  const stary3 = $("k3").onclick, stary4 = $("k4").onclick;
  $("k3").onclick = e => {
    if (sprzatanie()) { otworzSekcje(["dup"]); pokazZakladke("dup"); return; }
    otworzSekcje(["plan"]); if (stary3) stary3(e);
  };
  $("k4").onclick = e => { if (sprzatanie()) { otworzSekcje(["usun"]); return; } if (stary4) stary4(e); };
}

// ---------- 2. przeglądanie z klawiatury ----------
const KLAW = {
  dok: {karty: "#dok-siatka .karta", widok: "widok-dok"},
  pod: {karty: "#pod-lista .plik.zdj", widok: "widok-pod"},
  inne: {karty: "#inne-siatka .karta", widok: "widok-inne"},
};
const kursor = {el: null};

function karty() { const k = KLAW[zakladka]; return k ? [...document.querySelectorAll(k.karty)] : []; }
function ustawKursor(el, przewin = true) {
  if (kursor.el) kursor.el.classList.remove("kursor");
  kursor.el = el;
  if (el) { el.classList.add("kursor"); if (przewin) el.scrollIntoView({block: "nearest", behavior: "smooth"}); }
}
function sasiad(kierunek) {
  const lista = karty();
  if (!lista.length) return null;
  if (!kursor.el || !lista.includes(kursor.el)) return lista[0];
  const i = lista.indexOf(kursor.el);
  if (kierunek === "prawo") return lista[Math.min(i + 1, lista.length - 1)];
  if (kierunek === "lewo") return lista[Math.max(i - 1, 0)];
  const r = kursor.el.getBoundingClientRect(), sx = r.left + r.width / 2;
  const kandydaci = lista.filter(e => {
    const q = e.getBoundingClientRect();
    return kierunek === "dol" ? q.top > r.top + r.height / 2 : q.bottom < r.top + r.height / 2;
  });
  if (!kandydaci.length) return kursor.el;
  const rzad = kierunek === "dol" ? Math.min(...kandydaci.map(e => e.getBoundingClientRect().top))
                                  : Math.max(...kandydaci.map(e => e.getBoundingClientRect().top));
  const wRzedzie = kandydaci.filter(e => Math.abs(e.getBoundingClientRect().top - rzad) < 4);
  return wRzedzie.reduce((a, b) => Math.abs(b.getBoundingClientRect().left + b.offsetWidth / 2 - sx) <
                                   Math.abs(a.getBoundingClientRect().left + a.offsetWidth / 2 - sx) ? b : a);
}
const podgladOtwarty = () => document.querySelector(".nakladka[data-podglad]");
function powieksz(el) {
  const img = el && el.querySelector("img");
  if (img) img.dispatchEvent(new MouseEvent("dblclick", {bubbles: true}));
}
function zamknijPodglad() { const p = podgladOtwarty(); if (p) { const v = p.querySelector("video"); if (v) v.pause(); p.remove(); return true; } return false; }

document.addEventListener("keydown", e => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (e.key === "Escape" && zamknijPodglad()) { e.preventDefault(); return; }
  if (!KLAW[zakladka] || $("galeria-nakladka") && !$("galeria-nakladka").hidden) return;
  const cel = e.target;
  if (cel.closest && cel.closest("input, textarea, select, [contenteditable]")) return;
  if ([...document.querySelectorAll(".nakladka:not([data-podglad])")].some(n => !n.hidden)) return;  // otwarte okno
  const kier = {ArrowRight: "prawo", ArrowLeft: "lewo", ArrowDown: "dol", ArrowUp: "gora"}[e.key];
  if (kier) {
    e.preventDefault();
    const byl = !!podgladOtwarty();
    zamknijPodglad();
    ustawKursor(sasiad(kier));
    if (byl) powieksz(kursor.el);  // przeglądanie powiększonych zdjęć strzałkami
    return;
  }
  if (!kursor.el || !kursor.el.isConnected) { if (["1", "2", "3", " ", "Enter"].includes(e.key)) ustawKursor(karty()[0]); }
  const el = kursor.el;
  if (!el) return;
  const kat = {"1": "zdjecie", "2": "dokument", "3": "smieci"}[e.key];
  if (kat) {
    e.preventDefault();
    const b = el.querySelector(`.wybor button[data-k="${kat}"]`);
    if (b && !b.classList.contains("akt")) b.click();
    const byl = !!podgladOtwarty();
    setTimeout(() => {
      zamknijPodglad();
      const n = sasiad("prawo");
      if (n && n !== el) { ustawKursor(n); if (byl) powieksz(n); }
    }, 120);  // od razu następne zdjęcie — szybki przegląd
    return;
  }
  if (zakladka === "pod" && typeof an !== "undefined" && an.jedna && an.tryb === "podobne") {  // ▣ jedna grupa na ekran
    if (e.key === "Enter") { e.preventDefault(); zamknijPodglad(); zatwierdzJedna(); return; }
    if (e.key === "s" || e.key === "S") { e.preventDefault(); zamknijPodglad(); zatwierdzJedna(true); return; }
  }
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); if (!zamknijPodglad()) powieksz(el); return; }
  if ((e.key === "z" || e.key === "Z") && zakladka === "pod") {  // Podobne: zostaw / odłóż
    e.preventDefault();
    const cb = el.querySelector('input[type="checkbox"]');
    if (cb) cb.click();
  }
});
document.addEventListener("click", e => {
  const k = KLAW[zakladka];
  const el = k && e.target.closest && e.target.closest(k.karty);
  if (el) ustawKursor(el, false);
}, true);

// ściągawka nad kartami
for (const [zak, k] of Object.entries(KLAW)) {
  const w = $(k.widok);
  if (!w) continue;
  const s = document.createElement("div"); s.className = "klawiatura";
  s.innerHTML = "⌨ <b>←→↑↓</b> wybór zdjęcia · <b>1</b> 📷 zdjęcie · <b>2</b> 📄 dokument · <b>3</b> 🗑 śmieci" +
    (zak === "pod" ? " · <b>Z</b> zostaw/odłóż" : "") + " · <b>spacja</b> powiększ · <b>Esc</b> zamknij";
  s.title = "Po wyborze 1/2/3 program sam przechodzi do następnego zdjęcia";
  const f = w.querySelector(".filtry");
  (f || w.firstElementChild).insertAdjacentElement("afterend", s);
}

// ---------- 5. ekran powitalny ----------
function pokazPowitanie() {
  const n = document.createElement("div"); n.className = "powitanie"; n.setAttribute("role", "dialog");
  n.setAttribute("aria-label", "Jak zacząć");
  n.innerHTML = `<div class="pw-okno">
    <div class="pw-hero" aria-hidden="true"></div>
    <h2>👋 Witaj w Katalogatorze</h2>
    <p class="opis">Uporządkuję zdjęcia, filmy, muzykę i pliki. <b>Nic nie przeniosę bez Twojej zgody</b> — najpierw pokażę propozycję.</p>
    <p class="opis">U góry wybierasz tryb: <b>🗂 Porządkowanie</b> (kroki poniżej — nowa, uporządkowana biblioteka),
      <b>🧹 Sprzątanie</b> (duplikaty i śmieci w istniejących folderach, bez kopiowania) albo <b>🔭 Przeglądarka</b>
      (zdjęcia z dowolnych dysków na osi czasu i mapie). Każdy plik czytam z dysku raz — wszystkie tryby
      korzystają z tego samego indeksu.</p>
    <div class="pw-kroki">
      <div><span>1</span><b>📁 Wybierz foldery</b>Zaznacz <b>K</b> (kopiuj — oryginały zostają) albo <b>P</b> (przenieś) i wskaż, dokąd.</div>
      <div><span>2</span><b>🔍 Skanuj</b>Tylko odczyt. Zobaczysz raport: ile zdjęć, z jakich lat, ile z miejscem (GPS).</div>
      <div><span>3</span><b>✅ Przejrzyj</b>Duplikaty, dokumenty, podobne i „nie z aparatu” — klawisze 1 / 2 / 3.</div>
      <div><span>4</span><b>🌳 Drzewo i porządki</b>Popraw propozycję folderów i kliknij „Uporządkuj pliki…”. Każdą kopię sprawdzam; wszystko da się cofnąć.</div>
    </div>
    <details class="pw-slownik"><summary>Słowniczek</summary>
      <dl><dt>Kopiuj / Przenieś</dt><dd>kopiuj — oryginał zostaje; przenieś — oryginał znika dopiero po sprawdzeniu kopii</dd>
      <dt>Odłóż</dt><dd>przenieś do folderu <b>Odłożone</b> (duplikaty, podobne, śmieci) — nic nie jest kasowane</dd>
      <dt>Pomiń</dt><dd>plik zostaje tam, gdzie jest — nie będzie kopiowany ani przenoszony</dd>
      <dt>Cofnij</dt><dd>przycisk w komunikacie na dole albo w Drzewie (Ctrl+Z)</dd>
      <dt>📚 Biblioteka</dt><dd>oś czasu i mapa uporządkowanych zdjęć — także na telefonie</dd></dl>
    </details>
    <div class="pw-dol"><label><input type="checkbox" id="pw-nie-pokazuj" checked> Nie pokazuj przy starcie</label>
      <button class="glowny" id="pw-start">Zaczynamy →</button></div></div>`;
  document.body.append(n);
  const zamknij = () => {
    if ($("pw-nie-pokazuj").checked) api("/api/program/ustawienia", {powitanie_widziane: true}).catch(() => {});
    n.remove(); stan.powitanie_widziane = true;
    otworzSekcje(krokBiezacy());
  };
  $("pw-start").onclick = zamknij;
  n.onclick = e => { if (e.target === n) zamknij(); };
  n.addEventListener("keydown", e => { if (e.key === "Escape") zamknij(); });
  $("pw-start").focus();
}
let powitanieSprawdzone = false;
naStan.push(() => {
  if (powitanieSprawdzone || stan.powitanie_widziane === undefined) return;
  powitanieSprawdzone = true;
  if (!stan.powitanie_widziane) pokazPowitanie();
  else if (!document.body.classList.contains("zdalnie")) pokazWyborTrybu();
});

// ---------- ekran startowy: trzy duże kafelki — czym się dziś zajmujemy ----------
function pokazWyborTrybu() {
  if ($("wybor-trybu")) return;
  const n = document.createElement("div"); n.className = "wybor-trybu"; n.id = "wybor-trybu"; n.setAttribute("role", "dialog");
  const KAFLE = [
    ["porzadkowanie", "🗂", "Porządkowanie", "Kopiuję albo przenoszę zdjęcia i filmy do jednej uporządkowanej biblioteki: Rok → Miesiąc → Miejsce."],
    ["sprzatanie", "🧹", "Sprzątanie", "Duplikaty, podobne, nieostre i śmieci w istniejących folderach — bez kopiowania i bez nowego drzewa."],
    ["przegladarka", "🔭", "Przeglądarka", "Oglądanie zdjęć i filmów z dowolnych dysków: oś czasu, mapa, kolekcje, „tego dnia”."],
  ];
  const obecny = sprzatanie() ? "sprzatanie" : "porzadkowanie";
  n.innerHTML = `<div class="wt-okno"><h2>Czym się dziś zajmujemy?</h2>
    <div class="wt-kafle"></div>
    <div class="wt-dol"><span class="info">Projekt: <b></b> · tryb możesz zmienić w każdej chwili u góry okna</span>
      <button class="maly" id="wt-zostan">Zostań przy ostatnim (Esc)</button></div></div>`;
  n.querySelector(".wt-dol b").textContent = (stan.projekt && stan.projekt.nazwa) || "";
  const kafle = n.querySelector(".wt-kafle");
  for (const [t, ik, tyt, opis] of KAFLE) {
    const b = document.createElement("button"); b.className = "wt-kafel" + (t === obecny ? " ostatni" : "");
    b.innerHTML = `<span class="ik"></span><b></b><span class="op"></span>`;
    b.querySelector(".ik").textContent = ik; b.querySelector("b").textContent = tyt; b.querySelector(".op").textContent = opis;
    if (t === obecny) { const z = document.createElement("small"); z.textContent = "ostatnio"; b.append(z); }
    b.onclick = () => { zamknij(); document.querySelector(`.tryby button[data-tryb="${t}"]`).click(); };
    kafle.append(b);
  }
  const zamknij = () => { n.remove(); document.removeEventListener("keydown", klaw, true); };
  const klaw = e => {
    if (e.key === "Escape") { e.preventDefault(); zamknij(); }
    const i = {"1": 0, "2": 1, "3": 2}[e.key];
    if (i !== undefined) { e.preventDefault(); kafle.children[i].click(); }
  };
  document.addEventListener("keydown", klaw, true);
  n.querySelector("#wt-zostan").onclick = zamknij;
  document.body.append(n);
  (kafle.querySelector(".ostatni") || kafle.firstChild).focus();
}
if ($("m-powitanie")) $("m-powitanie").onclick = () => { $("pomoc-menu").hidden = true; pokazPowitanie(); };
