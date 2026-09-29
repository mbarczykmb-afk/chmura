// Propozycja drzewa, edytor (zmiana nazw, przenoszenie, scalanie, wykluczanie, cofanie)
// oraz porządkowanie plików. Korzysta z funkcji z index.html: $, api, stan, rozmiar, toast…
"use strict";

const plan = {foldery: [], podsum: null, folder: "", pliki: [], razem: 0, zazn: new Set(), rozwiniete: new Set([""]),
              wczytany: false, q: "", filtr: "", ostatni: null, przejrzane: new Set(), przejrzaneLicz: null};

function policzPrzejrzane() {
  const doSprawdzenia = plan.foldery.filter(f => f.nowe > 0).map(f => f.sciezka);
  plan.przejrzaneLicz = {wszystkie: doSprawdzenia.length,
                         przejrzane: doSprawdzenia.filter(f => plan.przejrzane.has(f)).length,
                         kolejka: doSprawdzenia.filter(f => !plan.przejrzane.has(f))};
}

// ---------- lewa kolumna: przyciski i podsumowanie ----------
function rysujPlanLewa() {
  const p = stan.plan;
  $("generuj").disabled = zajety() || !stan.ma_wyniki || !stan.cel;
  $("generuj").textContent = p ? "Utwórz propozycję od nowa" : "Utwórz propozycję drzewa";
  $("generuj").title = !stan.cel ? "Najpierw wybierz miejsce docelowe (Dokąd?)" : "";
  rysujZadanie("plan", "zad-plan");
  rysujZadanie("wykonanie", "zad-wykonanie");
  const box = $("podsum-plan");
  box.hidden = !p;
  if (p) {
    const doZrobienia = p.kopiuj + p.przenies;
    box.innerHTML = `<div>Do skopiowania: <b>${p.kopiuj}</b> (${rozmiar(p.kopiuj_b)}) · do przeniesienia:
      <b>${p.przenies}</b> (${rozmiar(p.przenies_b)})</div>
      <div style="color:var(--mut);margin-top:4px">Już w miejscu docelowym: ${p.istniejace} · pominięte: ${p.pominiete}
      · do sprawdzenia: ${p.uwagi}${p.zrobione ? ` · uporządkowane: ${p.zrobione}` : ""}${p.bledy ? ` · <span style="color:var(--blad)">błędy: ${p.bledy}</span>` : ""}</div>
      <div class="wiersz" style="margin-top:8px"><button class="maly" id="plan-edytuj">Edytuj drzewo →</button>
      <button class="maly" id="plan-wykonaj-l" ${doZrobienia ? "" : "disabled"}>Uporządkuj pliki…</button></div>`;
    $("plan-edytuj").onclick = () => pokazZakladke("drzewo");
    $("plan-wykonaj-l").onclick = otworzWykonanie;
    $("plan-wykonaj-l").disabled = !doZrobienia || zajety();
  }
  const w = stan.wykonanie;
  $("cofnij-wyk-box").hidden = !w || zajety();
  if (w) $("cofnij-wyk-opis").textContent = `Ostatnio uporządkowano ${w.n} plików.`;
  $("licz-drzewo").hidden = !p;
  if (p) $("licz-drzewo").textContent = p.kopiuj + p.przenies;
  $("k3").className = "krok klik " + (p ? "gotowy" : (stan.ma_wyniki ? "akt" : ""));
  $("k4").className = "krok klik " + (w ? "gotowy" : (p ? "akt" : ""));
  // po zakończeniu zadania planu/wykonania odśwież edytor
  for (const n of ["plan", "wykonanie"]) {
    const z = (stan.zad || {})[n] || {};
    if (plan["trwa_" + n] && !z.trwa && zakladka === "drzewo") wczytajDrzewo();
    if (plan["trwa_" + n] && !z.trwa && n === "plan") { plan.folder = ""; plan.wczytany = false; }
    plan["trwa_" + n] = !!z.trwa;
  }
}
naStan.push(rysujPlanLewa);

