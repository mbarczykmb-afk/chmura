// Ikony liniowe (kształty jak w Lucide, licencja ISC) — jeden spójny zestaw dla paska programu i Przeglądarki.
// Użycie w HTML: <i class="ikl" data-ik="kosz"></i> — skrypt wstawia SVG; kolor modułu z CSS (--ik-*), w aktywnym przycisku biały.
"use strict";

const IKONY_LINII = {
  porzadek: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/><path d="M8 10v4"/><path d="M12 10v2"/><path d="M16 10v6"/>',
  sprzatanie: '<path d="m11 10 3 3"/><path d="M6.5 21A3.5 3.5 0 1 0 3 17.5a2.62 2.62 0 0 1-.708 1.792A1 1 0 0 0 3 21z"/><path d="M9.969 17.031 21.378 5.624a1 1 0 0 0-3.002-3.002L6.967 14.031"/>' +
              '<path class="akcent" d="M5 3v4M3 5h4"/>',
  przegladarka: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/>',
  biblioteka: '<rect width="8" height="18" x="3" y="3" rx="1"/><path d="M7 3v18"/><path d="M20.4 18.9c.2.5-.1 1.1-.6 1.3l-1.9.7c-.5.2-1.1-.1-1.3-.6L11.1 5.1c-.2-.5.1-1.1.6-1.3l1.9-.7c.5-.2 1.1.1 1.3.6Z"/>',
  kosz: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
  odzysk: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  ustawienia: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  dyski: '<path d="M22 12H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><path d="M10 16h.01"/><circle class="dioda" cx="6" cy="16" r="1.4"/>',
  wyslij: '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
  statystyki: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M8 17v-3"/><path d="M13 17V9"/><path d="M18 17V5"/><path class="akcent" d="m7 9 5-4 6 2"/>',
  telefon: '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
  pomoc: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  kalendarz: '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/>',
  mapa: '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
  gwiazda: '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
  tegodnia: '<path d="M3 10h18V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h7"/><path d="M8 2v4"/><path d="M16 2v4"/><path d="M21.29 14.7a2.43 2.43 0 0 0-2.65-.52c-.3.12-.57.3-.8.53l-.34.34-.35-.34a2.43 2.43 0 0 0-2.65-.53c-.3.12-.56.3-.79.53-.95.94-1 2.53.2 3.74L17.5 22l3.6-3.55c1.2-1.21 1.14-2.8.19-3.74Z"/>',
  zdjecie: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
  film: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18M3 7.5h4M3 12h18M3 16.5h4M17 3v18M17 7.5h4M17 16.5h4"/>',
  dokument: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8M16 13H8M16 17H8"/>',
  szukaj: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  wiecej: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  zamknij: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  pinezka: '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
  ksiazka: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  zakaz: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
  aparat: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
  porownaj: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>',
  auto: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/>',
  start: '<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4Z"/>',
  blad: '<path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M3 21c0-2.1 1.7-3.9 3.8-4"/><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4"/><path d="M22 13h-4"/><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4"/>',
  ekran: '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
  drzewo: '<path d="M21 12h-8"/><path d="M21 6H8"/><path d="M21 18h-8"/><path d="M3 6v4c0 1.1.9 2 2 2h3"/><path d="M3 10v6c0 1.1.9 2 2 2h3"/>',
  muzyka: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  paczka: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
  pobierz: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  wgraj: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  zegar: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  swiat: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  zapisz: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  schowek: '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
  zaznacz: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
  olowek: '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
  nozyczki: '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
  osoba: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  ukryj: '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/>',
  etykieta: '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  odswiez: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  schowaj: '<path d="m18 15-6-6-6 6"/>',
  serie: '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path class="akcent" d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>',
  filtr: '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
  osoby: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path class="akcent" d="M22 21v-2a4 4 0 0 0-3-3.87"/><path class="akcent" d="M16 3.13a4 4 0 0 1 0 7.75"/>',
};

