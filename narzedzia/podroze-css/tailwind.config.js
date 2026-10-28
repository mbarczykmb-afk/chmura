// Konfiguracja budowania katalogator/ui/podroze/podroze.css (Tailwind 3). Uruchom z tego folderu:
//   npm i tailwindcss@3.4.17 && npx tailwindcss -c tailwind.config.js -i wejscie.css -o ../../katalogator/ui/podroze/podroze.css --minify
// Klasy są zbierane z index.html i skryptów aplikacji — po dodaniu nowych klas zbuduj CSS ponownie.
const ui = '../../katalogator/ui/podroze/';
module.exports = {
  darkMode: 'class',
  content: ['index.html', 'app.js', 'photo-matcher.js', 'booking-parser.js', 'export-manager.js'].map(f => ui + f),
  theme: {
    extend: {
      colors: {
        brand: {50: '#f0fdfa', 100: '#ccfbf1', 500: '#14b8a6', 600: '#0d9488', 900: '#134e4a'},
        slate: {850: '#151f32', 900: '#0f172a', 950: '#090d16'},
      },
    },
  },
};
