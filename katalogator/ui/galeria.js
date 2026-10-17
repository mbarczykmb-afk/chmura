// Przeglądarka biblioteki: oś czasu i mapa (OpenStreetMap). Działa w oknie programu i na telefonie.
"use strict";

const $ = id => document.getElementById(id);
const P = new URLSearchParams(location.search);
const W_PROGRAMIE = P.get("app") === "1";
const KLUCZ = "katalogator_galeria_t";
let TOKEN = P.get("t") || (() => { try { return localStorage.getItem(KLUCZ) || ""; } catch (e) { return ""; } })();
const MIESIACE = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
                  "październik", "listopad", "grudzień"];
const g = {widok: "os", lata: [], rok: null, mies: null, pliki: [], razem: 0, mapa: null, klaster: null, punkty: null,
           lista: [], poz: 0, zakres: "biblioteka",
           zrodlo: {typ: "os"},   // co pokazuje siatka: oś czasu / wyniki szukania / kolekcja / tego dnia
           obszar: null,          // prostokąt z mapy [lat1, lat2, lon1, lon2] — oś czasu tylko z tego miejsca
           dzien: null, pokaz: null,
           zazn: new Set(), ostatnioZazn: -1};  // ☑ zaznaczone zdjęcia (id) — akcje hurtem
const obszarParam = () => g.obszar ? {lat1: g.obszar[0], lat2: g.obszar[1], lon1: g.obszar[2], lon2: g.obszar[3]} : {};

// na telefonie: który zbiór oglądamy (z pilota: biblioteka / cały projekt / Przeglądarka dysków)
const Z_TELEFON = !W_PROGRAMIE && ["biblioteka", "wszystko", "przegladarka"].includes(P.get("z")) ? P.get("z") : "";
if (Z_TELEFON) g.zakres = Z_TELEFON;

