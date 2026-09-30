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
           lista: [], poz: 0, zakres: "biblioteka"};

function url(sciezka, param = {}) {
  const u = new URLSearchParams(param);
  if (TOKEN) u.set("t", TOKEN);
  if (W_PROGRAMIE) u.set("z", g.zakres);
  return sciezka + "?" + u.toString();
}
async function api(sciezka, param) {
  const r = await fetch(url(sciezka, param));
  if (r.status === 401 || r.status === 403) { pokazLogin(); throw new Error("Podaj PIN"); }
  const j = await r.json();
  if (!r.ok || j.blad) throw new Error(j.blad || r.statusText);
  return j;
}
const miniatura = (id, srednia = true) => url("/api/g/miniatura", srednia ? {id, srednia: 1} : {id});
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
  const r = await api("/api/g/lata");
  g.lata = r.lata;
  $("licznik").textContent = `${r.razem.toLocaleString("pl-PL")} zdjęć i filmów · z miejscem: ${r.z_gps.toLocaleString("pl-PL")}`;
  rysujWykres();
  if (tylkoLiczby && g.rok && g.lata.some(x => x.rok === g.rok)) { oznaczWykres(); return; }  // skan w toku
  const l = $("lata"); l.replaceChildren();
  if (!g.lata.length) {
    $("siatka").innerHTML = `<div class="pusto">${W_PROGRAMIE && g.zakres === "biblioteka"
      ? "Biblioteka jest jeszcze pusta — uporządkuj pliki albo wybierz „Wszystko w projekcie”."
      : g.zakres === "przegladarka"
        ? "Dodaj dysk lub folder (＋) i kliknij „Skanuj”. Przeglądarka tylko czyta — niczego nie zmienia ani nie przenosi."
        : "Brak zdjęć z datą."}</div>`;
    $("miesiace").replaceChildren(); return;
  }
  for (const rok of g.lata) {
    const b = document.createElement("button");
    b.innerHTML = `${rok.rok}<small>${rok.n.toLocaleString("pl-PL")}</small>`;
    b.onclick = () => wybierzRok(rok.rok);
    b.dataset.rok = rok.rok; l.append(b);
  }
  wybierzRok(g.lata.some(x => x.rok === g.rok) ? g.rok : g.lata[0].rok);
}
function wybierzRok(rok, mies = null) {
  g.rok = rok;
  document.querySelectorAll("#lata button").forEach(b => b.classList.toggle("akt", b.dataset.rok === rok));
  const r = g.lata.find(x => x.rok === rok);
  const m = $("miesiace"); m.replaceChildren();
  const wsz = document.createElement("button"); wsz.innerHTML = `cały rok<small>${r.n}</small>`; wsz.dataset.m = "";
  wsz.onclick = () => wybierzMiesiac(null); m.append(wsz);
  for (const x of [...r.miesiace].sort((a, b) => a.m - b.m)) {
    const b = document.createElement("button"); b.innerHTML = `${MIESIACE[x.m - 1] || "?"}<small>${x.n}</small>`;
    b.dataset.m = x.m; b.onclick = () => wybierzMiesiac(x.m); m.append(b);
  }
  wybierzMiesiac(mies);
  document.querySelector(`#lata button[data-rok="${rok}"]`)?.scrollIntoView({inline: "nearest", block: "nearest"});
}
async function wybierzMiesiac(mies) {
  g.mies = mies; g.pliki = [];
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
  const r = await api("/api/g/pliki", {rok: g.rok, miesiac: g.mies || 0, od: wiecej ? g.pliki.length : 0, ile: 200});
  g.pliki = wiecej ? g.pliki.concat(r.pliki) : r.pliki; g.razem = r.razem;
  rysujSiatke();
}
function rysujSiatke() {
  const s = $("siatka"); s.replaceChildren();
  g.pliki.forEach((p, i) => {
    const k = document.createElement("div"); k.className = "k"; k.title = p.nazwa;
    const ob = document.createElement("div"); ob.className = "ob";
    if (p.rodzaj === "zdjecie") {
      const im = new Image(); im.loading = "lazy"; im.alt = ""; im.src = miniatura(p.id);
      im.onerror = () => { ob.textContent = "🖼️"; }; ob.append(im);
    } else ob.textContent = "🎬";
    const op = document.createElement("div"); op.className = "op";
    op.innerHTML = "<div></div><div class='m'></div>";
    op.children[0].textContent = p.nazwa;
    op.children[1].textContent = dataTxt(p.data) + (p.lat != null ? " · 📍" : "");
    k.append(ob, op);
    k.onclick = () => pokazPelny(g.pliki, i);
    s.append(k);
  });
  if (g.pliki.length < g.razem) {
    const b = document.createElement("button"); b.className = "wiecej";
    b.textContent = `Pokaż kolejne (zostało ${(g.razem - g.pliki.length).toLocaleString("pl-PL")})`;
    b.onclick = () => wczytajPliki(true); s.append(b);
  }
  if (!g.pliki.length) s.innerHTML = '<div class="pusto">Brak zdjęć w tym okresie.</div>';
}

