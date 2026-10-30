// 📍 Bez GPS — propozycje lokalizacji dla zdjęć bez współrzędnych (bez_gps.py): ślad Stravy / Intervals.icu / GPX z tej samej
// chwili, zdjęcie z GPS zrobione obok, oś czasu Google z Podróży, a dla reszty GeoCLIP. Jak przy duplikatach: grupa zdjęć,
// propozycja na mapie obok, decyzja należy do Ciebie — „Dodaj lokalizację” zapisuje ją zwykłą drogą (EXIF / .xmp, z Cofnij).
"use strict";

const gps = {d: null, grupy: [], razem: 0, typ: "", wybrana: null, mapa: null, warstwy: null, punkt: null, zegar: null};
const GPS_ZRODLA = {slad: "🥾 Ślad", sasiad: "📷 Zdjęcie obok", wizyta: "🗺 Oś czasu", przejazd: "🚗 Przejazd", geoclip: "🧠 GeoCLIP"};

(function stylGps() {
  const s = document.createElement("style");
  s.textContent = `
  .gps-uklad{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,1fr);gap:14px;align-items:start}
  .gps-lewa{display:flex;flex-direction:column;gap:10px;min-width:0}
  .gps-prawa{position:sticky;top:0;height:calc(100vh - 150px);min-height:360px;border:1px solid var(--lin);border-radius:10px;overflow:hidden}
  #gps-mapa{width:100%;height:100%}
  .gps-pas{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 12px;border:1px solid var(--lin);border-radius:10px;background:var(--panel)}
  .gps-pas .info{color:var(--mut,#888);font-size:12.5px}
  .gps-pas input[type=text]{flex:1;min-width:220px}
  .gps-blad{color:#e5484d}
  .gps-pasek{flex-basis:100%;height:5px;border-radius:3px;background:var(--lin);overflow:hidden}
  .gps-pasek i{display:block;height:100%;background:var(--akc,#7354f0);width:0}
  .gps-gr{border:1px solid var(--lin);border-radius:10px;background:var(--panel);padding:10px 12px;cursor:pointer}
  .gps-gr.wyb{outline:2px solid var(--akc,#7354f0);outline-offset:-1px}
  .gps-gr .gl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:13px}
  .gps-gr .gl b{font-weight:650}
  .gps-gr .m{color:var(--mut,#888);font-size:12px}
  .gps-pew{font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;border:1px solid currentColor}
  .gps-pew.wysoka{color:#30a46c}.gps-pew.średnia{color:#d4a017}.gps-pew.niska,.gps-pew.przybliżona{color:#e5484d}
  .gps-min{display:flex;gap:4px;margin:8px 0;overflow:hidden}
  .gps-min img{width:64px;height:64px;object-fit:cover;border-radius:6px;flex:none;background:var(--lin)}
  .gps-min span{display:flex;align-items:center;justify-content:center;width:64px;height:64px;border-radius:6px;background:var(--lin);font-size:13px;flex:none}
  .gps-akcje{display:flex;gap:8px;flex-wrap:wrap}
  .gps-zrodla{display:flex;gap:6px;flex-wrap:wrap}
  @media (max-width:900px){.gps-uklad{grid-template-columns:1fr}.gps-prawa{position:relative;height:320px}}`;
  document.head.append(s);
})();