$("generuj").onclick = async () => {
  if (stan.plan && (stan.plan.cofnij) &&
      !confirm("Utworzyć propozycję od nowa? Twoje zmiany w drzewie zostaną utracone.")) return;
  try { stan = await api("/api/plan/generuj", {}); rysuj(); } catch (e) { toast(e.message); }
};
$("k3").onclick = () => { if (stan.plan) pokazZakladke("drzewo"); };
$("k4").onclick = () => { if (stan.plan) otworzWykonanie(); };
$("cofnij-wyk").onclick = async () => {
  if (!confirm("Cofnąć ostatnie porządkowanie?\n\nKopie zostaną usunięte, a przeniesione pliki wrócą na swoje miejsca.")) return;
  try { stan = await api("/api/wykonanie/cofnij", {}); rysuj(); } catch (e) { toast(e.message); }
};

// ---------- wykonanie ----------
async function otworzWykonanie() {
  let s;
  try { s = await api("/api/plan/sprawdz"); } catch (e) { toast(e.message); return; }
  const p = stan.plan || {};
  const opis = $("wyk-opis");
  if (s.blad) { opis.innerHTML = ""; opis.textContent = s.blad; $("wyk-start").disabled = true; }
  else {
    opis.innerHTML = `Miejsce docelowe: <b></b><br>
      Skopiuję <b>${p.kopiuj}</b> plików (${rozmiar(p.kopiuj_b)}), przeniosę <b>${p.przenies}</b> (${rozmiar(p.przenies_b)}).<br>
      Potrzebne miejsce: <b>${rozmiar(s.potrzeba)}</b> · wolne: <b>${rozmiar(s.wolne)}</b>` +
      (s.starczy ? "" : `<br><span style="color:var(--blad)">Za mało miejsca — zwolnij miejsce albo wyklucz część plików.</span>`);
    opis.querySelector("b").textContent = s.cel;
    $("wyk-start").disabled = !s.starczy || !s.plikow;
  }
  $("okno-wyk").hidden = false;
}
$("wyk-anuluj").onclick = () => { $("okno-wyk").hidden = true; };
$("wyk-start").onclick = async () => {
  $("okno-wyk").hidden = true;
  try { stan = await api("/api/wykonaj", {usun_puste: $("wyk-puste").checked}); rysuj(); }
  catch (e) { toast(e.message); }
};
$("plan-wykonaj").onclick = otworzWykonanie;

// ---------- edytor: drzewo folderów ----------
przyPokazaniu.drzewo = () => { if (!plan.wczytany) wczytajDrzewo(); };

async function wczytajDrzewo() {
  if (!stan.plan) {
    $("plan-drzewo").innerHTML = '<div class="wezel-w pusty">Najpierw utwórz propozycję drzewa (lewa kolumna).</div>';
    $("plan-pliki").replaceChildren(); $("plan-folder").textContent = ""; return;
  }
  const r = await api("/api/plan/drzewo");
  plan.foldery = r.foldery; plan.podsum = r.podsumowanie; plan.wczytany = true;
  plan.przejrzane = new Set(r.przejrzane || []); policzPrzejrzane();
  rysujDrzewo(); rysujPasek();
  await wczytajPliki(true);
}

function zbudujHierarchie() {
  const wezly = new Map();
  const wezel = sc => {
    if (!wezly.has(sc)) {
      wezly.set(sc, {sciezka: sc, nazwa: sc.split("/").pop(), dzieci: new Set(),
                     s: {nowe: 0, istniejace: 0, pominiete: 0, uwagi: 0, konflikty: 0, rozmiar: 0}});
      if (sc !== "") { const rodzic = sc.includes("/") ? sc.slice(0, sc.lastIndexOf("/")) : ""; wezel(rodzic).dzieci.add(sc); }
    }
    return wezly.get(sc);
  };
  wezel("");
  for (const f of plan.foldery) {
    const w = wezel(f.sciezka);
    let sc = f.sciezka;
    while (true) {   // sumy w górę drzewa
      const x = wezly.get(sc);
      for (const k of Object.keys(x.s)) x.s[k] += f[k] || 0;
      if (sc === "") break;
      sc = sc.includes("/") ? sc.slice(0, sc.lastIndexOf("/")) : "";
    }
    void w;
  }
  return wezly;
}

