// Analiza zdjęć: zdjęcia dokumentów (do potwierdzenia) oraz podobne / nieostre zdjęcia.
"use strict";

const an = {dok: [], dokZazn: new Set(), dokWczytane: false, tryb: "podobne", grupy: [], razem: 0, nieostre: [],
            odloz: new Set(), podWczytane: false, trwala: false, decyzje: new Map()};

function rysujAnalizeLewa() {
  $("analizuj").disabled = zajety() || !stan.ma_wyniki;
  const a = stan.analiza;
  $("analizuj").textContent = a ? "Analizuj ponownie (tylko nowe zdjęcia)" : "Analizuj zdjęcia";
  rysujZadanie("analiza", "zad-analiza");
  const box = $("podsum-analiza");
  const z = (stan.zad || {}).analiza || {};
  box.hidden = !a || z.trwa;
  if (a) {
    box.innerHTML = `Przeanalizowano <b>${a.przeanalizowane}</b> z ${a.zdjecia} zdjęć<br>
      Możliwe dokumenty do przejrzenia: <b>${a.dokumenty}</b> (potwierdzone: ${a.dokumenty_potwierdzone})<br>
      Grupy podobnych zdjęć: <b>${a.podobne_grupy}</b>
      <div class="wiersz" style="margin-top:8px"><button class="maly" id="an-dok">Dokumenty →</button>
      <button class="maly" id="an-pod">Podobne →</button></div>`;
    $("an-dok").onclick = () => pokazZakladke("dok");
    $("an-pod").onclick = () => pokazZakladke("pod");
  }
  $("licz-dok").hidden = !(a && a.dokumenty); if (a) $("licz-dok").textContent = a.dokumenty;
  $("licz-pod").hidden = !(a && a.podobne_grupy); if (a) $("licz-pod").textContent = a.podobne_grupy;
  if (an.trwala && !z.trwa) { an.dokWczytane = false; an.podWczytane = false; if (przyPokazaniu[zakladka]) przyPokazaniu[zakladka](); }
  an.trwala = !!z.trwa;
  if (a && !an.bylaAnaliza && (zakladka === "dok" || zakladka === "pod")) {  // wyniki doszły po otwarciu okna
    an.dokWczytane = false; an.podWczytane = false; przyPokazaniu[zakladka]();
  }
  an.bylaAnaliza = !!a;
}
const BRAK_ANALIZY = () => stan.wczytuje ? '<div class="pusto">Wczytuję wyniki projektu…</div>'
  : '<div class="pusto">Najpierw kliknij „Analizuj zdjęcia” w lewej kolumnie.</div>';
naStan.push(rysujAnalizeLewa);

$("analizuj").onclick = async () => {
  try { stan = await api("/api/analiza/start", {}); rysuj(); } catch (e) { toast(e.message); }
};

function karta(id, rodzaj, tytul, podpis, zaznaczona, klik, duza = false) {
  const k = document.createElement("div");
  k.className = "karta" + (duza ? " duza" : "") + (zaznaczona ? " zazn" : "");
  k.title = tytul;
  const ob = document.createElement("div"); ob.className = "ob"; if (!duza) ob.style.height = "140px";
  const img = new Image(); img.loading = "lazy"; img.alt = "";
  img.src = `/miniatura?t=${encodeURIComponent(TOKEN)}&id=${id}` + (duza ? "&srednia=1" : "");
  if (duza) img.ondblclick = e => { e.stopPropagation(); podgladDuzy(id, tytul); };
  img.onerror = () => { ob.textContent = IKONY[rodzaj] || "🖼️"; };
  ob.append(img);
  const op = document.createElement("div"); op.className = "op";
  const n = document.createElement("div"); n.className = "n"; n.textContent = tytul.split(/[\\/]/).pop();
  const m = document.createElement("div"); m.className = "m"; m.textContent = podpis;
  op.append(n, m);
  const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = zaznaczona;
  cb.onclick = e => e.stopPropagation();
  // klik(v) === true: zmiana obsłużona na miejscu (bez przerysowania całej listy)
  const ustaw = v => { if (klik(v) === true) { k.classList.toggle("zazn", v); cb.checked = v; } };
  cb.onchange = () => ustaw(cb.checked);
  k.onclick = () => ustaw(!k.classList.contains("zazn"));
  k.append(ob, op, cb);
  return k;
}

