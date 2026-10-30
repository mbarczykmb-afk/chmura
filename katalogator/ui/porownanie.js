// 🔀 Serie i porównanie obok siebie · 📦 eksport kopii · ✎ zmiana nazw · 📷 filtry (aparat, pora dnia)
"use strict";

// ---------- 📷 filtry: aparat / telefon, pora dnia ----------
function przeladujWidok() {
  g.punkty = null; g.przeladuj = true;
  if (g.widok === "kolekcje") rysujKolekcje();
  else if (g.widok === "osoby") rysujOsoby();
  else if (g.widok === "serie") rysujSerie();
  else if (g.widok === "gps") rysujGps(false);
  else if (g.widok === "foldery") { if (g.zrodlo.typ === "folder") pokazFolder(g.zrodlo.f, g.zrodlo.pod); rysujDrzewo(); }
  else if (g.widok === "mapa") pokazMape().catch(() => {});
  else if (g.zrodlo.typ === "os") { g.przeladuj = false; g.rok = null; start(); }
  else pokazWyniki(g.zrodlo);
  odswiezZnakFiltrow();
}
function odswiezZnakFiltrow() {
  const n = (g.aparat !== undefined && g.aparat !== null ? 1 : 0) + (g.pora ? 1 : 0);
  $("filtry-ile").hidden = !n; $("filtry-ile").textContent = n;
  $("filtry-btn").classList.toggle("akt", !!n);
  $("filtry-btn").title = n ? "Filtry: " + [g.aparat !== undefined && g.aparat !== null ? "📷 " + (g.aparat || "bez nazwy aparatu") : "",
                                           g.pora ? "🕐 " + $("filtr-pora").selectedOptions[0].textContent : ""].filter(Boolean).join(" · ")
                            : "Filtry: aparat / telefon, pora dnia";
}
$("filtry-btn").onclick = async e => {
  e.stopPropagation();
  const m = $("filtry-menu"); m.hidden = !m.hidden; $("menu").hidden = true;
  if (m.hidden) return;
  try {
    const r = await api("/api/g/aparaty"), sel = $("filtr-aparat"), bylo = g.aparat;
    sel.replaceChildren(new Option("wszystkie", "*"));
    for (const [a, n] of r.aparaty) sel.append(new Option(`${a || "— bez nazwy aparatu —"} (${n.toLocaleString("pl-PL")})`, a || "~"));
    sel.value = bylo === undefined || bylo === null ? "*" : (bylo || "~");
  } catch (er) { toastG(er.message); }
};
$("filtry-menu").addEventListener("click", e => e.stopPropagation());
document.addEventListener("click", () => { $("filtry-menu").hidden = true; });
$("filtr-aparat").onchange = () => { const v = $("filtr-aparat").value; g.aparat = v === "*" ? null : v === "~" ? "" : v; przeladujWidok(); };
$("filtr-pora").onchange = () => { g.pora = $("filtr-pora").value; przeladujWidok(); };
$("filtry-wyczysc").onclick = () => { g.aparat = null; g.pora = ""; $("filtr-aparat").value = "*"; $("filtr-pora").value = ""; $("filtry-menu").hidden = true; przeladujWidok(); };