function url(sciezka, param = {}) {
  const u = new URLSearchParams(param);
  if (TOKEN) u.set("t", TOKEN);
  if (W_PROGRAMIE || Z_TELEFON) u.set("z", g.zakres);
  return sciezka + "?" + u.toString();
}
async function api(sciezka, param) {
  if (g.rodzaj) param = {...(param || {}), r: g.rodzaj};  // filtr: zdjęcia / filmy / dokumenty
  param = {...(param || {}), kol: g.kol};                  // ⇅ od najnowszych / od najstarszych
  const r = await fetch(url(sciezka, param));
  if (r.status === 401 || r.status === 403) { pokazLogin(); throw new Error("Podaj PIN"); }
  const j = await r.json();
  if (!r.ok || j.blad) throw new Error(j.blad || r.statusText);
  return j;
}
const miniatura = (id, srednia = true) => url("/api/g/miniatura", srednia ? {id, srednia: 1} : {id});
// dzień roku jako "MM-DD" (bez roku) — do „Tego dnia”
const mdDzis = () => { const d = new Date(); return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
function mdPrzesun(md, o) {
  const d = new Date(2024, +md.slice(0, 2) - 1, +md.slice(3) + o);  // rok przestępny: 29 lutego istnieje
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const mdTxt = md => new Date(2024, +md.slice(0, 2) - 1, +md.slice(3)).toLocaleDateString("pl-PL", {day: "numeric", month: "long"});
const latTemu = n => n === 1 ? "rok temu" : `${n} ${n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? "lata" : "lat"} temu`;
const dataTxt = d => d ? new Date(d).toLocaleDateString("pl-PL", {day: "numeric", month: "long", year: "numeric"}) : "bez daty";

// ---------- logowanie (telefon) ----------
function pokazLogin() { if (!W_PROGRAMIE) { $("login").hidden = false; $("pin").focus(); } }
$("login-form").onsubmit = async e => {
  e.preventDefault();
  $("login-blad").textContent = "";
  try {
    const r = await fetch("/api/g/zaloguj", {method: "POST", headers: {"Content-Type": "application/json"},
                                               body: JSON.stringify({pin: $("pin").value})});
    const j = await r.json();
    if (!r.ok || !j.t) throw new Error(j.blad || "Zły PIN");
    TOKEN = j.t;
    try { localStorage.setItem(KLUCZ, TOKEN); } catch (err) { /* prywatne okno */ }
    $("login").hidden = true;
    start();
  } catch (err) { $("login-blad").textContent = err.message; }
};

// ---------- oś czasu ----------
async function wczytajLata(tylkoLiczby = false) {
  const r = await api("/api/g/lata", obszarParam());
  g.lata = r.lata;
  $("licznik").textContent = `${r.razem.toLocaleString("pl-PL")} zdjęć i filmów · z miejscem: ${r.z_gps.toLocaleString("pl-PL")}`;
  rysujWykres();
  if (tylkoLiczby && (g.zrodlo.typ !== "os" || g.widok !== "os")) { uklad(); return; }  // skan w toku: nie przerywaj wyników
  if (tylkoLiczby && g.rok && g.lata.some(x => x.rok === g.rok)) { oznaczWykres(); return; }  // skan w toku
  const l = $("lata"); l.replaceChildren();
  if (!g.lata.length) {
    if (g.zrodlo.typ !== "os") return;
    $("siatka").innerHTML = `<div class="pusto">${g.obszar ? "Brak zdjęć z datą w tym obszarze." : W_PROGRAMIE && g.zakres === "biblioteka"
      ? "<img class=\"ik3d-pusto\" alt=\"\" src=\"/ui/ikony3d/biblioteka.webp\"><br>Biblioteka jest jeszcze pusta — uporządkuj pliki albo wybierz „Wszystko w projekcie”."
      : g.zakres === "przegladarka"
        ? "<img class=\"ik3d-pusto\" alt=\"\" src=\"/ui/ikony3d/przegladarka.webp\"><br>Dodaj dysk lub folder (＋) i kliknij „Skanuj”. Przeglądarka tylko czyta dyski — niczego sama nie zmienia (usuwasz tylko Ty, przyciskiem 🗑, z możliwością cofnięcia)."
        : "Brak zdjęć z datą."}</div>`;
    $("miesiace").replaceChildren(); return;
  }
  const lata = g.kol === "stare" ? [...g.lata].reverse() : g.lata;  // lata w tej samej kolejności co zdjęcia
  for (const rok of lata) {
    const b = document.createElement("button");
    b.innerHTML = `${rok.rok}<small>${rok.n.toLocaleString("pl-PL")}</small>`;
    b.onclick = () => wybierzRok(rok.rok);
    b.dataset.rok = rok.rok; l.append(b);
  }
  wybierzRok(g.lata.some(x => x.rok === g.rok) ? g.rok : lata[0].rok);
}
function wybierzRok(rok, mies = null) {
  g.rok = rok;
  document.querySelectorAll("#lata button").forEach(b => b.classList.toggle("akt", b.dataset.rok === rok));
  const r = g.lata.find(x => x.rok === rok);
  const m = $("miesiace"); m.replaceChildren();
  const wsz = document.createElement("button"); wsz.innerHTML = `cały rok<small>${r.n}</small>`; wsz.dataset.m = "";
  wsz.onclick = () => wybierzMiesiac(null); m.append(wsz);
  for (const x of [...r.miesiace].sort((a, b) => g.kol === "stare" ? a.m - b.m : b.m - a.m)) {
    const b = document.createElement("button"); b.innerHTML = `${MIESIACE[x.m - 1] || "?"}<small>${x.n}</small>`;
    b.dataset.m = x.m; b.onclick = () => wybierzMiesiac(x.m); m.append(b);
  }
  wybierzMiesiac(mies);
  document.querySelector(`#lata button[data-rok="${rok}"]`)?.scrollIntoView({inline: "nearest", block: "nearest"});
}
async function wybierzMiesiac(mies) {
  g.mies = mies; g.pliki = [];
  if (g.zrodlo.typ !== "os") { g.zrodlo = {typ: "os"}; $("szukaj").value = ""; uklad(); }
  document.querySelectorAll("#miesiace button").forEach(b => b.classList.toggle("akt", b.dataset.m === String(mies || "")));
  oznaczWykres();
  await wczytajPliki();
}

// ---------- wykres: liczba zdjęć w każdym miesiącu (ciągła oś czasu, klik = miesiąc) ----------
function rysujWykres() {
  const w = $("wykres"); w.replaceChildren();
  const ile = new Map(); let min = Infinity, max = -Infinity, maks = 0;
  for (const r of g.lata) for (const m of r.miesiace) {
    if (!(m.m >= 1 && m.m <= 12)) continue;
    const k = +r.rok * 12 + m.m - 1; ile.set(k, m.n);
    min = Math.min(min, k); max = Math.max(max, k); maks = Math.max(maks, m.n);
  }
  w.hidden = !ile.size || g.widok !== "os";
  if (!ile.size) return;
  const tor = document.createElement("div"); tor.className = "w-tor";
  for (let rok = Math.floor(min / 12); rok <= Math.floor(max / 12); rok++) {
    const kol = document.createElement("div"); kol.className = "w-rok"; kol.dataset.rok = rok;
    const sl = document.createElement("div"); sl.className = "w-slupki";
    for (let m = 1; m <= 12; m++) {
      const n = ile.get(rok * 12 + m - 1) || 0;
      const b = document.createElement("button"); b.className = "w-s"; b.dataset.m = m; b.disabled = !n;
      b.setAttribute("aria-label", `${MIESIACE[m - 1]} ${rok}: ${n} zdjęć i filmów`);
      const i = document.createElement("i"); i.style.height = n ? `max(3px, ${(n / maks * 100).toFixed(1)}%)` : "0";
      b.append(i);
      const pokaz = () => tip(b, n, `${MIESIACE[m - 1]} ${rok}`);
      b.onpointerenter = pokaz; b.onfocus = pokaz; b.onpointerleave = b.onblur = () => tip(null);
      if (n) b.onclick = () => { if (g.rok !== String(rok)) wybierzRok(String(rok), m); else wybierzMiesiac(m); };
      sl.append(b);
    }
    const et = document.createElement("button"); et.className = "w-et"; et.textContent = rok;
    const suma = (g.lata.find(x => x.rok === String(rok)) || {}).n || 0;
    et.title = `${rok}: ${suma.toLocaleString("pl-PL")} — pokaż cały rok`;
    et.disabled = !suma; if (suma) et.onclick = () => wybierzRok(String(rok));
    kol.append(sl, et); tor.append(kol);
  }
  const mx = document.createElement("div"); mx.className = "w-max";
  mx.textContent = `najwięcej: ${maks.toLocaleString("pl-PL")} w miesiącu`;
  w.append(tor, mx);
  oznaczWykres();
}
function oznaczWykres() {
  document.querySelectorAll("#wykres .w-rok").forEach(k => {
    const ten = k.dataset.rok === String(g.rok);
    k.classList.toggle("akt", ten);
    k.querySelectorAll(".w-s").forEach(s => s.classList.toggle("akt", ten && g.mies === +s.dataset.m));
    if (ten) k.scrollIntoView({inline: "nearest", block: "nearest"});
  });
}
function tip(el, n, opis) {
  const t = $("w-tip");
  if (!el) { t.hidden = true; return; }
  t.replaceChildren();
  const b = document.createElement("b"); b.textContent = n.toLocaleString("pl-PL");
  const s = document.createElement("span"); s.textContent = opis;
  t.append(b, s); t.hidden = false;
  const r = el.getBoundingClientRect(), tr = t.getBoundingClientRect();
  t.style.left = Math.max(6, Math.min(innerWidth - tr.width - 6, r.left + r.width / 2 - tr.width / 2)) + "px";
  t.style.top = Math.max(6, r.top - tr.height - 8) + "px";
}
async function wczytajPliki(wiecej = false) {
  const od = wiecej ? g.pliki.length : 0, z = g.zrodlo;
  const r = z.typ === "szukaj" ? await api("/api/g/szukaj", {q: z.q, od, ile: 200})
    : z.typ === "kolekcja" ? await api("/api/g/kolekcja", {typ: z.kol, album: z.album || 0, od, ile: 200})
    : z.typ === "osoba" ? await api("/api/g/osoba", {id: z.osoba, od, ile: 200})
    : z.typ === "dzien" ? await api("/api/g/tego-dnia", {md: z.md || mdDzis(), dni: z.dni || 0})
    : await api("/api/g/pliki", {rok: g.rok, miesiac: g.mies || 0, od, ile: 200, ...obszarParam()});
  if (z !== g.zrodlo) return;  // w międzyczasie wybrano coś innego
  const bylo = wiecej ? g.pliki.length : 0;
  if (!wiecej) { g.zazn.clear(); g.ostatnioZazn = -1; }
  g.pliki = wiecej ? g.pliki.concat(r.pliki) : r.pliki; g.razem = r.razem;
  if (r.opis !== undefined) z.opis = r.opis;
  if (r.nazwa) z.nazwa = r.nazwa;
  if (z.typ === "dzien") { z.md = r.md; z.lata = r.lata; z.najblizszy = r.najblizszy; }
  rysujSiatke(bylo); rysujFiltr(); odswiezZazn();
}
// Przewijanie do końca siatki doczytuje kolejne zdjęcia (bez klikania „Pokaż kolejne”)
const doczytaj = "IntersectionObserver" in window ? new IntersectionObserver(wpisy => {
  for (const w of wpisy) if (w.isIntersecting && !g.doczytuje && w.target.isConnected) {
    g.doczytuje = true;
    wczytajPliki(true).catch(() => {}).finally(() => { g.doczytuje = false; });
  }
}, {root: $("siatka"), rootMargin: "0px 0px 800px 0px"}) : null;
function rysujSiatke(odIndeksu = 0) {  // odIndeksu > 0: dopisujemy tylko nowe (przewinięcie zostaje)
  const s = $("siatka");
  if (odIndeksu) s.querySelectorAll(":scope > .wiecej").forEach(b => { if (doczytaj) doczytaj.unobserve(b); b.remove(); });
  else s.replaceChildren();
  const dzien = g.zrodlo.typ === "dzien";
  let rok = odIndeksu && g.pliki[odIndeksu - 1] && g.pliki[odIndeksu - 1].data ? g.pliki[odIndeksu - 1].data.slice(0, 4) : null;
  g.pliki.forEach((p, i) => {
    if (i < odIndeksu) return;
    if (dzien && p.data && p.data.slice(0, 4) !== rok) {  // „Tego dnia”: nagłówek każdego roku
      rok = p.data.slice(0, 4);
      const n = (g.zrodlo.lata || []).find(x => x.rok === rok);
      const h = document.createElement("div"); h.className = "rok-nagl";
      h.append(rok); const sm = document.createElement("small");
      sm.textContent = (n ? latTemu(n.lat_temu) + " · " + liczbaZdjec(n.n) : ""); h.append(sm); s.append(h);
    }
    const k = document.createElement("div"); k.className = "k" + (g.zazn.has(p.id) ? " zazn" : ""); k.title = p.nazwa;
    k.dataset.i = i;
    const ob = document.createElement("div"); ob.className = "ob";
    if (p.rodzaj === "zdjecie") {
      const im = new Image(); im.loading = "lazy"; im.alt = ""; im.src = miniatura(p.id, false);  // mała: szybka, zapamiętywana na dysku
      im.onerror = () => { ob.textContent = "🖼️"; }; ob.append(im);
    } else miniaturaFilmu(p, ob);
    if (MOZE_USUWAC) {
      const x = document.createElement("button"); x.className = "kosz"; x.textContent = "🗑"; x.title = "Usuń (do kosza programu, można cofnąć)";
      x.onclick = e => { e.stopPropagation(); usunPliki([p]); }; ob.append(x);
    }
    const zz = document.createElement("button"); zz.className = "zz"; zz.title = "Zaznacz (Ctrl+klik, Shift+klik — zakres)";
    zz.setAttribute("aria-label", "Zaznacz"); zz.onclick = e => { e.stopPropagation(); zaznacz(i, e.shiftKey); }; ob.append(zz);
    const op = document.createElement("div"); op.className = "op";
    op.innerHTML = "<div></div><div class='m'></div>";
    op.children[0].textContent = p.nazwa;
    op.children[1].textContent = dataTxt(p.data) + (p.lat != null ? " · 📍" : "");
    k.append(ob, op);
    k.onclick = e => {
      if (g.dlugie) { g.dlugie = false; return; }  // po przytrzymaniu palcem (zaznaczenie) — bez otwierania
      if (g.zazn.size || e.ctrlKey || e.metaKey || e.shiftKey) { zaznacz(i, e.shiftKey); return; }
      pokazPelny(g.pliki, i);
    };
    s.append(k);
  });
  if (g.pliki.length < g.razem) {
    const b = document.createElement("button"); b.className = "wiecej";
    b.textContent = `Pokaż kolejne (zostało ${(g.razem - g.pliki.length).toLocaleString("pl-PL")})`;
    b.onclick = () => wczytajPliki(true); s.append(b);
    if (doczytaj) doczytaj.observe(b);
  }
  if (!g.pliki.length) s.innerHTML = `<div class="pusto">${g.zrodlo.typ === "szukaj" ? "Nic nie znaleziono. Spróbuj: miejscowość, kraj, rok, miesiąc albo fragment nazwy."
    : g.zrodlo.typ === "kolekcja" ? (g.zrodlo.kol === "ulubione" ? "Brak ulubionych — otwórz zdjęcie i kliknij ☆ Ulubione (albo F)." : "Album jest pusty — otwórz zdjęcie i kliknij ＋ Album.")
    : g.zrodlo.typ === "dzien" ? `Brak zdjęć z ${mdTxt(g.zrodlo.md || mdDzis())}${g.zrodlo.dni ? " (± " + g.zrodlo.dni + " dni)" : ""} z poprzednich lat.`
    : "Brak zdjęć w tym okresie."}</div>`;
  if (!g.pliki.length && g.zrodlo.typ === "dzien" && g.zrodlo.najblizszy) {
    const nb = g.zrodlo.najblizszy;
    s.firstElementChild.append(document.createElement("br"), przycisk(`Najbliższy dzień ze zdjęciami: ${mdTxt(nb.md)} (${liczbaZdjec(nb.n)}) →`,
      () => pokazWyniki({...g.zrodlo, md: nb.md}), "", "akt"));
  }
}

// ---------- ☑ zaznaczanie wielu: Ctrl/Shift+klik, kółko na miniaturze, przytrzymanie palcem ----------
function zaznacz(i, zakres = false) {
  const p = g.pliki[i]; if (!p) return;
  if (zakres && g.ostatnioZazn >= 0) {  // Shift: wszystko pomiędzy
    const [a, b] = [Math.min(g.ostatnioZazn, i), Math.max(g.ostatnioZazn, i)];
    for (let j = a; j <= b; j++) if (g.pliki[j]) g.zazn.add(g.pliki[j].id);
  } else if (g.zazn.has(p.id)) g.zazn.delete(p.id); else g.zazn.add(p.id);
  g.ostatnioZazn = i;
  odswiezZazn();
}
function odswiezZazn() {
  document.querySelectorAll("#siatka .k").forEach(k => {
    const p = g.pliki[+k.dataset.i]; k.classList.toggle("zazn", !!p && g.zazn.has(p.id));
  });
  const n = g.zazn.size, wyb = zaznaczone();
  document.body.classList.toggle("zaznaczanie", n > 0);
  $("zz").hidden = !n;
  const kilka = n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20);
  $("zz-ile").textContent = `${n.toLocaleString("pl-PL")} ${n === 1 || kilka ? "zaznaczone" : "zaznaczonych"}`;
  $("zz-data").hidden = $("zz-miejsce").hidden = $("zz-usun").hidden = !MOZE_USUWAC;
  $("zz-dok").hidden = !W_PROGRAMIE || !wyb.some(p => p.rodzaj === "zdjecie");
  $("zz-album").hidden = !W_PROGRAMIE;
  $("zz-z-albumu").hidden = !(W_PROGRAMIE && g.zrodlo.typ === "kolekcja" && g.zrodlo.kol === "album");
  const dok = wyb.filter(p => p.rodzaj === "zdjecie"), wszDok = dok.length && dok.every(p => p.dokument);
  $("zz-dok").textContent = wszDok ? "📷 Nie dokument" : "📄 Dokument";
  $("zz-wszystkie").textContent = g.pliki.length && g.pliki.every(p => g.zazn.has(p.id)) ? "☐ Odznacz" : "☑ Wszystkie";
}
const zaznaczone = () => g.pliki.filter(p => g.zazn.has(p.id));
function koniecZazn() { g.zazn.clear(); g.ostatnioZazn = -1; zamknijMenuAlb(); odswiezZazn(); }
$("zz-koniec").onclick = koniecZazn;
$("zz-wszystkie").onclick = async () => {
  if (g.pliki.length && g.pliki.every(p => g.zazn.has(p.id))) { koniecZazn(); return; }
  // wszystkie z widoku — także jeszcze niewczytane (do 5000)
  while (g.pliki.length < g.razem && g.pliki.length < 5000) { const n = g.pliki.length; await wczytajPliki(true); if (g.pliki.length === n) break; }
  for (const p of g.pliki) g.zazn.add(p.id);
  odswiezZazn();
};
$("zz-data").onclick = () => { const w = zaznaczone(); if (w.length) oknoDaty(w[0], w); };
$("zz-miejsce").onclick = () => { const w = zaznaczone(); if (w.length) oknoLokalizacji(w[0], w); };
$("zz-usun").onclick = async () => {
  const w = zaznaczone(); if (!w.length) return;
  if (w.length > 1 && !confirm(`Usunąć ${liczbaZdjec(w.length)}? Trafią do kosza programu (Odłożone/Usunięte) — można cofnąć.`)) return;
  await usunPliki(w); koniecZazn();
};
$("zz-dok").onclick = async () => {
  const w = zaznaczone().filter(p => p.rodzaj === "zdjecie"); if (!w.length) return;
  const tak = !w.every(p => p.dokument);
  try {
    const r = await post("/api/g/dokument", {ids: w.map(p => p.id), tak});
    for (const p of w) p.dokument = tak;
    toastG(tak ? `📄 ${liczbaZdjec(r.zmienione)} — dokumenty` : `📷 ${liczbaZdjec(r.zmienione)} — zwykłe zdjęcia`);
    if (g.rodzaj) { koniecZazn(); wczytajLata(true).catch(() => {}); wczytajPliki().catch(() => {}); } else odswiezZazn();
  } catch (e) { toastG(e.message); }
};
$("zz-album").onclick = e => {
  e.stopPropagation();
  if (document.querySelector(".menu-alb")) { zamknijMenuAlb(); return; }
  menuAlbumow($("zz"), zaznaczone().map(p => p.id), n => toastG(`＋ Dodano do „${n}”: ${liczbaZdjec(g.zazn.size)}`));
};
$("zz-z-albumu").onclick = async () => {
  const w = zaznaczone(); if (!w.length) return;
  await post("/api/g/album/usun-pliki", {album: g.zrodlo.album, ids: w.map(p => p.id)});
  koniecZazn(); wczytajPliki().catch(() => {}); toastG(`− Usunięto z albumu: ${liczbaZdjec(w.length)} (pliki zostają na dysku)`);
};
$("zz-zip").onclick = () => pobierzZip({ids: zaznaczone().map(p => p.id)});
// ⬇ ZIP: zaznaczone albo cały album — przeglądarka pobiera plik (bez czekania na spakowanie całości)
async function pobierzZip(co) {
  try {
    const r = co.ids ? await post("/api/g/zip", {ids: co.ids}) : {klucz: ""};
    const a = document.createElement("a");
    a.href = url("/api/g/zip", co.ids ? {k: r.klucz} : {album: co.album});
    a.download = ""; document.body.append(a); a.click(); a.remove();
    toastG("⬇ Pobieranie ZIP rozpoczęte — zdjęcia w oryginalnej jakości.");
  } catch (e) { toastG("Nie udało się: " + e.message); }
}
// menu albumów (podgląd i zaznaczone): istniejące + nowy
async function menuAlbumow(gdzie, ids, gotowe) {
  const m = document.createElement("div"); m.className = "menu-alb"; m.onclick = ev => ev.stopPropagation();
  m.textContent = "Wczytuję…"; gdzie.append(m);
  const r = await api("/api/g/albumy"); m.replaceChildren();
  for (const a of r.albumy) m.append(przycisk(`🗂 ${a.nazwa}`, async () => {
    await post("/api/g/album/dodaj", {album: a.id, ids}); zamknijMenuAlb(); gotowe(a.nazwa);
  }));
  m.append(przycisk("＋ Nowy album…", async () => {
    const n = prompt("Nazwa nowego albumu:"); if (!n) return;
    const w = await post("/api/g/album/nowy", {nazwa: n, ids}); zamknijMenuAlb(); gotowe(w.nazwa);
  }));
}
// telefon: przytrzymanie palcem na miniaturze zaczyna zaznaczanie
$("siatka").addEventListener("pointerdown", e => {
  const k = e.target.closest(".k"); if (!k || e.pointerType === "mouse") return;
  clearTimeout(g.dlugieZegar);
  const x = e.clientX, y = e.clientY;
  g.dlugieZegar = setTimeout(() => { g.dlugie = true; zaznacz(+k.dataset.i); if (navigator.vibrate) navigator.vibrate(30); }, 520);
  const stop = ev => { if (ev.type !== "pointermove" || Math.hypot(ev.clientX - x, ev.clientY - y) > 10) { clearTimeout(g.dlugieZegar); off(); } };
  const off = () => ["pointerup", "pointercancel", "pointermove"].forEach(t => $("siatka").removeEventListener(t, stop));
  ["pointerup", "pointercancel", "pointermove"].forEach(t => $("siatka").addEventListener(t, stop));
});
$("siatka").addEventListener("contextmenu", e => { if (e.target.closest(".k") && g.dlugie) e.preventDefault(); });
document.addEventListener("keydown", e => {
  if (!$("pelny").hidden || !$("ed").hidden) return;
  if (!$("dt").hidden) { if (e.key === "Escape") $("dt").hidden = true; if (e.key === "Enter") $("dt-zapisz").click(); return; }
  if (!$("lok").hidden) { if (e.key === "Escape") zamknijLok(); return; }
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if (e.key === "Escape" && g.zazn.size) koniecZazn();
  if ((e.ctrlKey || e.metaKey) && (e.key === "a" || e.key === "A") && g.pliki.length) { e.preventDefault(); $("zz-wszystkie").click(); }
  if (e.key === "Delete" && g.zazn.size && MOZE_USUWAC) $("zz-usun").click();
});

// ---------- podgląd na cały ekran ----------
async function pokazPelny(lista, poz) {
  g.lista = lista; g.poz = poz;
  $("pelny").hidden = false; zoomReset();
  const p = lista[poz], t = $("pelny-tresc"); t.replaceChildren();
  if (p.rodzaj === "film") {
    const v = document.createElement("video"); v.controls = true; v.autoplay = true;
    // MP4/MOV/WebM — oryginał; stare formaty (AVI, MPG, 3GP, WMV…) albo błąd (HEVC) — MP4 przerabiany w locie (ffmpeg)
    const natywny = /\.(mp4|m4v|mov|webm)$/i.test(p.nazwa || "");
    const zrodla = [...(natywny ? [url("/api/g/film", {id: p.id})] : []), url("/api/g/film-mp4", {id: p.id}),
                    url("/api/g/film-mp4", {id: p.id, f: "webm"})];
    let nr = 0;
    const info = document.createElement("div"); info.className = "film-info";
    info.textContent = "⏳ Przygotowuję stary format filmu…"; info.hidden = natywny;
    v.onplaying = () => { info.hidden = true; };
    v.src = zrodla[0];
    v.onerror = () => {  // np. HEVC z iPhone'a albo AVI — kolejne źródło: MP4, potem WebM (przerabiane w locie)
      if (++nr < zrodla.length) { info.hidden = false; v.src = zrodla[nr]; v.play().catch(() => {}); return; }
      const b = document.createElement("div"); b.className = "film-blad";
      b.append("🎬 Tego filmu nie da się odtworzyć (uszkodzony albo nietypowy format).", document.createElement("br"));
      if (W_PROGRAMIE) {
        const o = document.createElement("button"); o.textContent = "⤢ Otwórz w programie Windows"; o.onclick = e => { e.stopPropagation(); otworzWProgramie(p); }; b.append(o);
      } else {
        const a = document.createElement("a"); a.href = url("/api/g/film", {id: p.id}); a.download = p.nazwa; a.textContent = "⬇ Pobierz film"; b.append(a);
      }
      t.replaceChildren(b);
    };
    v.onended = () => { if (g.pokaz) krokPokazu(); };
    t.append(v, info);
  } else {
    const mini = new Image(); mini.src = miniatura(p.id); t.append(mini);  // najpierw szybka miniatura
    const im = new Image(); im.src = url("/api/g/podglad", {id: p.id});
    im.onload = () => { if (g.lista[g.poz] === p) { t.replaceChildren(im); zoomRysuj(); } };
  }
  $("pelny-opis").textContent = `${p.nazwa} · ${dataTxt(p.data)}`;
  $("pelny-opis").title = "Kółko myszy / szczypanie = powiększenie · dwuklik = 250% · przeciągnij, żeby przesunąć · 0 = całe";
  narzedziaPelnego(p); miniMapa(p);
  if (!$("wl").hidden) wlasciwosci(p);
  if (p.miejsce === undefined) {
    try {
      const d = await api("/api/g/plik", {id: p.id}); p.miejsce = d.miejsce; p.ulubione = d.ulubione; p.dokument = d.dokument;
      if (p.lat == null && d.lat != null) { p.lat = d.lat; p.lon = d.lon; }
    }
    catch (e) { p.miejsce = null; }
  }
  if (g.lista[g.poz] === p) { narzedziaPelnego(p); miniMapa(p); }
  if (g.lista[g.poz] === p && p.miejsce) $("pelny-opis").textContent += " · " + p.miejsce;
  if (p.rodzaj === "zdjecie") {  // 👤 kto jest na zdjęciu (imiona nadane w „Osoby”)
    if (p.osoby === undefined) {
      try { p.osoby = [...new Set((await api("/api/g/twarze-pliku", {id: p.id})).twarze.map(t => t.nazwa).filter(Boolean))]; }
      catch (e) { p.osoby = []; }
    }
    if (g.lista[g.poz] === p && p.osoby.length) $("pelny-opis").textContent += " · 👤 " + p.osoby.join(", ");
  }
  $("pelny").querySelector(".pop").hidden = poz <= 0;
  $("pelny").querySelector(".nast").hidden = poz >= lista.length - 1;
}
// mała mapa w rogu podglądu: gdzie zrobiono zdjęcie; klik = duża mapa w tym miejscu
function miniMapa(p) {
  const el = $("mini-mapa");
  if (!p || p.lat == null || typeof L === "undefined") { el.hidden = true; return; }
  el.hidden = false;
  if (!g.miniMapa) {
    g.miniMapa = L.map("mini-mapa-m", {zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false,
                                       doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false});
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19}).addTo(g.miniMapa);
    g.miniZnacznik = L.marker([p.lat, p.lon]).addTo(g.miniMapa);
    el.onclick = e => {
      e.stopPropagation();
      const q = g.lista[g.poz]; if (!q || q.lat == null) return;
      zamknijPelny(); widok("mapa");
      setTimeout(() => { if (g.mapa) g.mapa.setView([q.lat, q.lon], 16); }, 400);
    };
  }
  g.miniZnacznik.setLatLng([p.lat, p.lon]);
  setTimeout(() => { g.miniMapa.invalidateSize(); g.miniMapa.setView([p.lat, p.lon], 13); }, 30);
  $("mini-mapa-t").textContent = p.miejsce ? "📍 " + p.miejsce : "📍 miejsce zdjęcia";
}
function zamknijPelny() { stopPokaz(); $("pelny").hidden = true; $("pelny-tresc").replaceChildren(); zoomReset(); zamknijMenuAlb(); }