const gpsEl = (tag, wlasc = {}, ...dzieci) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(wlasc)) if (k in e) e[k] = v; else e.setAttribute(k, v);
  e.append(...dzieci.filter(x => x !== null && x !== undefined));
  return e;
};
const gpsData = s => s ? new Date(s).toLocaleString("pl-PL", {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"}) : "";
const gpsZdjec = n => `${n} ${n === 1 ? "zdjęcie" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "zdjęcia" : "zdjęć"}`;

async function rysujGps(odNowa = true) {
  const s = $("siatka");
  if (odNowa || !$("gps-lewa")) {
    s.replaceChildren(gpsEl("div", {className: "gps-uklad"},
      gpsEl("div", {className: "gps-lewa", id: "gps-lewa"}, gpsEl("div", {className: "pusto", textContent: "Wczytuję…"})),
      gpsEl("div", {className: "gps-prawa"}, gpsEl("div", {id: "gps-mapa"}))));
    gps.mapa = null; gps.wybrana = null;
  }
  try {
    gps.d = await api("/api/g/gps");
    const r = await api("/api/g/gps/grupy", {od: 0, ile: 40, typ: gps.typ});
    gps.grupy = r.grupy; gps.razem = r.razem;
  } catch (e) { $("gps-lewa").replaceChildren(gpsEl("div", {className: "pusto", textContent: e.message})); return; }
  if (g.widok !== "gps") return;
  rysujFiltr(); rysujGpsPanel(); rysujGpsGrupy(); gpsMapa();
  if (!gps.wybrana && gps.grupy.length) wybierzGps(gps.grupy[0]);
  gpsOdpytuj();
}

function gpsOdpytuj() {  // skan, pobieranie śladów i modelu idą w tle — odświeżaj panel, aż skończą
  clearTimeout(gps.zegar);
  const d = gps.d || {}, trwa = d.trwa || (d.slady && d.slady.pobieranie && d.slady.pobieranie.trwa) || (d.geoclip_model && d.geoclip_model.trwa);
  if (!trwa || g.widok !== "gps") return;
  gps.zegar = setTimeout(async () => {
    const byl = gps.d.trwa;
    try { gps.d = await api("/api/g/gps"); } catch (e) { return; }
    if (g.widok !== "gps") return;
    if (byl && !gps.d.trwa) { rysujGps(false); return; }   // skan skończony — nowe grupy
    rysujGpsPanel(); gpsOdpytuj();
  }, 1000);
}

function rysujGpsPanel() {
  const d = gps.d, lewa = $("gps-lewa");
  let panel = $("gps-panel");
  if (!panel) { panel = gpsEl("div", {id: "gps-panel", className: "gps-lewa"}); lewa.replaceChildren(panel, gpsEl("div", {id: "gps-lista", className: "gps-lewa"})); }
  panel.replaceChildren();
  const pas = gpsEl("div", {className: "gps-pas"});
  const sl = d.slady || {}, kl = sl.klucze || {}, model = d.geoclip_model || {}, u = d.ustawienia || {};
  // ▶ skan
  pas.append(d.trwa ? przycisk("■ Przerwij", async () => { await post("/api/g/gps/przerwij"); })
                    : przycisk("🔍 Szukaj propozycji", async () => {
                        try { await post("/api/g/gps/skanuj"); gps.d.trwa = true; rysujGpsPanel(); gpsOdpytuj(); } catch (e) { toastG(e.message); }
                      }, "Przegląda zdjęcia bez GPS i szuka dla nich miejsca w śladach, zdjęciach obok i osi czasu", "akt"));
  const lc = gpsEl("label", {className: "menu-cb", title: "Dla zdjęć bez żadnego tropu — rozpoznanie miejsca z samego obrazu (przybliżone)"});
  const cb = gpsEl("input", {type: "checkbox", checked: !!u.geoclip, disabled: !model.pobrany});
  cb.onchange = async () => { try { gps.d = await post("/api/g/gps/ustawienia", {geoclip: cb.checked}); } catch (e) { toastG(e.message); } rysujGpsPanel(); };
  lc.append(cb, " 🧠 GeoCLIP dla reszty");
  pas.append(lc);
  if (!model.pobrany) pas.append(model.trwa ? gpsEl("span", {className: "info", textContent: `⏳ model: ${model.zrobione || 0} z ${model.wszystkie || "?"} MB`})
    : przycisk("⬇ Pobierz model GeoCLIP (~400 MB)", async () => {
        try { await post("/api/g/gps/model"); gps.d = await api("/api/g/gps"); rysujGpsPanel(); gpsOdpytuj(); } catch (e) { toastG(e.message); }
      }, "Model rozpoznawania miejsca ze zdjęcia — działa na tym komputerze, zdjęcia nigdzie nie są wysyłane"));
  if (model.blad) pas.append(gpsEl("span", {className: "info gps-blad", textContent: model.blad}));
  // ⬇ ślady
  const sp = sl.pobieranie || {};
  if (kl.intervals || kl.strava) {
    pas.append(sp.trwa ? gpsEl("span", {className: "info", textContent: `⏳ ${sp.komunikat || "Pobieram ślady…"}${sp.wszystkie ? ` (${sp.zrobione} z ${sp.wszystkie})` : ""}`})
      : przycisk("⬇ Pobierz ślady z dni tych zdjęć", async () => {
          try { await post("/api/g/gps/slady"); gps.d = await api("/api/g/gps"); rysujGpsPanel(); gpsOdpytuj(); } catch (e) { toastG(e.message); }
        }, "Strava / Intervals.icu: ślady aktywności z dni, w których są zdjęcia bez GPS (zapamiętane na komputerze)"));
    if (!sp.trwa && (sp.blad || sp.komunikat)) pas.append(gpsEl("span", {className: "info" + (sp.blad ? " gps-blad" : ""), textContent: sp.blad || sp.komunikat}));
  } else pas.append(gpsEl("span", {className: "info", textContent: "Strava / Intervals.icu: klucze wpisz w programie — Ustawienia → Podróże → Ślady GPS."}));
  // 📁 GPX
  const gpx = gpsEl("input", {type: "text", value: u.folder_gpx || "", placeholder: "Folder z plikami GPX (np. eksport Sports Trackera)"});
  gpx.onchange = async () => { try { gps.d = await post("/api/g/gps/ustawienia", {folder_gpx: gpx.value.trim()}); toastG("Zapisano folder GPX."); } catch (e) { toastG(e.message); } };
  pas.append(gpsEl("span", {className: "info", textContent: "📁 GPX:"}), gpx);
  if (d.podpowiedz_gpx) pas.append(przycisk("Użyj: " + d.podpowiedz_gpx, async () => {
    try { gps.d = await post("/api/g/gps/ustawienia", {folder_gpx: d.podpowiedz_gpx}); rysujGpsPanel(); toastG("Zapisano folder GPX."); } catch (e) { toastG(e.message); }
  }, "Folder z eksportem Sports Trackera (projekt Szczyty)"));
  // stan
  if (d.trwa || d.komunikat || d.blad) {
    pas.append(gpsEl("span", {className: "info" + (d.blad ? " gps-blad" : ""), style: "flex-basis:100%", textContent: d.blad || d.komunikat}));
    if (d.trwa && d.wszystkie) { const p = gpsEl("div", {className: "gps-pasek"}, gpsEl("i")); p.firstChild.style.width = Math.round(100 * d.zrobione / d.wszystkie) + "%"; pas.append(p); }
  }
  panel.append(pas);
  // podsumowanie i filtr źródeł
  const ps = d.podsumowanie;
  if (ps) {
    const z = gpsEl("div", {className: "gps-zrodla"});
    const chip = (typ, tekst) => przycisk(tekst, () => { gps.typ = gps.typ === typ ? "" : typ; rysujGps(false); }, "", gps.typ === typ ? "akt" : "");
    z.append(chip("", `Wszystkie (${ps.propozycje})`));
    for (const [t, n] of Object.entries(ps.zrodla || {})) if (n) z.append(chip(t, `${GPS_ZRODLA[t]} (${n})`));
    panel.append(gpsEl("div", {className: "gps-pas"},
      gpsEl("span", {className: "info", style: "flex-basis:100%", textContent:
        `${gpsZdjec(ps.bez_gps)} bez GPS · propozycje dla ${ps.propozycje} (${ps.grupy} grup) · bez propozycji: ${ps.bez_propozycji}` +
        (ps.slady ? ` · ślady do porównania: ${ps.slady}` : "")}), z));
  }
}

function rysujGpsGrupy() {
  const l = $("gps-lista");
  l.replaceChildren();
  if (!gps.d.podsumowanie) { l.append(gpsEl("div", {className: "pusto", textContent: "Kliknij „🔍 Szukaj propozycji” — program znajdzie zdjęcia bez GPS i podpowie, gdzie zostały zrobione."})); return; }
  if (!gps.grupy.length) { l.append(gpsEl("div", {className: "pusto", textContent: "Brak propozycji do przejrzenia."})); return; }
  for (const x of gps.grupy) l.append(kartaGps(x));
  if (gps.razem > gps.grupy.length) l.append(przycisk(`Pokaż więcej (${gps.razem - gps.grupy.length})`, async () => {
    const r = await api("/api/g/gps/grupy", {od: gps.grupy.length, ile: 40, typ: gps.typ});
    gps.grupy.push(...r.grupy); rysujGpsGrupy();
  }));
}

function kartaGps(x) {
  const k = gpsEl("div", {className: "gps-gr" + (gps.wybrana === x ? " wyb" : "")});
  k.onclick = () => wybierzGps(x);
  k.append(gpsEl("div", {className: "gl"},
    gpsEl("b", {textContent: GPS_ZRODLA[x.typ] || x.typ}), gpsEl("span", {textContent: x.opis}),
    gpsEl("span", {className: "gps-pew " + x.pewnosc, textContent: x.pewnosc})));
  k.append(gpsEl("div", {className: "m", textContent: `${gpsZdjec(x.n)} · ${gpsData(x.od)}${x.do !== x.od ? " – " + gpsData(x.do) : ""}`}));
  const m = gpsEl("div", {className: "gps-min"});
  for (const id of x.ids.slice(0, 8)) {
    const im = new Image(); im.loading = "lazy"; im.alt = ""; im.src = miniatura(id, false);
    m.append(im);
  }
  if (x.n > 8) m.append(gpsEl("span", {textContent: "+" + (x.n - 8)}));
  k.append(m);
  const a = gpsEl("div", {className: "gps-akcje"});
  a.append(przycisk(`✓ Dodaj lokalizację (${x.n})`, e => { e.stopPropagation(); przyjmijGps(x); }, "Zapisuje propozycję w zdjęciach (JPEG — EXIF, inne — .xmp obok); można cofnąć", "akt"));
  a.append(przycisk("✕ Odrzuć", async e => {
    e.stopPropagation();
    try { await post("/api/g/gps/odrzuc", {ids: x.ids, typ: x.typ}); usunGps(x); toastG("Odrzucono — ta propozycja nie wróci."); } catch (er) { toastG(er.message); }
  }, "Ta propozycja nie wróci przy kolejnym szukaniu (inne źródła — tak)"));
  k.append(a);
  return k;
}

function gpsMapa() {
  if (gps.mapa) { setTimeout(() => gps.mapa.invalidateSize(), 50); return; }
  gps.mapa = L.map("gps-mapa", {worldCopyJump: true}).setView([52, 19], 5);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>'}).addTo(gps.mapa);
  gps.warstwy = L.layerGroup().addTo(gps.mapa);
  setTimeout(() => gps.mapa.invalidateSize(), 50);
}

function wybierzGps(x) {
  gps.wybrana = x; gps.punkt = null;
  document.querySelectorAll(".gps-gr").forEach(e => e.classList.remove("wyb"));
  const i = gps.grupy.indexOf(x), karty = document.querySelectorAll(".gps-gr");
  if (karty[i]) karty[i].classList.add("wyb");
  if (!gps.mapa) return;
  gps.warstwy.clearLayers();
  const granice = [];
  if (x.slad && x.slad.length > 1) {
    L.polyline(x.slad, {color: "#020617", weight: 7, opacity: 0.4, interactive: false}).addTo(gps.warstwy);
    L.polyline(x.slad, {color: "#fb923c", weight: 3.5, opacity: 0.95}).bindTooltip(x.opis, {sticky: true}).addTo(gps.warstwy);
    granice.push(...x.slad);
  }
  if (x.jeden_punkt) {   // GeoCLIP: jeden punkt dla całej grupy — można przesunąć albo wybrać inną propozycję
    const [, la, lo] = x.punkty[0];
    gps.punkt = [la, lo];
    const m = L.marker([la, lo], {draggable: true, autoPan: true}).addTo(gps.warstwy);
    m.bindTooltip("Propozycja — przeciągnij, jeśli trzeba poprawić", {direction: "top"});
    m.on("dragend", () => { const p = m.getLatLng(); gps.punkt = [p.lat, p.lng]; });
    for (const [ala, alo, p] of x.alternatywy || []) {
      L.circleMarker([ala, alo], {radius: 7, color: "#64748b", fillColor: "#94a3b8", fillOpacity: 0.8, weight: 2})
        .bindTooltip(`Inna możliwość (~${Math.round(p * 100)}%) — kliknij, aby wybrać`, {direction: "top"})
        .on("click", () => { m.setLatLng([ala, alo]); gps.punkt = [ala, alo]; }).addTo(gps.warstwy);
      granice.push([ala, alo]);
    }
    granice.push([la, lo]);
  } else {
    for (const [id, la, lo] of x.punkty) {
      L.circleMarker([la, lo], {radius: 6, color: "#fff", weight: 2, fillColor: "#7354f0", fillOpacity: 1})
        .bindTooltip(`<img src="${miniatura(id, false)}" style="width:120px;height:90px;object-fit:cover;border-radius:6px">`, {direction: "top"})
        .addTo(gps.warstwy);
      granice.push([la, lo]);
    }
  }
  if (granice.length) gps.mapa.fitBounds(L.latLngBounds(granice).pad(0.25), {maxZoom: x.typ === "geoclip" ? 9 : 16});
}

function usunGps(x) {
  const i = gps.grupy.indexOf(x);
  if (i >= 0) gps.grupy.splice(i, 1);
  gps.razem = Math.max(0, gps.razem - 1);
  if (gps.wybrana === x) gps.wybrana = null;
  rysujGpsGrupy();
  const nast = gps.grupy[Math.min(i, gps.grupy.length - 1)];
  if (nast) wybierzGps(nast); else if (gps.warstwy) gps.warstwy.clearLayers();
}

async function przyjmijGps(x) {
  // punkty z tą samą pozycją zapisujemy razem; GeoCLIP — jeden (być może przesunięty) punkt dla całej grupy
  const porcje = new Map();
  for (const [id, la, lo] of x.punkty) {
    const [pla, plo] = x.jeden_punkt && gps.wybrana === x && gps.punkt ? gps.punkt : [la, lo];
    const k = `${pla.toFixed(5)},${plo.toFixed(5)}`;
    if (!porcje.has(k)) porcje.set(k, {la: +pla.toFixed(6), lo: +plo.toFixed(6), ids: []});
    porcje.get(k).ids.push(id);
  }
  const ids = x.ids.slice();
  usunGps(x);
  let ok = 0;
  await zadanieTla("📍 Lokalizacja z propozycji", ids.length, async postep => {
    let n = 0;
    for (const p of porcje.values()) {
      if (await ustawLokalizacje(p.ids, p.la, p.lo, null, true)) ok += p.ids.length;
      n += p.ids.length; postep(n);
    }
    try { await post("/api/g/gps/przyjete", {ids}); } catch (e) { /* zniknie przy kolejnym szukaniu */ }
  });
  if (ok) toastG(`📍 Zapisano lokalizację: ${gpsZdjec(ok)}`, async () => {
    await ustawLokalizacje(ids, null, null, null, true);
    toastG("↶ Usunięto dodaną lokalizację — zdjęcia wrócą przy kolejnym szukaniu propozycji");
  });
}
