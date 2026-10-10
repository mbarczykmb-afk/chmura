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
           dzien: null, pokaz: null};
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
      ? "Biblioteka jest jeszcze pusta — uporządkuj pliki albo wybierz „Wszystko w projekcie”."
      : g.zakres === "przegladarka"
        ? "Dodaj dysk lub folder (＋) i kliknij „Skanuj”. Przeglądarka tylko czyta dyski — niczego sama nie zmienia (usuwasz tylko Ty, przyciskiem 🗑, z możliwością cofnięcia)."
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
    : z.typ === "dzien" ? await api("/api/g/tego-dnia", {md: z.md || mdDzis(), dni: z.dni || 0})
    : await api("/api/g/pliki", {rok: g.rok, miesiac: g.mies || 0, od, ile: 200, ...obszarParam()});
  if (z !== g.zrodlo) return;  // w międzyczasie wybrano coś innego
  const bylo = wiecej ? g.pliki.length : 0;
  g.pliki = wiecej ? g.pliki.concat(r.pliki) : r.pliki; g.razem = r.razem;
  if (r.opis !== undefined) z.opis = r.opis;
  if (r.nazwa) z.nazwa = r.nazwa;
  if (z.typ === "dzien") { z.md = r.md; z.lata = r.lata; z.najblizszy = r.najblizszy; }
  rysujSiatke(bylo); rysujFiltr();
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
    const k = document.createElement("div"); k.className = "k"; k.title = p.nazwa;
    const ob = document.createElement("div"); ob.className = "ob";
    if (p.rodzaj === "zdjecie") {
      const im = new Image(); im.loading = "lazy"; im.alt = ""; im.src = miniatura(p.id, false);  // mała: szybka, zapamiętywana na dysku
      im.onerror = () => { ob.textContent = "🖼️"; }; ob.append(im);
    } else miniaturaFilmu(p, ob);
    if (MOZE_USUWAC) {
      const x = document.createElement("button"); x.className = "kosz"; x.textContent = "🗑"; x.title = "Usuń (do kosza programu, można cofnąć)";
      x.onclick = e => { e.stopPropagation(); usunPliki([p]); }; ob.append(x);
    }
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
  if (p.miejsce === undefined) {
    try {
      const d = await api("/api/g/plik", {id: p.id}); p.miejsce = d.miejsce; p.ulubione = d.ulubione;
      if (p.lat == null && d.lat != null) { p.lat = d.lat; p.lon = d.lon; }
    }
    catch (e) { p.miejsce = null; }
  }
  if (g.lista[g.poz] === p) { narzedziaPelnego(p); miniMapa(p); }
  if (g.lista[g.poz] === p && p.miejsce) $("pelny-opis").textContent += " · " + p.miejsce;
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
  if (e.key === "Escape") { if (g.pokaz) stopPokaz(); else if (zoom.s > 1) zoomReset(); else zamknijPelny(); }
  if (e.key === "ArrowLeft" && zoom.s === 1) krokRecznie(-1);
  if (e.key === "ArrowRight" && zoom.s === 1) krokRecznie(1);
  if (e.key === "p" || e.key === "P") przelaczPokaz();
  if ((e.key === "f" || e.key === "F") && W_PROGRAMIE) $("p-ulub").click();
  if (!$("lok").hidden) { if (e.key === "Escape") zamknijLok(); return; }
  if (e.key === "Delete" && MOZE_USUWAC) $("p-usun").click();
  if ((e.key === "l" || e.key === "L") && MOZE_USUWAC) $("p-miejsce").click();
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
}
function pokazWyniki(zrodlo) {  // wyniki szukania, ulubione, album, tego dnia — w tej samej siatce
  g.zrodlo = zrodlo; g.widok = "os"; g.pliki = []; g.razem = 0;
  $("siatka").innerHTML = '<div class="pusto">Szukam…</div>';
  uklad(); wczytajPliki().catch(e => { $("siatka").innerHTML = `<div class="pusto">${e.message}</div>`; });
}
$("w-os").onclick = () => widok("os");
$("w-mapa").onclick = () => widok("mapa");
$("w-kolekcje").onclick = () => widok("kolekcje");
$("w-dzien").onclick = () => { g.widok = "os"; pokazWyniki({typ: "dzien", md: mdDzis(), dni: 0}); };

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
  } else if (g.widok === "os" && z.typ === "szukaj") {
    f.append(znacznik("🔍 " + (z.opis || z.q), () => { $("szukaj").value = ""; widok("os"); }, "Wyczyść szukanie"), inf(ile(g.razem)));
    const p = pokaz(); if (p) f.append(p);
    if (W_PROGRAMIE && g.razem) f.append(przycisk("＋ Zapisz jako album", () => zapiszJakoAlbum(z.opis || z.q), "Nowy album z wynikami (do 5000)"));
  } else if (g.widok === "os" && z.typ === "kolekcja") {
    f.append(przycisk("← Kolekcje", () => widok("kolekcje")));
    const t = document.createElement("span"); t.className = "tyt"; t.textContent = z.nazwa || ""; f.append(t, inf(ile(g.razem)));
    const p = pokaz(); if (p) f.append(p);
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
  for (const a of r.albumy) kafel("🗂", a.nazwa, a.n, a.okladka, () => pokazWyniki({typ: "kolekcja", kol: "album", album: a.id, nazwa: a.nazwa}));
  if (W_PROGRAMIE) kafel("＋", "Nowy album", null, null, async () => {
    const n = prompt("Nazwa nowego albumu:", "Wakacje " + new Date().getFullYear()); if (!n) return;
    await post("/api/g/album/nowy", {nazwa: n, ids: []}); rysujKolekcje();
  }, "nowy");
  if (!W_PROGRAMIE && !r.albumy.length && !r.ulubione.n) s.innerHTML = '<div class="pusto">Brak ulubionych i albumów — tworzy się je w programie na komputerze.</div>';
}

