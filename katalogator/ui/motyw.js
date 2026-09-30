// ---------- motyw jasny / ciemny i ekran startowy ----------
const IKONY_MOTYWU = {
  // w ciemnym pokazujemy słońce (przejście na jasny), w jasnym — księżyc
  slonce: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  ksiezyc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/></svg>',
};
const systemCiemny = matchMedia("(prefers-color-scheme: dark)");
let wybranyMotyw = document.documentElement.dataset.theme || "auto";

function motywEfektywny() {
  return wybranyMotyw === "auto" ? (systemCiemny.matches ? "dark" : "light") : wybranyMotyw;
}

function zastosujMotyw() {
  const root = document.documentElement;
  if (wybranyMotyw === "auto") delete root.dataset.theme; else root.dataset.theme = wybranyMotyw;
  const ciemny = motywEfektywny() === "dark";
  const b = $("motyw-btn");
  if (b) {
    b.innerHTML = ciemny ? IKONY_MOTYWU.slonce : IKONY_MOTYWU.ksiezyc;
    b.title = ciemny ? "Włącz jasny motyw" : "Włącz ciemny motyw";
  }
  // raport i biblioteka w ramkach — ten sam motyw
  for (const id of ["ramka", "galeria-ramka"]) motywRamki($(id));
}

function motywRamki(ramka) {
  try {
    const d = ramka && ramka.contentDocument;
    if (d && d.documentElement) d.documentElement.dataset.theme = motywEfektywny();
  } catch (e) { /* inna domena — pomijamy */ }
}

function ustawMotyw(m) {
  wybranyMotyw = m;
  zastosujMotyw();
  api("/api/program/ustawienia", {motyw: m}).catch(() => {});
}

$("motyw-btn").onclick = () => ustawMotyw(motywEfektywny() === "dark" ? "light" : "dark");
$("m-motyw-auto").onclick = () => { $("pomoc-menu").hidden = true; ustawMotyw("auto"); toast("Motyw jak w systemie Windows."); };
systemCiemny.addEventListener("change", () => { if (wybranyMotyw === "auto") zastosujMotyw(); });
for (const id of ["ramka", "galeria-ramka"]) $(id).addEventListener("load", () => motywRamki($(id)));
naStan.push(() => {
  if (stan.motyw && stan.motyw !== wybranyMotyw && !naStan.motywZaladowany) { wybranyMotyw = stan.motyw; zastosujMotyw(); }
  naStan.motywZaladowany = true;
});
zastosujMotyw();

// ekran startowy: grafika Katalogatora, znika po wczytaniu danych (min. 1,4 s) albo po kliknięciu
(() => {
  const s = $("start");
  if (!s) return;
  const t0 = performance.now();
  let schowany = false;
  const schowaj = () => {
    if (schowany) return;
    schowany = true;
    s.classList.add("znika");
    setTimeout(() => s.remove(), 700);
  };
  s.onclick = schowaj;
  naStan.push(() => setTimeout(schowaj, Math.max(0, 1400 - (performance.now() - t0))));
  setTimeout(schowaj, 6000);  // gdyby dane długo nie przychodziły
})();