// ---------- podgląd na cały ekran ----------
async function pokazPelny(lista, poz) {
  g.lista = lista; g.poz = poz;
  $("pelny").hidden = false;
  const p = lista[poz], t = $("pelny-tresc"); t.replaceChildren();
  if (p.rodzaj === "film") {
    const v = document.createElement("video"); v.controls = true; v.autoplay = true; v.src = url("/api/g/film", {id: p.id});
    t.append(v);
  } else {
    const mini = new Image(); mini.src = miniatura(p.id); t.append(mini);  // najpierw szybka miniatura
    const im = new Image(); im.src = url("/api/g/podglad", {id: p.id});
    im.onload = () => { if (g.lista[g.poz] === p) t.replaceChildren(im); };
  }
  $("pelny-opis").textContent = `${p.nazwa} · ${dataTxt(p.data)}`;
  if (p.miejsce === undefined) {
    try { const d = await api("/api/g/plik", {id: p.id}); p.miejsce = d.miejsce; } catch (e) { p.miejsce = null; }
  }
  if (g.lista[g.poz] === p && p.miejsce) $("pelny-opis").textContent += " · " + p.miejsce;
  $("pelny").querySelector(".pop").hidden = poz <= 0;
  $("pelny").querySelector(".nast").hidden = poz >= lista.length - 1;
}
function zamknijPelny() { $("pelny").hidden = true; $("pelny-tresc").replaceChildren(); }
function krok(d) { const n = g.poz + d; if (n >= 0 && n < g.lista.length) pokazPelny(g.lista, n); }
$("pelny").querySelector(".zam").onclick = zamknijPelny;
$("pelny").querySelector(".pop").onclick = e => { e.stopPropagation(); krok(-1); };
$("pelny").querySelector(".nast").onclick = e => { e.stopPropagation(); krok(1); };
$("pelny").onclick = e => { if (e.target.id === "pelny" || e.target.id === "pelny-tresc") zamknijPelny(); };
document.addEventListener("keydown", e => {
  if ($("pelny").hidden) return;
  if (e.key === "Escape") zamknijPelny();
  if (e.key === "ArrowLeft") krok(-1);
  if (e.key === "ArrowRight") krok(1);
});
let dotyk = null;  // przesuwanie palcem na telefonie
$("pelny").addEventListener("touchstart", e => { dotyk = e.touches[0].clientX; }, {passive: true});
$("pelny").addEventListener("touchend", e => {
  if (dotyk === null) return;
  const d = e.changedTouches[0].clientX - dotyk; dotyk = null;
  if (Math.abs(d) > 50) krok(d < 0 ? 1 : -1);
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
    const m = L.marker([lat, lon], {title: film ? "film" : "zdjęcie"});
    m.on("click", () => otworzPinezke(m, id, film));
    m.on("dblclick", e => { L.DomEvent.stop(e); pelnyZPinezki(id, film); });
    return m;
  });
  g.klaster.addLayers(markery);
  g.mapa.addLayer(g.klaster);
  if (markery.length) g.mapa.fitBounds(g.klaster.getBounds(), {padding: [30, 30], maxZoom: 14});
  info(markery.length
    ? `${markery.length.toLocaleString("pl-PL")} zdjęć i filmów na mapie · kliknij pinezkę = miniatura, dwa razy = całe zdjęcie`
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

// ---------- przełączanie widoków ----------
function widok(w) {
  g.widok = w;
  $("w-os").classList.toggle("akt", w === "os"); $("w-mapa").classList.toggle("akt", w === "mapa");
  $("os").hidden = w !== "os"; $("lata").hidden = w !== "os"; $("miesiace").hidden = w !== "os"; tip(null);
  $("wykres").hidden = w !== "os" || !$("wykres").childElementCount;
  $("mapa").hidden = w !== "mapa"; $("mapa-info").hidden = w !== "mapa";
  if (w === "mapa") pokazMape().catch(e => info(e.message));
}
$("w-os").onclick = () => widok("os");
$("w-mapa").onclick = () => widok("mapa");

// ---------- w oknie programu: zakres, zamykanie, udostępnianie na telefon ----------
if (W_PROGRAMIE) {
  $("zakres").hidden = false; $("na-telefon").hidden = false; $("zamknij").hidden = false;
  g.zakres = P.get("z") || "biblioteka"; $("zakres").value = g.zakres;
  $("zakres").onchange = () => { g.zakres = $("zakres").value; g.punkty = null; g.rok = null; ustawZakres(); start(); };
  $("zamknij").onclick = () => window.parent.postMessage("zamknij-galerie", "*");
  $("na-telefon").onclick = () => telefon(true);
  $("tel-zamknij").onclick = () => { $("telefon").hidden = true; };
  $("tel-wylacz").onclick = () => telefon(false);
  ustawZakres();
}
async function telefon(wlacz) {
  $("telefon").hidden = false; $("tel-tresc").textContent = wlacz ? "Uruchamiam…" : "Wyłączam…";
  try {
    const r = await fetch(url("/api/telefon"), {method: "POST", headers: {"Content-Type": "application/json", "X-Token": TOKEN},
                                                 body: JSON.stringify({wlacz, zakres: g.zakres})});
    const j = await r.json();
    if (!r.ok || j.blad) throw new Error(j.blad || r.statusText);
    if (!j.wlaczone) { $("telefon").hidden = true; return; }
    const adr = j.adresy[0] || "";
    const qr = qrcode(0, "M"); qr.addData(adr); qr.make();
    $("tel-tresc").innerHTML = `<div class="qr"><div>${qr.createSvgTag({cellSize: 5, margin: 2})}</div>
      <div><div class="info">PIN</div><div class="pin"></div></div></div>
      <div>Zeskanuj kod aparatem telefonu albo wpisz w przeglądarce telefonu: <code id="tel-adr"></code></div>
      <ul><li>Telefon musi być w tej samej sieci Wi-Fi — albo mieć włączony <b>Tailscale</b> (wtedy działa z każdego miejsca;
      adres zaczyna się od 100.): <span id="tel-inne"></span></li>
      <li>Windows może zapytać o zaporę — zaznacz <b>sieci prywatne</b> i kliknij <b>Zezwalaj</b>.</li>
      <li>Działa, dopóki Katalogator jest otwarty. Na 24/7 — Raspberry Pi (instrukcja w README).</li>
      <li>Tylko oglądanie — z telefonu nie da się niczego zmienić ani usunąć.</li></ul>`;
    $("tel-tresc").querySelector(".pin").textContent = j.pin;
    $("tel-adr").textContent = adr;
    $("tel-inne").textContent = j.adresy.slice(1).join(", ") || "—";
  } catch (e) { $("tel-tresc").textContent = e.message; }
}

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
  $("prz").hidden = !p;
  document.querySelector("header h1").textContent = p ? "🔭 Przeglądarka" : "📚 Biblioteka";
  document.title = (p ? "Przeglądarka" : "Biblioteka") + " — Katalogator";
  if (p) odswiezPrz();
}
function rysujPrz(s) {
  prz.foldery = s.foldery; prz.trwa = s.trwa;
  const f = $("prz-foldery"); f.replaceChildren();
  for (const sc of s.foldery) {
    const c = document.createElement("span"); c.className = "prz-f"; c.title = sc;
    const n = document.createElement("span"); n.textContent = "\u200E📁 " + sc;
    const x = document.createElement("button"); x.textContent = "✕"; x.title = "Usuń z przeglądarki (pliki zostają na dysku)";
    x.onclick = async () => { rysujPrz(await post("/api/przegladarka/foldery", {foldery: prz.foldery.filter(y => y !== sc)})); g.punkty = null; start(); };
    c.append(n, x); f.append(c);
  }
  $("prz-skanuj").disabled = s.trwa || !s.foldery.length;
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
  try { await wczytajLata(); if (g.widok === "mapa") await pokazMape(); }
  catch (e) { if (e.message !== "Podaj PIN") $("siatka").innerHTML = `<div class="pusto">${e.message}</div>`; }
}
start();