// ---------- dokumenty ----------
przyPokazaniu.dok = async () => {
  if (an.dokWczytane) return;
  const r = await api("/api/dokumenty");
  // najpierw jeszcze nieprzejrzane, potem już zapisane decyzje
  an.dok = r.kandydaci.filter(k => k.decyzja == null).concat(r.kandydaci.filter(k => k.decyzja != null));
  an.dokZazn = new Set(r.kandydaci.filter(k => k.zaznacz).map(k => k.id)); an.dokIle = DOK_NA_STRONE;
  an.dokWczytane = true; rysujDokumenty();
};

const DOK_NA_STRONE = 100;
const dokWidoczne = () => an.dok.slice(0, an.dokIle || DOK_NA_STRONE);
function dokStopka() {
  const w = dokWidoczne();
  $("dok-stopka").textContent = !an.dok.length ? "" :
    `Zaznaczone jako dokumenty: ${w.filter(d => an.dokZazn.has(d.id)).length} z ${w.length}` +
    (w.length < an.dok.length ? ` wyświetlonych (razem ${an.dok.length}; zapisuję tylko wyświetlone)` : "");
}
function rysujDokumenty() {
  const s = $("dok-siatka"); s.replaceChildren(); s.classList.add("duze");
  if (!stan.analiza) s.innerHTML = BRAK_ANALIZY();
  else if (!an.dok.length) s.innerHTML = '<div class="pusto">Nie znaleziono zdjęć przypominających dokumenty. 🎉</div>';
  for (const d of dokWidoczne()) {
    const z = an.dokZazn.has(d.id);
    s.append(karta(d.id, "zdjecie", d.wzgledna, `${(d.data || "").slice(0, 10)} · pewność ${Math.round(d.ocena * 100)}%` +
                   (d.decyzja === 1 ? " · ✓ zapisane" : d.decyzja === 0 ? " · zapisane: nie" : ""), z,
                   v => { v ? an.dokZazn.add(d.id) : an.dokZazn.delete(d.id); dokStopka(); return true; }, true));
  }
  const reszta = an.dok.length - dokWidoczne().length;
  if (reszta > 0) {
    const b = document.createElement("button"); b.className = "wiecej"; b.style.gridColumn = "1/-1";
    b.textContent = `Pokaż kolejne ${Math.min(DOK_NA_STRONE, reszta)} (zostało ${reszta})`;
    b.onclick = () => { an.dokIle = (an.dokIle || DOK_NA_STRONE) + DOK_NA_STRONE; rysujDokumenty(); };
    s.append(b);
  }
  dokStopka();
  $("dok-zapisz").disabled = !an.dok.length;
}
$("dok-wszystkie").onclick = () => { dokWidoczne().forEach(d => an.dokZazn.add(d.id)); rysujDokumenty(); };
$("dok-zadne").onclick = () => { dokWidoczne().forEach(d => an.dokZazn.delete(d.id)); rysujDokumenty(); };
$("dok-zapisz").onclick = async () => {
  const w = dokWidoczne();  // decydujemy tylko o tym, co było widać
  const tak = w.filter(d => an.dokZazn.has(d.id)).map(d => d.id);
  const nie = w.filter(d => !an.dokZazn.has(d.id)).map(d => d.id);
  try {
    const w = await api("/api/dokumenty/zapisz", {tak, nie});
    toast(`Zapisano. Dokumentów: ${w.dokumenty}.` + (w.plan && w.plan.zmienione ? ` Przeniesiono w drzewie: ${w.plan.zmienione}.` : ""));
    an.dokWczytane = false; plan.wczytany = false;
    stan = await api("/api/stan"); rysuj(); przyPokazaniu.dok();
  } catch (e) { toast(e.message); }
};

// ---------- podobne / nieostre ----------
przyPokazaniu.pod = async () => { if (!an.podWczytane) await wczytajPodobne(); };

