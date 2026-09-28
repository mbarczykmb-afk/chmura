// Projekty (praca na kilka dni), notatki, dziennik i folder przychodzący z harmonogramem.
"use strict";

const proj = {notatkiZmienione: false, dziennikCzas: 0, idPoprzedni: null};

function czasPL(t) {
  return new Date(t * 1000).toLocaleString("pl-PL", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"});
}

// ---------- nagłówek i sekcja „Projekt” ----------
function rysujProjekt() {
  const p = stan.projekt || {};
  $("projekt-nazwa").textContent = p.nazwa || "…";
  $("proj-tytul").textContent = p.nazwa || "";
  document.title = (p.nazwa ? p.nazwa + " — " : "") + "Katalogator";
  if (proj.idPoprzedni !== p.id) {           // przełączono projekt: odśwież wszystko
    proj.idPoprzedni = p.id;
    $("proj-notatki").value = p.notatki || "";
    $("proj-dom").value = p.dom || "";
    plan.wczytany = false; plan.folder = ""; an.dokWczytane = false; an.podWczytane = false; dupGrupy = [];
    pokazRaport(); wczytajDziennik();
    if (przyPokazaniu[zakladka]) przyPokazaniu[zakladka]();
  }
  const pl = stan.plan;
  const opis = [];
  if (stan.ma_wyniki) opis.push(stan.zrodla.length + " folder(y) źródłowe");
  if (pl) opis.push(`propozycja: ${pl.kopiuj + pl.przenies} plików do uporządkowania, uporządkowano ${pl.zrobione}`);
  $("proj-postep-opis").textContent = opis.join(" · ") || "Nowy projekt — zacznij od wybrania folderów poniżej.";
  const pr = plan.przejrzaneLicz;
  $("proj-postep").hidden = !(pl && pr && pr.wszystkie);
  if (pr && pr.wszystkie) {
    $("proj-postep").firstChild.style.width = (100 * pr.przejrzane / pr.wszystkie) + "%";
    $("proj-postep").title = `Przejrzano ${pr.przejrzane} z ${pr.wszystkie} folderów`;
    $("proj-postep-opis").textContent += ` · przejrzano ${pr.przejrzane}/${pr.wszystkie} folderów`;
  }
  // co 15 s odśwież dziennik
  if (Date.now() - proj.dziennikCzas > 15000) wczytajDziennik();
}
naStan.push(rysujProjekt);

async function wczytajDziennik() {
  proj.dziennikCzas = Date.now();
  try {
    const r = await api("/api/projekt/dziennik");
    const d = $("proj-dziennik"); d.replaceChildren();
    if (!r.wpisy.length) d.textContent = "Jeszcze nic się nie wydarzyło.";
    for (const w of r.wpisy) {
      const x = document.createElement("div");
      const b = document.createElement("b"); b.textContent = czasPL(w.czas) + " ";
      x.append(b, w.opis); d.append(x);
    }
  } catch (e) { /* okno mogło się zamknąć */ }
}

let czasNotatek = null;
$("proj-notatki").oninput = () => {
  clearTimeout(czasNotatek);
  czasNotatek = setTimeout(() => api("/api/projekty/zmien", {notatki: $("proj-notatki").value}).catch(e => toast(e.message)), 700);
};
$("proj-dom").onchange = async () => {
  try { await api("/api/projekty/zmien", {dom: $("proj-dom").value.trim()}); toast("Zapisano miejsce zamieszkania."); }
  catch (e) { toast(e.message); }
};

// ---------- okno projektów ----------
async function rysujListeProjektow() {
  const r = await api("/api/projekty");
  const l = $("lista-proj"); l.replaceChildren();
  for (const p of r.projekty) {
    const k = document.createElement("div"); k.className = "proj" + (p.id === r.biezacy ? " akt" : "");
    const nz = document.createElement("div"); nz.className = "nz"; nz.textContent = p.nazwa;
    const s = p.statystyki || {};
    const inf = document.createElement("div"); inf.className = "inf";
    inf.textContent = [p.ostatnio ? "ostatnio " + czasPL(p.ostatnio) : "", s.pliki ? `${s.pliki} plików, ${rozmiar(s.rozmiar)}` : "bez skanu",
                       s.foldery ? `przejrzano ${s.przejrzane}/${s.foldery} folderów` : "", s.uporzadkowane ? `uporządkowano ${s.uporzadkowane}` : "",
                       p.cel ? "→ " + p.cel : ""].filter(Boolean).join(" · ");
    if (p.notatki) { const n = document.createElement("div"); n.className = "inf"; n.textContent = "📝 " + p.notatki.slice(0, 140); inf.after(n); k.append(nz, inf, n); }
    else k.append(nz, inf);
    if (s.foldery) {
      const pp = document.createElement("div"); pp.className = "postep-proj inf";
      pp.innerHTML = `<i style="width:${100 * s.przejrzane / s.foldery}%"></i>`; k.append(pp);
    }
    const ak = document.createElement("div"); ak.className = "akcje";
    const otw = document.createElement("button"); otw.className = "maly"; otw.textContent = p.id === r.biezacy ? "Otwarty" : "Otwórz";
    otw.disabled = p.id === r.biezacy;
    otw.onclick = async () => {
      try { stan = await api("/api/projekty/otworz", {id: p.id}); $("okno-proj").hidden = true; rysuj(); toast("Otwarto projekt: " + p.nazwa); }
      catch (e) { toast(e.message); }
    };
    const zm = document.createElement("button"); zm.className = "maly"; zm.textContent = "Zmień nazwę";
    zm.onclick = async () => {
      const n = prompt("Nowa nazwa projektu:", p.nazwa);
      if (n && n.trim()) { await api("/api/projekty/zmien", {id: p.id, nazwa: n.trim()}); stan = await api("/api/stan"); rysuj(); rysujListeProjektow(); }
    };
    const us = document.createElement("button"); us.className = "maly"; us.textContent = "Usuń";
    us.onclick = async () => {
      if (!confirm(`Usunąć projekt „${p.nazwa}”?\n\nUsunę tylko dane projektu (ustawienia, skan, propozycję, historię). ` +
                   "Twoje zdjęcia i pliki NIE zostaną ruszone.")) return;
      try { stan = await api("/api/projekty/usun", {id: p.id}); rysuj(); rysujListeProjektow(); } catch (e) { toast(e.message); }
    };
    ak.append(otw, zm, us); k.append(ak); l.append(k);
  }
}
$("projekt-btn").onclick = () => { $("okno-proj").hidden = false; rysujListeProjektow(); };
$("okno-proj-zamknij").onclick = () => { $("okno-proj").hidden = true; };
$("okno-proj").onclick = e => { if (e.target === $("okno-proj")) $("okno-proj").hidden = true; };
$("nowy-proj-ok").onclick = async () => {
  const n = $("nowy-proj").value.trim();
  if (!n) { $("nowy-proj").focus(); return; }
  try { stan = await api("/api/projekty/nowy", {nazwa: n}); $("nowy-proj").value = ""; $("okno-proj").hidden = true; rysuj(); toast("Utworzono projekt: " + n); }
  catch (e) { toast(e.message); }
};
$("nowy-proj").onkeydown = e => { if (e.key === "Enter") $("nowy-proj-ok").click(); };

// ---------- folder przychodzący ----------
function rysujPrzychodzace() {
  const p = stan.projekt || {};
  const lista = $("przych-lista"); lista.replaceChildren();
  const foldery = p.przychodzace || [];
  if (!foldery.length) lista.innerHTML = '<div class="pusto">Nie dodano jeszcze folderu przychodzącego.</div>';
  foldery.forEach(f => lista.append(wierszFolderu(f, () =>
    zapisz({zrodla: stan.zrodla, cel: stan.cel, przychodzace: foldery.filter(x => x !== f)}))));
  $("przych-sprawdz").disabled = zajety() || !foldery.length || !stan.cel;
  $("przych-sprawdz").title = !stan.cel ? "Najpierw wybierz bibliotekę w sekcji „Dokąd?”" : "";
  rysujZadanie("przychodzace", "zad-przychodzace");
  const s = stan.przychodzace, box = $("przych-podsum");
  const z = (stan.zad || {}).przychodzace || {};
  box.hidden = !s || z.trwa;
  if (s) {
    const f = s.foldery.map(x => `<div>📁 ${x.folder.replace(/&/g, "&amp;").replace(/</g, "&lt;")} — <b>${x.n}</b></div>`).join("");
    box.innerHTML = s.przenies
      ? `<div>Do przeniesienia: <b>${s.przenies}</b> plików (${rozmiar(s.przenies_b)})</div>
         <div style="margin:6px 0;font-size:12px;max-height:120px;overflow:auto">${f}</div>
         ${s.pominiete ? `<div style="color:var(--mut)">Zostaje do ręcznego przejrzenia: ${s.pominiete}</div>` : ""}
         <div class="wiersz" style="margin-top:8px"><button class="maly" id="przych-wykonaj">Przenieś do biblioteki</button></div>`
      : `Brak nowych plików do przeniesienia.${s.pominiete ? ` Do ręcznego przejrzenia: ${s.pominiete}.` : ""}`;
    const b = document.getElementById("przych-wykonaj");
    if (b) b.onclick = async () => {
      if (!confirm(`Przenieść ${s.przenies} plików do biblioteki?\n\nKażda kopia jest sprawdzana, operację można cofnąć.`)) return;
      try { stan = await api("/api/przychodzace/wykonaj", {}); rysuj(); } catch (e) { toast(e.message); }
    };
    if (s.ostatnie && !z.trwa) {
      const c = document.createElement("div"); c.className = "cofnij";
      c.innerHTML = `<span>Ostatnio przeniesiono ${s.ostatnie.n} plików.</span>`;
      const cb = document.createElement("button"); cb.className = "maly"; cb.textContent = "Cofnij";
      cb.onclick = async () => {
        if (!confirm("Cofnąć ostatnie przeniesienie z folderu przychodzącego?")) return;
        try { stan = await api("/api/przychodzace/cofnij", {}); rysuj(); } catch (e) { toast(e.message); }
      };
      c.append(cb); box.append(c);
    }
  }
  const h = p.harmonogram;
  $("przych-harm-opis").textContent = h
    ? `✓ Codziennie o ${h} Windows sam sprawdzi i przeniesie nowe pliki (komputer musi być włączony). Wynik zobaczysz w dzienniku projektu.`
    : "Harmonogram wyłączony — sprawdzasz ręcznie przyciskiem powyżej.";
  if (h && document.activeElement !== $("przych-godzina")) $("przych-godzina").value = h;
  $("przych-harm").disabled = !foldery.length || !stan.cel || !stan.windows;
  $("przych-harm-wyl").disabled = !h;
  if (!stan.windows) $("przych-harm-opis").textContent += " (dostępny tylko w Windows)";
}
naStan.push(rysujPrzychodzace);

$("przych-dodaj").onclick = () => otworzWyborFolderu("Wybierz folder przychodzący", "", f => {
  const obecne = (stan.projekt && stan.projekt.przychodzace) || [];
  if (!obecne.includes(f)) zapisz({zrodla: stan.zrodla, cel: stan.cel, przychodzace: [...obecne, f]});
});
$("przych-sprawdz").onclick = async () => {
  try { stan = await api("/api/przychodzace/sprawdz", {}); rysuj(); } catch (e) { toast(e.message); }
};
async function ustawHarmonogram(godzina) {
  try { await api("/api/przychodzace/harmonogram", {godzina}); stan = await api("/api/stan"); rysuj();
        toast(godzina ? `Ustawiono: codziennie o ${godzina}.` : "Wyłączono harmonogram."); }
  catch (e) { toast(e.message); }
}
$("przych-harm").onclick = () => {
  const g = $("przych-godzina").value;
  if (!g) { toast("Wybierz godzinę."); return; }
  ustawHarmonogram(g);
};
$("przych-harm-wyl").onclick = () => ustawHarmonogram("");