// ---------- 📍 lokalizacja: dodaj / zmień / usuń (w pliku: JPEG — EXIF, inne — .xmp obok) ----------
// poprzednie: {id: [lat, lon] | [null, null]} — do „Cofnij”
async function ustawLokalizacje(ids, lat, lon, poprzednie, cicho = false) {
  let w;
  try { w = await post("/api/g/lokalizacja", {ids, lat, lon}); }
  catch (e) { toastG("Nie zapisano lokalizacji: " + e.message); return false; }
  if (!w.zmienione) { toastG("Nie zapisano lokalizacji: " + (w.bledy[0] || "")); return false; }
  for (const tab of [g.pliki, g.lista]) for (const p of tab || []) if (ids.includes(p.id) && w.poprzednie[p.id]) {
    p.lat = lat; p.lon = lon;
  }
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
function oknoLokalizacji(p) {
  lok.p = p; stopPokaz();
  $("lok").hidden = false;
  $("lok-tyt").textContent = `📍 ${p.nazwa || "Lokalizacja"}`;
  $("lok-szukaj").value = ""; $("lok-wyniki").replaceChildren();
  // „także inne zdjęcia z tego dnia bez lokalizacji” — najczęstszy przypadek: aparat bez GPS na wycieczce
  const dzien = (p.data || "").slice(0, 10);
  const inne = dzien ? (g.lista || []).filter(x => x.id !== p.id && x.lat == null && (x.data || "").slice(0, 10) === dzien) : [];
  $("lok-inne").hidden = !inne.length; $("lok-inne-cb").checked = false;
  lok.inne = inne; lok.wybrane = new Set(inne.map(x => x.id));
  rysujInneLok();
  $("lok-usun").hidden = p.lat == null;
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
  const cele = [p, ...($("lok-inne-cb").checked ? lok.inne.filter(x => lok.wybrane.has(x.id)) : [])];
  const pop = Object.fromEntries(cele.map(x => [x.id, [x.lat ?? null, x.lon ?? null]]));
  if (await ustawLokalizacje(cele.map(x => x.id), ll.lat, ll.lng, pop)) { lok.ostatnie = [ll.lat, ll.lng]; zamknijLok(); }
};
$("lok-usun").onclick = async () => {
  const p = lok.p;
  if (await ustawLokalizacje([p.id], null, null, {[p.id]: [p.lat, p.lon]})) zamknijLok();
};
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
  $("p-pokaz").textContent = g.pokaz ? "⏸ Pauza" : "▶ Pokaz";
}
const biezacy = () => g.lista[g.poz];
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
$("p-album").onclick = async e => {
  e.stopPropagation();
  if (document.querySelector(".menu-alb")) { zamknijMenuAlb(); return; }
  const p = biezacy(); if (!p) return;
  const m = document.createElement("div"); m.className = "menu-alb"; m.onclick = ev => ev.stopPropagation();
  m.textContent = "Wczytuję…"; $("pelny").append(m);
  const r = await api("/api/g/albumy"); m.replaceChildren();
  const dodaj = async (album, nazwa) => {
    await post("/api/g/album/dodaj", {album, ids: [p.id]}); zamknijMenuAlb();
    const b = $("p-album"); b.textContent = `✓ W „${nazwa}”`; setTimeout(() => { b.textContent = "＋ Album"; }, 1800);
  };
  for (const a of r.albumy) m.append(przycisk(`🗂 ${a.nazwa}`, () => dodaj(a.id, a.nazwa)));
  m.append(przycisk("＋ Nowy album…", async () => {
    const n = prompt("Nazwa nowego albumu:"); if (!n) return;
    const w = await post("/api/g/album/nowy", {nazwa: n, ids: [p.id]}); zamknijMenuAlb();
    const b = $("p-album"); b.textContent = `✓ W „${w.nazwa}”`; setTimeout(() => { b.textContent = "＋ Album"; }, 1800);
  }));
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
  if (!s.foldery.length && !naglowek.dyski) { naglowek.dyski = true; pokazDyski(); }  // nic nie dodano — od razu pokaż
  if (s.katalogator_pracuje && !s.trwa)  // ten sam dysk sieciowy — dwa zadania naraz idą wolniej
    $("prz-stan").textContent += " · Katalogator teraz porządkuje pliki — odświeżę się sam, gdy skończy";
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
