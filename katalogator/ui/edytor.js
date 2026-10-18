// ✏ Edytor zdjęć w Przeglądarce: obrót, przycięcie, jasność, kontrast, nasycenie, balans bieli.
// Podgląd liczony tutaj (canvas), zapis — przez program na pełnej rozdzielczości (katalogator/edycja.py, te same wzory).
"use strict";

const ED_SUWAKI = [["jasnosc", "☀ Jasność"], ["kontrast", "◑ Kontrast"], ["nasycenie", "🎨 Nasycenie"],
                   ["temperatura", "🌡 Balans bieli: zimno ↔ ciepło"], ["odcien", "Odcień: zieleń ↔ purpura"]];
const ed = {p: null, img: null, geo: null, op: null, tnie: false, prop: 0, przed: false, rys: 0, ciag: null};
const edPuste = () => ({obrot: 0, lustro: false, ciecie: null, jasnosc: 0, kontrast: 0, nasycenie: 0, temperatura: 0, odcien: 0});
const edZmiany = op => !!(op.obrot || op.lustro || op.ciecie || ED_SUWAKI.some(([k]) => op[k]));

// krzywe R, G, B — jak edycja.lut(): balans bieli → jasność (gamma) → kontrast
function edLut(op) {
  const t = op.temperatura / 100, n = op.odcien / 100, gamma = 2 ** (-op.jasnosc / 100), k = 1 + op.kontrast / 100;
  return [1 + 0.25 * t, 1 - 0.2 * n, 1 - 0.25 * t].map(w => {
    const l = new Uint8ClampedArray(256);
    for (let i = 0; i < 256; i++) {
      let v = Math.min(255, i * w);
      v = 255 * (v / 255) ** gamma;
      l[i] = Math.round((v - 128) * k + 128);
    }
    return l;
  });
}
function edFiltr(dane, op) {
  const d = dane.data, [lr, lg, lb] = edLut(op), s = 1 + op.nasycenie / 100;
  for (let i = 0; i < d.length; i += 4) {
    let r = lr[d[i]], gg = lg[d[i + 1]], b = lb[d[i + 2]];
    if (s !== 1) {  // jak PIL ImageEnhance.Color: szarość + (kolor − szarość) × s
      const y = (r * 299 + gg * 587 + b * 114) / 1000;
      r = y + (r - y) * s; gg = y + (gg - y) * s; b = y + (b - y) * s;
    }
    d[i] = r; d[i + 1] = gg; d[i + 2] = b;  // Uint8ClampedArray: przycina i zaokrągla
  }
  return dane;
}

// obraz po obrocie i odbiciu (zmniejszony do podglądu)
function edGeometria() {
  const im = ed.img, o = ed.op.obrot, bok = 1400;
  const sk = Math.min(1, bok / Math.max(im.naturalWidth, im.naturalHeight));
  const w = Math.round(im.naturalWidth * sk), h = Math.round(im.naturalHeight * sk);
  const c = document.createElement("canvas");
  [c.width, c.height] = o % 180 ? [h, w] : [w, h];
  const x = c.getContext("2d");
  x.translate(c.width / 2, c.height / 2);
  if (ed.op.lustro) x.scale(-1, 1);
  x.rotate(o * Math.PI / 180);
  x.drawImage(im, -w / 2, -h / 2, w, h);
  ed.geo = c;
}
function edRysuj() {
  cancelAnimationFrame(ed.rys);
  ed.rys = requestAnimationFrame(() => {
    if (!ed.geo) return;
    const G = ed.geo, c = ed.tnie || !ed.op.ciecie ? [0, 0, 1, 1] : ed.op.ciecie;
    const sx = Math.round(c[0] * G.width), sy = Math.round(c[1] * G.height);
    const sw = Math.max(1, Math.round(c[2] * G.width) - sx), sh = Math.max(1, Math.round(c[3] * G.height) - sy);
    const pl = $("ed-plotno"); pl.width = sw; pl.height = sh;
    const sc = $("ed-scena"), st = getComputedStyle(sc);  // zmieść w scenie (CSS max-height nie działa w siatce)
    const mw = sc.clientWidth - parseFloat(st.paddingLeft) - parseFloat(st.paddingRight);
    const mh = sc.clientHeight - parseFloat(st.paddingTop) - parseFloat(st.paddingBottom);
    const sk = Math.min(mw / sw, mh / sh);
    pl.style.width = `${Math.floor(sw * sk)}px`; pl.style.height = `${Math.floor(sh * sk)}px`;
    const x = pl.getContext("2d", {willReadFrequently: true});
    x.drawImage(G, sx, sy, sw, sh, 0, 0, sw, sh);
    if (!ed.przed && ED_SUWAKI.some(([k]) => ed.op[k])) x.putImageData(edFiltr(x.getImageData(0, 0, sw, sh), ed.op), 0, 0);
    edRamka();
    $("ed-zapisz").disabled = !edZmiany(edOp());
  });
}
// ramka przycinania nad podglądem (w trybie ✂ widać całe zdjęcie)
function edRamka() {
  const r = $("ed-ramka"); r.hidden = !ed.tnie;
  if (!ed.tnie) return;
  const c = ed.op.ciecie || [0, 0, 1, 1], pl = $("ed-plotno").getBoundingClientRect(), sc = $("ed-scena").getBoundingClientRect();
  Object.assign(r.style, {left: `${pl.left - sc.left + c[0] * pl.width}px`, top: `${pl.top - sc.top + c[1] * pl.height}px`,
                          width: `${(c[2] - c[0]) * pl.width}px`, height: `${(c[3] - c[1]) * pl.height}px`});
}
const edOp = () => {
  const op = {...ed.op};
  const c = op.ciecie;
  if (c && c[0] <= 0.001 && c[1] <= 0.001 && c[2] >= 0.999 && c[3] >= 0.999) op.ciecie = null;
  return op;
};

