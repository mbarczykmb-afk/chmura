// Analiza zdjęć: zdjęcia dokumentów (do potwierdzenia) oraz podobne / nieostre zdjęcia.
"use strict";

const an = {dok: [], dokWybor: new Map(), dokWczytane: false, tryb: "podobne", grupy: [], razem: 0, nieostre: [],
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
  : `<div class="pusto">Zdjęcia nie są jeszcze przeanalizowane.<br><button class="glowny" style="width:auto;margin-top:12px"
     ${zajety() || !stan.ma_wyniki ? "disabled" : ""} onclick="document.getElementById('analizuj').click()">Analizuj zdjęcia</button></div>`;
naStan.push(rysujAnalizeLewa);

$("analizuj").onclick = async () => {
  try { stan = await api("/api/analiza/start", {}); rysuj(); } catch (e) { toast(e.message); }
};

// ---------- decyzja: zdjęcie / dokument / śmieci (wspólna dla zakładek) ----------
const KAT_OPCJE = [["zdjecie", "📷 Zdjęcie"], ["dokument", "📄 Dokument"], ["smieci", "🗑 Śmieci"]];
const KAT_NAZWY = {zdjecie: "zdjęcie", dokument: "dokument", smieci: "śmieci"};

// Trzy przyciski; wybierz(k) -> Promise|undefined; ponowny klik aktywnego = cofnięcie wyboru (k = "").
function przyciskiWyboru(obecna, wybierz, pozwolCofniecie = true) {
  const wyb = document.createElement("div"); wyb.className = "wybor";
  let akt = obecna || "";
  const pokaz = () => wyb.querySelectorAll("button").forEach(b => b.classList.toggle("akt", b.dataset.k === akt));
  for (const [k, opis] of KAT_OPCJE) {
    const b = document.createElement("button"); b.className = "maly" + (k === "smieci" ? " s" : "");
    b.dataset.k = k; b.textContent = opis;
    b.onclick = async e => {
      e.preventDefault(); e.stopPropagation();
      const nowa = akt === k && pozwolCofniecie ? "" : k;
      try { await wybierz(nowa); akt = nowa; pokaz(); } catch (err) { toast(err.message); }
    };
    wyb.append(b);
  }
  wyb.ustaw = k => { akt = k || ""; pokaz(); };
  pokaz();
  return wyb;
}

// Wariant zapisywany od razu (Duplikaty, Podobne): decyzja dla wskazanych plików + przełożenie w drzewie.
function przyciskiKategorii(ids, obecna, poZmianie) {
  let poprzednia = obecna || "";
  const wyb = przyciskiWyboru(obecna, async nowa => {
    const w = await api("/api/kategoria", {ids, kat: nowa});
    const bylo = poprzednia; poprzednia = nowa;
    toast(nowa ? `Zapisano: ${KAT_NAZWY[nowa]}` + (w.plan && w.plan.zmienione ? " — przełożono w drzewie." : ".")
               : "Usunięto decyzję.", async () => {
      await api("/api/kategoria", {ids, kat: bylo}); poprzednia = bylo; wyb.ustaw(bylo);
      if (poZmianie) poZmianie(bylo);
      toast("Cofnięto."); if (typeof plan !== "undefined") plan.wczytany = false;
    });
    if (typeof plan !== "undefined") plan.wczytany = false;
    if (typeof inne !== "undefined") inne.wczytane = false;
    an.dokWczytane = false;
    if (poZmianie) poZmianie(nowa);
  });
  return wyb;
}

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
  // wybór na start: zapisana decyzja, a gdy jej brak — propozycja programu (pewne -> dokument, reszta -> zdjęcie)
  an.dokWybor = new Map(r.kandydaci.map(k => [k.id, k.kat || (k.decyzja === 1 ? "dokument" : k.decyzja === 0 ? "zdjecie"
                                                             : (k.zaznacz ? "dokument" : "zdjecie"))]));
  an.dokIle = DOK_NA_STRONE;
  an.dokWczytane = true; rysujDokumenty();
};

