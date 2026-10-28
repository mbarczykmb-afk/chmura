/* Odbiera motyw od Katalogatora (okno nadrzędne): atrybut data-katalogator-motyw="dark|light" na <html> i zmienne CSS
   --kat-bg, --kat-panel, --kat-fg, --kat-mut, --kat-lin, --kat-akc, --kat-akc-fg. Prosi o nie po załadowaniu, a potem
   dostaje je przy każdej zmianie motywu. Przyjmuje wiadomości tylko od okna nadrzędnego i tylko zmienne --kat-*. */
(function () {
  "use strict";
  var w = window, doc = document.documentElement, DOZWOLONE = /^--kat-[a-z-]+$/;
  function zastosuj(d) {
    if (!d || d.typ !== "katalogator-motyw") return;
    if (d.motyw === "dark" || d.motyw === "light") doc.setAttribute("data-katalogator-motyw", d.motyw);
    var k = d.kolory || {};
    Object.keys(k).forEach(function (n) {
      if (DOZWOLONE.test(n) && typeof k[n] === "string" && k[n].length < 200) doc.style.setProperty(n, k[n]);
    });
  }
  w.addEventListener("message", function (e) { if (e.source === w.parent) zastosuj(e.data); });
  if (w.parent !== w) w.parent.postMessage({typ: "katalogator-gotowe"}, "*");
})();