// ---------- powiększanie: kółko myszy (do kursora), dwuklik, szczypanie na telefonie, przeciąganie ----------
const zoom = {s: 1, x: 0, y: 0, palce: new Map(), start: null, zegar: null};
const obrazPelny = () => $("pelny-tresc").querySelector("img");
function zoomUstaw(s, px, py) {  // s — nowa skala; (px, py) — punkt ekranu, który ma zostać pod kursorem
  const im = obrazPelny(); if (!im) return;
  s = Math.min(8, Math.max(1, s));
  const r = im.getBoundingClientRect();
  const cx = (px ?? r.left + r.width / 2) - r.left, cy = (py ?? r.top + r.height / 2) - r.top;
  zoom.x += cx - cx * s / zoom.s; zoom.y += cy - cy * s / zoom.s; zoom.s = s;
  if (s === 1) { zoom.x = 0; zoom.y = 0; }
  zoomRysuj();
  const e = $("pelny-skala"); e.textContent = Math.round(s * 100) + "%"; e.style.opacity = s > 1 ? 1 : 0;
  clearTimeout(zoom.zegar); zoom.zegar = setTimeout(() => { e.style.opacity = 0; }, 1200);
}
function zoomRysuj() {
  const im = obrazPelny(); if (!im) return;
  im.style.transform = zoom.s === 1 ? "" : `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.s})`;
  im.classList.toggle("zoom", zoom.s > 1);
}
function zoomReset() { zoom.s = 1; zoom.x = 0; zoom.y = 0; zoom.palce.clear(); zoomRysuj(); $("pelny-skala").style.opacity = 0; }
$("pelny-tresc").addEventListener("wheel", e => {
  if (!obrazPelny()) return;
  e.preventDefault();
  zoomUstaw(zoom.s * Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0022)), e.clientX, e.clientY);
}, {passive: false});
$("pelny-tresc").addEventListener("dblclick", e => {
  if (e.target.tagName !== "IMG") return;
  e.preventDefault(); zoomUstaw(zoom.s > 1 ? 1 : 2.5, e.clientX, e.clientY);
});
$("pelny-tresc").addEventListener("pointerdown", e => {
  if (e.target.tagName !== "IMG") return;
  zoom.palce.set(e.pointerId, {x: e.clientX, y: e.clientY});
  e.target.setPointerCapture(e.pointerId);
  if (zoom.palce.size === 2) {
    const [a, b] = [...zoom.palce.values()];
    zoom.start = {d: Math.hypot(a.x - b.x, a.y - b.y), s: zoom.s};
  }
  e.target.classList.add("ciagnie");
});
$("pelny-tresc").addEventListener("pointermove", e => {
  const p = zoom.palce.get(e.pointerId); if (!p) return;
  if (zoom.palce.size === 2 && zoom.start) {  // szczypanie
    p.x = e.clientX; p.y = e.clientY;
    const [a, b] = [...zoom.palce.values()];
    zoomUstaw(zoom.start.s * Math.hypot(a.x - b.x, a.y - b.y) / zoom.start.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
  } else if (zoom.s > 1) {  // przesuwanie powiększonego zdjęcia
    zoom.x += e.clientX - p.x; zoom.y += e.clientY - p.y; p.x = e.clientX; p.y = e.clientY; zoomRysuj();
  }
});
for (const t of ["pointerup", "pointercancel"]) $("pelny-tresc").addEventListener(t, e => {
  zoom.palce.delete(e.pointerId); if (zoom.palce.size < 2) zoom.start = null;
  const im = obrazPelny(); if (im && !zoom.palce.size) im.classList.remove("ciagnie");
});
function krok(d) { const n = g.poz + d; if (n >= 0 && n < g.lista.length) pokazPelny(g.lista, n); }
function krokRecznie(d) { stopPokaz(); krok(d); }
$("pelny").querySelector(".zam").onclick = zamknijPelny;
$("pelny").querySelector(".pop").onclick = e => { e.stopPropagation(); krokRecznie(-1); };
$("pelny").querySelector(".nast").onclick = e => { e.stopPropagation(); krokRecznie(1); };
$("pelny").onclick = e => { if (e.target.id === "pelny" || e.target.id === "pelny-tresc") zamknijPelny(); };
document.addEventListener("keydown", e => {
  if ($("pelny").hidden) return;
  if (!$("dt").hidden) { if (e.key === "Escape") $("dt").hidden = true; if (e.key === "Enter") $("dt-zapisz").click(); return; }
  if (e.key === "Escape") { if (g.pokaz) stopPokaz(); else if (zoom.s > 1) zoomReset(); else zamknijPelny(); }
  if (e.key === "ArrowLeft" && zoom.s === 1) krokRecznie(-1);
  if (e.key === "ArrowRight" && zoom.s === 1) krokRecznie(1);
  if (e.key === "p" || e.key === "P") przelaczPokaz();
  if ((e.key === "f" || e.key === "F") && W_PROGRAMIE) $("p-ulub").click();
  if (!$("lok").hidden) { if (e.key === "Escape") zamknijLok(); return; }
  if (e.key === "Delete" && MOZE_USUWAC) $("p-usun").click();
  if ((e.key === "l" || e.key === "L") && MOZE_USUWAC) $("p-miejsce").click();
  if (e.key === "i" || e.key === "I") $("p-info").click();
  if ((e.key === "d" || e.key === "D") && W_PROGRAMIE && !$("p-dok").hidden) $("p-dok").click();
  if (e.key === "+" || e.key === "=") zoomUstaw(zoom.s * 1.4);
  if (e.key === "-") zoomUstaw(zoom.s / 1.4);
  if (e.key === "0") zoomUstaw(1);
});
let dotyk = null;  // przesuwanie palcem na telefonie
$("pelny").addEventListener("touchstart", e => { dotyk = e.touches.length === 1 ? e.touches[0].clientX : null; }, {passive: true});
$("pelny").addEventListener("touchend", e => {
  if (dotyk === null || zoom.s > 1 || zoom.palce.size) { dotyk = null; return; }  // powiększone: palec przesuwa
  const d = e.changedTouches[0].clientX - dotyk; dotyk = null;
  if (Math.abs(d) > 50) krokRecznie(d < 0 ? 1 : -1);
});

// ---------- mapa ----------
async function pokazMape() {
  if (!g.mapa) {
    g.mapa = L.map("mapa", {doubleClickZoom: false, worldCopyJump: true}).setView([52, 19], 6);
    const warstwa = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>'});
    let bledy = 0;
    warstwa.on("tileerror", () => {
      if (++bledy === 3) info("Brak połączenia z internetem — mapa bez podkładu (pinezki działają).");
    });
    warstwa.addTo(g.mapa);
  }
  setTimeout(() => g.mapa.invalidateSize(), 50);
  if (g.punkty) return;
  info("Wczytuję miejsca…");
  const r = await api("/api/g/mapa");
  g.punkty = r.punkty;
  if (g.klaster) g.mapa.removeLayer(g.klaster);
  g.klaster = L.markerClusterGroup({chunkedLoading: true, maxClusterRadius: 50, showCoverageOnHover: false});
  const markery = g.punkty.map(([id, lat, lon, film]) => {
    const m = L.marker([lat, lon], {title: film ? "film" : "zdjęcie", draggable: MOZE_USUWAC, autoPan: true});
    m.on("click", () => otworzPinezke(m, id, film));
    if (MOZE_USUWAC) m.on("dragend", () => {  // 📍 przesunięta pinezka = nowe miejsce zdjęcia
      const ll = m.getLatLng(), stare = [lat, lon];
      ustawLokalizacje([id], ll.lat, ll.lng, {[id]: stare}).then(ok => {
        if (ok) { lat = ll.lat; lon = ll.lng; } else m.setLatLng(stare);
      });
    });
    m.on("dblclick", e => { L.DomEvent.stop(e); pelnyZPinezki(id, film); });
    return m;
  });
  g.klaster.addLayers(markery);
  g.mapa.addLayer(g.klaster);
  if (markery.length) g.mapa.fitBounds(g.klaster.getBounds(), {padding: [30, 30], maxZoom: 14});
  info(markery.length
    ? `${markery.length.toLocaleString("pl-PL")} zdjęć i filmów na mapie · kliknij pinezkę = miniatura, dwa razy = całe zdjęcie` +
      (MOZE_USUWAC ? " · przeciągnij pinezkę = zmień miejsce" : "")
    : "Brak zdjęć z zapisanym miejscem (GPS).");
}
function info(t) { $("mapa-info").hidden = !t; $("mapa-info").textContent = t || ""; }
async function otworzPinezke(m, id, film) {
  const div = document.createElement("div"); div.className = "popup";
  div.innerHTML = film ? '<div style="font-size:48px;text-align:center">🎬</div>' : "";
  if (!film) {
    const im = new Image(); im.src = miniatura(id); im.alt = ""; im.title = "Kliknij, aby zobaczyć całe";
    im.onclick = () => pelnyZPinezki(id, film); div.append(im);
  }
  const n = document.createElement("div"); n.className = "n"; n.textContent = "…";
  const d = document.createElement("div"); d.className = "m";
  const b = document.createElement("button"); b.textContent = film ? "▶ Odtwórz" : "🔍 Całe zdjęcie";
  b.onclick = () => pelnyZPinezki(id, film);
  div.append(n, d, b);
  if (MOZE_USUWAC) {
    const u = document.createElement("button"); u.textContent = "✖ Usuń lokalizację"; u.className = "lok-usun";
    u.onclick = async () => {
      const ll = m.getLatLng();
      if (await ustawLokalizacje([id], null, null, {[id]: [ll.lat, ll.lng]})) { g.klaster.removeLayer(m); }
    };
    div.append(u);
  }
  m.bindPopup(div, {maxWidth: 260}).openPopup();
  try {
    const p = await api("/api/g/plik", {id});
    n.textContent = p.nazwa; d.textContent = dataTxt(p.data) + (p.miejsce ? " · " + p.miejsce : "");
  } catch (e) { n.textContent = e.message; }
}
async function pelnyZPinezki(id, film) {
  let p;
  try { p = await api("/api/g/plik", {id}); } catch (e) { p = {id, nazwa: "", data: null}; }
  p.rodzaj = film ? "film" : "zdjecie";
  pokazPelny([p], 0);
}

// ---------- zwarty nagłówek: tytuł, ⋯ menu, 📊 wykres, 💽 dyski, 🔍 na telefonie ----------
const naglowek = (() => {
  const czytaj = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v === "1"; } catch (e) { return d; } };
  return {wykres: czytaj("kat_g_wykres", innerWidth > 760), dyski: czytaj("kat_g_dyski", false)};
})();
function zapamietaj(k, v) { try { localStorage.setItem(k, v ? "1" : "0"); } catch (e) { /* bez pamięci */ } }
function tytul(ikona, nazwa) {
  const h = $("tytul"); h.replaceChildren(ikona);
  const t = document.createElement("span"); t.className = "t"; t.textContent = " " + nazwa; h.append(t);
  h.title = nazwa;
}
function pokazDyski() {
  const p = g.zakres === "przegladarka";
  $("prz").hidden = !p || !naglowek.dyski;
  $("dyski-btn").classList.toggle("akt", p && naglowek.dyski);
}
$("dyski-btn").onclick = () => { naglowek.dyski = !naglowek.dyski; zapamietaj("kat_g_dyski", naglowek.dyski); pokazDyski(); };
$("wykres-btn").onclick = () => { naglowek.wykres = !naglowek.wykres; zapamietaj("kat_g_wykres", naglowek.wykres); uklad(); };
$("menu-btn").onclick = e => { e.stopPropagation(); $("menu").hidden = !$("menu").hidden; };
$("menu").onclick = e => { if (e.target.tagName === "BUTTON" && !e.target.closest(".menu-rz")) $("menu").hidden = true; };
document.addEventListener("click", e => { if (!$("menu").hidden && !e.target.closest(".menu-w")) $("menu").hidden = true; });
// --- przestrzeń robocza: rozmiar miniatur, podpisy, chowanie pasków, pełny ekran (zapamiętane na tym urządzeniu) ---
const telefonWaski = matchMedia("(max-width:600px)").matches;
const robocza = (() => {
  let z = {};
  try { z = JSON.parse(localStorage.getItem("kat_g_robocza") || "{}"); } catch (e) { /* bez pamięci */ }
  return {kafel: z.kafel || (telefonWaski ? 105 : 200), podpisy: z.podpisy ?? !telefonWaski, chowaj: z.chowaj ?? true};
})();
function ustawRobocza(zmiany = {}) {
  Object.assign(robocza, zmiany);
  robocza.kafel = Math.max(80, Math.min(380, robocza.kafel));
  document.documentElement.style.setProperty("--kafel", robocza.kafel + "px");
  document.body.classList.toggle("bez-podpisow", !robocza.podpisy);
  if (!robocza.chowaj) document.body.classList.remove("zwiniete");
  $("kafel").value = robocza.kafel; $("podpisy").checked = robocza.podpisy; $("chowaj").checked = robocza.chowaj;
  try { localStorage.setItem("kat_g_robocza", JSON.stringify(robocza)); } catch (e) { /* bez pamięci */ }
}
ustawRobocza();
$("kafel").oninput = () => ustawRobocza({kafel: +$("kafel").value});
$("kafel-mn").onclick = () => { ustawRobocza({kafel: robocza.kafel - 30}); };
$("kafel-wi").onclick = () => { ustawRobocza({kafel: robocza.kafel + 30}); };
$("podpisy").onchange = () => ustawRobocza({podpisy: $("podpisy").checked});
$("chowaj").onchange = () => ustawRobocza({chowaj: $("chowaj").checked});
$("siatka").addEventListener("wheel", e => {  // Ctrl + kółko = większe / mniejsze miniatury
  if (!e.ctrlKey) return;
  e.preventDefault(); ustawRobocza({kafel: robocza.kafel + (e.deltaY < 0 ? 20 : -20)});
}, {passive: false});
let ostatniScroll = 0;
$("siatka").addEventListener("scroll", () => {
  const y = $("siatka").scrollTop;
  if (robocza.chowaj) {
    if (y > 160 && y > ostatniScroll + 30) document.body.classList.add("zwiniete");
    else if (y < ostatniScroll - 30 || y < 40) document.body.classList.remove("zwiniete");
  }
  if (Math.abs(y - ostatniScroll) > 30 || y < 40) ostatniScroll = y;
}, {passive: true});
const pelnyEkranMozliwy = !!(document.fullscreenEnabled && document.documentElement.requestFullscreen);
$("pelny-ekran").hidden = !pelnyEkranMozliwy;
$("pelny-ekran").onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => {});
};
document.addEventListener("fullscreenchange", () => {
  $("pelny-ekran").textContent = document.fullscreenElement ? "⛶ Zamknij pełny ekran" : "⛶ Pełny ekran";
});
// --- filtr rodzaju: wszystko / zdjęcia / filmy / dokumenty (zapamiętany) ---
g.rodzaj = (() => { try { return localStorage.getItem("kat_g_rodzaj") || ""; } catch (e) { return ""; } })();
function rysujRodzaje() {
  document.querySelectorAll("#rodzaje button").forEach(b => b.classList.toggle("akt", b.dataset.r === g.rodzaj));
  $("rodzaj-sel").value = g.rodzaj;
}
$("rodzaje").onclick = e => { const b = e.target.closest("button"); if (b) ustawRodzaj(b.dataset.r); };
$("rodzaj-sel").onchange = () => ustawRodzaj($("rodzaj-sel").value);
function ustawRodzaj(r) {
  g.rodzaj = r; try { localStorage.setItem("kat_g_rodzaj", g.rodzaj); } catch (er) { /* bez pamięci */ }
  rysujRodzaje();
  g.punkty = null; g.rok = null; g.mies = null;
  if (g.zrodlo.typ === "os") start(); else pokazWyniki(g.zrodlo);
}
rysujRodzaje();
// --- ⇅ kolejność: od najnowszych / od najstarszych (zapamiętana) ---
g.kol = (() => { try { return localStorage.getItem("kat_g_kol") === "stare" ? "stare" : "nowe"; } catch (e) { return "nowe"; } })();
function rysujKolejnosc() {
  const nowe = g.kol === "nowe";
  $("kolejnosc-t").textContent = nowe ? " Od najnowszych" : " Od najstarszych";
  $("kolejnosc").title = (nowe ? "Teraz: od najnowszych" : "Teraz: od najstarszych") + " — kliknij, żeby odwrócić kolejność zdjęć";
  $("kolejnosc").firstChild.textContent = nowe ? "↓" : "↑";
  $("menu-kol").textContent = nowe ? "⇅ Kolejność: od najnowszych" : "⇅ Kolejność: od najstarszych";
}
$("kolejnosc").onclick = () => {
  g.kol = g.kol === "nowe" ? "stare" : "nowe";
  try { localStorage.setItem("kat_g_kol", g.kol); } catch (e) { /* bez pamięci */ }
  rysujKolejnosc();
  if (g.widok === "kolekcje" || g.widok === "mapa") return;  // zadziała przy następnym otwarciu listy
  // oś czasu: od pierwszego roku w nowej kolejności (najnowszy / najstarszy)
  if (g.zrodlo.typ === "os") { g.rok = null; g.mies = null; wczytajLata().catch(() => {}); } else pokazWyniki(g.zrodlo);
};
rysujKolejnosc();
$("menu-kol").onclick = () => $("kolejnosc").click();
// --- pasek Przeglądarki chowany strzałką (zapamiętane) ---
function ustawPasek(schowany) {
  document.body.classList.toggle("pasek-schowany", schowany);
  try { localStorage.setItem("kat_g_pasek", schowany ? "1" : "0"); } catch (e) { /* bez pamięci */ }
}
ustawPasek((() => { try { return localStorage.getItem("kat_g_pasek") === "1"; } catch (e) { return false; } })());
$("pasek-schowaj").onclick = () => ustawPasek(true);
$("pasek-pokaz").onclick = () => ustawPasek(false);
$("menu-pokaz").onclick = () => { if (g.pliki.length) { pokazPelny(g.pliki, 0); startPokaz(); } };
$("szukaj-btn").onclick = () => {
  const h = document.querySelector("header"), on = !h.classList.contains("szuka");
  h.classList.toggle("szuka", on); if (on) $("szukaj").focus();
};
$("szukaj").addEventListener("blur", () => {
  if (!$("szukaj").value.trim()) document.querySelector("header").classList.remove("szuka");
});

