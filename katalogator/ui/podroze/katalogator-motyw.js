/* Adapter motywu Katalogatora dla aplikacji Google Timeline Travels (dopisywany do projektu przyciskiem
   „Zainstaluj adapter motywu” w Katalogatorze → Ustawienia → Podróże). Działa tylko wtedy, gdy aplikacja jest
   otwarta w zakładce Podróże (ramka Katalogatora) — samodzielnie w przeglądarce nic nie zmienia.

   Co robi: ustawia na <html> atrybuty  data-katalogator="1"  i  data-katalogator-motyw="dark|light"  oraz zmienne CSS
   --kat-bg, --kat-panel, --kat-fg, --kat-mut, --kat-lin, --kat-akc, --kat-akc-fg, --kat-font — takie same jak w
   Katalogatorze. Dalsze dopasowanie wyglądu aplikacji (karty, przyciski, mapa…) robi się w jej własnym CSS
   przez te zmienne, np.  html[data-katalogator] .trip-card { background: var(--kat-panel); } */
(function () {
  "use strict";
  var w = window;
  if (w.parent === w) return;                       // nie w ramce — nic nie robimy
  var doc = document.documentElement;
  var DOZWOLONE = /^--kat-[a-z-]+$/;
  function zastosuj(d) {
    if (!d || d.typ !== "katalogator-motyw") return;
    doc.setAttribute("data-katalogator", "1");
    if (d.motyw === "dark" || d.motyw === "light") doc.setAttribute("data-katalogator-motyw", d.motyw);
    var k = d.kolory || {};
    Object.keys(k).forEach(function (n) {
      if (DOZWOLONE.test(n) && typeof k[n] === "string" && k[n].length < 200) doc.style.setProperty(n, k[n]);
    });
  }
  w.addEventListener("message", function (e) {
    if (e.source !== w.parent) return;              // tylko od Katalogatora (rodzic ramki)
    zastosuj(e.data);
  });
  doc.setAttribute("data-katalogator", "1");
  var p = new URLSearchParams(location.search).get("motyw");
  if (p === "dark" || p === "light") doc.setAttribute("data-katalogator-motyw", p);
  w.parent.postMessage({typ: "katalogator-gotowe"}, "*");   // Katalogator odpowiada aktualnym motywem
})();