function edSuwaki() {
  const box = $("ed-suwaki"); box.replaceChildren();
  for (const [k, t] of ED_SUWAKI) {
    const d = document.createElement("label"); d.className = "ed-s " + k;
    const n = document.createElement("span"); n.textContent = t;
    const o = document.createElement("output"); o.title = "Kliknij — 0";
    const s = document.createElement("input"); s.type = "range"; s.min = -100; s.max = 100; s.value = ed.op[k]; s.id = "ed-" + k;
    const pokaz = () => { o.textContent = (ed.op[k] > 0 ? "+" : "") + ed.op[k]; };
    s.oninput = () => { ed.op[k] = +s.value; pokaz(); edRysuj(); };
    s.ondblclick = o.onclick = e => { e.preventDefault(); ed.op[k] = 0; s.value = 0; pokaz(); edRysuj(); };
    pokaz(); d.append(n, o, s); box.append(d);
  }
}
function edUstawSuwaki() { for (const [k] of ED_SUWAKI) { const s = $("ed-" + k); if (s) { s.value = ed.op[k]; s.oninput(); } } }

function otworzEdytor(p) {
  if (!p || p.rodzaj !== "zdjecie") return;
  stopPokaz();
  Object.assign(ed, {p, op: edPuste(), tnie: false, prop: 0, przed: false, geo: null, img: null});
  $("ed-tyt").textContent = "✏ " + (p.nazwa || "Edycja");
  $("ed-info").textContent = "Wczytuję…"; $("ed-zastap").checked = false; $("ed-zapisz").textContent = "Zapisz kopię";
  $("ed-prop").value = ""; $("ed-proporcje").hidden = true; $("ed-tnij").classList.remove("akt");
  edSuwaki();
  $("ed").hidden = false;
  const im = new Image();
  im.onload = () => {
    if (ed.p !== p) return;
    ed.img = im; edGeometria(); edRysuj();
    $("ed-info").textContent = "Podgląd jest zmniejszony — zapis w pełnej rozdzielczości, z datą i miejscem oryginału.";
  };
  im.onerror = () => { $("ed-info").textContent = "Nie udało się wczytać zdjęcia."; };
  im.src = url("/api/g/podglad", {id: p.id});
}
function zamknijEdytor() { $("ed").hidden = true; ed.p = null; ed.img = ed.geo = null; }

// --- obrót, odbicie (ramka przycięcia obraca się razem ze zdjęciem) ---
function edObroc(wPrawo) {
  // przy odbiciu lustrzanym obrót w danych jest odwrotny, żeby na ekranie zdjęcie kręciło się w stronę strzałki
  const d = (wPrawo ? 90 : 270) * (ed.op.lustro ? -1 : 1);
  ed.op.obrot = ((ed.op.obrot + d) % 360 + 360) % 360;
  const c = ed.op.ciecie;
  if (c) ed.op.ciecie = wPrawo ? [1 - c[3], c[0], 1 - c[1], c[2]] : [c[1], 1 - c[2], c[3], 1 - c[0]];
  edGeometria(); edRysuj();
}
$("ed-lewo").onclick = () => edObroc(false);
$("ed-prawo").onclick = () => edObroc(true);
$("ed-lustro").onclick = () => {
  ed.op.lustro = !ed.op.lustro;
  const c = ed.op.ciecie; if (c) ed.op.ciecie = [1 - c[2], c[1], 1 - c[0], c[3]];
  edGeometria(); edRysuj();
};

