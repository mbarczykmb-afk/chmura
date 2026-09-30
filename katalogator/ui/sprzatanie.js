// Tryby pracy (Porządkowanie / Sprzątanie / Przeglądarka) i tryb Sprzątanie: śmieci, odłożone, usuwanie na stałe.
"use strict";

// ---------- przełącznik trybów w nagłówku ----------
const OPIS_TRYBU = {
  porzadkowanie: "🗂 Porządkowanie — kopiuję lub przenoszę pliki do uporządkowanej biblioteki.",
  sprzatanie: "🧹 Sprzątanie — szukam duplikatów i śmieci w istniejących folderach; nic nie jest kopiowane ani przenoszone do biblioteki.",
};
let trybGalerii = false;  // Przeglądarka otwarta nad bieżącym trybem

function oznaczTryby() {
  const t = sprzatanie() ? "sprzatanie" : "porzadkowanie";
  document.querySelectorAll(".tryby button").forEach(b => {
    const akt = trybGalerii ? b.dataset.tryb === "przegladarka" : b.dataset.tryb === t;
    b.classList.toggle("akt", akt); b.setAttribute("aria-selected", String(akt));
  });
}

document.querySelectorAll(".tryby button").forEach(b => {
  b.onclick = async () => {
    const t = b.dataset.tryb;
    if (t === "przegladarka") { otworzGalerie("przegladarka"); trybGalerii = true; oznaczTryby(); return; }
    if (trybGalerii) { $("galeria-nakladka").hidden = true; $("galeria-ramka").src = "about:blank"; trybGalerii = false; }
    if ((t === "sprzatanie") === sprzatanie()) { oznaczTryby(); return; }
    try {
      stan = await api("/api/tryb", {tryb: t});
      pokazZakladke("raport"); rysuj(); toast(OPIS_TRYBU[t]);
    } catch (e) { toast(e.message); }
  };
});
window.addEventListener("message", e => {  // zamknięcie Przeglądarki (✕) — wracamy do bieżącego trybu
  if (e.data === "zamknij-galerie") { trybGalerii = false; oznaczTryby(); }
});

// wygląd zależny od trybu: sekcje, zakładki, kroki
let ostatniTryb = null;
naStan.push(() => {
  const s = sprzatanie();
  document.body.classList.toggle("tryb-sprzatanie", s);
  oznaczTryby();
  $("zrodla-tytul").textContent = s ? "Co sprzątamy?" : "Co porządkujemy?";
  $("k3").lastChild.textContent = s ? "Duplikaty i śmieci" : "Propozycja drzewa";
  $("k4").lastChild.textContent = s ? "Usuwanie" : "Porządkowanie";
  if (s) {
    $("k3").className = "krok klik " + (stan.duplikaty || smieci.wczytane ? "gotowy" : (stan.ma_wyniki ? "akt" : ""));
    $("k4").className = "krok klik " + ((window.odlozoneStan || {}).plikow ? "akt" : "");
  }
  // ukryta zakładka nie może zostać otwarta po zmianie trybu
  const ukryte = s ? ["dok", "inne", "drzewo"] : ["smieci"];
  if (ukryte.includes(zakladka)) pokazZakladke("raport");
  if (ostatniTryb !== s) { ostatniTryb = s; smieci.wczytane = false; if (s) odswiezOdlozone(); }
});