(function () {
  const st = document.createElement("style");
  st.textContent = `
:root{--ik-cyan:#22d3ee;--ik-blue:#60a5fa;--ik-violet:#a78bfa;--ik-steel:#94a3c4;--ik-gray:#94a3b8;--ik-amber:#fbbf24;--ik-green:#34d399}
@media (prefers-color-scheme:light){:root:not([data-theme="dark"]){--ik-cyan:#0891b2;--ik-blue:#2563eb;--ik-violet:#7c3aed;--ik-steel:#52627f;--ik-gray:#64748b;--ik-amber:#d97706;--ik-green:#059669}}
:root[data-theme="light"]{--ik-cyan:#0891b2;--ik-blue:#2563eb;--ik-violet:#7c3aed;--ik-steel:#52627f;--ik-gray:#64748b;--ik-amber:#d97706;--ik-green:#059669}
.ikl{display:inline-block;width:18px;height:18px;flex:none;vertical-align:-3.5px;color:var(--ik,currentColor);font-style:normal;line-height:0}
.ikl svg{width:100%;height:100%;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;overflow:visible}
.ikl .akcent{stroke:var(--ik-akc,currentColor)} .ikl .dioda{fill:var(--ik-green);stroke:none}
.ikl[data-ik=porzadek],.ikl[data-ik=przegladarka],.ikl[data-ik=wyslij]{--ik:var(--ik-cyan)}
.ikl[data-ik=sprzatanie]{--ik:var(--ik-blue);--ik-akc:var(--ik-amber)}
.ikl[data-ik=biblioteka]{--ik:var(--ik-violet)}
.ikl[data-ik=serie]{--ik:var(--ik-blue);--ik-akc:var(--ik-cyan)}
.ikl[data-ik=osoby]{--ik:var(--ik-cyan);--ik-akc:var(--ik-violet)}
.ikl[data-ik=statystyki]{--ik:var(--ik-cyan);--ik-akc:var(--ik-violet)}
.ikl[data-ik=kosz]{--ik:var(--ik-gray)}
.ikl[data-ik=odzysk]{--ik:var(--ik-blue)}
.ikl[data-ik=ustawienia],.ikl[data-ik=dyski],.ikl[data-ik=folder]{--ik:var(--ik-steel)}
.akt>.ikl,.akt .ikl,button.glowny .ikl{--ik:currentColor;--ik-akc:currentColor}
.akt .ikl .dioda{fill:currentColor}
/* neonowa poświata w ciemnym motywie — pasuje do kolorowych ikon Przeglądarki */
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .ikl svg{filter:drop-shadow(0 0 2.5px color-mix(in srgb,currentColor 70%,transparent))}}
:root[data-theme="dark"] .ikl svg{filter:drop-shadow(0 0 2.5px color-mix(in srgb,currentColor 70%,transparent))}`;
  document.head.append(st);
  const wstaw = (kor = document) => kor.querySelectorAll("i.ikl[data-ik]:not([data-ok])").forEach(i => {
    const k = IKONY_LINII[i.dataset.ik];
    if (!k) return;
    i.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${k}</svg>`; i.dataset.ok = "1";
  });
  window.wstawIkony = wstaw;

  // Emoji na początku napisu przycisku („📅 Data”) → ikona liniowa z tego samego zestawu. Emoji wyglądają inaczej
  // w każdym systemie i nie dają się pokolorować motywem; strzałki i znaki typu ✕ ‹ › ↺ zostają (to zwykłe znaki pisma).
  const Z_EMOJI = {
    "🗑": "kosz", "📅": "kalendarz", "📆": "kalendarz", "📍": "pinezka", "📄": "dokument", "📖": "ksiazka", "⛔": "zakaz",
    "📷": "aparat", "📸": "aparat", "🔀": "porownaj", "✨": "auto", "👋": "start", "🐞": "blad", "⚙": "ustawienia",
    "🛟": "odzysk", "🖥": "ekran", "🌳": "drzewo", "🎬": "film", "🎞": "film", "🎵": "muzyka", "🗜": "paczka", "📦": "paczka",
    "🔍": "szukaj", "🔎": "szukaj", "📤": "wgraj", "📱": "telefon", "🕰": "zegar", "🌍": "swiat", "💾": "zapisz",
    "📂": "folder", "📁": "folder", "📋": "schowek", "☑": "zaznacz", "✏": "olowek", "✂": "nozyczki", "👤": "osoba",
    "🙈": "ukryj", "🏷": "etykieta", "🔗": "link", "ℹ": "info", "⟳": "odswiez", "⬇": "pobierz", "🗺": "mapa",
    "🖼": "zdjecie", "🧹": "sprzatanie", "💽": "dyski", "📚": "biblioteka", "📊": "statystyki"};
  const WZOR = new RegExp("^(\\s*)(" + Object.keys(Z_EMOJI).join("|") + ")\\uFE0F?\\s*", "u");
  const zamien = b => {
    if (b.closest("[data-bez-ikon]")) return;
    const w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
    let n; while ((n = w.nextNode()) && !n.data.trim());
    if (!n) return;
    const m = WZOR.exec(n.data);
    if (!m) return;
    const przed = b.querySelector("img, .ikl, svg");   // przycisk ma już ikonę przed napisem — zostaw
    if (przed && (przed.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    const reszta = n.data.slice(m[0].length);
    const i = document.createElement("i");
    i.className = "ikl zem" + (reszta.trim() || n.nextSibling ? " z-tekstem" : "");
    i.dataset.ik = Z_EMOJI[m[2]];
    i.setAttribute("aria-hidden", "true");
    n.parentNode.insertBefore(i, n);
    n.data = reszta;
    wstaw(b);
  };
  const przejrzyj = kor => {
    if (kor.nodeType !== 1) kor = kor.parentElement;
    if (!kor) return;
    const b = kor.closest("button");
    if (b) zamien(b);
    kor.querySelectorAll("button").forEach(zamien);
  };
  const obserwuj = () => {
    przejrzyj(document.body);
    new MutationObserver(lista => {
      for (const z of lista) {
        if (z.type === "characterData") przejrzyj(z.target);
        else for (const d of z.addedNodes) if (d.nodeType === 1 || d.nodeType === 3) przejrzyj(d);
      }
    }).observe(document.body, {childList: true, subtree: true, characterData: true});
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { wstaw(); obserwuj(); });
  else { wstaw(); obserwuj(); }
})();