const DOK_NA_STRONE = 100;
const dokWidoczne = () => an.dok.slice(0, an.dokIle || DOK_NA_STRONE);
function dokStopka() {
  const w = dokWidoczne(), licz = k => w.filter(d => an.dokWybor.get(d.id) === k).length;
  $("dok-stopka").textContent = !an.dok.length ? "" :
    `Dokumenty: ${licz("dokument")} · zdjęcia: ${licz("zdjecie")} · śmieci: ${licz("smieci")} — z ${w.length}` +
    (w.length < an.dok.length ? ` wyświetlonych (razem ${an.dok.length}; zapisuję tylko wyświetlone)` : "");
}
function rysujDokumenty() {
  const s = $("dok-siatka"); s.replaceChildren(); s.classList.add("duze");
  if (!stan.analiza) s.innerHTML = BRAK_ANALIZY();
  else if (!an.dok.length) s.innerHTML = '<div class="pusto">Nie znaleziono zdjęć przypominających dokumenty. 🎉</div>';
  for (const d of dokWidoczne()) {
    const k = karta(d.id, "zdjecie", d.wzgledna, `${(d.data || "").slice(0, 10)} · pewność ${Math.round(d.ocena * 100)}%` +
                    (d.decyzja != null || d.kat ? " · ✓ zapisane" : ""), false, () => undefined, true);
    k.querySelector("input").remove(); k.onclick = null; k.style.cursor = "default";
    k.append(przyciskiWyboru(an.dokWybor.get(d.id), kat => { an.dokWybor.set(d.id, kat); dokStopka(); }, false));
    s.append(k);
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
$("dok-wszystkie").onclick = () => { dokWidoczne().forEach(d => an.dokWybor.set(d.id, "dokument")); rysujDokumenty(); };
$("dok-zadne").onclick = () => { dokWidoczne().forEach(d => an.dokWybor.set(d.id, "zdjecie")); rysujDokumenty(); };
$("dok-zapisz").onclick = async () => {
  const wybor = {}, bylo = {};  // decydujemy tylko o tym, co było widać
  for (const d of dokWidoczne()) {
    wybor[d.id] = an.dokWybor.get(d.id) || "zdjecie";
    bylo[d.id] = d.kat || (d.decyzja === 1 ? "dokument" : d.decyzja === 0 ? "zdjecie" : "");
  }
  try {
    const w = await api("/api/nie-z-aparatu/zapisz", {wybor});
    const n = Object.values(wybor).filter(k => k === "dokument").length;
    toast(`Zapisano: ${plikow(w.zapisane, ["decyzja", "decyzje", "decyzji"])} (dokumentów: ${n}).` +
          (w.plan && w.plan.zmienione ? ` Przełożono w drzewie: ${plikow(w.plan.zmienione)}.` : ""), () => cofnijZapis(bylo));
    if (typeof inne !== "undefined") inne.wczytane = false;
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
        r.append(gora, img, sc, op, przyciskiKategorii([w.id], w.kat, v => { w.kat = v; }));
        siatka.append(r);
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
    ? `Do odłożenia: ${doOdl.length} zdjęć${bajty ? ` (${rozmiar(bajty)})` : ""} — trafią do folderu Odłożone (można cofnąć)`
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
  const n = document.createElement("div"); n.className = "nakladka"; n.dataset.podglad = "1";
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
  if (!confirm(`Odłożyć ${ids.length} zdjęć do folderu Odłożone?\n\nNic nie jest kasowane — operację można cofnąć w sekcji „Duplikaty”.`)) return;
  try {
    const w = await api("/api/odloz", {ids, typ: an.tryb});
    toast(`Odłożono ${w.przeniesione} zdjęć.` + (w.pominiete.length ? ` Pominięto: ${w.pominiete.length}.` : ""), async () => {
      const c = await api("/api/duplikaty/cofnij", {});
      toast(`Przywrócono ${c.przywrocone} zdjęć.`);
      stan = await api("/api/stan"); rysuj(); an.podWczytane = false; wczytajPodobne();
    });
    stan = await api("/api/stan"); rysuj(); an.podWczytane = false; wczytajPodobne();
  } catch (e) { toast(e.message); }
};

// ---------- nie z aparatu: zdjęcie / dokument / śmieci ----------
const INNE_NA_STRONE = 100;
const inne = {lista: [], wybor: new Map(), ile: INNE_NA_STRONE, wczytane: false};
przyPokazaniu.inne = async () => {
  if (inne.wczytane) return;
  const r = await api("/api/nie-z-aparatu");
  inne.lista = r.pliki; inne.wybor = new Map(r.pliki.filter(p => p.decyzja).map(p => [p.id, p.decyzja]));
  inne.ile = INNE_NA_STRONE; inne.wczytane = true; rysujInne();
};
const inneWidoczne = () => inne.lista.slice(0, inne.ile);
function inneStopka() {
  const w = inneWidoczne(), n = w.filter(p => inne.wybor.has(p.id)).length;
  $("inne-stopka").textContent = !inne.lista.length ? "" :
    `Zdecydowano: ${n} z ${w.length}` + (w.length < inne.lista.length ? ` wyświetlonych (razem ${inne.lista.length})` : "") +
    " · bez decyzji zostają w drzewie jako zdjęcia „do sprawdzenia”";
}
function kartaInne(p) {
  const k = karta(p.id, "zdjecie", p.wzgledna, (p.data || "").slice(0, 10) + (p.szer ? ` · ${p.szer}×${p.wys}` : "") +
                  ` · ${rozmiar(p.rozmiar)}`, false, () => undefined, true);
  k.querySelector("input").remove(); k.onclick = null; k.style.cursor = "default";
  const pw = document.createElement("div"); pw.className = "m powod"; pw.textContent = "❔ " + p.powod;
  k.querySelector(".op").append(pw);
  k.append(przyciskiWyboru(inne.wybor.get(p.id), kat => {
    kat ? inne.wybor.set(p.id, kat) : inne.wybor.delete(p.id); inneStopka();
  }));
  return k;
}
function rysujInne() {
  const s = $("inne-siatka"); s.replaceChildren();
  if (!inne.lista.length) s.innerHTML = '<div class="pusto">Nie ma podejrzanych obrazów — wszystko wygląda na zdjęcia z aparatu. 🎉</div>';
  for (const p of inneWidoczne()) s.append(kartaInne(p));
  const reszta = inne.lista.length - inneWidoczne().length;
  if (reszta > 0) {
    const b = document.createElement("button"); b.className = "wiecej"; b.style.gridColumn = "1/-1";
    b.textContent = `Pokaż kolejne ${Math.min(INNE_NA_STRONE, reszta)} (zostało ${reszta})`;
    b.onclick = () => { inne.ile += INNE_NA_STRONE; rysujInne(); };
    s.append(b);
  }
  inneStopka();
  $("inne-zapisz").disabled = !inne.lista.length;
}
$("inne-wsz-zdj").onclick = () => { inneWidoczne().forEach(p => inne.wybor.set(p.id, "zdjecie")); rysujInne(); };
$("inne-wsz-smieci").onclick = () => { inneWidoczne().forEach(p => inne.wybor.set(p.id, "smieci")); rysujInne(); };
$("inne-zapisz").onclick = async () => {
  const wybor = {}, bylo = {};
  for (const p of inneWidoczne()) if (inne.wybor.has(p.id)) { wybor[p.id] = inne.wybor.get(p.id); bylo[p.id] = p.decyzja || ""; }
  if (!Object.keys(wybor).length) { toast("Najpierw wybierz coś przy obrazach."); return; }
  try {
    const w = await api("/api/nie-z-aparatu/zapisz", {wybor});
    toast(`Zapisano: ${plikow(w.zapisane, ["decyzja", "decyzje", "decyzji"])}.` + (w.plan && w.plan.zmienione ? ` Przełożono w drzewie: ${plikow(w.plan.zmienione)}.` : ""),
          () => cofnijZapis(bylo));
    inne.wczytane = false; an.dokWczytane = false; plan.wczytany = false;
    stan = await api("/api/stan"); rysuj(); przyPokazaniu.inne();
  } catch (e) { toast(e.message); }
};
naStan.push(() => {
  const n = stan.nie_z_aparatu;
  $("licz-inne").hidden = !n; if (n) $("licz-inne").textContent = n;
});

async function cofnijZapis(bylo) {  // przywraca decyzje sprzed zapisu zbiorczego
  await api("/api/nie-z-aparatu/zapisz", {wybor: bylo});
  toast("Cofnięto zapis decyzji.");
  inne.wczytane = false; an.dokWczytane = false; if (typeof plan !== "undefined") plan.wczytany = false;
  stan = await api("/api/stan"); rysuj();
  if (przyPokazaniu[zakladka]) przyPokazaniu[zakladka]();
}