// ---------- przełączanie widoków ----------
function uklad() {  // co widać: oś czasu (wykres, miesiące), wyniki/kolekcja (sama siatka), kolekcje, mapa
  const w = g.widok, os = w === "os" && g.zrodlo.typ === "os";
  $("w-os").classList.toggle("akt", os); $("w-mapa").classList.toggle("akt", w === "mapa");
  $("w-kolekcje").classList.toggle("akt", w === "kolekcje" || (w === "os" && g.zrodlo.typ === "kolekcja"));
  $("w-dzien").classList.toggle("akt", w === "os" && g.zrodlo.typ === "dzien");
  $("w-osoby").classList.toggle("akt", w === "osoby" || (w === "os" && g.zrodlo.typ === "osoba"));
  $("os").hidden = w === "mapa"; $("lata").hidden = !os; $("miesiace").hidden = !os; tip(null);
  $("wykres").hidden = !os || !$("wykres").childElementCount || !naglowek.wykres;
  $("wykres-btn").hidden = !os; $("wykres-btn").classList.toggle("akt", naglowek.wykres);
  $("mapa").hidden = w !== "mapa"; $("mapa-info").hidden = w !== "mapa"; $("mapa-os").hidden = w !== "mapa";
  rysujFiltr();
}
function widok(w) {
  g.widok = w;
  if (w === "os" && g.zrodlo.typ !== "os") { g.zrodlo = {typ: "os"}; $("szukaj").value = ""; wczytajPliki(); }
  uklad();
  if (w === "mapa") pokazMape().catch(e => info(e.message));
  if (w === "kolekcje") rysujKolekcje();
  if (w === "osoby") rysujOsoby();
}
function pokazWyniki(zrodlo) {  // wyniki szukania, ulubione, album, tego dnia — w tej samej siatce
  g.zrodlo = zrodlo; g.widok = "os"; g.pliki = []; g.razem = 0;
  $("siatka").innerHTML = '<div class="pusto">Szukam…</div>';
  uklad(); wczytajPliki().catch(e => { $("siatka").innerHTML = `<div class="pusto">${e.message}</div>`; });
}
$("w-os").onclick = () => widok("os");
$("w-mapa").onclick = () => widok("mapa");
$("w-kolekcje").onclick = () => widok("kolekcje");
$("w-osoby").onclick = () => widok("osoby");
$("w-dzien").onclick = () => { g.widok = "os"; pokazWyniki({typ: "dzien", md: mdDzis(), dni: 0}); };

// ---------- w oknie programu: zakres, zamykanie, udostępnianie na telefon ----------
if (W_PROGRAMIE) {
  document.body.classList.add("w-programie");
  $("zakres").hidden = false; $("na-telefon").hidden = false; $("zamknij").hidden = false;
  g.zakres = P.get("z") || "biblioteka"; $("zakres").value = g.zakres;
  $("zakres").onchange = () => { g.zakres = $("zakres").value; g.punkty = null; g.rok = null; ustawZakres(); start(); };
  $("zamknij").onclick = () => window.parent.postMessage("zamknij-galerie", "*");
  $("na-telefon").onclick = () => telefon(true);
  $("tel-zamknij").onclick = () => { $("telefon").hidden = true; };
  $("tel-wylacz").onclick = () => telefon(false);
  ustawZakres();
  if (P.get("tel") === "1") telefon(true);  // 📱 w nagłówku programu
}
if (!W_PROGRAMIE && P.get("pilot")) {  // telefon: powrót do pilota (stan komputera, kolejne kroki)
  $("zamknij").hidden = false; $("zamknij").textContent = "←"; $("zamknij").title = "Wróć do pilota";
  $("zamknij").onclick = () => { location.href = "/"; };
  tytul(...({przegladarka: ["🔭", "Przeglądarka"], wszystko: ["🗂", "Projekt"]}[g.zakres] || ["📚", "Biblioteka"]));
}
function telSterowanie() {
  const c = $("tel-ster");
  if (c) return c.checked;
  try { return localStorage.getItem("katalogator_tel_ster") !== "0"; } catch (e) { return true; }
}
async function telefon(wlacz, pin) {
  $("telefon").hidden = false; $("tel-tresc").textContent = wlacz ? "Uruchamiam…" : "Wyłączam…";
  try {
    const r = await fetch(url("/api/telefon"), {method: "POST", headers: {"Content-Type": "application/json", "X-Token": TOKEN},
                                                 body: JSON.stringify({wlacz, zakres: g.zakres, sterowanie: telSterowanie(),
                                                                       ...(pin !== undefined ? {pin} : {})})});
    const j = await r.json();
    if (!r.ok || j.blad) throw new Error(j.blad || r.statusText);
    if (!j.wlaczone) { $("telefon").hidden = true; return; }
    const adr = j.adresy[0] || "";
    const qr = qrcode(0, "M"); qr.addData(adr); qr.make();
    $("tel-tresc").innerHTML = `<div class="qr"><div>${qr.createSvgTag({cellSize: 5, margin: 2})}</div>
      <div><div class="info">PIN</div><div class="pin"></div>
        <button id="tel-pin" class="tel-pin" title="Własny PIN — zapamiętany na stałe (np. łatwy do zapamiętania w domowej sieci)">✎ Ustaw swój PIN</button>
        <div class="info" id="tel-pin-info"></div></div></div>
      <div>Zeskanuj kod aparatem telefonu albo wpisz w przeglądarce telefonu: <code id="tel-adr"></code></div>
      <ul><li>Telefon musi być w tej samej sieci Wi-Fi — albo mieć włączony <b>Tailscale</b> (wtedy działa z każdego miejsca;
      adres zaczyna się od 100.): <span id="tel-inne"></span></li>
      <li>Windows może zapytać o zaporę — zaznacz <b>sieci prywatne</b> i kliknij <b>Zezwalaj</b>.</li>
      <li>Działa, dopóki komputer jest włączony: zamknięcie okna nie wyłącza telefonu (program pracuje w tle),
      a po ponownym uruchomieniu telefon włącza się sam — z tym samym PIN-em. Wyłączasz przyciskiem „Wyłącz” niżej.</li>
      <li>Na telefonie: pilot (postęp, kolejne kroki) i <b>🖥 Pełny program</b> — Duplikaty, Dokumenty, Podobne, Drzewo,
      kosz, jak na komputerze (gdy zaznaczone niżej „Pozwól sterować”).</li>
      <li><b>Spoza domu</b>: włącz w telefonie VPN do domu (WireGuard na domowym serwerze albo Tailscale) i otwórz ten sam adres.
      Programu nie wystawiamy wprost do internetu.</li></ul>
      <label class="tel-ster"><input type="checkbox" id="tel-ster"> Pozwól sterować z telefonu (uruchamianie kroków, przerywanie)</label>
      <label class="tel-ster" id="tel-auto-w"><input type="checkbox" id="tel-auto"> Uruchamiaj Katalogator razem z Windows (w tle, bez okna) —
      telefon działa od razu po restarcie komputera</label>`;
    $("tel-auto-w").hidden = !j.autostart_mozliwy;
    $("tel-auto").checked = !!j.autostart;
    $("tel-auto").onchange = async () => {
      const c = $("tel-auto");
      try {
        const r = await fetch(url("/api/autostart"), {method: "POST", headers: {"Content-Type": "application/json", "X-Token": TOKEN},
                                                       body: JSON.stringify({wlacz: c.checked})});
        const w = await r.json();
        if (!r.ok || w.blad) throw new Error(w.blad || r.statusText);
        c.checked = !!w.autostart;
      } catch (e) { c.checked = !c.checked; alert(e.message); }
    };
    $("tel-ster").checked = j.sterowanie !== false;
    $("tel-pin-info").textContent = j.wlasny_pin ? "Twój PIN — stały" : "losowy przy każdym włączeniu";
    $("tel-pin").onclick = () => {
      const n = prompt("Twój PIN na telefon (4–12 cyfr) — zostanie zapamiętany.\nZostaw puste, żeby wrócić do losowego PIN-u.",
                       j.wlasny_pin ? j.pin : "");
      if (n !== null) telefon(true, n.trim());
    };
    $("tel-ster").onchange = () => {
      try { localStorage.setItem("katalogator_tel_ster", $("tel-ster").checked ? "1" : "0"); } catch (e) { /* bez pamięci */ }
      telefon(true);
    };
    $("tel-tresc").querySelector(".pin").textContent = j.pin;
    $("tel-adr").textContent = adr;
    $("tel-inne").textContent = j.adresy.slice(1).join(", ") || "—";
  } catch (e) {
    if (pin !== undefined) { alert(e.message); return telefon(true); }  // zły PIN — wracamy do bieżącego
    $("tel-tresc").textContent = e.message;
  }
}