// ---------- 🔀 serie: lista stosów ----------
async function rysujSerie() {
  const s = $("siatka"); s.innerHTML = '<div class="pusto">Szukam serii zdjęć…</div>';
  let r; try { r = await api("/api/g/serie", {ile: 300}); } catch (e) { s.innerHTML = `<div class="pusto">${e.message}</div>`; return; }
  if (g.widok !== "serie") return;
  g.serie = r; rysujFiltr(); s.replaceChildren();
  if (!r.serie.length) { s.innerHTML = '<div class="pusto">Nie ma serii — czyli kilku zdjęć zrobionych jedno po drugim (w ciągu paru sekund) w tym samym miejscu.</div>'; return; }
  for (const x of r.serie) {
    const k = document.createElement("div"); k.className = "k seria"; k.style.cursor = "pointer";
    const ob = document.createElement("div"); ob.className = "ob";
    const im = new Image(); im.loading = "lazy"; im.alt = ""; im.draggable = false; im.src = miniatura(x.ids[0], false); ob.append(im);
    const ile = document.createElement("span"); ile.className = "ile"; ile.textContent = "▣ " + x.n; ob.append(ile);
    const op = document.createElement("div"); op.className = "op"; op.innerHTML = "<div></div><div class='m'></div>";
    op.children[0].textContent = `${x.n} ujęć · ${x.folder}`;
    op.children[1].textContent = dataTxt(x.data) + ", " + (x.data || "").slice(11, 16);
    k.append(ob, op); k.title = "Porównaj obok siebie i zostaw najlepsze";
    k.onclick = () => porownaj(x.ids); s.append(k);
  }
}

