// Wskaźnik pracy w tle (lewy dolny róg): wczytywanie miniatur, danych, wyników projektu, skan Przeglądarki…
// Każde źródło: aktywnosc.ustaw(klucz, {tytul, zrobione, wszystkie, opis}) / aktywnosc.usun(klucz).
// Bez „wszystkie” pasek jest nieokreślony (przesuwa się).
(() => {
  "use strict";
  const styl = document.createElement("style");
  styl.textContent = `
#aktywnosc{position:fixed;left:14px;bottom:14px;z-index:3900;display:flex;flex-direction:column;gap:6px;pointer-events:none;
  width:min(300px,calc(100vw - 28px))}
#aktywnosc .ak{background:var(--panel,#111a2e);color:var(--fg,#e7ecf7);border:1px solid var(--lin,#2a3550);border-radius:10px;
  padding:7px 10px;font:12.5px/1.3 system-ui,-apple-system,"Segoe UI",sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.25);
  animation:ak-wejdz .2s ease-out}
#aktywnosc .ak .t{display:flex;justify-content:space-between;gap:10px;white-space:nowrap}
#aktywnosc .ak .t span:first-child{overflow:hidden;text-overflow:ellipsis}
#aktywnosc .ak .t span:last-child{color:var(--mut,#8a97b4);font-variant-numeric:tabular-nums}
#aktywnosc .ak .o{color:var(--mut,#8a97b4);font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px}
#aktywnosc .ak .p{height:4px;border-radius:999px;background:var(--lin,#2a3550);margin-top:5px;overflow:hidden}
#aktywnosc .ak .p i{display:block;height:100%;width:0;border-radius:999px;background:var(--akc,#5b8cff);transition:width .3s}
#aktywnosc .ak .p.nieokr i{width:35%;animation:ak-jedz 1.2s ease-in-out infinite}
@keyframes ak-jedz{0%{margin-left:-35%}100%{margin-left:100%}}
@keyframes ak-wejdz{from{opacity:0;transform:translateY(6px)}}
@media print{#aktywnosc{display:none}}`;
  document.head.append(styl);
  const pudlo = document.createElement("div"); pudlo.id = "aktywnosc"; pudlo.setAttribute("aria-live", "polite");
  const dodaj = () => document.body.append(pudlo);
  if (document.body) dodaj(); else document.addEventListener("DOMContentLoaded", dodaj);

  const zrodla = new Map();
  let planowane = false;
  function rysuj() {
    planowane = false;
    const widoczne = new Set();
    for (const [klucz, d] of zrodla) {
      widoczne.add(klucz);
      let el = pudlo.querySelector(`[data-k="${klucz}"]`);
      if (!el) {
        el = document.createElement("div"); el.className = "ak"; el.dataset.k = klucz;
        el.innerHTML = '<div class="t"><span></span><span></span></div><div class="o"></div><div class="p"><i></i></div>';
        pudlo.append(el);
      }
      const proc = d.wszystkie ? Math.min(100, Math.round(100 * (d.zrobione || 0) / d.wszystkie)) : null;
      el.querySelector(".t span").textContent = "⏳ " + d.tytul;
      el.querySelector(".t span:last-child").textContent = d.wszystkie
        ? `${(d.zrobione || 0).toLocaleString("pl-PL")} / ${d.wszystkie.toLocaleString("pl-PL")}` : "";
      const o = el.querySelector(".o"); o.textContent = d.opis || ""; o.hidden = !d.opis;
      const p = el.querySelector(".p"); p.classList.toggle("nieokr", proc === null);
      p.firstChild.style.width = proc === null ? "" : proc + "%";
    }
    for (const el of [...pudlo.children]) if (!widoczne.has(el.dataset.k)) el.remove();
  }
  const zaplanuj = () => { if (!planowane) { planowane = true; requestAnimationFrame(rysuj); } };
  window.aktywnosc = {
    ustaw(klucz, dane) { zrodla.set(klucz, dane); zaplanuj(); },
    usun(klucz) { if (zrodla.delete(klucz)) zaplanuj(); },
  };

  // --- miniatury: ile widocznych jeszcze się wczytuje (leniwe poza ekranem się nie liczą) ---
  const MINIATURA = /\/(miniatura|api\/g\/miniatura)\?/;
  let zaladowane = 0;
  const policz = e => { const t = e.target; if (t && t.tagName === "IMG" && MINIATURA.test(t.src || "")) zaladowane++; };
  document.addEventListener("load", policz, true);
  document.addEventListener("error", policz, true);
  function blisko(im) {
    if (!im.isConnected || im.loading === "lazy" && !im.offsetParent) return false;
    const r = im.getBoundingClientRect();
    return r.width > 0 && r.bottom > -400 && r.top < innerHeight + 400;
  }
  setInterval(() => {
    let czeka = 0;
    for (const im of document.images) if (!im.complete && MINIATURA.test(im.src || "") && blisko(im)) czeka++;
    if (czeka) window.aktywnosc.ustaw("miniatury", {tytul: "Wczytuję miniatury", zrobione: zaladowane, wszystkie: zaladowane + czeka});
    else { zaladowane = 0; window.aktywnosc.usun("miniatury"); }
  }, 400);

  // --- zapytania do programu trwające dłużej niż chwilę (lista duplikatów, dokumenty, mapa…) ---
  const POMIJAJ = /\/api\/(stan|ping|pilot|przegladarka)(\?|$)/;  // ciągłe odpytywanie o stan — to nie „praca”
  let trwa = 0, zegar = null;
  const staryFetch = window.fetch.bind(window);
  window.fetch = async (wejscie, opcje) => {
    const adres = typeof wejscie === "string" ? wejscie : (wejscie && wejscie.url) || "";
    if (POMIJAJ.test(adres) || !adres.startsWith("/")) return staryFetch(wejscie, opcje);
    if (++trwa === 1) zegar = setTimeout(() => window.aktywnosc.ustaw("dane", {tytul: "Wczytuję dane…"}), 600);
    try { return await staryFetch(wejscie, opcje); }
    finally { if (--trwa === 0) { clearTimeout(zegar); window.aktywnosc.usun("dane"); } }
  };
})();
