// Konfiguracja budowania katalogator/ui/podroze/podroze.css (Tailwind 3). Uruchom z tego folderu:
//   npm i tailwindcss@3.4.17 && node paleta.js > ../../katalogator/ui/podroze/paleta.css \
//     && npx tailwindcss -c tailwind.config.js -i wejscie.css -o ../../katalogator/ui/podroze/podroze.css --minify
// Klasy są zbierane z index.html i skryptów aplikacji — po dodaniu nowych klas zbuduj CSS ponownie.
// Kolory (slate, teal, emerald…) to zmienne --p-* z paleta.css (motyw Katalogatora: jasny / ciemny) — patrz paleta.js.
const ui = '../../katalogator/ui/podroze/';
const {colors} = require('./paleta.js');
module.exports = {
  darkMode: 'class',
  content: ['index.html', 'app.js', 'photo-matcher.js', 'booking-parser.js', 'export-manager.js', 'trasa.js', 'os-czasu.js', 'kraje.js', 'nowe.js'].map(f => ui + f),
  theme: {
    extend: {
      colors,
      fontFamily: {sans: ['var(--kat-font)', 'system-ui', 'sans-serif']},
    },
  },
};
