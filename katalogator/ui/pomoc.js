// Pomoc: zgłaszanie problemów (raport diagnostyczny), aktualizacje, informacje o programie.
"use strict";

const akt = {info: null};

// ---------- menu „?” ----------
$("pomoc-btn").onclick = e => { e.stopPropagation(); $("pomoc-menu").hidden = !$("pomoc-menu").hidden; };
document.addEventListener("click", () => { $("pomoc-menu").hidden = true; });

// ---------- raport ----------
async function otworzRaport() {
  $("pomoc-menu").hidden = true;
  $("okno-raport").hidden = false;
  $("raport-tekst").value = "Zbieram informacje…";
  try {
    const r = await api("/api/raport-bledow");
    $("raport-tekst").value = r.tekst;
    $("raport-info").textContent = "Dziennik: " + r.plik_logu;
  } catch (e) { $("raport-tekst").value = "Nie udało się przygotować raportu: " + e.message; }
}
function pelnyRaport() {
  const opis = $("raport-opis").value.trim();
  return (opis ? "=== Opis problemu ===\n" + opis + "\n\n" : "") + $("raport-tekst").value;
}
$("m-zglos").onclick = otworzRaport;
$("raport-zamknij").onclick = () => { $("okno-raport").hidden = true; };
$("raport-kopiuj").onclick = async () => {
  try { await navigator.clipboard.writeText(pelnyRaport()); toast("Skopiowano raport — wklej go w rozmowie z Claude."); }
  catch (e) { $("raport-tekst").select(); document.execCommand("copy"); toast("Skopiowano raport."); }
};
$("raport-zapisz").onclick = async () => {
  try { const r = await api("/api/raport-bledow/zapisz", {opis: $("raport-opis").value.trim()}); toast("Zapisano: " + r.plik); $("raport-info").textContent = "Zapisano: " + r.plik; }
  catch (e) { toast(e.message); }
};
$("raport-github").onclick = async () => {
  try {
    await api("/api/raport-bledow/github", {opis: $("raport-opis").value.trim()});
    toast("Otworzyłem przeglądarkę ze zgłoszeniem — dołącz tam zapisany plik raportu.");
  } catch (e) { toast(e.message); }
};

// ---------- aktualizacje ----------
async function sprawdzAktualizacje(wymus) {
  try {
    const w = await api("/api/aktualizacja" + (wymus ? "?wymus=1" : ""));
    akt.info = w;
    let pominieta = null;
    try { pominieta = localStorage.getItem("katalogator-pomin-wersje"); } catch (e) { /* brak pamięci przeglądarki */ }
    const pokaz = w.nowa && (wymus || pominieta !== w.najnowsza);
    $("baner-akt").hidden = !pokaz;
    if (pokaz) {
      $("baner-tekst").textContent = `Dostępna jest nowa wersja Katalogatora: ${w.najnowsza} (masz ${w.biezaca}).`;
      $("baner-instaluj").hidden = !(w.url_instalatora && stan.windows);
    }
    if (wymus && !w.nowa) toast(w.blad || `Masz najnowszą wersję (${w.biezaca}).`);
  } catch (e) { if (wymus) toast(e.message); }
}
$("m-aktualizacje").onclick = () => { $("pomoc-menu").hidden = true; sprawdzAktualizacje(true); };
$("baner-pozniej").onclick = () => {
  try { localStorage.setItem("katalogator-pomin-wersje", akt.info.najnowsza); } catch (e) { /* ignoruj */ }
  $("baner-akt").hidden = true;
};
$("baner-co").onclick = () => api("/api/otworz-strone", {url: akt.info.url_strony});
$("baner-instaluj").onclick = async () => {
  if (zajety()) { toast("Poczekaj, aż skończy się bieżące zadanie."); return; }
  if (!confirm(`Pobrać i zainstalować wersję ${akt.info.najnowsza}?\n\nKatalogator zamknie się, a instalator poprowadzi Cię dalej. ` +
               "Twoje projekty i ustawienia zostaną zachowane.")) return;
  try {
    await api("/api/aktualizacja/instaluj", {url: akt.info.url_instalatora});
    $("baner-tekst").textContent = "Pobieram instalator…";
    for (const id of ["baner-co", "baner-instaluj", "baner-pozniej"]) $(id).hidden = true;
  } catch (e) { toast(e.message); }
};
naStan.push(() => {
  const z = (stan.zad || {}).aktualizacja || {};
  if (z.trwa && z.wszystkie) $("baner-tekst").textContent = `Pobieram instalator… ${Math.round(100 * z.zrobione / z.wszystkie)}%`;
  else if (!z.trwa && z.komunikat && !$("baner-akt").hidden) $("baner-tekst").textContent = z.komunikat + (z.blad ? " " + z.blad : "");
});

// ---------- o programie ----------
$("m-o").onclick = async () => {
  $("pomoc-menu").hidden = true;
  const o = await api("/api/o-programie");
  $("o-wersja").textContent = o.wersja;
  const d = $("o-szczegoly"); d.replaceChildren();
  for (const [k, v] of [["System", o.system], ["Dane programu (projekty)", o.katalog], ["Dziennik błędów", o.plik_logu],
                        ["Program", o.sciezka_programu]]) {
    const x = document.createElement("div"); const b = document.createElement("b"); b.textContent = k + ": ";
    x.append(b, v); d.append(x);
  }
  $("o-akt").checked = o.sprawdzaj_aktualizacje;
  $("okno-o").hidden = false;
};
$("o-akt").onchange = () => api("/api/program/ustawienia", {sprawdzaj_aktualizacje: $("o-akt").checked});
$("o-zamknij").onclick = () => { $("okno-o").hidden = true; };

setTimeout(() => sprawdzAktualizacje(false), 3000);