function odznaki(s) {
  const o = [];
  if (s.nowe) o.push(`<i class="b-nowe" title="nowe pliki">${s.nowe}</i>`);
  if (s.istniejace) o.push(`<i class="b-ist" title="już są w miejscu docelowym">${s.istniejace}</i>`);
  if (s.uwagi) o.push(`<i class="b-uw" title="do sprawdzenia">${s.uwagi}</i>`);
  if (s.konflikty) o.push(`<i class="b-kol" title="ta sama nazwa — dostanie dopisek (2)">${s.konflikty}</i>`);
  if (s.pominiete) o.push(`<i class="b-pom" title="pominięte">${s.pominiete}</i>`);
  return o.join("");
}

function rysujDrzewo() {
  const wezly = zbudujHierarchie();
  const kont = $("plan-drzewo"); kont.replaceChildren();
  const celPelny = (stan.plan && stan.plan.cel) || "Miejsce docelowe";
  const cel = celPelny.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || celPelny;
  const rysuj1 = (sc, el) => {
    const w = wezly.get(sc);
    const box = document.createElement("div");
    const r = document.createElement("div"); r.className = "pw" + (sc === plan.folder ? " akt" : "");
    const dz = [...w.dzieci].sort((a, b) => a.localeCompare(b, "pl", {numeric: true}));
    const strz = document.createElement("button"); strz.className = "strz";
    strz.textContent = dz.length ? (plan.rozwiniete.has(sc) ? "▼" : "▶") : "";
    strz.onclick = e => { e.stopPropagation(); plan.rozwiniete.has(sc) ? plan.rozwiniete.delete(sc) : plan.rozwiniete.add(sc); rysujDrzewo(); };
    const n = document.createElement("span"); n.className = "nz";
    n.textContent = (sc === "" ? "💾 " : "📁 ") + (sc === "" ? cel : w.nazwa); n.title = sc || celPelny;
    const o = document.createElement("span"); o.className = "odz"; o.innerHTML = odznaki(w.s);
    r.append(strz, n);
    if (plan.przejrzane.has(sc)) { const ok = document.createElement("span"); ok.className = "ok"; ok.textContent = "✓"; ok.title = "Przejrzany"; r.append(ok); }
    r.append(o);
    r.onclick = () => {
      plan.folder = sc; plan.rozwiniete.add(sc); plan.q = ""; plan.filtr = "";
      $("plan-q").value = ""; $("plan-filtr").value = ""; rysujDrzewo(); wczytajPliki(true);
    };
    // przeciąganie folderów i upuszczanie plików/folderów
    if (sc !== "" && w.s.nowe + w.s.pominiete > 0) {
      r.draggable = true;
      r.ondragstart = e => { e.dataTransfer.setData("text/katalogator-folder", sc); e.dataTransfer.effectAllowed = "move"; };
    }
    r.ondragover = e => { e.preventDefault(); r.classList.add("cel-drop"); };
    r.ondragleave = () => r.classList.remove("cel-drop");
    r.ondrop = async e => {
      e.preventDefault(); r.classList.remove("cel-drop");
      const folder = e.dataTransfer.getData("text/katalogator-folder");
      const pliki = e.dataTransfer.getData("text/katalogator-pliki");
      if (folder && folder !== sc) {
        const nowa = (sc ? sc + "/" : "") + folder.split("/").pop();
        await edycja("/api/plan/zmien-nazwe", {stara: folder, nowa});
        if (plan.folder === folder) plan.folder = nowa;
        wczytajPliki(true);
      } else if (pliki) {
        await edycja("/api/plan/przenies", {ids: JSON.parse(pliki), folder: sc});
      }
    };
    box.append(r);
    if (dz.length && plan.rozwiniete.has(sc)) {
      const d = document.createElement("div"); d.className = "pd";
      for (const c of dz) rysuj1(c, d);
      box.append(d);
    }
    el.append(box);
  };
  rysuj1("", kont);
  const lista = $("lista-folderow"); lista.replaceChildren();
  for (const sc of [...wezly.keys()].sort()) if (sc) { const o = document.createElement("option"); o.value = sc; lista.append(o); }
}

function rysujPasek() {
  const p = plan.podsum || stan.plan || {};
  $("plan-cofnij").disabled = !p.cofnij; $("plan-ponow").disabled = !p.ponow;
  $("plan-opis-op").textContent = p.cofnij ? "Ostatnio: " + p.cofnij.opis : "";
  $("plan-stopka").textContent = stan.plan ? `Do skopiowania ${stan.plan.kopiuj} · do przeniesienia ${stan.plan.przenies}` +
    ` · ${rozmiar((stan.plan.kopiuj_b || 0) + (stan.plan.przenies_b || 0))}` : "";
  $("plan-wykonaj").disabled = !stan.plan || !(stan.plan.kopiuj + stan.plan.przenies) || zajety();
}
naStan.push(() => { if (zakladka === "drzewo") rysujPasek(); });