// --- przycinanie ---
function edTnij(wlacz) {
  ed.tnie = wlacz; $("ed-tnij").classList.toggle("akt", wlacz); $("ed-proporcje").hidden = !wlacz;
  $("ed-tnij").textContent = wlacz ? "✓ Gotowe" : "✂ Przytnij";
  if (wlacz && !ed.op.ciecie) ed.op.ciecie = [0, 0, 1, 1];
  edRysuj();
}
$("ed-tnij").onclick = () => edTnij(!ed.tnie);
$("ed-tnij-reset").onclick = () => { ed.op.ciecie = [0, 0, 1, 1]; $("ed-prop").value = ""; ed.prop = 0; edRysuj(); };
$("ed-prop").onchange = () => {
  const v = $("ed-prop").value, G = ed.geo; if (!G) return;
  ed.prop = v === "org" ? (ed.img.naturalWidth / ed.img.naturalHeight) : +v || 0;
  if (!ed.prop) return;
  // największy kadr o tych proporcjach, na środku obecnego
  const c = ed.op.ciecie || [0, 0, 1, 1], sx = (c[0] + c[2]) / 2, sy = (c[1] + c[3]) / 2;
  let w = 1, h = w * G.width / (G.height * ed.prop);
  if (h > 1) { h = 1; w = h * G.height * ed.prop / G.width; }
  const x0 = Math.min(Math.max(0, sx - w / 2), 1 - w), y0 = Math.min(Math.max(0, sy - h / 2), 1 - h);
  ed.op.ciecie = [x0, y0, x0 + w, y0 + h]; edRysuj();
};
$("ed-ramka").addEventListener("pointerdown", e => {
  e.preventDefault(); e.stopPropagation();
  $("ed-ramka").setPointerCapture(e.pointerId);
  ed.ciag = {rog: e.target.dataset.r || "", x: e.clientX, y: e.clientY, c: [...ed.op.ciecie]};
});
$("ed-ramka").addEventListener("pointermove", e => {
  const z = ed.ciag; if (!z) return;
  const pl = $("ed-plotno").getBoundingClientRect(), G = ed.geo;
  const dx = (e.clientX - z.x) / pl.width, dy = (e.clientY - z.y) / pl.height, MIN = 0.03;
  let [x0, y0, x1, y1] = z.c;
  if (!z.rog) {  // przesuwanie całej ramki
    const w = x1 - x0, h = y1 - y0;
    x0 = Math.min(Math.max(0, x0 + dx), 1 - w); y0 = Math.min(Math.max(0, y0 + dy), 1 - h);
    ed.op.ciecie = [x0, y0, x0 + w, y0 + h]; edRysuj(); return;
  }
  const lewy = z.rog.includes("w"), gorny = z.rog.includes("n");
  if (lewy) x0 = Math.min(Math.max(0, x0 + dx), x1 - MIN); else x1 = Math.max(Math.min(1, x1 + dx), x0 + MIN);
  if (gorny) y0 = Math.min(Math.max(0, y0 + dy), y1 - MIN); else y1 = Math.max(Math.min(1, y1 + dy), y0 + MIN);
  if (ed.prop) {  // stałe proporcje: wysokość z szerokości (róg naprzeciwko stoi w miejscu)
    let w = x1 - x0, h = w * G.width / (G.height * ed.prop);
    const wolne = gorny ? y1 : 1 - y0;
    if (h > wolne) { h = wolne; w = h * G.height * ed.prop / G.width; }
    if (lewy) x0 = x1 - w; else x1 = x0 + w;
    if (gorny) y0 = y1 - h; else y1 = y0 + h;
  }
  ed.op.ciecie = [x0, y0, x1, y1]; edRysuj();
});
for (const t of ["pointerup", "pointercancel"]) $("ed-ramka").addEventListener(t, () => { ed.ciag = null; });
addEventListener("resize", () => { if (!$("ed").hidden) edRysuj(); });