// ---------- 🔀 porównanie: 2–4 zdjęcia obok siebie, wspólne powiększenie, ✓ zostaw najlepsze ----------
const por = {ids: [], od: 0, zost: new Set(), z: 1, cx: 0.5, cy: 0.5, ostr: {}, ciag: null};
const porIle = () => Math.min(4, por.ids.length);
async function porownaj(ids) {
  por.ids = ids.slice(0, 40); por.od = 0; por.zost = new Set(); por.z = 1; por.cx = por.cy = 0.5; por.ostr = {};
  $("por").hidden = false; $("por-zostaw").hidden = !MOZE_USUWAC; stopPokaz && stopPokaz();
  rysujPor();
  try {  // ostrość — podpowiedź; najostrzejsze od razu oznaczone ✓
    por.ostr = (await api("/api/g/ostrosc", {ids: por.ids.slice(0, 12).join(",")})).ostrosc;
    const naj = Object.entries(por.ostr).sort((a, b) => b[1] - a[1])[0];
    if (naj && !por.zost.size) por.zost.add(+naj[0]);
    rysujPor();
  } catch (e) { /* bez podpowiedzi */ }
}
function rysujPor() {
  const k = porIle(), pan = $("por-panele"); pan.replaceChildren();
  pan.style.gridTemplateColumns = `repeat(${k <= 2 ? k : 2}, 1fr)`;
  if (k > 2) pan.style.gridTemplateRows = "1fr 1fr"; else pan.style.gridTemplateRows = "1fr";
  if (k === 3) pan.style.gridTemplateColumns = "repeat(3, 1fr)", pan.style.gridTemplateRows = "1fr";
  const maxO = Math.max(1, ...Object.values(por.ostr));
  for (let j = 0; j < k; j++) {
    const id = por.ids[(por.od + j) % por.ids.length], p = (g.pliki.find(x => x.id === id) || {id});
    const d = document.createElement("div"); d.className = "pan" + (por.zost.has(id) ? " zost" : ""); d.dataset.id = id;
    const im = new Image(); im.alt = ""; im.draggable = false; im.src = url("/api/g/podglad", {id});
    const et = document.createElement("div"); et.className = "et";
    const n = document.createElement("span"); n.textContent = `${j + 1}. ${p.nazwa || ""}`;
    et.append(n);
    if (por.ostr[id] !== undefined) {
      const o = document.createElement("span"); o.title = "Ostrość (względem najostrzejszego w serii)";
      o.innerHTML = `ostrość <span class="ostr"><i style="width:${Math.round(100 * por.ostr[id] / maxO)}%"></i></span>`; et.append(o);
    }
    const ok = document.createElement("span"); ok.className = "ok"; ok.textContent = por.zost.has(id) ? "✓ zostaw" : "zostaw?";
    ok.onclick = e => { e.stopPropagation(); przelaczZost(id); };
    et.append(ok); d.append(im, et); pan.append(d);
  }
  const pas = $("por-pasek"); pas.replaceChildren(); pas.hidden = por.ids.length <= 4;
  por.ids.forEach((id, i) => {
    const im = new Image(); im.src = miniatura(id, false); im.alt = ""; im.title = "Pokaż";
    const wid = (i - por.od + por.ids.length) % por.ids.length < k;
    im.className = (wid ? "wid " : "") + (por.zost.has(id) ? "zost" : "");
    im.onclick = () => { por.od = i; rysujPor(); }; pas.append(im);
  });
  $("por-info").textContent = `${por.ids.length} zdjęć · ✓ zostaw: ${por.zost.size} · kółko myszy = powiększenie wszystkich naraz, przeciągnij = przesuń, 1–4 = ✓, Enter = zatwierdź`;
  $("por-wstecz").hidden = $("por-dalej").hidden = por.ids.length <= k;
  porTransform();
}
function przelaczZost(id) { por.zost.has(id) ? por.zost.delete(id) : por.zost.add(id); rysujPor(); }
function porTransform() {
  for (const d of $("por-panele").children) {
    const W = d.clientWidth, H = d.clientHeight, im = d.querySelector("img");
    const tx = W / 2 - por.cx * W * por.z, ty = H / 2 - por.cy * H * por.z;
    im.style.transform = `translate(${tx}px, ${ty}px) scale(${por.z})`;
  }
}
const ogr = (v, a, b) => Math.max(a, Math.min(b, v));
$("por-panele").addEventListener("wheel", e => {
  const d = e.target.closest(".pan"); if (!d) return; e.preventDefault();
  const r = d.getBoundingClientRect(), W = r.width, H = r.height, mx = e.clientX - r.left, my = e.clientY - r.top;
  const px = por.cx - (W / 2 - mx) / (W * por.z), py = por.cy - (H / 2 - my) / (H * por.z);  // punkt pod kursorem
  por.z = ogr(por.z * (e.deltaY < 0 ? 1.25 : 0.8), 1, 10);
  por.cx = por.z === 1 ? 0.5 : px + (W / 2 - mx) / (W * por.z); por.cy = por.z === 1 ? 0.5 : py + (H / 2 - my) / (H * por.z);
  porTransform();
}, {passive: false});
$("por-panele").addEventListener("pointerdown", e => {
  const d = e.target.closest(".pan"); if (!d || e.target.closest(".ok")) return;
  por.ciag = {x: e.clientX, y: e.clientY, cx: por.cx, cy: por.cy, W: d.clientWidth, H: d.clientHeight, ruch: false, id: +d.dataset.id};
});
addEventListener("pointermove", e => {
  const c = por.ciag; if (!c) return;
  if (Math.hypot(e.clientX - c.x, e.clientY - c.y) > 4) c.ruch = true;
  if (por.z > 1) { por.cx = c.cx - (e.clientX - c.x) / (c.W * por.z); por.cy = c.cy - (e.clientY - c.y) / (c.H * por.z); porTransform(); }
});
addEventListener("pointerup", () => { const c = por.ciag; por.ciag = null; if (c && !c.ruch) przelaczZost(c.id); });
$("por-panele").addEventListener("dblclick", e => { if (!e.target.closest(".pan")) return; por.z = por.z > 1 ? 1 : 3; if (por.z === 1) por.cx = por.cy = 0.5; porTransform(); });
addEventListener("resize", () => { if (!$("por").hidden) porTransform(); });
$("por-wstecz").onclick = () => { por.od = (por.od - 1 + por.ids.length) % por.ids.length; rysujPor(); };
$("por-dalej").onclick = () => { por.od = (por.od + 1) % por.ids.length; rysujPor(); };
const zamknijPor = () => { $("por").hidden = true; };
$("por-zamknij").onclick = zamknijPor;
$("por-zostaw").onclick = async () => {
  if (!por.zost.size) { toastG("Zaznacz ✓ co najmniej jedno zdjęcie, które zostaje."); return; }
  const usun = por.ids.filter(id => !por.zost.has(id));
  if (!usun.length) { zamknijPor(); return; }
  if (!await oknoTak(`Zostawić ${por.zost.size}, a ${usun.length} pozostałych przenieść do kosza programu (Odłożone/Usunięte)?\n\nMożna cofnąć.`)) return;
  zamknijPor();
  const lista = usun.map(id => g.pliki.find(p => p.id === id) || {id, nazwa: ""});
  if (!$("pelny").hidden) zamknijPelny();
  await usunPliki(lista);
  if (g.widok === "serie") rysujSerie();
};
document.addEventListener("keydown", e => {
  if ($("por").hidden) return;
  e.stopImmediatePropagation();
  if (e.key === "Escape") zamknijPor();
  else if (e.key === "ArrowRight") $("por-dalej").click();
  else if (e.key === "ArrowLeft") $("por-wstecz").click();
  else if (e.key === "Enter") $("por-zostaw").click();
  else if (e.key === "0") { por.z = 1; por.cx = por.cy = 0.5; porTransform(); }
  else if (/^[1-4]$/.test(e.key) && +e.key <= porIle()) przelaczZost(por.ids[(por.od + +e.key - 1) % por.ids.length]);
}, true);
$("zz-por").onclick = () => { const w = zaznaczone().filter(p => p.rodzaj === "zdjecie").map(p => p.id); if (w.length >= 2) porownaj(w); };
$("p-seria").onclick = e => { e.stopPropagation(); const p = biezacy(); if (p && p.seria) porownaj(p.seria); };