// ---------- zakładka Śmieci ----------
const smieci = {lista: [], zazn: new Set(), wczytane: false};
przyPokazaniu.smieci = async () => {
  if (smieci.wczytane) return;
  $("smieci-lista").innerHTML = '<div class="pusto">Szukam śmieci…</div>';
  try {
    const r = await api("/api/smieci");
    smieci.lista = r.pliki; smieci.zazn = new Set(r.pliki.map(p => p.id)); smieci.wczytane = true;
    rysujSmieci();
  } catch (e) { $("smieci-lista").innerHTML = `<div class="pusto">${e.message}</div>`; }
};
function rysujSmieci() {
  const l = $("smieci-lista"); l.replaceChildren();
  $("licz-smieci").hidden = !smieci.lista.length; $("licz-smieci").textContent = smieci.lista.length;
  if (!stan.ma_wyniki) { l.innerHTML = '<div class="pusto">Najpierw zeskanuj foldery (krok 2).</div>'; smieciStopka(); return; }
  if (!smieci.lista.length) { l.innerHTML = '<div class="pusto">Nie znalazłem śmieci. 🎉</div>'; smieciStopka(); return; }
  const grupy = new Map();
  for (const p of smieci.lista) { if (!grupy.has(p.powod)) grupy.set(p.powod, []); grupy.get(p.powod).push(p); }
  for (const [powod, pliki] of [...grupy].sort((a, b) => b[1].length - a[1].length)) {
    const d = document.createElement("details"); d.className = "smieci-gr"; d.open = pliki.length <= 200;
    const s = document.createElement("summary");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.title = "Zaznacz / odznacz całą grupę";
    const ustawCb = () => { const n = pliki.filter(p => smieci.zazn.has(p.id)).length; cb.checked = n === pliki.length; cb.indeterminate = n > 0 && n < pliki.length; };
    cb.onclick = e => { e.stopPropagation(); pliki.forEach(p => cb.checked ? smieci.zazn.add(p.id) : smieci.zazn.delete(p.id)); rysujSmieci(); };
    const t = document.createElement("span"); t.textContent = powod;
    const inf = document.createElement("span"); inf.className = "info";
    inf.textContent = `${plikow(pliki.length)} · ${rozmiar(pliki.reduce((a, p) => a + p.rozmiar, 0))}`;
    s.append(cb, t, inf); d.append(s); ustawCb();
    const rysujWiersze = () => {
      for (const p of pliki.slice(0, 1000)) {
        const w = document.createElement("label"); w.className = "smieci-w";
        const c = document.createElement("input"); c.type = "checkbox"; c.checked = smieci.zazn.has(p.id);
        c.onchange = () => { c.checked ? smieci.zazn.add(p.id) : smieci.zazn.delete(p.id); ustawCb(); smieciStopka(); };
        let ob;
        if (p.rodzaj === "zdjecie" && p.rozmiar) { ob = new Image(); ob.loading = "lazy"; ob.alt = ""; ob.src = `/miniatura?t=${encodeURIComponent(TOKEN)}&id=${p.id}`; ob.onerror = () => { ob.replaceWith(Object.assign(document.createElement("span"), {className: "ik", textContent: "🖼️"})); }; }
        else { ob = document.createElement("span"); ob.className = "ik"; ob.textContent = p.rozmiar ? "📄" : "∅"; }
        const sc = document.createElement("span"); sc.className = "sc"; sc.title = p.sciezka; sc.textContent = "‎" + p.wzgledna;
        const r = document.createElement("span"); r.className = "gdzie"; r.textContent = rozmiar(p.rozmiar);
        w.append(c, ob, sc, r); d.append(w);
      }
      if (pliki.length > 1000) d.append(Object.assign(document.createElement("div"), {className: "pusto", textContent: `… i ${pliki.length - 1000} więcej (też zaznaczone, jeśli grupa jest zaznaczona)`}));
    };
    if (d.open) rysujWiersze(); else d.addEventListener("toggle", () => { if (d.open && d.childElementCount === 1) rysujWiersze(); }, {once: true});
    l.append(d);
  }
  smieciStopka();
}
function smieciStopka() {
  const z = smieci.lista.filter(p => smieci.zazn.has(p.id));
  $("smieci-stopka").textContent = smieci.lista.length
    ? `Zaznaczono ${plikow(z.length)} (${rozmiar(z.reduce((a, p) => a + p.rozmiar, 0))}) — trafią do Odłożone/Śmieci, można cofnąć` : "";
  $("smieci-odloz").disabled = !z.length || zajety();
}
$("smieci-wsz").onclick = () => { smieci.zazn = new Set(smieci.lista.map(p => p.id)); rysujSmieci(); };
$("smieci-zadne").onclick = () => { smieci.zazn.clear(); rysujSmieci(); };
$("smieci-odloz").onclick = async () => {
  const ids = smieci.lista.filter(p => smieci.zazn.has(p.id)).map(p => p.id);
  try {
    const w = await api("/api/odloz", {ids, typ: "smieci"});
    toast(`✓ Odłożono ${plikow(w.przeniesione)} do Odłożone/Śmieci.` + (w.pominiete.length ? ` Pominięto: ${w.pominiete.length}.` : ""), async () => {
      const c = await api("/api/duplikaty/cofnij", {}); toast(`Przywrócono ${plikow(c.przywrocone)}.`);
      smieci.wczytane = false; stan = await api("/api/stan"); rysuj(); przyPokazaniu.smieci(); odswiezOdlozone();
    });
    smieci.wczytane = false; stan = await api("/api/stan"); rysuj(); przyPokazaniu.smieci(); odswiezOdlozone();
  } catch (e) { toast(e.message); }
};

