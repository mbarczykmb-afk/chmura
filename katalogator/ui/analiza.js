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
const BRAK_ANALIZY = () => stan.wczytuje ? '<div class="pusto">Wczytuję wyniki projektu… (duży projekt — to może potrwać do minuty)</div>'
  : stan.blad_wczytania ? `<div class="pusto">Nie udało się wczytać wyników: ${stan.blad_wczytania}</div>`
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
// sugestia: propozycja programu (przerywana ramka) — to jeszcze nie decyzja.
// Zapisana decyzja trafia do data-decyzja: karta szarzeje i dostaje plakietkę „✓ Dokument” (CSS).
function przyciskiWyboru(obecna, wybierz, pozwolCofniecie = true, sugestia = "") {
  const wyb = document.createElement("div"); wyb.className = "wybor";
  let akt = obecna || "";
  const pokaz = () => {
    wyb.querySelectorAll("button").forEach(b => {
      b.classList.toggle("akt", b.dataset.k === akt);
      b.classList.toggle("prop", !akt && b.dataset.k === sugestia);
    });
    if (akt) wyb.dataset.decyzja = akt; else delete wyb.dataset.decyzja;
  };
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
const KAT_GDZIE = {dokument: "trafi do Dokumenty › Dokumenty z <rok>", zdjecie: "zostaje wśród zdjęć",
                   smieci: "trafi do Odłożone › Śmieci"};
function przyciskiKategorii(ids, obecna, poZmianie, sugestia = "") {
  let poprzednia = obecna || "";
  const wyb = przyciskiWyboru(obecna, async nowa => {
    const w = await api("/api/kategoria", {ids, kat: nowa});
    const bylo = poprzednia; poprzednia = nowa;
    const ile = ids.length > 1 ? ` (${plikow(ids.length)})` : "";
    toast(nowa ? `✓ Zapisano: ${KAT_NAZWY[nowa]}${ile} — ${KAT_GDZIE[nowa]}.`
               : `Usunięto decyzję${ile} — wraca propozycja programu.`, async () => {
      await api("/api/kategoria", {ids, kat: bylo}); poprzednia = bylo; wyb.ustaw(bylo);
      if (poZmianie) poZmianie(bylo);
      toast("Cofnięto."); if (typeof plan !== "undefined") plan.wczytany = false;
    });
    if (typeof plan !== "undefined") plan.wczytany = false;
    if (typeof inne !== "undefined") inne.wczytane = false;
    an.dokWczytane = false;
    if (poZmianie) poZmianie(nowa);
  }, true, sugestia);
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
  img.onerror = () => { ob.firstChild === img && img.replaceWith(IKONY[rodzaj] || "🖼️"); };
  ob.append(img, przyciskKosz(id, tytul, k));
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
// Każde kliknięcie 📷/📄/🗑 zapisuje się od razu (jak w Duplikatach i Podobnych); zdjęcie z decyzją szarzeje.
const dokZapisana = d => d.kat || (d.decyzja === 1 ? "dokument" : d.decyzja === 0 ? "zdjecie" : "");
const dokSugestia = d => d.zaznacz ? "dokument" : "zdjecie";
przyPokazaniu.dok = async () => {
  if (an.dokWczytane) return;
  const r = await api("/api/dokumenty");
  // już ułożone (z decyzją) są schowane — „↺ pokaż przejrzane” je przywraca
  const zrob = r.kandydaci.filter(k => dokZapisana(k));
  an.dok = an.dokPokazUkryte ? r.kandydaci.filter(k => !dokZapisana(k)).concat(zrob) : r.kandydaci.filter(k => !dokZapisana(k));
  an.dokUkryte = an.dokPokazUkryte ? 0 : zrob.length; an.dokPokazUkryte = false;
  an.dokIle = DOK_NA_STRONE;
  an.dokWczytane = true; rysujDokumenty();
};

const DOK_NA_STRONE = 100;
const dokWidoczne = () => an.dok.slice(0, an.dokIle || DOK_NA_STRONE);
// ułożone znikają przed wczytaniem kolejnych — na ekranie zostają tylko te do zdecydowania
function dokNastepne() {
  const zrob = an.dok.filter(dokZapisana).length;
  an.dokUkryte = (an.dokUkryte || 0) + zrob;
  an.dok = an.dok.filter(d => !dokZapisana(d)); an.dokIle = DOK_NA_STRONE;
  rysujDokumenty(); $("dok-siatka").scrollTop = 0; $("dok-siatka").scrollIntoView({block: "nearest"});
}
const kopieTxt = d => d.kopie && d.kopie.length ? ` · +${plikow(d.kopie.length, ["kopia", "kopie", "kopii"])}` : "";
function przyciskUkryte(n, akcja) {
  const b = document.createElement("button"); b.className = "maly"; b.style.marginLeft = "8px";
  b.textContent = `↺ pokaż ${n} przejrzanych`; b.onclick = akcja; return b;
}
function dokStopka() {
  const zrobione = an.dok.filter(dokZapisana).length + (an.dokUkryte || 0), razem = an.dok.length + (an.dokUkryte || 0);
  const bez = dokWidoczne().filter(d => !dokZapisana(d));
  $("dok-stopka").innerHTML = !razem ? "" :
    `<b>Przejrzane: ${zrobione} z ${razem}</b>` +
    (zrobione === razem ? " · ✓ wszystko zdecydowane" : ` · zostało ${razem - zrobione}`) +
    " · decyzja zapisuje się od razu po kliknięciu";
  if (an.dokUkryte) $("dok-stopka").append(przyciskUkryte(an.dokUkryte, () => { an.dokPokazUkryte = true; an.dokWczytane = false; przyPokazaniu.dok(); }));
  $("dok-zapisz").disabled = !bez.length;
  $("dok-zapisz").textContent = bez.length ? `Zatwierdź propozycje dla pozostałych (${bez.length})` : "Wszystko zdecydowane ✓";
}
function rysujDokumenty() {
  const s = $("dok-siatka"); s.replaceChildren(); s.classList.add("duze");
  if (!stan.analiza) s.innerHTML = BRAK_ANALIZY();
  else if (!an.dok.length) s.innerHTML = an.dokUkryte ? '<div class="pusto">✓ Wszystkie dokumenty przejrzane.</div>'
    : '<div class="pusto">Nie znaleziono zdjęć przypominających dokumenty. 🎉</div>';
  for (const d of dokWidoczne()) {
    const k = karta(d.id, "zdjecie", d.wzgledna, `${(d.data || "").slice(0, 10)} · pewność ${Math.round(d.ocena * 100)}%` + kopieTxt(d),
                    false, () => undefined, true);
    k.querySelector("input").remove(); k.onclick = null; k.style.cursor = "default";
    k.append(przyciskiKategorii([d.id, ...(d.kopie || [])], dokZapisana(d), v => { d.kat = v; d.decyzja = null; dokStopka(); dokDalej(); }, dokSugestia(d)));
    s.append(k);
  }
  dokDalej();
  dokStopka();
}
// „Schowaj przejrzane i pokaż kolejne” — odświeżany przy każdej decyzji (bez przerysowania kart)
function dokDalej() {
  const s = $("dok-siatka"); s.querySelectorAll(":scope > .wiecej").forEach(b => b.remove());
  const zrobione = dokWidoczne().filter(dokZapisana).length;
  const reszta = an.dok.length - dokWidoczne().length;
  if (!(reszta > 0 || zrobione)) return;
  const b = document.createElement("button"); b.className = "wiecej"; b.style.gridColumn = "1/-1";
  const dalej = an.dok.filter(d => !dokZapisana(d)).length - dokWidoczne().filter(d => !dokZapisana(d)).length;
  b.textContent = zrobione ? `Schowaj przejrzane (${zrobione}) i pokaż kolejne` + (dalej > 0 ? ` (zostało ${dalej})` : "")
                           : `Pokaż kolejne ${Math.min(DOK_NA_STRONE, reszta)} (zostało ${reszta})`;
  b.onclick = () => zrobione ? dokNastepne() : (an.dokIle = (an.dokIle || DOK_NA_STRONE) + DOK_NA_STRONE, rysujDokumenty());
  s.append(b);
}
// zbiorczo — tylko zdjęcia jeszcze bez decyzji (wyświetlone); zapis od razu, z „Cofnij”
async function dokZbiorczo(kat) {
  const bez = dokWidoczne().filter(d => !dokZapisana(d));
  if (!bez.length) { toast("Wszystkie wyświetlone zdjęcia mają już decyzję."); return; }
  const wybor = {}, bylo = {};
  for (const d of bez) for (const id of [d.id, ...(d.kopie || [])]) { wybor[id] = kat || dokSugestia(d); bylo[id] = ""; }
  try {
    const w = await api("/api/nie-z-aparatu/zapisz", {wybor});
    const n = Object.values(wybor).filter(k => k === "dokument").length;
    toast(`✓ Zapisano ${plikow(w.zapisane, ["decyzję", "decyzje", "decyzji"])}: dokumenty ${n}, zdjęcia ${Object.keys(wybor).length - n}.` +
          (w.plan && w.plan.zmienione ? ` Przełożono w drzewie: ${plikow(w.plan.zmienione)}.` : ""), () => cofnijZapis(bylo));
    if (typeof inne !== "undefined") inne.wczytane = false;
    for (const d of bez) { d.kat = wybor[d.id]; d.decyzja = null; }
    plan.wczytany = false; dokNastepne();  // zatwierdzone znikają — od razu następne do przejrzenia
    stan = await api("/api/stan"); rysuj();
  } catch (e) { toast(e.message); }
}
$("dok-wszystkie").onclick = () => dokZbiorczo("dokument");
$("dok-zadne").onclick = () => dokZbiorczo("zdjecie");
$("dok-zapisz").onclick = () => dokZbiorczo("");

// ---------- podobne / nieostre ----------
przyPokazaniu.pod = async () => { if (!an.podWczytane) await wczytajPodobne(); };

async function wczytajPodobne(wiecej) {
  if (an.tryb === "podobne") {
    const r = await api(`/api/podobne?od=${wiecej ? an.grupy.length : 0}&ile=30`);
    an.grupy = wiecej ? an.grupy.concat(r.grupy) : r.grupy; an.razem = r.razem; an.przejrzane = r.przejrzane || 0;
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
    if (an.przejrzane) {
      const a = document.createElement("button"); a.className = "maly"; a.style.marginLeft = "8px";
      a.textContent = `↺ pokaż ${an.przejrzane} przejrzanych`;
      a.onclick = async () => { await api("/api/przejrzane", {rodzaj: "podobne", klucze: [], wartosc: false}); an.podWczytane = false; wczytajPodobne(); };
      $("pod-info").append(a);
    }
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
        z.textContent = (i === 0 ? "★ " : "") + (zost ? "zostaje" : "odłożę") + (w.kopia ? " · = identyczna kopia" : "");
        if (w.kopia) z.title = "Ten sam plik co inne zdjęcie w tej grupie (bajt w bajt) — spokojnie do odłożenia";
        const gora = document.createElement("div"); gora.className = "gora"; gora.append(c, z);
        const op = document.createElement("span"); op.className = "zn2"; op.textContent = opisZdjecia(w);
        r.append(gora, img, sc, op, przyciskiKategorii([w.id], w.kat, v => { w.kat = v; }),
                 przyciskKosz(w.id, w.wzgledna, r, "na-zdj"));
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
  const pomPod = an.tryb === "podobne" ? an.grupy.filter(g => (an.decyzje.get(g.map(w => w.id).join("-")) || {}).pomin).length : 0;
  $("pod-odloz").disabled = !doOdl.length && !pomPod;
  $("pod-odloz").textContent = an.tryb === "podobne" ? (doOdl.length ? "Odłóż zaznaczone kopie i pokaż kolejne" : "Oznacz jako przejrzane i pokaż kolejne") : "Odłóż zaznaczone";
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
// Duży podgląd: kółko = powiększenie (do kursora), przeciąganie, dwuklik; z listą — ‹ › i strzałki między plikami
// (np. wszystkie kopie w grupie duplikatów). lista: [{id, nazwa}]
function podgladDuzy(id, nazwa, lista = null) {
  lista = lista && lista.length ? lista : [{id, nazwa}];
  let poz = Math.max(0, lista.findIndex(x => x.id === id));
  const n = document.createElement("div"); n.className = "nakladka"; n.dataset.podglad = "1";
  const img = new Image();
  img.style.cssText = "max-width:90vw;max-height:82vh;border-radius:8px;background:#000;transform-origin:0 0";
  img.title = "Kółko myszy = powiększenie · przeciągnij, żeby przesunąć · kliknij obok albo Esc, żeby zamknąć";
  const podpis = document.createElement("div");
  podpis.style.cssText = "position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:rgba(0,0,0,.65);color:#fff;" +
    "padding:6px 14px;border-radius:999px;font-size:13px;max-width:90vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
  const kosz = przyciskKosz(id, nazwa, null);
  kosz.style.cssText = "position:fixed;top:16px;right:16px;width:auto;height:auto;padding:8px 14px;font-size:14px;opacity:1";
  kosz.textContent = "🗑 Usuń";
  kosz.onclick = e => { e.stopPropagation(); zamknij(); usunWProjekcie([lista[poz].id], lista[poz].nazwa, null); };
  const strzalka = (znak, d) => {
    const b = document.createElement("button"); b.textContent = znak; b.title = d < 0 ? "Poprzedni (←)" : "Następny (→)";
    b.style.cssText = `position:fixed;top:50%;${d < 0 ? "left" : "right"}:16px;transform:translateY(-50%);width:48px;height:48px;` +
      "border-radius:999px;border:0;background:rgba(255,255,255,.15);color:#fff;font-size:26px;cursor:pointer";
    b.onclick = e => { e.stopPropagation(); idz(d); };
    return b;
  };
  n.append(img, podpis, kosz);
  if (lista.length > 1) n.append(strzalka("‹", -1), strzalka("›", 1));
  document.body.append(n);
  const z = {s: 1, x: 0, y: 0, ciagnie: null, ruszyl: false};
  const rysuj = () => { img.style.transform = z.s === 1 ? "" : `translate(${z.x}px,${z.y}px) scale(${z.s})`;
                        img.style.cursor = z.s > 1 ? "grab" : "zoom-in"; };
  function pokaz() {
    const p = lista[poz];
    img.src = `/miniatura?t=${encodeURIComponent(TOKEN)}&id=${p.id}&duza=1`; img.alt = p.nazwa || "";
    podpis.textContent = (lista.length > 1 ? `${poz + 1} / ${lista.length} · ` : "") + "\u200E" + (p.nazwa || "");
    z.s = 1; z.x = 0; z.y = 0; rysuj();
  }
  function idz(d) { poz = (poz + d + lista.length) % lista.length; pokaz(); }
  const ustaw = (s, px, py) => {
    s = Math.min(8, Math.max(1, s)); const r = img.getBoundingClientRect();
    const cx = px - r.left, cy = py - r.top;
    z.x += cx - cx * s / z.s; z.y += cy - cy * s / z.s; z.s = s; if (s === 1) { z.x = 0; z.y = 0; }
    rysuj();
  };
  n.addEventListener("wheel", e => { e.preventDefault(); ustaw(z.s * Math.exp(-e.deltaY * 0.0022), e.clientX, e.clientY); },
                     {passive: false});
  img.ondblclick = e => { e.stopPropagation(); ustaw(z.s > 1 ? 1 : 2.5, e.clientX, e.clientY); };
  img.onpointerdown = e => { e.preventDefault(); z.ciagnie = {x: e.clientX, y: e.clientY}; z.ruszyl = false; img.setPointerCapture(e.pointerId); };
  img.onpointermove = e => {
    if (!z.ciagnie || z.s === 1) return;
    z.x += e.clientX - z.ciagnie.x; z.y += e.clientY - z.ciagnie.y; z.ciagnie = {x: e.clientX, y: e.clientY};
    z.ruszyl = true; rysuj();
  };
  img.onpointerup = () => { z.ciagnie = null; };
  const klawisze = e => {
    if (e.key === "Escape") zamknij();
    else if (e.key === "ArrowLeft" && lista.length > 1) idz(-1);
    else if (e.key === "ArrowRight" && lista.length > 1) idz(1);
    else if (e.key === "Delete") kosz.click();
    else return;
    e.preventDefault(); e.stopPropagation();
  };
  document.addEventListener("keydown", klawisze, true);
  function zamknij() { n.remove(); document.removeEventListener("keydown", klawisze, true); }
  n.onclick = e => { if (e.target === img && (z.ruszyl || z.s > 1)) return; zamknij(); };
  pokaz();
}
$("pod-filtry").onclick = e => {
  const b = e.target.closest(".filtr"); if (!b) return;
  document.querySelectorAll("#pod-filtry .filtr").forEach(x => x.classList.toggle("akt", x === b));
  an.tryb = b.dataset.r; an.podWczytane = false; wczytajPodobne();
};
$("pod-odloz").onclick = async () => {
  const ids = doOdlozenia();
  // podobne: grupy „zostaw wszystkie” znikają jako przejrzane
  const przejrzane = an.tryb === "podobne" ? an.grupy.filter(g => (an.decyzje.get(g.map(w => w.id).join("-")) || {}).pomin)
    .map(g => g.map(w => w.sciezka).sort().join("|")) : [];
  if (przejrzane.length) await api("/api/przejrzane", {rodzaj: "podobne", klucze: przejrzane});
  if (!ids.length) { toast(`Przejrzane: ${przejrzane.length} grup zostaje bez zmian.`); an.podWczytane = false; wczytajPodobne(); return; }
  if (!confirm(`Odłożyć ${ids.length} zdjęć do kosza (folder Odłożone)?\n\nNic nie jest kasowane — operację można cofnąć.`)) return;
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
  // już zdecydowane są schowane — „↺ pokaż przejrzane” je przywraca
  inne.lista = inne.pokazUkryte ? r.pliki : r.pliki.filter(p => !p.decyzja);
  inne.ukryte = inne.pokazUkryte ? 0 : r.pliki.length - inne.lista.length; inne.pokazUkryte = false;
  inne.wybor = new Map(inne.lista.filter(p => p.decyzja).map(p => [p.id, p.decyzja]));
  inne.ile = INNE_NA_STRONE; inne.wczytane = true; rysujInne();
};
const inneWidoczne = () => inne.lista.slice(0, inne.ile);
function inneNastepne() {
  const zrob = inne.lista.filter(p => inne.wybor.has(p.id)).length;
  inne.ukryte = (inne.ukryte || 0) + zrob;
  inne.lista = inne.lista.filter(p => !inne.wybor.has(p.id)); inne.ile = INNE_NA_STRONE;
  rysujInne(); $("inne-siatka").scrollIntoView({block: "nearest"});
}
function inneStopka() {
  const n = inne.lista.filter(p => inne.wybor.has(p.id)).length + (inne.ukryte || 0), razem = inne.lista.length + (inne.ukryte || 0);
  $("inne-stopka").innerHTML = !razem ? "" :
    `<b>Przejrzane: ${n} z ${razem}</b>` + (n === razem ? " · ✓ wszystko zdecydowane" : ` · zostało ${razem - n}`) +
    " · decyzja zapisuje się od razu; bez decyzji zostają w drzewie jako zdjęcia „do sprawdzenia”";
  if (inne.ukryte) $("inne-stopka").append(przyciskUkryte(inne.ukryte, () => { inne.pokazUkryte = true; inne.wczytane = false; przyPokazaniu.inne(); }));
}
function kartaInne(p) {
  const k = karta(p.id, "zdjecie", p.wzgledna, (p.data || "").slice(0, 10) + (p.szer ? ` · ${p.szer}×${p.wys}` : "") +
                  ` · ${rozmiar(p.rozmiar)}` + kopieTxt(p), false, () => undefined, true);
  k.querySelector("input").remove(); k.onclick = null; k.style.cursor = "default";
  const pw = document.createElement("div"); pw.className = "m powod"; pw.textContent = "❔ " + p.powod;
  k.querySelector(".op").append(pw);
  k.append(przyciskiKategorii([p.id, ...(p.kopie || [])], inne.wybor.get(p.id), kat => {
    kat ? inne.wybor.set(p.id, kat) : inne.wybor.delete(p.id); p.decyzja = kat || null; inneStopka(); inneDalej();
  }));
  return k;
}
function rysujInne() {
  const s = $("inne-siatka"); s.replaceChildren();
  if (!inne.lista.length) s.innerHTML = inne.ukryte ? '<div class="pusto">✓ Wszystko przejrzane.</div>'
    : '<div class="pusto">Nie ma podejrzanych obrazów — wszystko wygląda na zdjęcia z aparatu. 🎉</div>';
  for (const p of inneWidoczne()) s.append(kartaInne(p));
  inneDalej();
  inneStopka();
}
function inneDalej() {
  const s = $("inne-siatka"); s.querySelectorAll(":scope > .wiecej").forEach(b => b.remove());
  const zrobione = inneWidoczne().filter(p => inne.wybor.has(p.id)).length;
  const reszta = inne.lista.length - inneWidoczne().length;
  if (!(reszta > 0 || zrobione)) return;
  const b = document.createElement("button"); b.className = "wiecej"; b.style.gridColumn = "1/-1";
  const dalej = inne.lista.filter(p => !inne.wybor.has(p.id)).length - inneWidoczne().filter(p => !inne.wybor.has(p.id)).length;
  b.textContent = zrobione ? `Schowaj przejrzane (${zrobione}) i pokaż kolejne` + (dalej > 0 ? ` (zostało ${dalej})` : "")
                           : `Pokaż kolejne ${Math.min(INNE_NA_STRONE, reszta)} (zostało ${reszta})`;
  b.onclick = () => zrobione ? inneNastepne() : (inne.ile += INNE_NA_STRONE, rysujInne());
  s.append(b);
}
async function inneZbiorczo(kat) {
  const bez = inneWidoczne().filter(p => !inne.wybor.has(p.id));
  if (!bez.length) { toast("Wszystkie wyświetlone obrazy mają już decyzję."); return; }
  const wybor = {}, bylo = {};
  for (const p of bez) for (const id of [p.id, ...(p.kopie || [])]) { wybor[id] = kat; bylo[id] = ""; }
  try {
    const w = await api("/api/nie-z-aparatu/zapisz", {wybor});
    toast(`✓ Zapisano ${plikow(w.zapisane, ["decyzję", "decyzje", "decyzji"])}: ${KAT_NAZWY[kat]}.` +
          (w.plan && w.plan.zmienione ? ` Przełożono w drzewie: ${plikow(w.plan.zmienione)}.` : ""), () => cofnijZapis(bylo));
    for (const p of bez) { inne.wybor.set(p.id, kat); p.decyzja = kat; }
    an.dokWczytane = false; plan.wczytany = false; inneNastepne();  // zatwierdzone znikają — następne
    stan = await api("/api/stan"); rysuj();
  } catch (e) { toast(e.message); }
}
$("inne-wsz-zdj").onclick = () => inneZbiorczo("zdjecie");
$("inne-wsz-smieci").onclick = () => inneZbiorczo("smieci");
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