// ---------- 📦 eksport: kopie do folderu (mniejsze, bez GPS, ze znakiem wodnym) ----------
const eks = (() => { try { return JSON.parse(localStorage.getItem("kat_eksport") || "{}"); } catch (e) { return {}; } })();
$("zz-eksport").onclick = () => {
  const lista = zaznaczone(); if (!lista.length) return;
  $("eks-ile").textContent = `${liczbaZdjec(lista.length)} — oryginały zostają nietknięte.`;
  $("eks-cel").value = eks.cel || ""; if (eks.bok !== undefined) $("eks-bok").value = eks.bok;
  if (eks.jakosc) $("eks-jak").value = eks.jakosc; $("eks-gps").checked = eks.bez_gps !== false; $("eks-znak").value = eks.znak || "";
  $("eks").hidden = false;
};
$("eks-wybierz").onclick = () => { $("eks").hidden = true; wybierzFolder("Gdzie zapisać kopie?", sc => { $("eks-cel").value = sc; $("eks").hidden = false; }); };
$("eks-anuluj").onclick = () => { $("eks").hidden = true; };
$("eks-ok").onclick = () => {
  const cel = $("eks-cel").value; if (!cel) { toastG("Wybierz folder docelowy."); return; }
  Object.assign(eks, {cel, bok: +$("eks-bok").value, jakosc: +$("eks-jak").value, bez_gps: $("eks-gps").checked, znak: $("eks-znak").value});
  try { localStorage.setItem("kat_eksport", JSON.stringify(eks)); } catch (e) { /* bez pamięci */ }
  const lista = zaznaczone(); $("eks").hidden = true; koniecZazn();
  zadanieTla("📦 Eksport", lista.length, async postep => {
    let ok = 0; const bl = [];
    for (const p of lista) {
      try { await post("/api/g/eksport", {id: p.id, ...eks}); ok++; } catch (e) { bl.push(e.message); }
      postep(ok + bl.length);
    }
    toastG(`📦 Zapisano ${liczbaZdjec(ok)} w ${cel}` + (bl.length ? ` · nie udało się: ${bl.length} (${bl[0]})` : ""));
  });
};

// ---------- ✎ zmiana nazw według wzorca — z podglądem i „Cofnij” ----------
const ZNACZNIKI = [["{data}", "data 2019-07-14"], ["{czas}", "godzina 14-35-02"], ["{rok}", "rok"], ["{mies}", "miesiąc"], ["{dzien}", "dzień"],
                   ["{miejsce}", "miejscowość"], ["{aparat}", "aparat"], ["{folder}", "folder"], ["{nazwa}", "dotychczasowa nazwa"], ["{nr}", "numer 001"]];