// ---------- edytor: pliki w folderze ----------
function trybSzukania() { return !!(plan.q || plan.filtr); }
async function wczytajPliki(odNowa) {
  if (odNowa) { plan.pliki = []; plan.zazn.clear(); plan.ostatni = null; }
  const r = trybSzukania()
    ? await api(`/api/plan/szukaj?q=${encodeURIComponent(plan.q)}&filtr=${plan.filtr}&od=${plan.pliki.length}&ile=200`)
    : await api(`/api/plan/pliki?folder=${encodeURIComponent(plan.folder)}&od=${plan.pliki.length}&ile=200`);
  plan.pliki = plan.pliki.concat(r.pliki); plan.razem = r.razem;
  rysujPliki();
}

function rysujPliki() {
  const szuk = trybSzukania();
  const celPelny = (stan.plan && stan.plan.cel) || "";
  $("plan-folder").textContent = szuk ? `🔍 Wyniki: ${plan.razem}` :
    (plan.folder || celPelny.split(/[\\/]/).filter(Boolean).pop() || "Miejsce docelowe");
  $("plan-folder").title = szuk ? "" : (plan.folder || celPelny);
  const korzen = plan.folder === "" || szuk;
  for (const id of ["f-zmien", "f-przenies", "f-wyklucz", "f-przywroc"]) $(id).disabled = korzen;
  const przejrz = plan.przejrzane.has(plan.folder);
  $("f-przejrzany").disabled = szuk || !plan.pliki.some(f => f.tryb !== "istniejacy");
  $("f-przejrzany").textContent = przejrz ? "✓ Przejrzany (cofnij)" : "✓ Oznacz jako przejrzany";
  const lz = plan.przejrzaneLicz;
  $("f-nastepny").disabled = !lz || !lz.kolejka.length;
  $("f-nastepny").textContent = lz ? `Następny → (${lz.przejrzane}/${lz.wszystkie})` : "Następny →";
  const s = $("plan-pliki"); s.replaceChildren(); s.classList.add("duze");
  if (!plan.pliki.length) {
    s.innerHTML = '<div class="pusto">W tym folderze nie ma bezpośrednio plików — wybierz podfolder.</div>';
  }
  for (const [idx, f] of plan.pliki.entries()) {
    const k = document.createElement("div");
    const ist = f.tryb === "istniejacy";
    k.className = "karta duza" + (plan.zazn.has(f.id) ? " zazn" : "") + (f.pominiety ? " pom" : "") + (ist ? " ist" : "");
    k.title = (ist ? "Już jest w miejscu docelowym:\n" : "Źródło:\n") + f.sciezka + (f.uwaga ? "\n\n" + f.uwaga : "");
    const ob = document.createElement("div"); ob.className = "ob";
    if (f.rodzaj === "zdjecie" && f.plik_id != null) {
      const img = new Image(); img.loading = "lazy"; img.alt = "";
      img.src = `/miniatura?t=${encodeURIComponent(TOKEN)}&id=${f.plik_id}&srednia=1`;
      img.onerror = () => { ob.textContent = IKONY.zdjecie; };
      img.draggable = false;  // przeciąga się kartę, nie obrazek
      img.ondblclick = e => { e.stopPropagation(); podgladDuzy(f.plik_id, f.nazwa); };
      ob.append(img);
    } else if (f.rodzaj === "film" && f.plik_id != null) {
      ob.append(podgladFilmu(f.plik_id));
    } else ob.textContent = IKONY[f.rodzaj] || "📄";
    const op = document.createElement("div"); op.className = "op";
    const n = document.createElement("div"); n.className = "n"; n.textContent = f.nazwa;
    const m = document.createElement("div"); m.className = "m";
    m.textContent = (f.data ? f.data.slice(0, 10) : "") + " · " + rozmiar(f.rozmiar);
    op.append(n, m);
    if (szuk) {
      const fo = document.createElement("div"); fo.className = "m"; fo.textContent = "📁 " + (f.cel.includes("/") ? f.cel.slice(0, f.cel.lastIndexOf("/")) : "/");
      fo.title = f.cel; op.append(fo);
    }
    if (f.wynik && f.wynik.startsWith("blad")) {
      const b = document.createElement("div"); b.className = "m bl"; b.textContent = "⚠ " + f.wynik.slice(6); op.append(b);
    } else if (f.wynik === "ok") {
      const b = document.createElement("div"); b.className = "m"; b.style.color = "var(--ok)"; b.textContent = "✓ uporządkowany"; op.append(b);
    } else if (f.uwaga) {
      const u = document.createElement("div"); u.className = "m uw"; u.textContent = "🔵 " + f.uwaga; op.append(u);
    }
    k.append(ob, op);
    if (!ist) {
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = plan.zazn.has(f.id);
      cb.onclick = e => e.stopPropagation();
      cb.onchange = () => { cb.checked ? plan.zazn.add(f.id) : plan.zazn.delete(f.id); plan.ostatni = idx; rysujPliki(); };
      const zn = document.createElement("span"); zn.className = "zn " + (f.tryb === "przenies" ? "p" : "k");
      zn.textContent = f.pominiety ? "pominięty" : (f.tryb === "przenies" ? "P" : "K");
      k.append(cb, zn);
      k.onclick = e => {
        if (e.shiftKey && plan.ostatni != null) {   // zaznaczenie zakresu
          const [a, b] = [Math.min(plan.ostatni, idx), Math.max(plan.ostatni, idx)];
          plan.pliki.slice(a, b + 1).forEach(x => { if (x.tryb !== "istniejacy") plan.zazn.add(x.id); });
        } else plan.zazn.has(f.id) ? plan.zazn.delete(f.id) : plan.zazn.add(f.id);
        plan.ostatni = idx; rysujPliki();
      };
      k.draggable = true;
      k.ondragstart = e => {
        const ids = plan.zazn.has(f.id) ? [...plan.zazn] : [f.id];
        e.dataTransfer.setData("text/katalogator-pliki", JSON.stringify(ids)); e.dataTransfer.effectAllowed = "move";
      };
    } else {
      const zn = document.createElement("span"); zn.className = "zn"; zn.textContent = "już jest"; k.append(zn);
    }
    s.append(k);
  }
  if (plan.pliki.length < plan.razem) {
    const b = document.createElement("button"); b.className = "wiecej";
    b.textContent = `Pokaż więcej (${plan.razem - plan.pliki.length})`; b.onclick = () => wczytajPliki(false);
    s.append(b);
  }
  $("akcje-zazn").hidden = !plan.zazn.size;
  $("ile-zazn").textContent = `Zaznaczono: ${plan.zazn.size}`;
}