// ---------- Usuwanie: co czeka w folderach Odłożone ----------
window.odlozoneStan = null;
const odlZazn = new Map();  // kategoria -> zaznaczona
async function odswiezOdlozone() {
  if (!sprzatanie()) return;
  try { window.odlozoneStan = await api("/api/odlozone"); } catch (e) { return; }
  const o = window.odlozoneStan, l = $("odl-lista"); l.replaceChildren();
  if (!o.plikow) l.innerHTML = '<div class="pusto">Nic jeszcze nie odłożono — w zakładkach <b>Duplikaty</b>, <b>🗑 Śmieci</b> i <b>Podobne</b> odłóż to, czego nie chcesz.</div>';
  const IKONY_ODL = {"Duplikaty": "📑", "Śmieci": "🗑", "Podobne": "🖼", "Nieostre": "🌫"};
  for (const k of o.kategorie) {
    if (!odlZazn.has(k.nazwa)) odlZazn.set(k.nazwa, k.nazwa !== "Podobne" && k.nazwa !== "Nieostre");  // zdjęcia — rozważnie
    const w = document.createElement("label"); w.className = "odl";
    const c = document.createElement("input"); c.type = "checkbox"; c.checked = odlZazn.get(k.nazwa);
    c.onchange = () => { odlZazn.set(k.nazwa, c.checked); przyciskUsun(); };
    const t = document.createElement("span"); t.textContent = `${IKONY_ODL[k.nazwa] || "📦"} ${k.nazwa}`;
    const r = document.createElement("b"); r.textContent = `${plikow(k.plikow)} · ${rozmiar(k.bajty)}`;
    w.append(c, t, r); l.append(w);
  }
  przyciskUsun(); ukladPrzewodnika();
}
function przyciskUsun() {
  const o = window.odlozoneStan || {kategorie: []};
  const wyb = o.kategorie.filter(k => odlZazn.get(k.nazwa));
  $("odl-usun").disabled = !wyb.length || zajety();
  $("odl-usun").textContent = wyb.length ? `🗑 Usuń na stałe ${plikow(wyb.reduce((a, k) => a + k.plikow, 0))} (${rozmiar(wyb.reduce((a, k) => a + k.bajty, 0))})…` : "🗑 Usuń na stałe…";
}
$("odl-usun").onclick = async () => {
  const o = window.odlozoneStan; if (!o) return;
  const wyb = o.kategorie.filter(k => odlZazn.get(k.nazwa));
  const n = wyb.reduce((a, k) => a + k.plikow, 0), b = wyb.reduce((a, k) => a + k.bajty, 0);
  if (!confirm(`Usunąć NA STAŁE ${plikow(n)} (${rozmiar(b)}) z folderów Odłożone: ${wyb.map(k => k.nazwa).join(", ")}?\n\n` +
               "Tego NIE da się cofnąć. Na dysku sieciowym (My Cloud) nie ma Kosza — pliki znikną od razu.")) return;
  try { stan = await api("/api/odlozone/usun", {kategorie: wyb.map(k => k.nazwa), puste: $("odl-puste").checked}); rysuj(); }
  catch (e) { toast(e.message); }
};
// po zakończeniu usuwania / odkładania — odśwież listę
let bylaPracaUsuwania = false;
naStan.push(() => {
  if (!sprzatanie()) return;
  rysujZadanie("usuwanie", "zad-usuwanie");
  const z = (stan.zad || {}).usuwanie || {};
  if (bylaPracaUsuwania && !z.trwa) { odswiezOdlozone(); smieci.wczytane = false; if (zakladka === "smieci") przyPokazaniu.smieci(); }
  bylaPracaUsuwania = !!z.trwa;
  przyciskUsun();
});
// odkładanie w Duplikatach/Podobnych też zmienia Odłożone
{
  const staryFetch = window.api;
  window.api = async (sciezka, dane) => {
    const w = await staryFetch(sciezka, dane);
    if (sprzatanie() && /^\/api\/(odloz|duplikaty\/(przenies|cofnij))/.test(sciezka)) setTimeout(odswiezOdlozone, 300);
    if (sprzatanie() && sciezka === "/api/skanuj") smieci.wczytane = false;
    return w;
  };
}
