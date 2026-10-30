// Paleta Podróży: klasy Tailwind (slate, teal, emerald…) czytają kolory ze zmiennych CSS, więc cały interfejs podąża za
// motywem Katalogatora (jasny / ciemny) bez zmiany znaczników. Generuje też plik katalogator/ui/podroze/paleta.css:
//   node paleta.js > ../../katalogator/ui/podroze/paleta.css
const tw = require('tailwindcss/colors');
const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

// neutralne: grafit Katalogatora (--bg #131416, --panel #1b1c1f, --lin #2c2e33, --mut #a2a5ad, --fg #ececee; jasny: #f4f4f6 / #fff / #e3e4e8 / #5a5d66 / #18181b)
const SLATE = {
  dark:  {50: '#f6f6f7', 100: '#ececee', 200: '#d7d8dc', 300: '#bcbec5', 400: '#a2a5ad', 500: '#7b7e87', 600: '#53565e', 700: '#3a3c42', 800: '#2c2e33', 850: '#232428', 900: '#1b1c1f', 950: '#131416'},
  light: {50: '#0b0b0d', 100: '#18181b', 200: '#2a2b30', 300: '#3f4046', 400: '#5a5d66', 500: '#7b7e87', 600: '#a4a6ae', 700: '#cfd0d6', 800: '#e3e4e8', 850: '#f0f0f3', 900: '#ffffff', 950: '#f4f4f6'},
};
// akcent (fiolet Katalogatora, --akc #7354f0 / jasny #6d28d9) — zastępuje turkus „teal” i „brand”
const AKCENT = {50: '#f5f3ff', 100: '#ede9fe', 200: '#ddd6fe', 300: '#c4b5fd', 400: '#a78bfa', 500: '#7354f0', 600: '#6240d8', 700: '#5232b8', 800: '#3f2890', 900: '#2d1d68', 950: '#1c1342'};
// jasny motyw: odcienie jasne (tekst/obwódki w ciemnym) ↔ ciemne; mocne wypełnienia 500–700 bez zmian (biały tekst na nich)
const FLIP = {50: 950, 100: 900, 200: 800, 300: 700, 400: 600, 500: 500, 600: 600, 700: 700, 800: 200, 900: 100, 950: 50};
const RODZINY = ['emerald', 'amber', 'rose', 'purple', 'sky', 'blue', 'red', 'indigo', 'yellow', 'orange', 'cyan', 'green', 'pink', 'stone'];

const hex = h => { const n = parseInt(h.slice(1), 16); return `${n >> 16} ${(n >> 8) & 255} ${n & 255}`; };
const skala = {};   // nazwa → {dark: {shade: hex}, light: {shade: hex}}
skala.slate = SLATE;
skala.teal = {dark: AKCENT, light: Object.fromEntries(SHADES.map(s => [s, AKCENT[FLIP[s]]]))};
skala.brand = skala.teal;
for (const f of RODZINY) skala[f] = {dark: tw[f], light: Object.fromEntries(SHADES.map(s => [s, tw[f][FLIP[s]]]))};

const colors = {};
for (const [nazwa, s] of Object.entries(skala)) {
  colors[nazwa] = {};
  for (const sh of Object.keys(s.dark)) colors[nazwa][sh] = `rgb(var(--p-${nazwa}-${sh}) / <alpha-value>)`;
}
const zmienne = tryb => Object.entries(skala).flatMap(([n, s]) => Object.entries(s[tryb]).map(([sh, h]) => `--p-${n}-${sh}:${hex(h)}`)).join(';');

const DARK_KAT = '--kat-bg:#131416;--kat-panel:#1b1c1f;--kat-fg:#ececee;--kat-mut:#a2a5ad;--kat-lin:#2c2e33;--kat-akc:#7354f0;--kat-akc-fg:#fff;' +
  '--neon-c:#22d3ee;--neon-v:#a78bfa;--neon-m:#e879f9;--ok:#34d399;--blad:#f87171;--przen:#fbbf24;--cien:0 1px 0 rgba(255,255,255,.03) inset,0 12px 32px rgba(0,0,0,.4)';
const LIGHT_KAT = '--kat-bg:#f4f4f6;--kat-panel:#ffffff;--kat-fg:#18181b;--kat-mut:#5a5d66;--kat-lin:#e3e4e8;--kat-akc:#6d28d9;--kat-akc-fg:#fff;' +
  '--neon-c:#0891b2;--neon-v:#7c3aed;--neon-m:#c026d3;--ok:#059669;--blad:#dc2626;--przen:#d97706;--cien:0 1px 2px rgba(24,24,27,.05),0 6px 20px rgba(24,24,27,.06)';

if (require.main === module) {
  console.log(`/* GENEROWANE: narzedzia/podroze-css/paleta.js — nie edytuj ręcznie. Paleta Tailwind jako zmienne (R G B), ciemny i jasny motyw Katalogatora. */
html[data-podroze]{${zmienne('dark')};${DARK_KAT};color-scheme:dark}
html[data-podroze][data-katalogator-motyw="light"]{${zmienne('light')};${LIGHT_KAT};color-scheme:light}
@media (prefers-color-scheme:light){html[data-podroze]:not([data-katalogator-motyw]){${zmienne('light')};${LIGHT_KAT};color-scheme:light}}`);
}
module.exports = {colors};