// Klatka z filmu (przeglądarka czyta tylko początek pliku); dwuklik = odtwarzanie
function podgladFilmu(id) {
  const v = document.createElement("video");
  v.muted = true; v.preload = "metadata"; v.playsInline = true;
  v.src = `/plik?t=${encodeURIComponent(TOKEN)}&id=${id}#t=1`;
  v.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover";
  const znak = document.createElement("span"); znak.textContent = "▶";
  znak.style.cssText = "position:absolute;bottom:6px;left:8px;font-size:16px;color:#fff;text-shadow:0 0 4px #000";
  const box = document.createElement("div"); box.style.cssText = "position:absolute;inset:0";
  v.onerror = () => { box.replaceChildren(); box.style.cssText = "display:grid;place-items:center;font-size:34px"; box.textContent = IKONY.film; };
  box.ondblclick = e => { e.stopPropagation(); odtworz(id); };
  box.append(v, znak);
  return box;
}
function odtworz(id) {
  const n = document.createElement("div"); n.className = "nakladka"; n.dataset.podglad = "1";
  const v = document.createElement("video"); v.controls = true; v.autoplay = true;
  v.src = `/plik?t=${encodeURIComponent(TOKEN)}&id=${id}`;
  v.style.cssText = "max-width:90vw;max-height:85vh;border-radius:8px;background:#000";
  n.append(v); n.onclick = e => { if (e.target === n) { v.pause(); n.remove(); } };
  document.body.append(n);
}

