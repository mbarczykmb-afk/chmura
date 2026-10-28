// Ślad trasy na mapie wyprawy: odcinki z prawdziwym śladem GPS rysujemy linią ciągłą, a miejsca, w których ślad się urywa
// (Google zapisał tylko początek i koniec przejazdu) — linią przerywaną, żeby prosta kreska nie udawała drogi.
// Opcjonalnie („Wyznacz drogi”) luki są dociągane po drogach z publicznego routera OpenStreetMap (wysyła tylko współrzędne
// końców luki, po wyraźnej zgodzie; wyniki zapamiętuje w przeglądarce).
"use strict";
(function () {
  const PROG_LUKI_KM = 1.5, PROG_LOTU_KM = 150, MAKS_DROG = 60;
  const ZGODA = 'podroze_drogi_zgoda', PAMIEC = 'podroze_drogi:';
  let warstwy = [], kontrolka = null, luki = [], droga = [], licznikRysunku = 0, jestSlad = false;
  const slady = new Map();   // id wyprawy → obietnica z śladami Strava / Intervals.icu (slady.py)
  const nazwaPliku = (id) => String(id).replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 100);
  const KOLORY = { rower: '#facc15', narty: '#e0f2fe', plyw: '#38bdf8', inne: '#fb923c' };
  const rodzaj = (typ) => /ride|bike|cycl|rower/i.test(typ) ? 'rower' : /ski|snow/i.test(typ) ? 'narty' : /swim|kayak|row|paddle/i.test(typ) ? 'plyw' : 'inne';

  const km = (a, b) => {
    const r = Math.PI / 180, dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  };
  const lsGet = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* pełna pamięć — trasa po prostu nie zostanie zapamiętana */ } };

  function punkty(trip, dzien) {
    const wynik = [];
    for (const d of (trip.days || [])) {
      if (dzien !== 'all' && d.dayNumber !== parseInt(dzien, 10)) continue;
      for (const p of (d.path || [])) {
        if (!Array.isArray(p) || !isFinite(p[0]) || !isFinite(p[1]) || (!p[0] && !p[1])) continue;
        const o = wynik[wynik.length - 1];
        if (!o || o[0] !== p[0] || o[1] !== p[1]) wynik.push([p[0], p[1]]);
      }
    }
    return wynik;
  }
  function podziel(pkt) {
    const slady = [], przerwy = [];
    let biezacy = pkt.length ? [pkt[0]] : [];
    for (let i = 1; i < pkt.length; i++) {
      const d = km(pkt[i - 1], pkt[i]);
      if (d > PROG_LUKI_KM) {
        if (biezacy.length > 1) slady.push(biezacy);
        przerwy.push({ a: pkt[i - 1], b: pkt[i], km: d, lot: d >= PROG_LOTU_KM });
        biezacy = [pkt[i]];
      } else biezacy.push(pkt[i]);
    }
    if (biezacy.length > 1) slady.push(biezacy);
    return { slady, przerwy };
  }

  const klucz = (l) => PAMIEC + [l.a[0], l.a[1], l.b[0], l.b[1]].map(v => v.toFixed(4)).join(',');
  function zapamietana(l) {
    const t = lsGet(klucz(l)); if (!t) return null;
    try { return JSON.parse(t); } catch (e) { return null; }
  }

  function czysc(mapa) {
    warstwy.forEach(w => { if (mapa) mapa.removeLayer(w); });
    warstwy = []; luki = []; droga = []; jestSlad = false;
    if (kontrolka && mapa) { mapa.removeControl(kontrolka); }
    kontrolka = null;
  }

  function rysujPrzerwy(mapa) {
    warstwy.filter(w => w._np === 'przerwa').forEach(w => { mapa.removeLayer(w); });
    warstwy = warstwy.filter(w => w._np !== 'przerwa');
    for (const l of luki) {
      let w;
      const z = !l.lot && zapamietana(l);
      if (z && z.length > 1) w = L.polyline(z, { color: '#38bdf8', weight: 3, opacity: 0.85, lineCap: 'round', lineJoin: 'round' });
      else w = L.polyline([l.a, l.b], l.lot
        ? { color: '#a78bfa', weight: 2, opacity: 0.85, dashArray: '2 9', lineCap: 'round' }
        : { color: '#94a3b8', weight: 2, opacity: 0.85, dashArray: '5 8' });
      w._np = 'przerwa';
      w.bindTooltip(l.lot ? `✈ Przelot ~${Math.round(l.km)} km (bez śladu)` : z ? `🛣 Trasa po drogach ~${l.km.toFixed(1)} km (szacunek)` : `Brak śladu GPS ~${l.km.toFixed(1)} km (linia prosta)`, { sticky: true });
      w.addTo(mapa); warstwy.push(w);
    }
  }

  function legenda(mapa) {
    const kon = L.control({ position: 'bottomleft' });
    kon.onAdd = () => {
      const d = L.DomUtil.create('div', 'np-trasa-leg'); L.DomEvent.disableClickPropagation(d);
      const doDrog = luki.filter(l => !l.lot && !zapamietana(l)).length;
      d.innerHTML =
        `<div><span class="np-lin" style="border-color:#00f0ff"></span>ślad GPS</div>` +
        `<div><span class="np-lin" style="border-top-style:dashed;border-color:#94a3b8"></span>brak śladu (linia prosta)</div>` +
        (luki.some(l => l.lot) ? `<div><span class="np-lin" style="border-top-style:dotted;border-color:#a78bfa"></span>przelot</div>` : '') +
        (jestSlad ? `<div><span class="np-lin" style="border-color:#fb923c"></span>ślad ze Stravy / Intervals.icu</div>` : '') +
        (luki.some(l => !l.lot && zapamietana(l)) ? `<div><span class="np-lin" style="border-color:#38bdf8"></span>trasa po drogach (szacunek)</div>` : '') +
        (doDrog ? `<button type="button" id="np-drogi">🛣 Wyznacz drogi (${Math.min(doDrog, MAKS_DROG)})</button><small>Pyta publiczny router OpenStreetMap o drogę między końcami luk — wysyła tylko te współrzędne.</small>` : '');
      const b = d.querySelector('#np-drogi'); if (b) b.addEventListener('click', () => wyznacz(mapa, b));
      return d;
    };
    kon.addTo(mapa); kontrolka = kon;
  }

  async function wyznaczJedna(l) {
    const profil = l.km <= 5 ? ['routed-foot', 'foot'] : ['routed-car', 'driving'];
    const url = `https://routing.openstreetmap.de/${profil[0]}/route/v1/${profil[1]}/${l.a[1]},${l.a[0]};${l.b[1]},${l.b[0]}?overview=full&geometries=geojson`;
    const ac = new AbortController(), t = setTimeout(() => ac.abort(), 9000);
    try {
      const r = await fetch(url, { signal: ac.signal }); if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      const c = j.routes && j.routes[0] && j.routes[0].geometry && j.routes[0].geometry.coordinates;
      if (!c || c.length < 2) throw new Error('brak trasy');
      const krok = Math.max(1, Math.floor(c.length / 400));
      const pkt = c.filter((_, i) => i % krok === 0 || i === c.length - 1).map(([lo, la]) => [+la.toFixed(5), +lo.toFixed(5)]);
      lsSet(klucz(l), JSON.stringify(pkt));
      return true;
    } finally { clearTimeout(t); }
  }

  async function wyznacz(mapa, przycisk) {
    if (lsGet(ZGODA) !== '1') {
      const ok = window.confirm('Wyznaczenie dróg wyśle do publicznego routera OpenStreetMap (routing.openstreetmap.de) współrzędne początku i końca każdego odcinka bez śladu GPS.\n\nNic więcej (daty, nazwy, zdjęcia) nie jest wysyłane. Kontynuować?');
      if (!ok) return;
      lsSet(ZGODA, '1');
    }
    const lista = luki.filter(l => !l.lot && !zapamietana(l)).slice(0, MAKS_DROG);
    let zrobione = 0, bledy = 0;
    przycisk.disabled = true;
    const kolejka = lista.slice();
    const pracownik = async () => {
      while (kolejka.length) {
        const l = kolejka.shift();
        try { await wyznaczJedna(l); } catch (e) { bledy++; }
        zrobione++; przycisk.textContent = `⏳ ${zrobione} z ${lista.length}…`;
      }
    };
    await Promise.all([pracownik(), pracownik(), pracownik()]);
    if (kontrolka) { mapa.removeControl(kontrolka); kontrolka = null; }
    rysujPrzerwy(mapa); legenda(mapa);
    if (bledy && typeof showToast === 'function') showToast(`🛣 Nie udało się wyznaczyć ${bledy} z ${lista.length} odcinków (brak sieci lub drogi).`);
  }

  function odlegloscDoSladu(pt, tracks) {
    let naj = Infinity;
    for (const t of tracks) for (const p of t.pts) { const d = km(pt, p); if (d < naj) naj = d; if (naj < 0.05) return naj; }
    return naj;
  }

  // Ślady ze Stravy / Intervals.icu: rysowane na wierzchu; luka, której oba końce leżą przy takim śladzie, przestaje być „linią prostą”.
  function dolozSlady(mapa, trip, dzien, numer) {
    if (!trip || trip.id === undefined) return;
    if (!slady.has(trip.id)) {
      slady.set(trip.id, fetch('slady/' + encodeURIComponent(nazwaPliku(trip.id)) + '.json', { cache: 'no-cache' })
        .then(r => r.ok ? r.json() : null).then(d => (d && Array.isArray(d.aktywnosci)) ? d.aktywnosci : null).catch(() => null));
    }
    slady.get(trip.id).then((akt) => {
      if (numer !== licznikRysunku || !akt || !akt.length) return;   // użytkownik przeszedł już dalej
      const d = dzien === 'all' ? null : (trip.days || []).find(x => x.dayNumber === parseInt(dzien, 10));
      const wybrane = akt.filter(a => !d || String(a.start || '').slice(0, 10) === String(d.date || '').slice(0, 10));
      if (!wybrane.length) return;
      for (const a of wybrane) {
        const pts = (a.pts || []).map(p => [p[0], p[1]]);
        if (pts.length < 2) continue;
        const kolor = KOLORY[rodzaj(a.typ)];
        const obrys = L.polyline(pts, { color: '#020617', weight: 7, opacity: 0.5, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(mapa);
        const linia = L.polyline(pts, { color: kolor, weight: 3.5, opacity: 0.95, lineCap: 'round', lineJoin: 'round' }).addTo(mapa);
        const nazwa = String(a.nazwa || 'Aktywność').replace(/</g, '&lt;');
        linia.bindTooltip(`${nazwa} · ${a.typ || ''} · ${a.km || 0} km<br><small>${a.zrodlo === 'strava' ? 'Strava' : 'Intervals.icu'}</small>`, { sticky: true });
        obrys._np = linia._np = 'aktywnosc'; warstwy.push(obrys, linia);
      }
      jestSlad = true;
      const przed = luki.length;
      luki = luki.filter(l => l.lot || !(odlegloscDoSladu(l.a, wybrane) < 0.3 && odlegloscDoSladu(l.b, wybrane) < 0.3));
      if (kontrolka) { mapa.removeControl(kontrolka); kontrolka = null; }
      if (luki.length !== przed) rysujPrzerwy(mapa);
      legenda(mapa);
    });
  }

  // Rysuje trasę wyprawy (lub jednego dnia). Zwraca false, gdy wyprawa nie ma śladu z dni — wtedy rysuje stara metoda
  // (ślady ze Stravy / Intervals.icu i tak zostaną dołożone, jeśli są pobrane).
  function rysuj(mapa, trip, dzien) {
    czysc(mapa);
    const numer = ++licznikRysunku;
    const pkt = punkty(trip, dzien);
    let narysowano = false;
    if (pkt.length >= 2) {
      const { slady: sl, przerwy } = podziel(pkt);
      luki = przerwy;
      for (const s of sl) {
        const w = L.polyline(s, { color: '#00f0ff', weight: 3.5, opacity: 0.9, lineCap: 'round', lineJoin: 'round' }).addTo(mapa);
        w._np = 'slad'; warstwy.push(w);
      }
      rysujPrzerwy(mapa);
      legenda(mapa);
      narysowano = true;
    }
    dolozSlady(mapa, trip, dzien, numer);
    return narysowano;
  }
  window.trasaPodrozy = { rysuj, czysc, _podziel: podziel, _punkty: punkty };
})();