// --- ✨ Auto: balans bieli (szary świat), jasność do średniej ~46%, kontrast z rozrzutu jasności ---
$("ed-auto").onclick = () => {
  const G = ed.geo; if (!G) return;
  const d = G.getContext("2d").getImageData(0, 0, G.width, G.height).data;
  let r = 0, gg = 0, b = 0, n = 0, l2 = 0;
  for (let i = 0; i < d.length; i += 16) {  // co czwarty piksel wystarczy
    r += d[i]; gg += d[i + 1]; b += d[i + 2]; n++;
    const y = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000; l2 += y * y;
  }
  r /= n; gg /= n; b /= n;
  const sr = (r + gg + b) / 3, ogr = (v, a, z) => Math.round(Math.max(a, Math.min(z, v)));
  ed.op.temperatura = ogr((sr / Math.max(r, 1) - sr / Math.max(b, 1)) * 200, -60, 60);
  ed.op.odcien = ogr((1 - sr / Math.max(gg, 1)) * 500, -40, 40);
  const m = Math.min(0.95, Math.max(0.05, sr / 255)), sd = Math.sqrt(Math.max(0, l2 / n - sr * sr)) / 255;
  ed.op.jasnosc = ogr(-100 * Math.log2(Math.log(0.46) / Math.log(m)), -70, 70);
  ed.op.kontrast = ogr((0.21 / Math.max(sd, 0.05) - 1) * 100, -20, 40);
  ed.op.nasycenie = Math.max(ed.op.nasycenie, 8);
  edUstawSuwaki();
};
$("ed-reset").onclick = () => { ed.op = edPuste(); ed.prop = 0; $("ed-prop").value = ""; edTnij(false); edGeometria(); edUstawSuwaki(); };
const edPrzed = v => { ed.przed = v; edRysuj(); };
$("ed-porownaj").addEventListener("pointerdown", () => edPrzed(true));
for (const t of ["pointerup", "pointerleave", "pointercancel"]) $("ed-porownaj").addEventListener(t, () => { if (ed.przed) edPrzed(false); });
$("ed-zastap").onchange = () => { $("ed-zapisz").textContent = $("ed-zastap").checked ? "Zapisz (zastąp)" : "Zapisz kopię"; };
$("ed-anuluj").onclick = async () => {
  if (edZmiany(edOp()) && !await oknoTak("Porzucić zmiany?")) return;
  zamknijEdytor();
};

// --- zapis ---
$("ed-zapisz").onclick = async () => {
  const p = ed.p, op = edOp(), zastap = $("ed-zastap").checked;
  if (!p || !edZmiany(op)) return;
  const b = $("ed-zapisz"); b.disabled = true; $("ed-info").textContent = "⏳ Zapisuję w pełnej rozdzielczości…";
  let w;
  try { w = await post("/api/g/edytuj", {id: p.id, op, zastap}); }
  catch (e) { $("ed-info").textContent = "Nie zapisano: " + e.message; b.disabled = false; return; }
  zamknijEdytor();
  const nowy = w.plik || {id: w.id, nazwa: w.nazwa, rodzaj: "zdjecie", data: p.data, lat: p.lat, lon: p.lon};
  for (const tab of new Set([g.pliki, g.lista])) {
    const i = tab.indexOf(p); if (i < 0) continue;
    if (zastap) tab[i] = nowy; else tab.splice(i + 1, 0, nowy);
  }
  if (!zastap) g.razem++;
  rysujSiatke();
  const poz = g.lista.indexOf(nowy);
  if (!$("pelny").hidden && poz >= 0) pokazPelny(g.lista, poz);
  toastG(zastap ? `✏ Zapisano zmiany w „${nowy.nazwa}” (oryginał w Odłożone/Usunięte)` : `✏ Zapisano kopię „${nowy.nazwa}”`,
    async () => {
      try {
        const c = await post("/api/g/edytuj/cofnij", {id: nowy.id, partia: w.partia || 0});
        toastG(zastap ? (c.przywrocone ? "Przywrócono oryginał" : "Nie przywrócono: " + (c.bledy || [])[0]) : "Usunięto kopię");
      } catch (e) { toastG(e.message); }
      if (biezacy() === nowy) zamknijPelny();
      wczytajPliki().catch(() => {});
    });
};
$("p-edytuj").onclick = e => { e.stopPropagation(); otworzEdytor(biezacy()); };

// ---------- ✏ hurtem: obrót / odbicie / ✨ Auto dla zaznaczonych — w tle, z paskiem postępu i „Cofnij” ----------
try { $("zz-zastap").checked = localStorage.getItem("kat_zz_zastap") === "1"; } catch (e) { /* bez pamięci */ }
$("zz-zastap").onchange = () => { try { localStorage.setItem("kat_zz_zastap", $("zz-zastap").checked ? "1" : "0"); } catch (e) { /* bez pamięci */ }
                                   $("edycja-zast-cb").checked = $("zz-zastap").checked; };