// ---------- pasek nad siatką: szukanie, obszar z mapy, kolekcja, tego dnia ----------
function liczbaZdjec(n) {
  const f = n === 1 ? "zdjęcie" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? "zdjęcia" : "zdjęć";
  return `${n.toLocaleString("pl-PL")} ${f}`;
}
function przycisk(tekst, akcja, tytul = "", klasa = "") {
  const b = document.createElement("button"); b.textContent = tekst; b.onclick = akcja;
  if (tytul) b.title = tytul; if (klasa) b.className = klasa; return b;
}
function znacznik(tekst, zamknij, tytul) {
  const z = document.createElement("span"); z.className = "zn"; z.append(tekst);
  const x = przycisk("✕", zamknij, tytul); z.append(x); return z;
}
function rysujFiltr() {
  const f = $("filtr"); f.replaceChildren();
  const z = g.zrodlo, ile = liczbaZdjec;
  const inf = t => { const s = document.createElement("span"); s.className = "info"; s.textContent = t; return s; };
  const pokaz = () => g.pliki.length ? przycisk("▶ Pokaz slajdów", () => { pokazPelny(g.pliki, 0); startPokaz(); }, "Pokaz na cały ekran (P)") : null;
  if (g.widok === "kolekcje") {
    const t = document.createElement("span"); t.className = "tyt"; t.textContent = "⭐ Kolekcje"; f.append(t, inf("ulubione i albumy"));
  } else if (g.widok === "osoby") {
    filtrOsob(f, inf);
  } else if (g.widok === "os" && z.typ === "osoba") {
    f.append(przycisk("← Osoby", () => widok("osoby")));
    const t = document.createElement("span"); t.className = "tyt"; t.textContent = "👤 " + (z.nazwa || "Bez imienia"); f.append(t, inf(ile(g.razem)));
    const p = pokaz(); if (p) f.append(p);
    if (W_PROGRAMIE) f.append(przycisk("✎ Imię", async () => {
      const n = prompt("Imię (albo opis, np. „Babcia Zosia”):", z.nazwa || ""); if (n === null) return;
      const w = await post("/api/g/osoba/nazwa", {id: z.osoba, nazwa: n});
      if (w.polaczono) { z.osoba = w.polaczono; toastG(`👤 Połączono z „${n.trim()}” — to ta sama osoba.`); }
      z.nazwa = n.trim(); pokazWyniki(z);
    }, "Nadaj imię — potem znajdziesz tę osobę także wpisując imię w wyszukiwarkę"),
    przycisk("🙈 Ukryj", async () => { await post("/api/g/osoba/ukryj", {id: z.osoba, tak: true}); widok("osoby"); },
             "Ukryj tę osobę na liście (np. obcy w tle) — zdjęcia zostają"));
    if (g.razem) f.append(przycisk("＋ Zapisz jako album", () => zapiszJakoAlbum(z.nazwa || "Osoba"), "Nowy album ze zdjęciami tej osoby"));
  } else if (g.widok === "os" && z.typ === "szukaj") {
    f.append(znacznik("🔍 " + (z.opis || z.q), () => { $("szukaj").value = ""; widok("os"); }, "Wyczyść szukanie"), inf(ile(g.razem)));
    const p = pokaz(); if (p) f.append(p);
    if (W_PROGRAMIE && g.razem) f.append(przycisk("＋ Zapisz jako album", () => zapiszJakoAlbum(z.opis || z.q), "Nowy album z wynikami (do 5000)"));
  } else if (g.widok === "os" && z.typ === "kolekcja") {
    f.append(przycisk("← Kolekcje", () => widok("kolekcje")));
    const t = document.createElement("span"); t.className = "tyt"; t.textContent = z.nazwa || ""; f.append(t, inf(ile(g.razem)));
    const p = pokaz(); if (p) f.append(p);
    if (g.razem) f.append(przycisk("⬇ ZIP", () => z.kol === "album" ? pobierzZip({album: z.album}) : pobierzZip({ids: g.pliki.map(x => x.id)}),
                                   "Pobierz cały album jako ZIP (oryginały)"));
    if (W_PROGRAMIE && z.kol === "album") f.append(przycisk(z.udostepniony ? "🔗 Udostępniony" : "🔗 Udostępnij",
      () => udostepnij(z), "Link do tego albumu dla rodziny — bez PIN-u, tylko oglądanie i pobieranie", z.udostepniony ? "akt" : ""));
    if (W_PROGRAMIE && z.kol === "album") {
      f.append(przycisk("✎ Zmień nazwę", async () => {
        const n = prompt("Nowa nazwa albumu:", z.nazwa || ""); if (!n) return;
        const w = await post("/api/g/album/nazwa", {album: z.album, nazwa: n}); z.nazwa = w.nazwa; rysujFiltr();
      }), przycisk("🗑 Usuń album", async () => {
        if (!confirm(`Usunąć album „${z.nazwa}”?\n\nZdjęcia zostają na dysku — znika tylko album.`)) return;
        await post("/api/g/album/usun", {album: z.album}); widok("kolekcje");
      }));
    }
  } else if (g.widok === "os" && z.typ === "dzien") {
    const md = z.md || mdDzis();
    const nav = document.createElement("span"); nav.className = "dzien-nav";
    const b = document.createElement("b"); b.textContent = mdTxt(md) + (md === mdDzis() ? " (dziś)" : "");
    nav.append(przycisk("‹", () => pokazWyniki({...z, md: mdPrzesun(md, -1)}), "Dzień wcześniej"), b,
               przycisk("›", () => pokazWyniki({...z, md: mdPrzesun(md, 1)}), "Dzień później"));
    f.append(znacznik("🕰 Tego dnia w poprzednich latach", () => widok("os")), nav);
    if (md !== mdDzis()) f.append(przycisk("Dziś", () => pokazWyniki({...z, md: mdDzis()})));
    const sel = document.createElement("select"); sel.title = "Ile dni wokół tej daty";
    for (const [v, t] of [[0, "tylko ten dzień"], [3, "± 3 dni"], [7, "± tydzień"]]) {
      const o = document.createElement("option"); o.value = v; o.textContent = t; sel.append(o);
    }
    sel.value = z.dni || 0; sel.onchange = () => pokazWyniki({...z, dni: +sel.value}); f.append(sel);
    if (g.razem) f.append(inf(ile(g.razem) + " · z " + (z.lata || []).length + ((z.lata || []).length === 1 ? " roku" : " lat")));
    const p = pokaz(); if (p) f.append(p);
  } else if (g.widok === "os") {
    if (g.obszar) f.append(znacznik("📍 Obszar z mapy", () => { g.obszar = null; g.rok = null; wczytajLata(); rysujFiltr(); },
                                    "Pokaż wszystkie miejsca"));
    const p = pokaz(); if (p && f.childElementCount) f.append(p);
  }
  f.hidden = !f.childElementCount;
  const d = g.dzien && g.dzien.razem ? g.dzien : null;  // „tego dnia lata temu” — znaczek na 🕰 zamiast paska
  $("dzien-ile").hidden = !d; $("dzien-ile").textContent = d ? (d.razem > 99 ? "99+" : d.razem) : "";
  $("w-dzien").title = d ? `Tego dnia w poprzednich latach: ${d.lata.map(x => x.rok).slice(0, 6).join(", ")} (${d.razem})`
    : "Zdjęcia z tego samego dnia w poprzednich latach";
  $("menu-pokaz").disabled = !g.pliki.length;
}

// ---------- wyszukiwarka ----------
let szukajZegar = null;
$("szukaj").addEventListener("input", () => {
  clearTimeout(szukajZegar);
  szukajZegar = setTimeout(() => {
    const q = $("szukaj").value.trim();
    if (q.length >= 2) pokazWyniki({typ: "szukaj", q}); else if (!q && g.zrodlo.typ === "szukaj") widok("os");
  }, 450);
});
$("szukaj").addEventListener("keydown", e => {
  if (e.key === "Enter") { clearTimeout(szukajZegar); const q = $("szukaj").value.trim(); if (q) pokazWyniki({typ: "szukaj", q}); }
  if (e.key === "Escape") { $("szukaj").value = ""; if (g.zrodlo.typ === "szukaj") widok("os"); }
});
async function wszystkieId() {  // wszystkie wyniki (do 5000) — np. do zapisania jako album
  while (g.pliki.length < Math.min(g.razem, 5000)) { const n = g.pliki.length; await wczytajPliki(true); if (g.pliki.length === n) break; }
  return g.pliki.map(p => p.id);
}
async function zapiszJakoAlbum(nazwa) {
  const n = prompt("Nazwa nowego albumu:", nazwa); if (!n) return;
  const ids = await wszystkieId();
  const w = await post("/api/g/album/nowy", {nazwa: n, ids});
  alert(`Utworzono album „${w.nazwa}” (${w.dodane} zdjęć). Znajdziesz go w ⭐ Kolekcje.`);
}

// ---------- kolekcje: ulubione i albumy ----------
async function rysujKolekcje() {
  const s = $("siatka"); s.innerHTML = '<div class="pusto">Wczytuję…</div>';
  let r; try { r = await api("/api/g/albumy"); } catch (e) { s.innerHTML = `<div class="pusto">${e.message}</div>`; return; }
  if (g.widok !== "kolekcje") return;
  s.replaceChildren();
  const kafel = (ikona, nazwa, n, okladka, klik, klasa = "") => {
    const k = document.createElement("div"); k.className = "k album " + klasa; k.style.cursor = "pointer";
    const ob = document.createElement("div"); ob.className = "ob"; ob.textContent = ikona;
    if (okladka) { const im = new Image(); im.src = miniatura(okladka, false); im.alt = ""; ob.append(im); }
    const op = document.createElement("div"); op.className = "op"; op.innerHTML = "<div></div><div class='m'></div>";
    op.children[0].textContent = nazwa; op.children[1].textContent = n === null ? "" : liczbaZdjec(n);
    k.append(ob, op); k.onclick = klik; s.append(k);
  };
  kafel("⭐", "Ulubione", r.ulubione.n, r.ulubione.okladka, () => pokazWyniki({typ: "kolekcja", kol: "ulubione"}));
  for (const a of r.albumy) kafel("🗂", a.nazwa, a.n, a.okladka, () => pokazWyniki({typ: "kolekcja", kol: "album", album: a.id, nazwa: a.nazwa, udostepniony: a.udostepniony}));
  if (W_PROGRAMIE) kafel("＋", "Nowy album", null, null, async () => {
    const n = prompt("Nazwa nowego albumu:", "Wakacje " + new Date().getFullYear()); if (!n) return;
    await post("/api/g/album/nowy", {nazwa: n, ids: []}); rysujKolekcje();
  }, "nowy");
  if (!W_PROGRAMIE && !r.albumy.length && !r.ulubione.n) s.innerHTML = '<div class="pusto">Brak ulubionych i albumów — tworzy się je w programie na komputerze.</div>';
}

// ---------- 👤 osoby: twarze z dysków, grupowane w osoby (wykrywanie w tle, na tym komputerze) ----------
const osoby = {wyb: new Set(), dane: null, zegar: null, wszystkie: false, uzywane: false};
function filtrOsob(f, inf) {
  const t = document.createElement("span"); t.className = "tyt"; t.textContent = "👤 Osoby"; f.append(t);
  const d = osoby.dane;
  if (!d) return;
  const st = d.stan || {};
  if (st.trwa) {
    const pr = st.wszystkie ? st.zrobione / st.wszystkie : 0;
    const p = document.createElement("span"); p.className = "twarze-pasek"; p.innerHTML = "<i></i>"; p.firstChild.style.width = Math.round(pr * 100) + "%";
    f.append(inf(st.wszystkie ? `Szukam twarzy: ${st.zrobione.toLocaleString("pl-PL")} z ${st.wszystkie.toLocaleString("pl-PL")} zdjęć · twarzy: ${st.twarzy}` : st.komunikat || "…"), p);
    if (W_PROGRAMIE) f.append(przycisk("Przerwij", async () => { await post("/api/g/twarze/przerwij", {}); rysujOsoby(); }));
  } else {
    f.append(inf(st.blad ? "⚠ " + st.blad : `${liczbaOsob(d.osoby.length)} · przejrzane zdjęcia: ${d.przejrzane.toLocaleString("pl-PL")} z ${d.zdjec.toLocaleString("pl-PL")}`));
    if (W_PROGRAMIE && d.przejrzane < d.zdjec && !d.niedostepne && (d.przejrzane || d.osoby.length))
      f.append(przycisk(d.przejrzane ? "👤 Szukaj na nowych zdjęciach" : "👤 Znajdź twarze", startTwarzy, "Przegląda zdjęcia na tym komputerze — nic nie wysyła do internetu", "akt"));
  }
  if (d.pozostale || osoby.wszystkie) f.append(przycisk(osoby.wszystkie ? "Tylko ważne" : `Pokaż wszystkie (+${d.pozostale})`,
    () => { osoby.wszystkie = !osoby.wszystkie; rysujOsoby(); }, "Także osoby z jednego zdjęcia i ukryte"));
  if (W_PROGRAMIE && osoby.wyb.size >= 2) f.append(przycisk(`🔗 Połącz zaznaczone (${osoby.wyb.size})`, async () => {
    const w = await post("/api/g/osoba/polacz", {ids: [...osoby.wyb]}); osoby.wyb.clear();
    toastG("👤 Połączono — to jedna osoba."); if (w.ok) rysujOsoby();
  }, "Ta sama osoba rozpoznana jako kilka — połącz w jedną", "akt"));
  if (osoby.wyb.size) f.append(przycisk("Odznacz", () => { osoby.wyb.clear(); rysujOsoby(); }));
}
function liczbaOsob(n) {
  const k = n % 10, d = n % 100;
  return `${n} ${n === 1 ? "osoba" : k >= 2 && k <= 4 && !(d >= 12 && d <= 14) ? "osoby" : "osób"}`;
}
async function startTwarzy() {
  try { await post("/api/g/twarze/start", {}); } catch (e) { toastG(e.message); return; }
  toastG("👤 Szukam twarzy w tle — możesz dalej oglądać zdjęcia.");
  rysujOsoby();
}
async function rysujOsoby() {
  const s = $("siatka");
  if (!osoby.dane) s.innerHTML = '<div class="pusto">Wczytuję…</div>';
  let d; try { d = await api("/api/g/osoby", osoby.wszystkie ? {wszystkie: 1} : {}); } catch (e) { s.innerHTML = `<div class="pusto">${e.message}</div>`; return; }
  if (g.widok !== "osoby") return;
  osoby.dane = d; osoby.uzywane = d.przejrzane > 0;
  clearTimeout(osoby.zegar);
  if (d.stan && d.stan.trwa) osoby.zegar = setTimeout(() => { if (g.widok === "osoby") rysujOsoby(); }, 2500);
  rysujFiltr();
  s.replaceChildren();
  if (!d.osoby.length) {
    s.innerHTML = `<div class="pusto"><img class="ik3d-pusto" alt="" src="/ui/ikony3d/przegladarka.webp"><br>${
      d.niedostepne ? d.niedostepne
      : d.stan && d.stan.trwa ? "Szukam twarzy… pierwsze osoby pojawią się tu za chwilę."
      : d.przejrzane ? "Nie znalazłem jeszcze osób, które są na co najmniej dwóch zdjęciach."
      : W_PROGRAMIE ? "Katalogator znajdzie twarze na Twoich zdjęciach i zgrupuje je w osoby — wszystko na tym komputerze, bez wysyłania do internetu.<br>Potem nadaj imiona i szukaj zdjęć po imieniu."
      : "Twarze wyszukuje program na komputerze (👤 Osoby)."}</div>`;
    if (W_PROGRAMIE && !d.niedostepne && !(d.stan && d.stan.trwa) && d.przejrzane < d.zdjec)
      s.firstChild.append(document.createElement("br"), document.createElement("br"), przycisk("👤 Znajdź twarze na zdjęciach", startTwarzy, "", "akt"));
    return;
  }
  for (const o of d.osoby) {
    const k = document.createElement("div"); k.className = "k osoba" + (osoby.wyb.has(o.id) ? " wyb" : "");
    const ob = document.createElement("div"); ob.className = "ob";
    if (o.twarz) { const im = new Image(); im.src = url("/api/g/twarz", {id: o.twarz}); im.alt = ""; im.loading = "lazy"; ob.append(im); } else ob.textContent = "👤";
    const zn = document.createElement("span"); zn.className = "zn-wyb"; zn.textContent = "✓";
    const op = document.createElement("div"); op.className = "op"; op.innerHTML = "<div></div><div class='m'></div>";
    op.children[0].textContent = o.nazwa || "Bez imienia"; if (!o.nazwa) op.children[0].className = "bez";
    op.children[1].textContent = liczbaZdjec(o.n) + (o.ukryta ? " · ukryta" : "");
    k.title = (o.nazwa || "Bez imienia") + " — kliknij: zdjęcia" + (W_PROGRAMIE ? " · Ctrl+klik: zaznacz (do łączenia)" : "");
    k.append(zn, ob, op);
    k.onclick = e => {
      if (W_PROGRAMIE && (e.ctrlKey || e.metaKey || osoby.wyb.size)) {
        osoby.wyb.has(o.id) ? osoby.wyb.delete(o.id) : osoby.wyb.add(o.id);
        k.classList.toggle("wyb", osoby.wyb.has(o.id)); rysujFiltr(); return;
      }
      if (o.ukryta && W_PROGRAMIE) post("/api/g/osoba/ukryj", {id: o.id, tak: false}).catch(() => {});
      pokazWyniki({typ: "osoba", osoba: o.id, nazwa: o.nazwa});
    };
    s.append(k);
  }
}

