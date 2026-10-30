// Podróże: brakujące ikony liniowe (Lucide, ISC) + zamiana wiodących emoji na <i class="ikl"> (jak w ikony.js). Ładować po /ui/ikony.js.
"use strict";
(function () {
  const NOWE = {
    gory: '<path d="m8 3 4 8 5-5 5 15H2L8 3z"/>',
    trasa: '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    nocleg: '<path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"/><path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"/><path d="M12 4v6"/><path d="M2 18h20"/>',
    jedzenie: '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    samolot: '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
    kompas: '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/>',
    wykres: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    kroki: '<path d="M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z"/><path d="M16 17h4"/><path d="M4 13h4"/>',
    samochod: '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
    bilet: '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/>',
    poczta: '<path d="m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7"/><rect x="2" y="4" width="20" height="16" rx="2"/>',
    drukuj: '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    klepsydra: '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
    cel: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    iskry: '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/><path d="M20 2v4"/><path d="M22 4h-4"/><circle cx="4" cy="20" r="2"/>',
    blyskawica: '<path d="M15.914 4a1.5 1.5 0 00-2.474-1.561l-9 9A1.5 1.5 0 005.5 14h4.002a.5.5 0 01.471.666L8.086 20a1.5 1.5 0 002.475 1.56l9-9A1.5 1.5 0 0018.5 10h-3.997a.5.5 0 01-.472-.667z"/>',
    kalendarz2: '<path d="M8 2v3"/><path d="M16 2v3"/><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M8 13h.01"/><path d="M12 13h.01"/><path d="M16 13h.01"/><path d="M8 17h.01"/><path d="M12 17h.01"/><path d="M16 17h.01"/>',
    dodaj_zdjecia: '<path d="M16 5h6"/><path d="M19 2v6"/><path d="M21 11.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7.5"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/>',
    dziennik: '<path d="M15 12h-5"/><path d="M15 8h-5"/><path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"/>'
  };
  for (const k in NOWE) if (!(k in IKONY_LINII)) IKONY_LINII[k] = NOWE[k];

  const Z = {
    "\u{1F9ED}": "kompas", "\u{1F4C2}": "folder", "\u{1F4C1}": "folder", "\u26A1": "blyskawica", "\u2728": "iskry",
    "\u2753": "pomoc", "\u{1F552}": "zegar", "\u23F3": "klepsydra", "\u{1F512}": "info", "\u{1F4F8}": "aparat",
    "\u{1F5FA}": "mapa", "\u{1F30D}": "swiat", "\u{1F310}": "swiat", "\u{1F5D3}": "kalendarz", "\u{1F4C5}": "kalendarz",
    "\u{1F4CD}": "pinezka", "\u{1F97E}": "kroki", "\u{1F697}": "samochod", "\u{1F4EC}": "poczta", "\u{1F4E4}": "wgraj",
    "\u{1F4CA}": "wykres", "\u{1F4BE}": "zapisz", "\u{1F4CB}": "schowek", "\u{1F5A8}": "drukuj", "\u{1F3AF}": "cel",
    "\u{1F4C8}": "wykres", "\u2708": "podroze", "\u270F": "olowek", "\u{1F5BC}": "dodaj_zdjecia", "\u{1F50D}": "szukaj",
    "\u26F0": "gory", "\u{1F3D4}": "gory", "\u{1F4DD}": "dziennik", "\u2B07": "pobierz", "\u27F3": "odswiez"};
  const WZOR = new RegExp("^(\\s*)(" + Object.keys(Z).join("|") + ")\\uFE0F?\\s*", "u");
  const SEL = "button, a, h1, h2, h3, h4, label, summary, [role=tab], .np-ik, [data-emoji-ikona]";

  if (!document.querySelector("style[data-ik-podroze]")) {
    const st = document.createElement("style");
    st.dataset.ikPodroze = "1";
    st.textContent = ".ikl.zem{width:16px;height:16px}.ikl.z-tekstem{margin-right:.4em}" +
      ".ikl{display:inline-block;flex:none}.ikl svg{width:100%;height:100%;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}";
    document.head.append(st);
  }

  const zamien = el => {
    if (el.closest("[data-bez-ikon],[data-dane]")) return;
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n; while ((n = w.nextNode()) && !n.data.trim());
    if (!n) return;
    const m = WZOR.exec(n.data);
    if (!m) return;
    const k = Z[m[2]];
    if (!IKONY_LINII[k]) return;
    const przed = el.querySelector("img, .ikl, svg");
    if (przed && (przed.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    const reszta = n.data.slice(m[0].length);
    const i = document.createElement("i");
    i.className = "ikl zem" + (reszta.trim() || n.nextSibling ? " z-tekstem" : "");
    i.dataset.ik = k;
    i.setAttribute("aria-hidden", "true");
    n.parentNode.insertBefore(i, n);
    n.data = reszta;
    if (typeof wstawIkony === "function") wstawIkony(el);
  };

  window.zamienEmojiPodroze = function (root) {
    root = root || document.body;
    if (!root) return;
    if (root.nodeType === 3) root = root.parentElement;
    if (!root || root.nodeType !== 1) return;
    const e = root.closest(SEL);
    if (e) zamien(e);
    root.querySelectorAll(SEL).forEach(zamien);
  };

  let kolejka = new Set(), plan = false;
  const wykonaj = () => {
    plan = false;
    const l = kolejka; kolejka = new Set();
    l.forEach(n => { if (n.isConnected) window.zamienEmojiPodroze(n); });
  };
  const dodaj = n => { kolejka.add(n); if (!plan) { plan = true; requestAnimationFrame(wykonaj); } };
  const start = () => {
    window.zamienEmojiPodroze(document.body);
    new MutationObserver(lista => {
      for (const z of lista) {
        if (z.type === "characterData") dodaj(z.target);
        else for (const d of z.addedNodes) if (d.nodeType === 1 || d.nodeType === 3) dodaj(d);
      }
    }).observe(document.body, {childList: true, subtree: true, characterData: true});
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