$("edycja-zast-cb").checked = $("zz-zastap").checked;
$("edycja-btn").hidden = !MOZE_USUWAC;  // tryb edycji — w oknie programu i na telefonie z pilotem
ustawTrybEdycji(trybEdycji());
async function edycjaHurtem(op, nazwa) {
  const lista = zaznaczone().filter(p => p.rodzaj === "zdjecie");
  if (!lista.length) { toastG("Wśród zaznaczonych nie ma zdjęć — filmów nie zmieniam."); return; }
  edycjaPlikow(lista, op, nazwa, true, koniecZazn);
}
// wspólne dla edycji hurtem i szybkiego obrotu na miniaturze (tryb edycji)
async function edycjaPlikow(lista, op, nazwa, pytaj = true, poZgodzie = () => {}) {
  const zastap = $("zz-zastap").checked;
  if (zastap && pytaj && !await oknoTak(`${nazwa}: zastąpić oryginały (${liczbaZdjec(lista.length)})?\n\n` +
                         "Oryginały trafią do kosza programu (Odłożone/Usunięte) — można cofnąć.")) return;
  poZgodzie();
  const zrobione = [];
  zadanieTla(nazwa, lista.length, async postep => {
    const bl = [];
    for (const p of lista) {
      try {
        const w = await post("/api/g/edytuj", {id: p.id, op, zastap});
        const nowy = w.plik || {id: w.id, nazwa: w.nazwa, rodzaj: "zdjecie", data: p.data, lat: p.lat, lon: p.lon};
        for (const tab of new Set([g.pliki, g.lista])) {
          const i = tab.indexOf(p); if (i < 0) continue;
          if (zastap) tab[i] = nowy; else tab.splice(i + 1, 0, nowy);
        }
        if (!zastap) g.razem++;
        zrobione.push({nowy, partia: w.partia || 0});
      } catch (e) { bl.push(e.message); }
      const n = zrobione.length + bl.length;
      postep(n);
      if (n % 25 === 0) rysujSiatke();  // obrócone miniatury pojawiają się w trakcie
    }
    rysujSiatke();
    toastG(`${nazwa}: ${liczbaZdjec(zrobione.length)}` + (zastap ? " (oryginały w Odłożone/Usunięte)" : " — zapisane jako kopie „(edytowane)”") +
           (bl.length ? ` · nie udało się: ${bl.length} (${bl[0]})` : ""),
      zrobione.length ? () => zadanieTla("↶ Cofam " + nazwa.replace(/^\S+\s/, "").toLowerCase(), zrobione.length, async krok => {
        let i = 0, zle = 0;
        for (const z of zrobione) {
          try { await post("/api/g/edytuj/cofnij", {id: z.nowy.id, partia: z.partia}); } catch (e) { zle++; }
          krok(++i);
        }
        wczytajPliki().catch(() => {});
        toastG(zle ? `↶ Cofnięto, ale nie wszystko: ${zle} błędów` : (zastap ? "↶ Przywrócono oryginały" : "↶ Usunięto kopie"));
      }) : null);
  });
}
$("zz-lewo").onclick = () => edycjaHurtem({obrot: 270}, "↺ Obrót w lewo");
$("zz-prawo").onclick = () => edycjaHurtem({obrot: 90}, "↻ Obrót w prawo");
$("zz-180").onclick = () => edycjaHurtem({obrot: 180}, "⟳ Obrót o 180°");
$("zz-lustro").onclick = () => edycjaHurtem({lustro: true}, "⇋ Odbicie");
$("zz-auto").onclick = () => edycjaHurtem({auto: true}, "✨ Auto-poprawa");
document.addEventListener("keydown", e => {
  if ($("ed").hidden) {
    if ((e.key === "e" || e.key === "E") && !$("pelny").hidden && !$("p-edytuj").hidden && $("dt").hidden && $("lok").hidden
        && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); otworzEdytor(biezacy()); }
    return;
  }
  e.stopImmediatePropagation();
  if (e.key === "Escape") $("ed-anuluj").click();
  if ((e.key === "c" || e.key === "C") && e.target.tagName !== "SELECT") edTnij(!ed.tnie);
  if (e.key === " " && !e.repeat && e.target.tagName !== "BUTTON") { e.preventDefault(); edPrzed(true); }
}, true);
document.addEventListener("keyup", e => { if (!$("ed").hidden && e.key === " " && ed.przed) edPrzed(false); }, true);