// 🔗 udostępnianie albumu: link przez serwer telefonu (sieć domowa / Tailscale), bez PIN-u, tylko ten album
async function udostepnij(z, wlacz = true) {
  let w;
  try { w = await post("/api/g/album/udostepnij", {album: z.album, wlacz}); } catch (e) { alert(e.message); return; }
  z.udostepniony = !!w.token; rysujFiltr();
  if (!w.token) { $("udo").hidden = true; toastG("🔗 Link do albumu wyłączony — przestał działać."); return; }
  const t = $("udo-tresc"); t.replaceChildren();
  const adr = (w.adresy || [])[0];
  if (!adr) {
    t.innerHTML = `<p>Link jest gotowy, ale zadziała dopiero po włączeniu <b>📱 Na telefon</b> (menu ⋯) — album
      jest udostępniany przez ten sam serwer co telefon.</p>`;
    t.append(przycisk("📱 Włącz teraz", async () => { $("udo").hidden = true; await telefon(true); udostepnij(z); }, "", "akt"));
  } else {
    const qr = qrcode(0, "M"); qr.addData(adr); qr.make();
    t.innerHTML = `<div class="qr"><div>${qr.createSvgTag({cellSize: 4, margin: 2})}</div><div>
      <div class="info">Link do albumu „<span id="udo-nazwa"></span>”</div><code id="udo-adr"></code>
      <div style="margin-top:8px"><button id="udo-kopiuj" class="akt">📋 Kopiuj link</button></div></div></div>
      <ul><li>Bez PIN-u: kto ma link, widzi <b>tylko ten album</b> (oglądanie, pobieranie, ZIP) — nic więcej.</li>
      <li>Działa w Twojej sieci domowej oraz dla osób w Twoim <b>Tailscale</b> (adresy 100.…: <span id="udo-inne"></span>) —
      rodzinie spoza domu udostępnij komputer w Tailscale (Share…) albo wyślij ZIP.</li>
      <li>Dopóki komputer jest włączony i działa „📱 Na telefon”.</li></ul>`;
    $("udo-nazwa").textContent = z.nazwa || ""; $("udo-adr").textContent = adr;
    $("udo-inne").textContent = w.adresy.slice(1).join(", ") || "—";
    $("udo-kopiuj").onclick = async () => {
      try { await navigator.clipboard.writeText(adr); $("udo-kopiuj").textContent = "✓ Skopiowano"; }
      catch (e) { prompt("Skopiuj link:", adr); }
    };
  }
  $("udo-wylacz").onclick = () => { if (confirm("Wyłączyć link? Kto go ma, nie zobaczy już albumu.")) udostepnij(z, false); };
  $("udo").hidden = false;
}
$("udo-zamknij").onclick = () => { $("udo").hidden = true; };

// 📤 wysyłanie do biblioteki (telefon: zdjęcia prosto z galerii) — plik po pliku, z postępem
$("wyslij-btn").onclick = () => $("wyslij-pliki").click();
$("wyslij-pliki").onchange = async () => {
  const pliki = [...$("wyslij-pliki").files]; $("wyslij-pliki").value = "";
  if (!pliki.length) return;
  const razem = pliki.reduce((a, f) => a + f.size, 0);
  let wyslane = 0, juz = 0, bledy = [], bajty = 0, folder = "";
  for (const [i, f] of pliki.entries()) {
    try {
      const w = await new Promise((ok, nie) => {
        const x = new XMLHttpRequest();
        x.open("POST", url("/api/g/wyslij", {nazwa: f.name, mtime: f.lastModified || 0}));
        x.setRequestHeader("X-Token", TOKEN); x.setRequestHeader("Content-Type", "application/octet-stream");
        x.upload.onprogress = e => {
          const pr = Math.round(100 * (bajty + e.loaded) / Math.max(razem, 1));
          toastG(`📤 Wysyłam ${i + 1} z ${pliki.length} · ${pr}%`);
        };
        x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (e) { /* nie JSON */ }
                           x.status < 300 && !j.blad ? ok(j) : nie(new Error(j.blad || x.statusText)); };
        x.onerror = () => nie(new Error("brak połączenia"));
        x.send(f);
      });
      if (w.juz_jest) juz++; else { wyslane++; folder = w.folder; }
    } catch (e) { bledy.push(`${f.name}: ${e.message}`); }
    bajty += f.size;
  }
  toastG(`📤 Wysłano: ${liczbaZdjec(wyslane)}` + (folder ? ` → biblioteka/${folder}` : "") +
         (juz ? ` · już były w bibliotece: ${juz}` : "") + (bledy.length ? ` · nie udało się: ${bledy.length} (${bledy[0]})` : ""));
  if (wyslane) { wczytajLata(true).catch(() => {}); if (g.zrodlo.typ === "os") wczytajPliki().catch(() => {}); }
};

// ---------- 📍 lokalizacja: dodaj / zmień / usuń (w pliku: JPEG — EXIF, inne — .xmp obok) ----------
// poprzednie: {id: [lat, lon] | [null, null]} — do „Cofnij”
// postep(zrobione) — przy wielu plikach zapis idzie porcjami (pasek „w tle”)
async function ustawLokalizacje(ids, lat, lon, poprzednie, cicho = false, postep = null) {
  const w = {zmienione: 0, bledy: [], poprzednie: {}};
  const PORCJA = postep ? 20 : ids.length || 1;
  for (let i = 0; i < ids.length; i += PORCJA) {
    const czesc = ids.slice(i, i + PORCJA);
    try {
      const r = await post("/api/g/lokalizacja", {ids: czesc, lat, lon});
      w.zmienione += r.zmienione || 0; w.bledy.push(...(r.bledy || [])); Object.assign(w.poprzednie, r.poprzednie || {});
      for (const tab of [g.pliki, g.lista]) for (const p of tab || []) if (r.poprzednie && r.poprzednie[p.id]) { p.lat = lat; p.lon = lon; }
    } catch (e) { w.bledy.push(e.message); }
    if (postep) postep(Math.min(ids.length, i + PORCJA));
  }
  if (!w.zmienione) { toastG("Nie zapisano lokalizacji: " + (w.bledy[0] || "")); return false; }
  if (g.widok !== "mapa") g.punkty = null;  // mapa wczyta się na nowo
  wczytajLata(true).catch(() => {});
  if (!$("pelny").hidden) { narzedziaPelnego(biezacy()); miniMapa(biezacy()); }
  if (cicho) return true;
  const n = w.zmienione, co = n === 1 ? "zdjęcia" : `${n} zdjęć`;
  toastG((lat === null ? `📍 Usunięto lokalizację ${co}` : `📍 Zapisano lokalizację ${co}`) +
         (w.bledy.length ? ` · nie udało się: ${w.bledy.length} (${w.bledy[0]})` : ""), async () => {
    // cofnięcie: każdemu przywracamy jego poprzednie miejsce (grupami)
    const grupy = new Map();
    for (const [id, [la, lo]] of Object.entries(poprzednie || w.poprzednie)) {
      if (!(id in w.poprzednie)) continue;
      const k = la === null ? "brak" : `${la},${lo}`;
      if (!grupy.has(k)) grupy.set(k, {la, lo, ids: []});
      grupy.get(k).ids.push(+id);
    }
    for (const x of grupy.values()) await ustawLokalizacje(x.ids, x.la, x.lo, null, true);
    g.punkty = null; if (g.widok === "mapa") pokazMape().catch(() => {});
    toastG("↶ Przywrócono poprzednią lokalizację");
  });
  return true;
}