async function wczytajPodobne(wiecej) {
  if (an.tryb === "podobne") {
    const r = await api(`/api/podobne?od=${wiecej ? an.grupy.length : 0}&ile=30`);
    an.grupy = wiecej ? an.grupy.concat(r.grupy) : r.grupy; an.razem = r.razem;
  } else {
    const r = await api("/api/nieostre?ile=150");
    an.nieostre = r.pliki;
  }
  if (!wiecej) { an.odloz.clear(); an.decyzje.clear(); }
  for (const g of an.grupy) {   // jak w duplikatach: najlepsze zostaje, reszta do odłożenia
    const klucz = g.map(w => w.id).join("-");
    if (!an.decyzje.has(klucz)) an.decyzje.set(klucz, {zostaw: new Set([g[0].id]), pomin: false});
  }
  an.podWczytane = true; rysujPodobne();
}

function opisZdjecia(w) {
  return [w.szer && w.wys ? `${w.szer}×${w.wys}` : "", rozmiar(w.rozmiar), w.mtime ? data(w.mtime) : ""]
    .filter(Boolean).join(" · ");
}

function rysujPodobne() {
  const l = $("pod-lista"); l.replaceChildren();
  if (!stan.analiza) { l.innerHTML = BRAK_ANALIZY(); }
  else if (an.tryb === "podobne") {
    $("pod-info").textContent = `${an.razem} grup · ★ = najwyższa rozdzielczość i ostrość · kliknij, żeby zostawić więcej · dwuklik na miniaturze = powiększenie`;
    if (!an.grupy.length) l.innerHTML = '<div class="pusto">Nie znaleziono podobnych zdjęć.</div>';
    for (const g of an.grupy) {
      const d = an.decyzje.get(g.map(w => w.id).join("-"));
      const k = document.createElement("div"); k.className = "grupa pod" + (d.pomin ? " pominieta" : "");
      const odz = g.filter(w => !d.pomin && !d.zostaw.has(w.id));
      const gl = document.createElement("div"); gl.className = "gl";
      gl.innerHTML = `<strong>${g.length} podobne zdjęcia · odłożę ${odz.length} · odzyskasz ${rozmiar(odz.reduce((a, w) => a + w.rozmiar, 0))}</strong>`;
      const pom = document.createElement("label"); pom.className = "pomin";
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = d.pomin;
      cb.onchange = () => { d.pomin = cb.checked; rysujPodobne(); };
      pom.append(cb, "zostaw wszystkie"); gl.append(pom); k.append(gl);
      const siatka = document.createElement("div"); siatka.className = "pod-siatka"; k.append(siatka);
      g.forEach((w, i) => {
        const zost = d.pomin || d.zostaw.has(w.id);
        const r = document.createElement("label"); r.className = "plik zdj " + (zost ? "zostaje" : "odklada");
        const c = document.createElement("input"); c.type = "checkbox"; c.checked = zost; c.title = "Zostaw to zdjęcie";
        c.onchange = () => {
          if (c.checked) { d.zostaw.add(w.id); d.pomin = false; }
          else if (d.zostaw.size > 1) d.zostaw.delete(w.id);
          else { toast("Przynajmniej jedno zdjęcie z grupy musi zostać."); }
          rysujPodobne();
        };
        const img = new Image(); img.loading = "lazy"; img.alt = "";
        img.src = `/miniatura?t=${encodeURIComponent(TOKEN)}&id=${w.id}&srednia=1`;
        img.ondblclick = e => { e.preventDefault(); podgladDuzy(w.id, w.wzgledna); };
        const sc = document.createElement("span"); sc.className = "sc"; sc.title = w.sciezka;
        const cz = w.wzgledna.split(/[\\/]/); const nazwa = cz.pop();
        const em = document.createElement("em"); em.textContent = cz.length ? cz.join("\\") + "\\" : "";
        sc.append("\u200E", em, nazwa);
        const z = document.createElement("span"); z.className = "znak";
        z.textContent = (i === 0 ? "★ " : "") + (zost ? "zostaje" : "odłożę");
        const gora = document.createElement("div"); gora.className = "gora"; gora.append(c, z);
        const op = document.createElement("span"); op.className = "zn2"; op.textContent = opisZdjecia(w);
        r.append(gora, img, sc, op); siatka.append(r);
      });
      l.append(k);
    }
    if (an.grupy.length < an.razem) {
      const b = document.createElement("button"); b.className = "wiecej"; b.textContent = "Pokaż więcej grup";
      b.onclick = () => wczytajPodobne(true); l.append(b);
    }
  } else {
    $("pod-info").textContent = "Najmniej ostre zdjęcia (od najbardziej rozmazanych). Sprawdź przed odłożeniem — nocne i celowo rozmyte też tu trafią.";
    const s = document.createElement("div"); s.className = "siatka"; s.style.maxHeight = "none";
    for (const w of an.nieostre) {
      s.append(karta(w.id, "zdjecie", w.wzgledna, `${(w.data || "").slice(0, 10)} · ostrość ${Math.round(w.ostrosc)}`,
                     an.odloz.has(w.id), v => { v ? an.odloz.add(w.id) : an.odloz.delete(w.id); rysujPodobne(); }));
    }
    if (!an.nieostre.length) s.innerHTML = '<div class="pusto">Brak przeanalizowanych zdjęć.</div>';
    l.append(s);
  }
  const doOdl = doOdlozenia();
  const bajty = an.tryb === "podobne"
    ? an.grupy.flat().filter(w => doOdl.includes(w.id)).reduce((a, w) => a + w.rozmiar, 0) : 0;
  $("pod-stopka").textContent = doOdl.length
    ? `Do odłożenia: ${doOdl.length} zdjęć${bajty ? ` (${rozmiar(bajty)})` : ""} — trafią do _Duplikaty_Katalogator (można cofnąć)`
    : (an.tryb === "podobne" ? "Nic do odłożenia — wszystkie zdjęcia zostają." : "Zaznacz zdjęcia, które chcesz odłożyć.");
  $("pod-odloz").disabled = !doOdl.length;
  $("pod-odloz").textContent = an.tryb === "podobne" ? "Odłóż zaznaczone kopie" : "Odłóż zaznaczone";
}
function doOdlozenia() {
  if (an.tryb !== "podobne") return [...an.odloz];
  const ids = [];
  for (const g of an.grupy) {
    const d = an.decyzje.get(g.map(w => w.id).join("-"));
    if (d && !d.pomin) g.forEach(w => { if (!d.zostaw.has(w.id)) ids.push(w.id); });
  }
  return ids;
}
function podgladDuzy(id, nazwa) {
  const n = document.createElement("div"); n.className = "nakladka";
  const img = new Image(); img.src = `/miniatura?t=${encodeURIComponent(TOKEN)}&id=${id}&duza=1`; img.alt = nazwa;
  img.style.cssText = "max-width:90vw;max-height:85vh;border-radius:8px;background:#000";
  n.append(img); n.onclick = () => n.remove(); document.body.append(n);
}
$("pod-filtry").onclick = e => {
  const b = e.target.closest(".filtr"); if (!b) return;
  document.querySelectorAll("#pod-filtry .filtr").forEach(x => x.classList.toggle("akt", x === b));
  an.tryb = b.dataset.r; an.podWczytane = false; wczytajPodobne();
};
$("pod-odloz").onclick = async () => {
  const ids = doOdlozenia();
  if (!confirm(`Odłożyć ${ids.length} zdjęć do folderu _Duplikaty_Katalogator?\n\nNic nie jest kasowane — operację można cofnąć w sekcji „Duplikaty”.`)) return;
  try {
    const w = await api("/api/odloz", {ids, typ: an.tryb});
    toast(`Odłożono ${w.przeniesione} zdjęć.` + (w.pominiete.length ? ` Pominięto: ${w.pominiete.length}.` : ""));
    stan = await api("/api/stan"); rysuj(); an.podWczytane = false; wczytajPodobne();
  } catch (e) { toast(e.message); }
};
