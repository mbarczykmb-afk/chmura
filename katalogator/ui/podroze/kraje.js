// Mapa państw: odwiedzone państwa na mapie świata z liczbą wycieczek; kliknięcie filtruje katalog.
// Państwo wyprawy wyznaczamy ze współrzędnych jej miejsc (granice: kraje.json, Natural Earth — domena publiczna).
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  let poligony = null;       // [{a2, n, lx, ly, bbox, wielokaty}]
  let mapa = null, warstwa = null, znaczniki = [], liczniki = new Map(), wybrane = null, wszystkie = [];

  const nazwaPL = (a2, zapas) => { try { return new Intl.DisplayNames(['pl'], { type: 'region' }).of(a2) || zapas; } catch (e) { return zapas || a2; } };
  const wycieczek = (n) => `${n} ${n === 1 ? 'wycieczka' : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 'wycieczki' : 'wycieczek'}`;

  function wPierscieniu(lon, lat, pierscien) {
    let w = false;
    for (let i = 0, j = pierscien.length - 1; i < pierscien.length; j = i++) {
      const [xi, yi] = pierscien[i], [xj, yj] = pierscien[j];
      if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) w = !w;
    }
    return w;
  }
  function wielokaty(g) { return g.type === 'Polygon' ? [g.coordinates] : g.coordinates; }
  function przygotuj(dane) {
    poligony = dane.features.map(f => {
      const w = wielokaty(f.geometry);
      const bb = w.map(p => { const o = p[0]; let a = 180, b = 90, c = -180, d = -90; for (const [x, y] of o) { if (x < a) a = x; if (x > c) c = x; if (y < b) b = y; if (y > d) d = y; } return [a, b, c, d]; });
      return { a2: f.properties.a2, n: f.properties.n, lx: f.properties.lx, ly: f.properties.ly, bb, w, f };
    });
  }
  function krajPunktu(lat, lon) {
    if (!poligony) return null;
    for (const k of poligony) {
      for (let i = 0; i < k.w.length; i++) {
        const [a, b, c, d] = k.bb[i];
        if (lon < a || lon > c || lat < b || lat > d) continue;
        const p = k.w[i];
        if (wPierscieniu(lon, lat, p[0]) && !p.slice(1).some(o => wPierscieniu(lon, lat, o))) return k.a2;
      }
    }
    return null;
  }
  // państwa wyprawy: z miejsc (bez lotnisk), te, w których jest ≥ 12% miejsc; zawsze przynajmniej jedno
  function krajeTripu(trip) {
    if (trip._kraje) return trip._kraje;
    if (!poligony) return [];
    const m = (trip.events || []).filter(e => e.type === 'place' && e.category !== 'airport' && isFinite(e.lat) && isFinite(e.lon) && (e.lat || e.lon));
    const krok = Math.max(1, Math.floor(m.length / 80)), licz = new Map();
    let razem = 0;
    for (let i = 0; i < m.length; i += krok) {
      const a2 = krajPunktu(m[i].lat, m[i].lon); razem++;
      if (a2) licz.set(a2, (licz.get(a2) || 0) + 1);
    }
    const posort = [...licz.entries()].sort((a, b) => b[1] - a[1]);
    trip._kraje = posort.filter(([, n], i) => i === 0 || n >= razem * 0.12).map(([a2]) => a2);
    return trip._kraje;
  }

  const barwaLicz = (n) => n >= 8 ? '#5eead4' : n >= 4 ? '#14b8a6' : n >= 2 ? '#0f766e' : '#134e4a';

  function przelicz() {
    liczniki = new Map();
    for (const t of wszystkie) for (const a2 of krajeTripu(t)) liczniki.set(a2, (liczniki.get(a2) || 0) + 1);
  }
  function styl(a2) {
    const n = liczniki.get(a2) || 0, wyb = wybrane === a2;
    if (!n) return { fillColor: '#94a3b8', fillOpacity: 0.14, color: '#64748b', weight: 0.5, opacity: 0.6 };
    return { fillColor: barwaLicz(n), fillOpacity: 0.92, color: wyb ? '#ffffff' : '#99f6e4', weight: wyb ? 2.4 : 0.8, opacity: 1 };
  }

  function rysujMape() {
    const pole = $('kraje-mapa');
    if (!pole || !poligony || typeof L === 'undefined') return;
    if (!mapa) {
      mapa = L.map(pole, { crs: L.CRS.EPSG4326, zoomControl: true, attributionControl: false, worldCopyJump: false, minZoom: 0, maxZoom: 8, zoomSnap: 0.25, zoomDelta: 0.5,
                           maxBounds: [[-70, -200], [88, 200]], maxBoundsViscosity: 0.8 });
      warstwa = L.geoJSON({ type: 'FeatureCollection', features: poligony.map(k => k.f) }, {
        style: (f) => styl(f.properties.a2),
        onEachFeature: (f, sl) => {
          sl.on('click', () => { if (liczniki.get(f.properties.a2)) wybierz(wybrane === f.properties.a2 ? null : f.properties.a2); });
          sl.on('mouseover', () => { if (liczniki.get(f.properties.a2)) sl.setStyle({ weight: 2, color: '#fff' }); });
          sl.on('mouseout', () => sl.setStyle(styl(f.properties.a2)));
        }
      }).addTo(mapa);
      mapa.invalidateSize(); pokazOdwiedzone();
    }
    warstwa.setStyle((f) => styl(f.properties.a2));
    warstwa.eachLayer(sl => {
      const a2 = sl.feature.properties.a2, n = liczniki.get(a2) || 0, p = poligony.find(k => k.a2 === a2);
      sl.unbindTooltip();
      if (n) { sl.bindTooltip(`${nazwaPL(a2, p && p.n)} · ${wycieczek(n)}`, { sticky: true }); sl.getElement && sl.getElement() && sl.getElement().style.setProperty('cursor', 'pointer'); }
      else sl.bindTooltip(nazwaPL(a2, p && p.n), { sticky: true });
    });
    znaczniki.forEach(z => mapa.removeLayer(z)); znaczniki = [];
    for (const [a2, n] of liczniki) {
      const p = poligony.find(k => k.a2 === a2); if (!p) continue;
      znaczniki.push(L.marker([p.ly, p.lx], { interactive: false, keyboard: false, zIndexOffset: 500,
        icon: L.divIcon({ className: '', html: `<div class="np-kraj-licz">${n}</div>`, iconSize: [24, 20], iconAnchor: [12, 10] }) }).addTo(mapa));
    }
    listaKraje();
    const opis = $('kraje-opis');
    if (opis) opis.textContent = liczniki.size ? `${liczniki.size} ${liczniki.size === 1 ? 'państwo' : 'państw'} · kliknij, aby pokazać tylko jego wycieczki` : 'Brak współrzędnych miejsc w wyprawach';
    setTimeout(() => mapa && mapa.invalidateSize(), 100);
  }
  function listaKraje() {
    const ul = $('kraje-lista'); if (!ul) return;
    const wiersze = [...liczniki.entries()].map(([a2, n]) => ({ a2, n, nazwa: nazwaPL(a2, (poligony.find(k => k.a2 === a2) || {}).n) }))
      .sort((x, y) => y.n - x.n || x.nazwa.localeCompare(y.nazwa, 'pl'));
    ul.replaceChildren(...wiersze.map(w => {
      const li = document.createElement('li'), b = document.createElement('button');
      b.type = 'button'; b.setAttribute('aria-pressed', String(wybrane === w.a2)); b.title = `${w.nazwa} — ${wycieczek(w.n)}`;
      b.innerHTML = `<span class="np-kod">${w.a2}</span><span class="np-nazwa"></span><span class="np-n">${w.n}</span>`;
      b.querySelector('.np-nazwa').textContent = w.nazwa;
      b.onclick = () => wybierz(wybrane === w.a2 ? null : w.a2);
      li.append(b); return li;
    }));
  }
  function pokazSwiat() { if (mapa) { mapa.invalidateSize(); mapa.fitBounds([[-56, -175], [80, 178]], { animate: false }); } }
  function pokazOdwiedzone() {
    if (!mapa) return;
    const pkt = []; for (const a2 of liczniki.keys()) { const p = poligony.find(k => k.a2 === a2); if (p) pkt.push([p.ly, p.lx]); }
    if (!pkt.length) { pokazSwiat(); return; }
    mapa.invalidateSize();
    mapa.fitBounds(L.latLngBounds(pkt).pad(0.3), { maxZoom: 5, animate: false });
  }

  function wybierz(a2) {
    wybrane = a2;
    const f = $('kraje-filtr');
    if (f) {
      f.hidden = !a2;
      if (a2) { const p = poligony.find(k => k.a2 === a2); $('kraje-filtr-nazwa').textContent = `${nazwaPL(a2, p && p.n)} · ${liczniki.get(a2) || 0}`; }
    }
    if (warstwa) warstwa.setStyle((x) => styl(x.properties.a2));
    listaKraje();
    if (typeof renderCatalogGrid === 'function') renderCatalogGrid();
  }

  // wywoływane z app.js po przeliczeniu katalogu
  function po(trips) {
    if (trips !== wszystkie) { wszystkie = trips || []; if (poligony) przelicz(); }
    if (poligony) rysujMape();
  }
  window.kraje = {
    krajeTripu, po,
    filtr: (trip) => !wybrane || krajeTripu(trip).includes(wybrane),
    wyczysc: () => wybierz(null)
  };

  const x = $('kraje-filtr-x'); if (x) x.onclick = () => wybierz(null);
  const b1 = $('kraje-odwiedzone'); if (b1) b1.onclick = pokazOdwiedzone;
  const b2 = $('kraje-swiat'); if (b2) b2.onclick = pokazSwiat;

  fetch('kraje.json').then(r => r.json()).then(d => {
    przygotuj(d);
    if (typeof renderCatalogGrid === 'function' && typeof detectedTrips !== 'undefined' && detectedTrips.length) renderCatalogGrid();
  }).catch(() => { const o = $('kraje-opis'); if (o) o.textContent = 'Nie udało się wczytać granic państw'; });
})();