// okno wyboru miejsca: kliknij na mapie / przeciągnij pinezkę / wyszukaj miejscowość
const lok = {mapa: null, znacznik: null, p: null};
function oknoLokalizacji(p, zbior = null) {
  lok.p = p; lok.zbior = zbior; stopPokaz();
  $("lok").hidden = false;
  $("lok-tyt").textContent = zbior ? `📍 ${liczbaZdjec(zbior.length)}` : `📍 ${p.nazwa || "Lokalizacja"}`;
  $("lok-szukaj").value = ""; $("lok-wyniki").replaceChildren();
  // „także inne zdjęcia z tego dnia bez lokalizacji” — najczęstszy przypadek: aparat bez GPS na wycieczce
  const dzien = (p.data || "").slice(0, 10);
  const inne = dzien && !zbior ? (g.lista || []).filter(x => x.id !== p.id && x.lat == null && (x.data || "").slice(0, 10) === dzien) : [];
  $("lok-inne").hidden = !inne.length; $("lok-inne-cb").checked = false;
  lok.inne = inne; lok.wybrane = new Set(inne.map(x => x.id));
  rysujInneLok();
  $("lok-usun").hidden = zbior ? !zbior.some(x => x.lat != null) : p.lat == null;
  if (!lok.mapa) {
    lok.mapa = L.map("lok-mapa", {doubleClickZoom: false}).setView([52, 19], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>'}).addTo(lok.mapa);
    lok.mapa.on("click", e => ustawZnacznik(e.latlng.lat, e.latlng.lng));
  }
  if (lok.znacznik) { lok.mapa.removeLayer(lok.znacznik); lok.znacznik = null; }
  setTimeout(() => {
    lok.mapa.invalidateSize();
    if (p.lat != null) { ustawZnacznik(p.lat, p.lon); lok.mapa.setView([p.lat, p.lon], 14); }
    else lok.mapa.setView(lok.ostatnie || [52, 19], lok.ostatnie ? 12 : 6);
  }, 30);
  $("lok-zapisz").disabled = true;
  $("lok-pomoc").textContent = p.lat == null ? "Kliknij na mapie, gdzie zrobiono zdjęcie — albo wyszukaj miejscowość."
                                              : "Przeciągnij pinezkę albo kliknij w nowe miejsce.";
}
function ustawZnacznik(la, lo) {
  if (!lok.znacznik) {
    lok.znacznik = L.marker([la, lo], {draggable: true}).addTo(lok.mapa);
    lok.znacznik.on("dragend", () => { $("lok-zapisz").disabled = false; });
  } else lok.znacznik.setLatLng([la, lo]);
  $("lok-zapisz").disabled = false;
}
// miniatury pozostałych zdjęć z tego dnia: widać, czego dotyczy zmiana; klik — wyłącz / włącz zdjęcie
function rysujInneLok() {
  const n = lok.inne.filter(x => lok.wybrane.has(x.id)).length, wsz = lok.inne.length;
  $("lok-inne-t").textContent = `także ${liczbaZdjec(n)} z tego dnia bez lokalizacji` + (n < wsz ? ` (z ${wsz})` : "");
  const m = $("lok-inne-min"); m.hidden = !$("lok-inne-cb").checked || !wsz;
  if (m.hidden) return;
  m.replaceChildren();
  for (const x of lok.inne) {
    const b = document.createElement("button"); b.type = "button";
    b.className = "lok-min" + (lok.wybrane.has(x.id) ? " wyb" : "");
    b.title = (x.nazwa || "") + (lok.wybrane.has(x.id) ? " — kliknij, żeby pominąć" : " — pominięte; kliknij, żeby dołączyć");
    if (x.rodzaj === "film") b.textContent = "🎬";
    else { const im = new Image(); im.loading = "lazy"; im.alt = ""; im.src = miniatura(x.id, false); b.append(im); }
    b.onclick = () => { lok.wybrane.has(x.id) ? lok.wybrane.delete(x.id) : lok.wybrane.add(x.id); rysujInneLok(); };
    m.append(b);
  }
}
$("lok-inne-cb").onchange = rysujInneLok;
function zamknijLok() { $("lok").hidden = true; }
$("lok-anuluj").onclick = zamknijLok;
$("lok").onclick = e => { if (e.target.id === "lok") zamknijLok(); };
$("lok-zapisz").onclick = async () => {
  if (!lok.znacznik) return;
  const ll = lok.znacznik.getLatLng(), p = lok.p;
  const cele = lok.zbior || [p, ...($("lok-inne-cb").checked ? lok.inne.filter(x => lok.wybrane.has(x.id)) : [])];
  const pop = Object.fromEntries(cele.map(x => [x.id, [x.lat ?? null, x.lon ?? null]]));
  lok.ostatnie = [ll.lat, ll.lng]; zamknijLok();  // okno znika od razu — zapis idzie w tle, można dalej przeglądać
  zadanieTla("📍 Zapisuję lokalizację", cele.length, postep => ustawLokalizacje(cele.map(x => x.id), ll.lat, ll.lng, pop, false, postep));
};
$("lok-usun").onclick = async () => {
  const cele = (lok.zbior || [lok.p]).filter(x => x.lat != null);
  zamknijLok();
  if (cele.length) zadanieTla("📍 Usuwam lokalizację", cele.length,
    postep => ustawLokalizacje(cele.map(x => x.id), null, null, Object.fromEntries(cele.map(x => [x.id, [x.lat, x.lon]])), false, postep));
};

// ---------- ⏳ operacje w tle: kolejka + panel z paskami z boku ekranu ----------
const tlo = {kolejka: Promise.resolve(), ile: 0};
function zadanieTla(nazwa, razem, praca) {
  const wiersz = document.createElement("div"); wiersz.className = "tlo-z";
  const tyt = document.createElement("div"), pasek = document.createElement("div"), wyp = document.createElement("i");
  pasek.className = "tlo-p"; pasek.append(wyp);
  const pokaz = (n, stan = "") => {
    tyt.textContent = `${nazwa} · ${n} / ${razem}${stan}`;
    wyp.style.width = (razem ? Math.round(100 * n / razem) : 100) + "%";
  };
  wiersz.append(tyt, pasek); $("tlo").append(wiersz); $("tlo").hidden = false; tlo.ile++;
  pokaz(0, " · czeka");
  const koniec = () => {
    wiersz.classList.add("gotowe"); pokaz(razem, " ✓");
    setTimeout(() => { wiersz.remove(); if (!--tlo.ile) $("tlo").hidden = true; }, 2500);
  };
  tlo.kolejka = tlo.kolejka.then(() => { pokaz(0); return praca(n => pokaz(n)); }).catch(e => toastG(nazwa + ": " + e.message)).finally(koniec);
  return tlo.kolejka;
}
// zamknięcie okna w trakcie — zapytaj (przerwany zapis = część plików bez zmiany)
window.addEventListener("beforeunload", e => { if (tlo.ile) { e.preventDefault(); e.returnValue = ""; } });
let lokZegar = null;
$("lok-szukaj").oninput = () => {
  clearTimeout(lokZegar);
  const q = $("lok-szukaj").value.trim();
  if (q.length < 2) { $("lok-wyniki").replaceChildren(); return; }
  lokZegar = setTimeout(async () => {
    let wyniki = [];
    try { wyniki = (await api("/api/g/miejsce", {q})).miejsca; } catch (e) { /* bez wyników lokalnych */ }
    if (!wyniki.length) {  // poza Polską / ulice — OpenStreetMap (internet, jak podkład mapy)
      try {
        const r = await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=6&accept-language=pl&q=" + encodeURIComponent(q));
        wyniki = (await r.json()).map(x => ({nazwa: x.display_name, lat: +x.lat, lon: +x.lon}));
      } catch (e) { /* brak internetu */ }
    }
    const l = $("lok-wyniki"); l.replaceChildren();
    if (!wyniki.length) { l.append(Object.assign(document.createElement("div"), {className: "info", textContent: "Nic nie znaleziono."})); return; }
    for (const m of wyniki) l.append(przycisk("📍 " + m.nazwa, () => {
      ustawZnacznik(m.lat, m.lon); lok.mapa.setView([m.lat, m.lon], 13); l.replaceChildren();
    }));
  }, 300);
};
$("p-miejsce").onclick = e => { e.stopPropagation(); const p = biezacy(); if (p) oknoLokalizacji(p); };

// ---------- 🗑 usuwanie: do kosza programu (Odłożone/Usunięte), z cofaniem ----------
// w oknie programu i na telefonie z pilotem (serwer 24/7 jest tylko do oglądania)
const MOZE_USUWAC = W_PROGRAMIE || !!P.get("pilot");
$("wyslij-btn").hidden = $("menu-wyslij").hidden = !MOZE_USUWAC;
$("menu-wyslij").onclick = () => $("wyslij-pliki").click();
function toastG(tekst, cofnij) {
  const t = $("toast-g"); t.replaceChildren(tekst);
  if (cofnij) t.append(przycisk("Cofnij", async () => { t.hidden = true; await cofnij(); }));
  t.hidden = false; clearTimeout(toastG.z); toastG.z = setTimeout(() => { t.hidden = true; }, 8000);
}
async function usunPliki(lista) {
  let w;
  try { w = await post("/api/g/usun", {ids: lista.map(p => p.id)}); } catch (e) { toastG("Nie usunięto: " + e.message); return; }
  const ids = new Set(lista.map(p => p.id));
  const bylPelny = !$("pelny").hidden, poz = g.poz;
  for (const tab of [g.pliki, g.lista]) {
    for (let i = tab.length - 1; i >= 0; i--) if (ids.has(tab[i].id)) tab.splice(i, 1);
  }
  g.razem = Math.max(0, g.razem - w.usuniete);
  rysujSiatke(); rysujFiltr(); wczytajLata(true).catch(() => {});
  if (bylPelny) { if (!g.lista.length) zamknijPelny(); else pokazPelny(g.lista, Math.min(poz, g.lista.length - 1)); }
  const n = w.usuniete;
  toastG((n === 1 ? `🗑 Usunięto „${lista[0].nazwa}”` : `🗑 Usunięto ${liczbaZdjec(n)}`) +
         (w.pominiete && w.pominiete.length ? ` · pominięto ${w.pominiete.length}: ${w.pominiete[0]}` : ""),
         async () => {
           try {
             const c = await post("/api/g/usun/cofnij", {partia: w.partia});
             toastG(`Przywrócono ${liczbaZdjec(c.przywrocone)}` + (c.bledy.length ? ` · ${c.bledy[0]}` : ""));
           } catch (e) { toastG(e.message); }
           wczytajLata(true).catch(() => {}); wczytajPliki().catch(() => {});
         });
}
$("p-usun").onclick = e => { e.stopPropagation(); const p = biezacy(); if (p) usunPliki([p]); };

// ---------- podgląd: ulubione, album, pokaz slajdów, otwieranie w programie ----------
function narzedziaPelnego(p) {
  const ul = $("p-ulub");
  ul.hidden = !W_PROGRAMIE; ul.classList.toggle("akt", !!p.ulubione); ul.textContent = p.ulubione ? "★ Ulubione" : "☆ Ulubione";
  $("p-album").hidden = !W_PROGRAMIE;
  $("p-z-albumu").hidden = !(W_PROGRAMIE && g.zrodlo.typ === "kolekcja" && g.zrodlo.kol === "album" && g.lista === g.pliki);
  $("p-otworz").hidden = !W_PROGRAMIE;
  $("p-usun").hidden = !MOZE_USUWAC;
  $("p-miejsce").hidden = !MOZE_USUWAC;
  if (p) $("p-miejsce").textContent = p.lat != null ? "📍 Zmień miejsce" : "📍 Dodaj miejsce";
  $("p-data").hidden = !MOZE_USUWAC;
  $("p-edytuj").hidden = !MOZE_USUWAC || !p || p.rodzaj !== "zdjecie";
  const dk = $("p-dok"); dk.hidden = !W_PROGRAMIE || (p && p.rodzaj === "film");
  dk.classList.toggle("akt", !!(p && p.dokument));
  dk.textContent = p && p.dokument ? "📄 Dokument ✓" : "📄 To dokument";
  dk.title = p && p.dokument ? "Oznaczone jako dokument — kliknij, żeby wrócić do zwykłych zdjęć (D)"
                             : "Oznacz jako dokument — trafi do filtra 📄 Dokumenty (D)";
  $("p-pokaz").textContent = g.pokaz ? "⏸ Pauza" : "▶ Pokaz";
}
const biezacy = () => g.lista[g.poz];
// ℹ właściwości: gdzie leży plik (folder, pełna ścieżka), rozmiar, wymiary, aparat, skąd data, miejsce, osoby
const ZRODLA_DATY = {exif: "z aparatu (EXIF)", film: "z nagrania", nazwa: "z nazwy pliku", folder: "z nazwy folderu",
                     plik: "data zmiany pliku (brak daty z aparatu — sprawdź)"};
function rozmiarTxt(b) {
  if (b == null) return "";
  const j = ["B", "KB", "MB", "GB"]; let i = 0, v = b;
  while (v >= 1024 && i < j.length - 1) { v /= 1024; i++; }
  return (i ? v.toLocaleString("pl-PL", {maximumFractionDigits: 1}) : v) + " " + j[i];
}
function czasTxt(s) {
  s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`;
}
async function wlasciwosci(p) {
  const t = $("wl-tresc"); t.textContent = "Wczytuję…";
  let d; try { d = await api("/api/g/wlasciwosci", {id: p.id}); } catch (e) { t.textContent = e.message; return; }
  if (biezacy() !== p) return;
  t.replaceChildren();
  const dl = document.createElement("dl");
  const wiersz = (k, v) => { if (v === null || v === undefined || v === "") return; const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); if (v instanceof Node) dd.append(v); else dd.textContent = v; dl.append(dt, dd); };
  const kod = x => { const c = document.createElement("code"); c.textContent = x; return c; };
  wiersz("Nazwa", d.nazwa);
  wiersz("Folder", kod(d.folder));
  wiersz("Rodzaj", (d.rodzaj === "film" ? "🎬 film" : "📷 zdjęcie") + (d.format ? " · " + d.format : "") + (d.kodek ? " · " + d.kodek : ""));
  wiersz("Rozmiar", rozmiarTxt(d.rozmiar));
  if (d.szer) wiersz("Wymiary", `${d.szer} × ${d.wys} px` + (d.rodzaj === "zdjecie" ? ` (${(d.szer * d.wys / 1e6).toLocaleString("pl-PL", {maximumFractionDigits: 1})} Mpx)` : ""));
  if (d.czas) wiersz("Długość", czasTxt(d.czas) + (d.dzwiek ? " · dźwięk " + d.dzwiek : ""));
  wiersz("Zrobione", d.data ? dataTxt(d.data) + (d.data.length > 10 ? ", " + d.data.slice(11, 16) : "") : "brak daty");
  wiersz("Skąd data", ZRODLA_DATY[d.zrodlo_daty] || d.zrodlo_daty);
  wiersz("Aparat", d.aparat);
  if (d.lat != null) wiersz("Miejsce", (d.miejsce ? d.miejsce + " · " : "") + `${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}`);
  if (d.osoby && d.osoby.length) wiersz("Osoby", "👤 " + d.osoby.join(", "));
  wiersz("Zmieniony", d.zmieniony ? new Date(d.zmieniony * 1000).toLocaleString("pl-PL") : "");
  t.append(dl);
  if (!d.istnieje) { const z = document.createElement("div"); z.className = "zle"; z.textContent = "⚠ Pliku nie ma w tym miejscu — dysk odłączony albo plik przeniesiono."; t.append(z); }
  const ak = document.createElement("div"); ak.className = "wl-akcje";
  if (W_PROGRAMIE) ak.append(przycisk("📂 Pokaż w folderze", async () => {
    try { await post("/api/g/pokaz-w-folderze", {id: p.id}); } catch (e) { toastG(e.message); }
  }, "Otwiera Eksplorator Windows z zaznaczonym plikiem"));
  ak.append(przycisk("📋 Kopiuj ścieżkę", async () => {
    try { await navigator.clipboard.writeText(d.sciezka); toastG("📋 Skopiowano: " + d.sciezka); }
    catch (e) { prompt("Ścieżka pliku:", d.sciezka); }
  }));
  if (p.rodzaj === "zdjecie" && d.lat == null && MOZE_USUWAC) ak.append(przycisk("📍 Dodaj miejsce", () => $("p-miejsce").click()));
  t.append(ak);
  const sc = document.createElement("div"); sc.className = "info"; sc.style.opacity = ".75"; sc.append("Pełna ścieżka: ", kod(d.sciezka)); t.append(sc);
}
$("p-info").onclick = e => {
  e && e.stopPropagation && e.stopPropagation();
  const w = $("wl"); w.hidden = !w.hidden; $("p-info").classList.toggle("akt", !w.hidden);
  try { localStorage.setItem("kat_wl", w.hidden ? "0" : "1"); } catch (er) { /* bez pamięci */ }
  if (!w.hidden && biezacy()) wlasciwosci(biezacy());
};
$("wl-zamknij").onclick = e => { e.stopPropagation(); $("p-info").click(); };
$("wl").addEventListener("click", e => e.stopPropagation());
$("wl").addEventListener("wheel", e => e.stopPropagation(), {passive: true});
try { if (localStorage.getItem("kat_wl") === "1") { $("wl").hidden = false; $("p-info").classList.add("akt"); } } catch (e) { /* bez pamięci */ }
// 📄 zdjęcie ↔ dokument
$("p-dok").onclick = async e => {
  e && e.stopPropagation && e.stopPropagation();
  const p = biezacy(); if (!p) return;
  try {
    const w = await post("/api/g/dokument", {ids: [p.id], tak: !p.dokument});
    p.dokument = w.dokument; narzedziaPelnego(p);
    toastG(p.dokument ? `📄 „${p.nazwa}” — dokument` : `📷 „${p.nazwa}” — zwykłe zdjęcie`);
  } catch (err) { toastG(err.message); }
};
// 📅 zmiana daty zrobienia (w pliku: EXIF w JPEG, .xmp obok w innych formatach)
function oknoDaty(p, zbior = null) {
  stopPokaz();
  const pad = n => String(n).padStart(2, "0");
  const iso = t => `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}T${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
  let inne;
  if (zbior) {  // zaznaczone: najwcześniejsza data jako punkt odniesienia
    const z = zbior.filter(x => x.data).sort((a, b) => a.data < b.data ? -1 : 1);
    p = z[0] || zbior[0]; inne = zbior.filter(x => x !== p);
    $("dt-tyt").textContent = `📅 ${liczbaZdjec(zbior.length)}`;
    $("dt-inne-t").textContent = "zachowaj odstępy między nimi (przesuń wszystkie o tyle samo; bez zaznaczenia — każde dostanie tę samą datę)";
    $("dt-inne").hidden = false; $("dt-inne-cb").checked = z.length > 1;
  } else {
    $("dt-tyt").textContent = `📅 ${p.nazwa || "Data"}`;
    const dzien = (p.data || "").slice(0, 10);
    inne = dzien ? (g.lista || []).filter(x => x.id !== p.id && (x.data || "").slice(0, 10) === dzien) : [];
    $("dt-inne").hidden = !inne.length; $("dt-inne-cb").checked = false;
    $("dt-inne-t").textContent = `przesuń też ${liczbaZdjec(inne.length)} z tego samego dnia o tyle samo`;
  }
  $("dt-wart").value = (p.data || "").slice(0, 16) || "";
  $("dt").hidden = false; $("dt-wart").focus();
  $("dt-zapisz").onclick = async () => {
    const nowa = $("dt-wart").value;
    if (!nowa) return;
    const cele = [{p, data: nowa}];
    const przesun = $("dt-inne-cb").checked && p.data;
    const roznica = przesun ? new Date(nowa) - new Date(p.data.slice(0, 19)) : 0;
    for (const x of inne) {
      if (przesun && x.data) cele.push({p: x, data: iso(new Date(new Date(x.data.slice(0, 19)).getTime() + roznica))});
      else if (zbior) cele.push({p: x, data: nowa});  // zaznaczone bez zachowania odstępów: ta sama data
    }
    $("dt").hidden = true;  // okno znika od razu — zapis idzie w tle, można dalej przeglądać
    zadanieTla("📅 Zmieniam datę", cele.length, async postep => {
      let zm = 0, bl = [];
      for (const c of cele) {
        try {
          const w = await post("/api/g/data", {ids: [c.p.id], data: c.data});
          if (w.zmienione) { c.p.data = w.data; zm++; } else bl = bl.concat(w.bledy || []);
        } catch (err) { bl.push(err.message); }
        postep(zm + bl.length);
      }
      toastG(`📅 Zmieniono datę: ${liczbaZdjec(zm)}` + (bl.length ? ` · nie udało się: ${bl.length} (${bl[0]})` : ""));
      if (!$("pelny").hidden && biezacy() === p) $("pelny-opis").textContent = `${p.nazwa} · ${dataTxt(p.data)}` + (p.miejsce ? " · " + p.miejsce : "");
      if (zbior) rysujSiatke();
      g.punkty = null; wczytajLata(true).catch(() => {});
    });
  };
}
// 📅 zmiana daty zrobienia (w pliku: EXIF w JPEG, .xmp obok w innych formatach)
$("p-data").onclick = e => { e.stopPropagation(); const p = biezacy(); if (p) oknoDaty(p); };
$("dt-anuluj").onclick = () => { $("dt").hidden = true; };
$("dt").onclick = e => { if (e.target.id === "dt") $("dt").hidden = true; };
$("p-ulub").onclick = async e => {
  e && e.stopPropagation && e.stopPropagation();
  const p = biezacy(); if (!p) return;
  try { const w = await post("/api/g/ulubione", {id: p.id}); p.ulubione = w.ulubione; narzedziaPelnego(p); } catch (err) { alert(err.message); }
};
$("p-z-albumu").onclick = async e => {
  e.stopPropagation(); const p = biezacy(); if (!p) return;
  await post("/api/g/album/usun-pliki", {album: g.zrodlo.album, ids: [p.id]});
  const i = g.pliki.indexOf(p); g.pliki.splice(i, 1); g.razem--; rysujSiatke(); rysujFiltr();
  if (!g.pliki.length) zamknijPelny(); else pokazPelny(g.pliki, Math.min(i, g.pliki.length - 1));
};
$("p-otworz").onclick = e => { e.stopPropagation(); const p = biezacy(); if (p) otworzWProgramie(p); };
async function otworzWProgramie(p) { stopPokaz(); try { await post("/api/g/otworz", {id: p.id}); } catch (e) { alert(e.message); } }
function zamknijMenuAlb() { document.querySelectorAll(".menu-alb").forEach(m => m.remove()); }
$("p-album").onclick = e => {
  e.stopPropagation();
  if (document.querySelector(".menu-alb")) { zamknijMenuAlb(); return; }
  const p = biezacy(); if (!p) return;
  menuAlbumow($("pelny"), [p.id], nazwa => {
    const b = $("p-album"); b.textContent = `✓ W „${nazwa}”`; setTimeout(() => { b.textContent = "＋ Album"; }, 1800);
  });
};
function startPokaz() {
  if (g.pokaz) return;
  g.pokaz = setTimeout(krokPokazu, 4000);
  try { if (!document.fullscreenElement) $("pelny").requestFullscreen().catch(() => {}); } catch (e) { /* bez pełnego ekranu */ }
  narzedziaPelnego(biezacy() || {});
}
function stopPokaz() {
  if (!g.pokaz) return;
  clearTimeout(g.pokaz); g.pokaz = null;
  try { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); } catch (e) { /* nic */ }
  if (!$("pelny").hidden) narzedziaPelnego(biezacy() || {});
}
function przelaczPokaz() { if (g.pokaz) stopPokaz(); else startPokaz(); }
async function krokPokazu() {
  if (!g.pokaz) return;
  const v = $("pelny-tresc").querySelector("video");
  if (v && !v.ended && !v.error && !v.paused) { g.pokaz = setTimeout(krokPokazu, 1000); return; }  // film gra do końca
  if (g.poz >= g.lista.length - 1 && g.lista === g.pliki && g.pliki.length < g.razem) await wczytajPliki(true);
  if (!g.pokaz) return;
  if (g.poz < g.lista.length - 1) { krok(1); g.pokaz = setTimeout(krokPokazu, 4000); } else stopPokaz();
}
$("p-pokaz").onclick = e => { e.stopPropagation(); przelaczPokaz(); };

