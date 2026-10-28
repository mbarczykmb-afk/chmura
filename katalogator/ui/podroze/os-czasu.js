// Oś czasu wypraw: wszystkie wyprawy na jednej przewijanej osi (lata, miesiące), kliknięcie otwiera wyprawę.
// Wyprawy spoza bieżącego filtru (rok, szukanie, państwo) są przygaszone.
"use strict";
(function () {
  const DZIEN = 86400000, WIERSZ = 24, GORA = 4, OS = 28;
  const SKALE = [0.18, 0.3, 0.55, 0.9, 1.6, 3];
  let skala = 4, dane = null, pierwszy = true;

  const $ = (id) => document.getElementById(id);
  const krotki = (t) => String(t || '').replace(/\s*\([^()]*\d{4}\)\s*$/, '').trim();
  const barwa = (trip) => {
    const k = window.kraje && window.kraje.krajeTripu ? window.kraje.krajeTripu(trip) : [];
    if (!k.length) return 'hsl(172 70% 32%)';
    let h = 0; for (const c of k[0]) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${(h * 7) % 360} 55% 38%)`;
  };

  function rysuj(wszystkie, widoczne, otworz) {
    dane = { wszystkie, widoczne, otworz };
    const sekcja = $('os-czasu'), tor = $('os-czasu-tor'), przew = $('os-czasu-przew');
    if (!sekcja || !tor) return;
    const lista = (wszystkie || []).filter(t => t.startDate instanceof Date && !isNaN(t.startDate));
    sekcja.hidden = lista.length === 0;
    if (!lista.length) return;

    const ppd = SKALE[skala];
    const min = Math.min(...lista.map(t => +t.startDate)), maks = Math.max(...lista.map(t => +(t.endDate || t.startDate)));
    const rokOd = new Date(min).getFullYear(), rokDo = new Date(maks).getFullYear();
    const poczatek = new Date(rokOd, 0, 1).getTime(), koniec = new Date(rokDo + 1, 0, 1).getTime();
    const x = (ms) => Math.round((ms - poczatek) / DZIEN * ppd) + 10;
    const szer = x(koniec) + 30;

    const widz = new Set(widoczne || []);
    const wolne = [];   // koniec ostatniej wyprawy w wierszu (px)
    const kolejne = lista.map((t, i) => ({ t, i })).sort((a, b) => a.t.startDate - b.t.startDate);
    const html = [];
    for (const { t } of kolejne) {
      const l = x(+t.startDate);
      const w = Math.max(9, Math.round((((+(t.endDate || t.startDate)) - +t.startDate) / DZIEN + 1) * ppd));
      const nazwa = krotki(t.title), et = nazwa.length > 24 ? nazwa.slice(0, 23) + '…' : nazwa;
      const zajete = w + 6 + Math.round(et.length * 6.3);   // kropka + podpis obok, żeby się nie nakładały
      let wiersz = wolne.findIndex(k => k + 6 < l);
      if (wiersz < 0) { wiersz = wolne.length; wolne.push(0); }
      wolne[wiersz] = l + zajete;
      const okres = `${t.startDate.toLocaleDateString('pl-PL')} – ${(t.endDate || t.startDate).toLocaleDateString('pl-PL')}`;
      const idx = lista.indexOf(t);
      html.push(`<button class="np-os-wyp${widz.has(t) ? '' : ' np-przygas'}" data-i="${idx}" style="left:${l}px;top:${GORA + wiersz * WIERSZ}px;width:${zajete}px" ` +
        `title="${nazwa.replace(/"/g, '&quot;')} · ${okres}"><i style="width:${w}px;background:${barwa(t)}"></i><span>${et.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</span></button>`);
    }
    const wys = GORA + Math.max(1, wolne.length) * WIERSZ + OS;
    let osie = '';
    for (let r = rokOd; r <= rokDo + 1; r++) {
      osie += `<div class="np-os-rok" style="left:${x(new Date(r, 0, 1).getTime())}px"><span>${r}</span></div>`;
      if (ppd >= 0.9 && r <= rokDo) for (let m = 1; m < 12; m++) osie += `<div class="np-os-msc" style="left:${x(new Date(r, m, 1).getTime())}px"></div>`;
    }
    tor.style.width = szer + 'px'; tor.style.height = wys + 'px';
    tor.innerHTML = osie + html.join('');
    tor.querySelectorAll('.np-os-wyp').forEach(b => b.addEventListener('click', () => {
      if (przew._przeciagnieto) return;
      const t = lista[+b.dataset.i];
      if (otworz) otworz(dane.wszystkie.indexOf(t));
    }));
    const n = widz.size;
    $('os-czasu-opis').textContent = `${n === lista.length ? lista.length + ' wypraw' : n + ' z ' + lista.length + ' wypraw'} · ${rokOd}–${rokDo} · kliknij wyprawę, aby ją otworzyć`;
    if (pierwszy) { pierwszy = false; przew.scrollLeft = przew.scrollWidth; }
  }

  function przesun(kierunek) { const p = $('os-czasu-przew'); if (p) p.scrollBy({ left: kierunek * p.clientWidth * 0.7, behavior: 'smooth' }); }
  function zmienSkale(d) {
    const n = Math.max(0, Math.min(SKALE.length - 1, skala + d));
    if (n === skala || !dane) return;
    const p = $('os-czasu-przew'), srodek = (p.scrollLeft + p.clientWidth / 2) / SKALE[skala];
    skala = n; rysuj(dane.wszystkie, dane.widoczne, dane.otworz);
    p.scrollLeft = srodek * SKALE[skala] - p.clientWidth / 2;
  }

  const p = $('os-czasu-przew');
  if (p) {
    $('os-czasu-lewo').onclick = () => przesun(-1);
    $('os-czasu-prawo').onclick = () => przesun(1);
    $('os-czasu-oddal').onclick = () => zmienSkale(-1);
    $('os-czasu-przybliz').onclick = () => zmienSkale(1);
    $('os-czasu-teraz').onclick = () => p.scrollTo({ left: p.scrollWidth, behavior: 'smooth' });
    let start = null;   // przeciąganie osi myszą
    p.addEventListener('pointerdown', (e) => { if (e.button === 0 && !e.target.closest('.np-os-wyp')) start = { x: e.clientX, l: p.scrollLeft }; });
    window.addEventListener('pointermove', (e) => {
      if (!start) return;
      const dx = e.clientX - start.x;
      if (Math.abs(dx) > 3) { p._przeciagnieto = true; p.classList.add('np-chwyt'); }
      p.scrollLeft = start.l - dx;
    });
    window.addEventListener('pointerup', () => { start = null; p.classList.remove('np-chwyt'); setTimeout(() => { p._przeciagnieto = false; }, 0); });
  }
  window.osCzasu = { rysuj, odswiez: () => dane && rysuj(dane.wszystkie, dane.widoczne, dane.otworz) };
})();