const nzw = {lista: [], nazwy: [], zegar: 0};
$("nzw-znaczniki").replaceChildren(...ZNACZNIKI.map(([z, t]) => {
  const b = document.createElement("button"); b.textContent = z; b.title = t;
  b.onclick = () => { const i = $("nzw-wzor"); const p = i.selectionStart ?? i.value.length; i.value = i.value.slice(0, p) + z + i.value.slice(i.selectionEnd ?? p); i.focus(); podgladNazw(); };
  return b;
}));
try { const w = localStorage.getItem("kat_nzw_wzor"); if (w) $("nzw-wzor").value = w; } catch (e) { /* bez pamięci */ }
async function podgladNazw() {
  const t = $("nzw-podglad");
  try {
    const r = await post("/api/g/nazwy-podglad", {ids: nzw.lista.map(p => p.id), wzor: $("nzw-wzor").value, start: +$("nzw-start").value || 0});
    nzw.nazwy = r.nazwy;
    const zle = r.nazwy.filter(x => x.konflikt).length;
    t.innerHTML = "<table></table>";
    for (const x of r.nazwy.slice(0, 200)) {
      const tr = document.createElement("tr"); const a = document.createElement("td"), b = document.createElement("td");
      a.textContent = x.stara; b.textContent = "→ " + x.nowa + (x.konflikt ? "  ⚠ taka nazwa już jest" : ""); if (x.konflikt) b.className = "zle";
      tr.append(a, b); t.firstChild.append(tr);
    }
    $("nzw-ok").disabled = !!zle; $("nzw-ok").textContent = zle ? `${zle} konfliktów — zmień wzór (np. dodaj {nr})` : `Zmień nazwy (${r.nazwy.length})`;
  } catch (e) { t.textContent = e.message; }
}
$("nzw-wzor").oninput = $("nzw-start").oninput = () => { clearTimeout(nzw.zegar); nzw.zegar = setTimeout(podgladNazw, 250); };
$("zz-nazwy").onclick = () => { nzw.lista = zaznaczone(); if (!nzw.lista.length) return; $("nzw").hidden = false; podgladNazw(); };
$("nzw-anuluj").onclick = () => { $("nzw").hidden = true; };
$("nzw-ok").onclick = () => {
  const plan = nzw.nazwy.filter(x => x.nowa !== x.stara); $("nzw").hidden = true;
  try { localStorage.setItem("kat_nzw_wzor", $("nzw-wzor").value); } catch (e) { /* bez pamięci */ }
  if (!plan.length) return;
  koniecZazn();
  const zrobione = [];
  const zmien = (id, nazwa) => { for (const tab of new Set([g.pliki, g.lista])) for (const p of tab || []) if (p.id === id) p.nazwa = nazwa; };
  zadanieTla("✎ Zmiana nazw", plan.length, async postep => {
    const bl = [];
    for (const x of plan) {
      try { const w = await post("/api/g/zmien-nazwe", {id: x.id, nazwa: x.nowa}); zmien(x.id, w.nazwa); zrobione.push({id: x.id, stara: w.stara}); }
      catch (e) { bl.push(e.message); }
      postep(zrobione.length + bl.length);
    }
    rysujSiatke();
    toastG(`✎ Zmieniono nazwy: ${zrobione.length}` + (bl.length ? ` · nie udało się: ${bl.length} (${bl[0]})` : ""), zrobione.length ? () =>
      zadanieTla("↶ Przywracam nazwy", zrobione.length, async krok => {
        let i = 0;
        for (const z of zrobione) { try { const w = await post("/api/g/zmien-nazwe", {id: z.id, nazwa: z.stara}); zmien(z.id, w.nazwa); } catch (e) { /* dalej */ } krok(++i); }
        rysujSiatke(); toastG("↶ Przywrócono poprzednie nazwy");
      }) : null);
  });
};
for (const id of ["eks", "nzw"]) $(id).addEventListener("click", e => { if (e.target.id === id) $(id).hidden = true; });