// ---------- filmy: klatka jako miniatura (wyciągana w przeglądarce, zapamiętywana przez program) ----------
const filmy = {kolejka: [], trwa: 0};
const obserwator = "IntersectionObserver" in window ? new IntersectionObserver(wpisy => {
  for (const w of wpisy) if (w.isIntersecting) { obserwator.unobserve(w.target); filmy.kolejka.push(w.target._film); nastepnyFilm(); }
}, {rootMargin: "300px"}) : null;
function miniaturaFilmu(p, ob) {
  const z = document.createElement("span"); z.className = "znak-f"; z.textContent = "▶ film"; ob.append("🎬", z);
  ob._film = {p, ob, z};
  if (obserwator) obserwator.observe(ob);  // zapamiętana klatka albo wyciągnięcie jej z filmu — gdy kafelek jest widoczny
  else filmy.kolejka.push(ob._film);
}
function nastepnyFilm() {
  while (filmy.trwa < 2 && filmy.kolejka.length) {
    const {p, ob, z} = filmy.kolejka.shift(); filmy.trwa++;
    if (!p.bezMin) {  // najpierw klatka zapamiętana wcześniej przez program
      const im = new Image(); im.alt = "";
      im.onload = () => { ob.prepend(im); filmy.trwa--; nastepnyFilm(); };
      im.onerror = () => { p.bezMin = true; filmy.trwa--; filmy.kolejka.unshift({p, ob, z}); nastepnyFilm(); };
      im.src = miniatura(p.id, false);
      continue;
    }
    const v = document.createElement("video"); v.muted = true; v.preload = "metadata"; v.playsInline = true;
    let koniec = false;
    const zakoncz = () => { if (koniec) return; koniec = true; clearTimeout(zeg); v.removeAttribute("src"); v.load(); filmy.trwa--; nastepnyFilm(); };
    const zeg = setTimeout(zakoncz, 20000);
    v.onloadedmetadata = () => {
      if (isFinite(v.duration)) z.textContent = "▶ " + Math.floor(v.duration / 60) + ":" + String(Math.floor(v.duration % 60)).padStart(2, "0");
      v.currentTime = Math.min(1, (v.duration || 2) * 0.1);
    };
    v.onseeked = () => {
      try {
        const c = document.createElement("canvas"), sk = Math.min(1, 360 / (v.videoWidth || 360));
        c.width = Math.round((v.videoWidth || 320) * sk); c.height = Math.round((v.videoHeight || 240) * sk);
        c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
        const d = c.toDataURL("image/jpeg", 0.8);
        const im = new Image(); im.alt = ""; im.src = d; ob.prepend(im);
        if (W_PROGRAMIE) post("/api/g/miniatura-filmu", {id: p.id, jpg: d}).catch(() => {});
      } catch (e) { /* bez klatki */ }
      zakoncz();
    };
    v.onerror = () => { z.textContent = "▶ film"; z.title = "Stary format — odtwarzany po przerobieniu (ffmpeg)"; zakoncz(); };
    v.src = url("/api/g/film", {id: p.id});
  }
}

// ---------- mapa → oś czasu ----------
$("mapa-os").onclick = () => {
  if (!g.mapa) return;
  const b = g.mapa.getBounds();
  g.obszar = [b.getSouth(), b.getNorth(), b.getWest(), b.getEast()].map(x => Math.round(x * 1e5) / 1e5);
  g.rok = null; g.zrodlo = {typ: "os"}; $("szukaj").value = "";
  widok("os"); wczytajLata();
};

// ---------- przeglądarka dysków: wybrane dyski tylko skanowane i oglądane ----------
async function post(sciezka, dane) {
  const r = await fetch(url(sciezka), {method: "POST", headers: {"Content-Type": "application/json", "X-Token": TOKEN},
                                       body: JSON.stringify(dane || {})});
  const j = await r.json();
  if (!r.ok || j.blad) throw new Error(j.blad || r.statusText);
  return j;
}
const prz = {foldery: [], trwa: false, zegar: null, licz: 0};
function ustawZakres() {
  const p = g.zakres === "przegladarka";
  $("dyski-btn").hidden = !p; pokazDyski();
  tytul(...(p ? ["🔭", "Przeglądarka"] : ["📚", "Biblioteka"]));
  document.title = (p ? "Przeglądarka" : "Biblioteka") + " — Katalogator";
  if (p) odswiezPrz();
}
function rysujPrz(s) {
  prz.foldery = s.foldery; prz.trwa = s.trwa;
  const sel = $("prz-zestaw"); sel.replaceChildren();
  for (const z of s.zestawy || []) {
    const o = document.createElement("option"); o.value = z.id;
    o.textContent = `📂 ${z.nazwa}` + (z.n ? ` (${z.n})` : ""); sel.append(o);
  }
  sel.value = s.aktywny; prz.aktywny = s.aktywny;
  prz.nazwa = ((s.zestawy || []).find(z => z.id === s.aktywny) || {}).nazwa || "";
  $("prz-z-usun").disabled = (s.zestawy || []).length < 2;
  const f = $("prz-foldery"); f.replaceChildren();
  for (const sc of s.foldery) {
    const c = document.createElement("span"); c.className = "prz-f"; c.title = sc;
    const n = document.createElement("span"); n.textContent = "\u200E📁 " + sc;
    const x = document.createElement("button"); x.textContent = "✕"; x.title = "Usuń z przeglądarki (pliki zostają na dysku)";
    x.onclick = async () => { rysujPrz(await post("/api/przegladarka/foldery", {foldery: prz.foldery.filter(y => y !== sc)})); g.punkty = null; start(); };
    c.append(n, x); f.append(c);
  }
  $("prz-skanuj").disabled = s.trwa || !s.foldery.length;
  $("prz-auto").checked = s.auto !== false;
  $("prz-auto").parentElement.title = "Przy starcie programu i potem co " + (s.co_godzin || 6) + " h wczytuję nowe i zmienione pliki (tylko odczyt)" +
    (s.ostatni_skan ? " · ostatnio: " + new Date(s.ostatni_skan * 1000).toLocaleString("pl-PL") : "");
  $("prz-przerwij").hidden = !s.trwa;
  const pasek = $("prz-pasek"); pasek.hidden = !s.trwa;
  if (s.trwa) {
    const u = s.wszystkie ? Math.min(1, s.zrobione / s.wszystkie) : null;
    pasek.firstChild.style.width = u === null ? "15%" : (u * 100).toFixed(1) + "%";
    $("prz-stan").textContent = [s.komunikat, s.etap, s.wszystkie ? `${s.zrobione.toLocaleString("pl-PL")} / ${s.wszystkie.toLocaleString("pl-PL")}`
      : s.zrobione ? s.zrobione.toLocaleString("pl-PL") + " plików" : "", s.eta ? `zostało ok. ${Math.ceil(s.eta / 60)} min` : "",
      s.czeka || ""].filter(Boolean).join(" · ");
  } else {
    $("prz-stan").textContent = s.blad ? "Błąd: " + s.blad : (s.komunikat || (s.foldery.length ? "Kliknij „Skanuj”, żeby wczytać zdjęcia." : ""));
  }
  const zn = $("dyski-stan");
  zn.hidden = !(s.trwa || s.blad || !s.foldery.length);
  zn.textContent = s.trwa ? (s.wszystkie ? Math.round(100 * Math.min(1, s.zrobione / s.wszystkie)) + "%" : "⟳") : s.blad ? "!" : "+";
  // 📚 uporządkowana biblioteka — w Przeglądarce od razu (pusta Przeglądarka: sama; inaczej jednym klikiem)
  const bib = $("prz-bib"); bib.hidden = !s.biblioteka;
  if (s.biblioteka) {
    bib.textContent = "📚 Dodaj bibliotekę"; bib.title = "Dodaj uporządkowaną bibliotekę do Przeglądarki: " + s.biblioteka;
    bib.onclick = () => dodajBiblioteke(s.biblioteka);
    if (!s.foldery.length && !s.trwa && !prz.bibAuto) { prz.bibAuto = true; dodajBiblioteke(s.biblioteka, true); return; }
  }
  if (!s.foldery.length && !naglowek.dyski) { naglowek.dyski = true; pokazDyski(); }  // nic nie dodano — od razu pokaż
  if (s.katalogator_pracuje && !s.trwa)  // ten sam dysk sieciowy — dwa zadania naraz idą wolniej
    $("prz-stan").textContent += " · Katalogator teraz porządkuje pliki — odświeżę się sam, gdy skończy";
}
async function dodajBiblioteke(sc, samo = false) {
  try {
    rysujPrz(await post("/api/przegladarka/foldery", {foldery: [...prz.foldery, sc]}));
    await post("/api/przegladarka/skanuj", {});
    toastG(samo ? `📚 Przeglądarka pokazuje Twoją bibliotekę (${sc}) — wczytuję zdjęcia…` : `📚 Dodano bibliotekę — wczytuję zdjęcia…`);
    odswiezPrz();
  } catch (e) { toastG(e.message); }
}
async function odswiezPrz() {
  try {
    const s = await api("/api/przegladarka");
    const bylo = prz.trwa; rysujPrz(s);
    if (s.trwa) {
      if (++prz.licz % 4 === 0) wczytajLata(true).catch(() => {});  // zdjęcia pojawiają się w trakcie skanu
      clearTimeout(prz.zegar); prz.zegar = setTimeout(odswiezPrz, 1000);
    } else if (bylo) { g.punkty = null; start(); }
  } catch (e) { $("prz-stan").textContent = e.message; }
}
$("prz-skanuj").onclick = async () => {
  try { rysujPrz(await post("/api/przegladarka/skanuj")); odswiezPrz(); } catch (e) { $("prz-stan").textContent = e.message; }
};
$("prz-przerwij").onclick = () => post("/api/przegladarka/przerwij").catch(() => {});
async function zestaw(akcja, dane = {}) {  // przełączenie zestawu = nowa oś czasu, mapa i wyszukiwanie
  try { rysujPrz(await post("/api/przegladarka/zestaw", {akcja, ...dane})); }
  catch (e) { alert(e.message); return; }
  if (akcja === "nazwa") return;
  g.punkty = null; g.rok = null; g.obszar = null; g.zrodlo = {typ: "os"}; $("szukaj").value = "";
  if (g.widok === "kolekcje") g.widok = "os";
  start();
  if (akcja === "nowy") { $("wybierz").hidden = false; pokazWybor(null); }  // od razu dodaj pierwszy dysk
}
$("prz-zestaw").onchange = () => zestaw("wybierz", {id: +$("prz-zestaw").value});
$("prz-z-nowy").onclick = () => {
  const n = prompt("Nazwa nowego zestawu dysków (np. Rodzina, Praca, Stary laptop):"); if (n) zestaw("nowy", {nazwa: n});
};
$("prz-z-nazwa").onclick = () => {
  const n = prompt("Nowa nazwa zestawu:", prz.nazwa); if (n) zestaw("nazwa", {id: prz.aktywny, nazwa: n});
};
$("prz-z-usun").onclick = () => {
  if (confirm(`Usunąć zestaw „${prz.nazwa}”?\n\nDyski i zdjęcia zostają — znika tylko ta lista w Przeglądarce.`))
    zestaw("usun", {id: prz.aktywny});
};
$("prz-auto").onchange = () => post("/api/przegladarka/auto", {auto: $("prz-auto").checked}).then(rysujPrz).catch(() => {});
// wybór dysku / folderu
const wyb = {sciezka: null};
async function pokazWybor(sciezka) {
  wyb.sciezka = sciezka;
  const l = $("wyb-lista"); l.replaceChildren(); $("wyb-ok").disabled = !sciezka;
  $("wyb-sciezka").textContent = sciezka || "Dyski";
  $("wyb-gora").disabled = !sciezka;
  try {
    if (!sciezka) {
      const r = await api("/api/dyski");
      for (const d of r.dyski) {
        const b = document.createElement("button");
        b.textContent = `${d.siec ? "🌐" : "💽"} ${d.sciezka}${d.etykieta ? " — " + d.etykieta : ""}`;
        b.disabled = d.dostepny === false; b.onclick = () => pokazWybor(d.sciezka); l.append(b);
      }
    } else {
      const r = await api("/api/foldery", {sciezka});
      if (r.blad) l.textContent = r.blad;
      for (const f of r.foldery || []) {
        const b = document.createElement("button"); const p = f.sciezka || f;
        b.textContent = "📁 " + (f.nazwa || String(p).split(/[\\/]/).filter(Boolean).pop());
        b.onclick = () => pokazWybor(p); l.append(b);
      }
      if (!(r.foldery || []).length && !r.blad) l.innerHTML = '<div class="info" style="padding:10px">Brak podfolderów — możesz wybrać ten folder.</div>';
    }
  } catch (e) { l.textContent = e.message; }
}
$("prz-dodaj").onclick = () => { $("wybierz").hidden = false; pokazWybor(null); };
$("wyb-anuluj").onclick = () => { $("wybierz").hidden = true; };
$("wyb-gora").onclick = () => {  // folder wyżej; z katalogu głównego dysku — lista dysków
  const s = (wyb.sciezka || "").replace(/[\\/]+$/, "");
  if (!s || /^[A-Za-z]:$/.test(s)) { pokazWybor(null); return; }
  const i = Math.max(s.lastIndexOf("\\"), s.lastIndexOf("/"));
  let nad = i < 0 ? null : i === 0 ? "/" : s.slice(0, i);
  if (nad && /^[A-Za-z]:$/.test(nad)) nad += "\\";
  if (nad && /^\\\\[^\\]*$/.test(nad)) nad = null;  // \\serwer — wracamy do dysków
  pokazWybor(nad);
};
$("wyb-ok").onclick = async () => {
  $("wybierz").hidden = true;
  try {
    rysujPrz(await post("/api/przegladarka/foldery", {foldery: [...prz.foldery, wyb.sciezka]}));
    $("prz-skanuj").click();  // od razu wczytaj
  } catch (e) { $("prz-stan").textContent = e.message; }
};

async function start() {
  try {
    await wczytajLata();
    if (g.widok === "mapa") await pokazMape();
    try { g.dzien = await api("/api/g/tego-dnia"); } catch (e) { g.dzien = null; }
    if (g.widok === "kolekcje") rysujKolekcje();
    if (P.get("dzien") && !start.byl) { start.byl = true; pokazWyniki({typ: "dzien", md: mdDzis(), dni: 0}); return; }
    uklad();
  }
  catch (e) { if (e.message !== "Podaj PIN") $("siatka").innerHTML = `<div class="pusto">${e.message}</div>`; }
}
start();
