// ✈ Podróże — zakładka z aplikacją Google Timeline Travels (osobny serwer Node.js z folderu projektu na tym komputerze).
// Dane podróży nie opuszczają folderu projektu; Katalogator uruchamia serwer, pokazuje go w ramce i przekazuje motyw.
"use strict";

const pod = {d: null, laduje: false, ramkaAdres: ""};

// Motyw Katalogatora → aplikacja w ramce (adapter motywu: katalogator-motyw.js w projekcie). Zmienne --kat-* = nasze tokeny.
function motywPodrozy() {
  const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim();
  return {typ: "katalogator-motyw", motyw: cs.colorScheme.includes("dark") ? "dark" : "light",
          kolory: {"--kat-bg": v("--bg"), "--kat-panel": v("--panel"), "--kat-fg": v("--fg"), "--kat-mut": v("--mut"),
                   "--kat-lin": v("--lin"), "--kat-akc": v("--akc"), "--kat-akc-fg": v("--akc-fg")}};
}
function wyslijMotywPodrozy() {
  const r = $("podroze-ramka");
  if (!pod.ramkaAdres || !r.contentWindow) return;
  try { r.contentWindow.postMessage(motywPodrozy(), new URL(pod.ramkaAdres).origin); } catch (e) { /* ramka jeszcze się ładuje */ }
}
window.addEventListener("message", e => {
  // adapter w aplikacji prosi o motyw po załadowaniu; odpowiadamy tylko ramce Podróży z jej adresu
  if (!e.data || e.data.typ !== "katalogator-gotowe" || e.source !== $("podroze-ramka").contentWindow) return;
  if (pod.ramkaAdres && e.origin === new URL(pod.ramkaAdres).origin) wyslijMotywPodrozy();
});
new MutationObserver(wyslijMotywPodrozy).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme", "style"]});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", wyslijMotywPodrozy);