// ---------- operacje ----------
async function edycja(sciezka, dane) {
  let w;
  try { w = await api(sciezka, dane); }
  catch (e) { toast(e.message); return null; }
  const cofalne = !/\/(cofnij|ponow)$/.test(sciezka);
  const cofnijTo = cofalne ? () => edycja("/api/plan/cofnij", {}) : null;
  if (w.scalono) toast("Scalono z istniejącym folderem.", cofnijTo);
  else if (w.foldery) toast(`Zmieniono: ${plikow(w.zmienione)}` + (w.pominiete ? ` (pominięto ${w.pominiete} — to nie zdjęcia/filmy lub brak daty)` : "") + ".", cofnijTo);
  else if (!cofalne && w.opis) toast((sciezka.endsWith("cofnij") ? "Cofnięto: " : "Ponowiono: ") + w.opis);
  else if (cofalne && w.zmienione) toast(`Zmieniono: ${plikow(w.zmienione)}.`, cofnijTo);
  plan.zazn.clear();
  const r = await api("/api/plan/drzewo");
  plan.foldery = r.foldery; plan.podsum = r.podsumowanie;
  plan.przejrzane = new Set(r.przejrzane || []); policzPrzejrzane();
  if (!plan.foldery.some(f => f.sciezka === plan.folder || f.sciezka.startsWith(plan.folder + "/")) && plan.folder) {
    plan.folder = plan.folder.includes("/") ? plan.folder.slice(0, plan.folder.lastIndexOf("/")) : "";
  }
  rysujDrzewo(); await wczytajPliki(true);
  stan = await api("/api/stan"); rysuj(); rysujPasek();
  return w;
}

function zapytajFolder(tytul, opis, poczatek) {
  return new Promise(ok => {
    $("okno-folder-tytul").textContent = tytul; $("okno-folder-opis").textContent = opis;
    const inp = $("okno-folder-sciezka"); inp.value = poczatek || "";
    $("okno-folder").hidden = false; setTimeout(() => { inp.focus(); inp.select(); }, 30);
    const koniec = w => { $("okno-folder").hidden = true; $("okno-folder-ok").onclick = null; inp.onkeydown = null; ok(w); };
    $("okno-folder-ok").onclick = () => koniec(inp.value.trim().replace(/^\/+|\/+$/g, ""));
    $("okno-folder-anuluj").onclick = () => koniec(null);
    inp.onkeydown = e => { if (e.key === "Enter") $("okno-folder-ok").click(); if (e.key === "Escape") koniec(null); };
  });
}

$("f-zmien").onclick = async () => {
  const stara = plan.folder;
  const rodzic = stara.includes("/") ? stara.slice(0, stara.lastIndexOf("/")) : "";
  const nazwa = prompt("Nowa nazwa folderu:", stara.split("/").pop());
  if (!nazwa || nazwa === stara.split("/").pop()) return;
  const nowa = (rodzic ? rodzic + "/" : "") + nazwa.replace(/[\\/]/g, "_");
  if (await edycja("/api/plan/zmien-nazwe", {stara, nowa})) { plan.folder = nowa; wczytajPliki(true); rysujDrzewo(); }
};
$("f-przenies").onclick = async () => {
  const stara = plan.folder;
  const cel = await zapytajFolder("Przenieś folder", `Przenoszę „${stara.split("/").pop()}” do:`,
                                  stara.includes("/") ? stara.slice(0, stara.lastIndexOf("/")) : "");
  if (cel === null) return;
  const nowa = (cel ? cel + "/" : "") + stara.split("/").pop();
  if (await edycja("/api/plan/zmien-nazwe", {stara, nowa})) { plan.folder = nowa; wczytajPliki(true); rysujDrzewo(); }
};
$("f-wyklucz").onclick = () => edycja("/api/plan/wyklucz", {folder: plan.folder, wartosc: true});
$("f-przywroc").onclick = () => edycja("/api/plan/wyklucz", {folder: plan.folder, wartosc: false});
$("z-przenies").onclick = async () => {
  const cel = await zapytajFolder("Przenieś do folderu", `Przenoszę ${plan.zazn.size} zaznaczonych plików do:`, plan.folder);
  if (cel !== null) edycja("/api/plan/przenies", {ids: [...plan.zazn], folder: cel});
};
$("z-nowy").onclick = async () => {
  const cel = await zapytajFolder("Nowy folder z zaznaczonych", `Utworzę folder i przeniosę do niego ${plan.zazn.size} plików:`,
                                  (plan.folder ? plan.folder + "/" : "") + "Nowy folder");
  if (cel) edycja("/api/plan/przenies", {ids: [...plan.zazn], folder: cel});
};
$("z-wyklucz").onclick = () => edycja("/api/plan/wyklucz", {ids: [...plan.zazn], wartosc: true});
$("z-przywroc").onclick = () => edycja("/api/plan/wyklucz", {ids: [...plan.zazn], wartosc: false});
$("z-odznacz").onclick = () => { plan.zazn.clear(); rysujPliki(); };
$("f-przejrzany").onclick = async () => {
  const wart = !plan.przejrzane.has(plan.folder);
  try {
    await api("/api/plan/przejrzany", {folder: plan.folder, wartosc: wart});
    wart ? plan.przejrzane.add(plan.folder) : plan.przejrzane.delete(plan.folder);
    policzPrzejrzane(); rysujDrzewo(); rysujPliki(); rysujProjekt();
    if (wart && plan.przejrzaneLicz.kolejka.length) toast("Przejrzane. „Następny →” przeniesie Cię do kolejnego folderu.");
    else if (wart) toast("Wszystkie foldery przejrzane! 🎉 Możesz uporządkować pliki.");
  } catch (e) { toast(e.message); }
};
$("f-nastepny").onclick = () => {
  const lz = plan.przejrzaneLicz; if (!lz || !lz.kolejka.length) return;
  const nast = lz.kolejka.find(f => f.localeCompare(plan.folder, "pl", {numeric: true}) > 0) || lz.kolejka[0];
  plan.folder = nast; plan.q = ""; plan.filtr = ""; $("plan-q").value = ""; $("plan-filtr").value = "";
  let x = nast; while (x.includes("/")) { x = x.slice(0, x.lastIndexOf("/")); plan.rozwiniete.add(x); }
  rysujDrzewo(); wczytajPliki(true);
};
$("f-wszystkie").onclick = () => { plan.pliki.forEach(f => { if (f.tryb !== "istniejacy") plan.zazn.add(f.id); }); rysujPliki(); };
$("z-miejsce").onclick = () => {
  const m = prompt(`Miejsce dla ${plan.zazn.size} zaznaczonych zdjęć/filmów (np. Hel, Zakopane, dom).\n` +
                   "Pliki trafią do folderów „<Miesiąc> na Helu” według swojej daty.", "");
  if (m && m.trim()) edycja("/api/plan/ustaw-miejsce", {ids: [...plan.zazn], miejsce: m.trim()});
};
$("z-data").onclick = () => {
  const d = prompt(`Nowa data dla ${plan.zazn.size} zaznaczonych (RRRR-MM-DD albo RRRR-MM).\n` +
                   "Zmieni się tylko miejsce w drzewie (rok/miesiąc) — plik nie jest modyfikowany.", "");
  if (d && d.trim()) edycja("/api/plan/ustaw-date", {ids: [...plan.zazn], data: d.trim()});
};
let czasSzukania = null;
$("plan-q").oninput = () => {
  clearTimeout(czasSzukania);
  czasSzukania = setTimeout(() => { plan.q = $("plan-q").value.trim(); wczytajPliki(true); }, 300);
};
$("plan-filtr").onchange = () => { plan.filtr = $("plan-filtr").value; wczytajPliki(true); };
$("plan-cofnij").onclick = () => edycja("/api/plan/cofnij", {});
$("plan-ponow").onclick = () => edycja("/api/plan/ponow", {});
$("pelny-ekran").onclick = () => {
  document.body.classList.toggle("pelny");
  $("pelny-ekran").textContent = document.body.classList.contains("pelny") ? "⤡ Pokaż ustawienia" : "⤢ Pełny ekran";
};
document.addEventListener("keydown", e => {
  if (zakladka !== "drzewo" || !(e.ctrlKey || e.metaKey) || e.target.tagName === "INPUT") return;
  if (e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); if (!$("plan-cofnij").disabled) $("plan-cofnij").click(); }
  if (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey)) {
    e.preventDefault(); if (!$("plan-ponow").disabled) $("plan-ponow").click();
  }
});