function pokazRamkePodrozy(adres) {
  const r = $("podroze-ramka"), motyw = motywPodrozy().motyw;
  const url = `${adres}?katalogator=1&motyw=${motyw}`;
  $("podroze-konfig").hidden = true; r.hidden = false;
  if (pod.ramkaAdres !== adres) { pod.ramkaAdres = adres; r.src = url; }   // aplikacja zostaje załadowana między zakładkami
  $("podroze-opis").textContent = adres.replace(/^http:\/\//, "").replace(/\/$/, "") +
    (pod.d && pod.d.zewnetrzny ? " · uruchomiony poza Katalogatorem" : "");
  $("podroze-stop").hidden = !(pod.d && pod.d.wlasny);
}
function pokazKonfiguracjePodrozy() {
  $("podroze-ramka").hidden = true; $("podroze-konfig").hidden = false; $("podroze-stop").hidden = true;
  $("podroze-opis").textContent = "ustawienia";
  const t = $("podroze-konfig-tresc"); t.replaceChildren();
  t.append(sekcjaPodrozy(pod.d, async () => { await odswiezPodroze(); pokazKonfiguracjePodrozy(); }));
}
async function odswiezPodroze() { pod.d = await api("/api/podroze"); return pod.d; }

async function otworzPodroze() {
  $("pomoc-menu").hidden = true;
  zamknijUstawienia();
  if (!$("galeria-nakladka").hidden) { zamknijGalerie(); trybGalerii = false; }
  $("podroze-nakladka").hidden = false; trybPodroze = true; oznaczTryby();
  try { await odswiezPodroze(); } catch (e) { toast(e.message); return; }
  const d = pod.d;
  if (d.dziala) { pokazRamkePodrozy(d.adres); return; }
  if (d.folder && !d.blad_folderu && d.node && d.auto) {      // start automatyczny
    $("podroze-opis").textContent = "uruchamiam serwer…";
    $("podroze-ramka").hidden = true; $("podroze-konfig").hidden = false;
    $("podroze-konfig-tresc").replaceChildren(el("div", {className: "info", textContent: "⏳ Uruchamiam serwer Podróży z folderu projektu…"}));
    try { pod.d = await api("/api/podroze", {akcja: "start"}); pokazRamkePodrozy(pod.d.adres); return; }
    catch (e) { toast(e.message); await odswiezPodroze().catch(() => {}); }
  }
  pokazKonfiguracjePodrozy();
}

// Sekcja ustawień Podróży — w zakładce (gdy serwer nie działa) i w Ustawieniach.
function sekcjaPodrozy(d, odswiez) {
  const s = sekcja("✈ Podróże — Google Timeline Travels");
  const zmien = async (dane, komunikat) => {
    try { pod.d = await api("/api/podroze", dane); if (komunikat) toast(komunikat); }
    catch (e) { toast(e.message); }
    odswiez();
  };
  s.append(el("div", {className: "info", innerHTML: "Zakładka pokazuje Twoją aplikację <b>Google Timeline Travels</b> (wyprawy, trasy GPS, szczyty, zdjęcia). " +
    "Katalogator uruchamia jej serwer (<code>node server.js</code>) z wybranego folderu. <b>Dane podróży zostają w tym folderze</b> — " +
    "Katalogator ich nie kopiuje ani nie wysyła, a historia lokalizacji nie trafia do repozytorium programu."}));

  const folder = el("input", {type: "text", value: d.folder || "", placeholder: d.podpowiedz || "C:\\…\\google-timeline-travels", id: "podroze-folder"});
  folder.onchange = () => zmien({folder: folder.value.trim()}, "Zapisano folder projektu.");
  s.append(wiersz(etyk("Folder projektu"), folder,
    przyc("Wybierz…", () => otworzWyborFolderu("Folder projektu Google Timeline Travels", d.folder || "", f => zmien({folder: f}, "Zapisano folder projektu.")))));
  if (!d.folder && d.podpowiedz)
    s.append(wiersz(el("span", {className: "info", textContent: "Znaleziono projekt: " + d.podpowiedz}),
                    przyc("Użyj tego folderu", () => zmien({folder: d.podpowiedz}, "Zapisano folder projektu."), "glowny")));
  if (d.blad_folderu) s.append(el("div", {className: "zle", textContent: d.blad_folderu}));

  const port = el("input", {type: "number", value: d.port, min: 1024, max: 65535, style: "width:110px", id: "podroze-port"});
  port.onchange = () => zmien({port: +port.value}, "Zapisano port.");
  s.append(wiersz(etyk("Port serwera"), port,
    el("span", {className: "info", textContent: d.node ? "Node.js: " + d.node : "⚠ Brak Node.js — zainstaluj go (nodejs.org), potrzebny do uruchomienia serwera."})));
  s.append(pole("Uruchamiaj serwer automatycznie po wejściu w zakładkę Podróże", d.auto, v => zmien({auto: v})));

  const gotowy = d.folder && !d.blad_folderu && d.node;
  s.append(wiersz(
    d.dziala ? el("span", {className: "ok", textContent: d.zewnetrzny ? "● Serwer działa (uruchomiony poza Katalogatorem)" : "● Serwer działa"})
             : el("span", {className: "info", textContent: "○ Serwer zatrzymany"}),
    d.dziala ? przyc("Otwórz zakładkę", () => otworzPodroze(), "glowny") : przyc("▶ Uruchom serwer", () => zmien({akcja: "start"}, "Serwer Podróży działa."), "glowny"),
    d.wlasny ? przyc("⏹ Zatrzymaj", () => zmien({akcja: "stop"}, "Zatrzymano serwer Podróży.")) : null));
  if (!gotowy && !d.dziala) s.lastChild.querySelector("button.glowny").disabled = true;

  s.append(el("div", {className: "info", innerHTML: "<b>Adapter motywu</b> — jeden skrypt i styl dopisywane do projektu (z kopią <code>index.html.katalogator.bak</code>). " +
    "Dzięki nim aplikacja w zakładce dostaje czcionkę, kolory i jasny / ciemny motyw Katalogatora (zmienne CSS <code>--kat-*</code>), " +
    "a dalsze dopasowanie wyglądu kart i map robisz we własnym CSS projektu."}));
  s.append(wiersz(
    el("span", {className: d.adapter ? "ok" : "info", textContent: d.adapter ? "✓ Adapter zainstalowany w projekcie" : "Adapter nie jest zainstalowany"}),
    d.adapter ? przyc("Usuń adapter", () => zmien({akcja: "adapter-usun"}, "Usunięto adapter z projektu."))
              : przyc("Zainstaluj adapter motywu", () => zmien({akcja: "adapter"}, "Zainstalowano adapter — odśwież zakładkę."), "", "Dopisuje do index.html jedną linię (z kopią zapasową)")));
  if (!d.folder || d.blad_folderu) s.lastChild.querySelectorAll("button").forEach(b => b.disabled = true);
  return s;
}

$("podroze-odswiez").onclick = () => { const r = $("podroze-ramka"); if (pod.ramkaAdres) r.src = r.src; };
$("podroze-przegladarka").onclick = () => { if (pod.ramkaAdres) window.open(pod.ramkaAdres, "_blank"); };
$("podroze-ust").onclick = async () => { try { await odswiezPodroze(); } catch (e) { toast(e.message); } pokazKonfiguracjePodrozy(); };
$("podroze-stop").onclick = async () => {
  try { pod.d = await api("/api/podroze", {akcja: "stop"}); } catch (e) { toast(e.message); return; }
  pod.ramkaAdres = ""; $("podroze-ramka").src = "about:blank"; pokazKonfiguracjePodrozy();
};
