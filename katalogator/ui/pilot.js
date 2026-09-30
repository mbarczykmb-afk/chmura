// Pilot na telefon: co robi Katalogator na komputerze, kolejne kroki projektu, przeglądanie.
"use strict";

const $ = id => document.getElementById(id);
const KLUCZ = "katalogator_galeria_t";  // ten sam PIN-token co galeria na telefonie
let TOKEN = (() => { try { return localStorage.getItem(KLUCZ) || ""; } catch (e) { return ""; } })();
let S = null, zegar = null, wysylam = false;

const IKONY = {skan: "🔍", dup: "👯", analiza: "🧠", plan: "🌳", wykonanie: "📦", usuwanie: "🗑"};
const ZADANIA = {skan: "Skanowanie", dup: "Duplikaty", analiza: "Analiza zdjęć", plan: "Propozycja",
                 wykonanie: "Porządkowanie", przychodzace: "Folder przychodzący", aktualizacja: "Aktualizacja",
                 usuwanie: "Usuwanie"};

function czas(s) {
  if (s == null) return "";
  s = Math.round(s);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60 ? (s % 60) + " s" : ""}`.trim();
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}
function rozmiar(b) {
  const j = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (b >= 1024 && i < j.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(i > 1 ? 1 : 0).replace(".", ",")} ${j[i]}`;
}
function toast(t) {
  const e = $("toast"); e.textContent = t; e.hidden = false;
  clearTimeout(toast.z); toast.z = setTimeout(() => { e.hidden = true; }, 3500);
}
function el(tag, cls, tekst) {
  const e = document.createElement(tag); if (cls) e.className = cls; if (tekst != null) e.textContent = tekst; return e;
}

async function api(sciezka, dane) {
  const opcje = {headers: {"X-Token": TOKEN}};
  if (dane !== undefined) {
    opcje.method = "POST"; opcje.headers["Content-Type"] = "application/json"; opcje.body = JSON.stringify(dane);
  }
  const r = await fetch(sciezka, opcje);
  if (r.status === 401 || r.status === 403) { $("login").hidden = false; throw new Error("Podaj PIN"); }
  const j = await r.json();
  if (!r.ok || j.blad) throw new Error(j.blad || r.statusText);
  return j;
}

$("login-form").onsubmit = async e => {
  e.preventDefault(); $("login-blad").textContent = "";
  try {
    const r = await fetch("/api/g/zaloguj", {method: "POST", headers: {"Content-Type": "application/json"},
                                               body: JSON.stringify({pin: $("pin").value})});
    const j = await r.json();
    if (!r.ok || !j.t) throw new Error(j.blad || "Zły PIN");
    TOKEN = j.t;
    try { localStorage.setItem(KLUCZ, TOKEN); } catch (err) { /* prywatne okno */ }
    $("login").hidden = true; odswiez();
  } catch (err) { $("login-blad").textContent = err.message; }
};

// ---------- rysowanie ----------
function rysuj() {
  const s = S, zajety = !!s.biezace;
  $("wer").textContent = "wersja " + s.wersja;
  // projekt
  const sel = $("projekt");
  if (document.activeElement !== sel) {
    sel.replaceChildren(...s.projekty.map(p => {
      const o = el("option", "", (p.typ === "sprzatanie" ? "🧹 " : "🗂 ") + p.nazwa); o.value = p.id; return o;
    }));
    sel.value = s.projekt.id;
  }
  sel.disabled = zajety || !s.sterowanie;
  $("foldery").textContent = (s.projekt.typ === "sprzatanie" ? "Sprzątanie: " : "Źródła: ") +
    (s.projekt.zrodla.join(", ") || "nie wybrano") + (s.projekt.cel ? " → " + s.projekt.cel : "");
  // teraz
  const b = s.biezace, p = $("teraz-pasek");
  if (b) {
    $("teraz-t").textContent = "⏳ " + b.tytul + (b.procent != null ? ` — ${b.procent}%` : "");
    p.hidden = false; p.classList.toggle("nieokr", b.procent == null);
    p.firstElementChild.style.width = b.procent != null ? b.procent + "%" : "";
    const o = [];
    if (b.etap) o.push(b.etap);
    if (b.wszystkie) o.push(`${(b.zrobione || 0).toLocaleString("pl-PL")} z ${b.wszystkie.toLocaleString("pl-PL")}`);
    if (b.bajty_s) o.push(rozmiar(b.bajty_s) + "/s");
    if (b.eta) o.push("zostało ok. " + czas(b.eta));
    if (b.czeka) o.push("⚠ " + b.czeka);
    $("teraz-o").textContent = o.join(" · ");
    $("przerwij").hidden = !s.sterowanie;
  } else {
    $("teraz-t").textContent = "✅ Komputer czeka na kolejny krok";
    p.hidden = true; $("teraz-o").textContent = ""; $("przerwij").hidden = true;
  }
  // kroki
  const k = $("kroki"); k.replaceChildren();
  s.kroki.forEach((x, i) => {
    const trwa = b && (b.nazwa === x.klucz);
    const w = el("div", "krok" + (x.zrobiony ? " zrob" : "") + (x.nastepny ? " nast" : "") + (trwa ? " trwa" : ""));
    w.append(el("div", "ik", trwa ? "⏳" : x.zrobiony ? "✓" : String(i + 1)));
    const t = el("div"); t.append(el("div", "t", (IKONY[x.klucz] || "") + " " + x.tytul));
    if (x.opis) t.append(el("div", "o", x.opis));
    w.append(t);
    const przyc = el("button", x.nastepny ? "gl" : "", trwa ? "trwa…" : x.zrobiony ? "Ponów" : "Uruchom");
    przyc.disabled = !s.sterowanie || zajety || !x.dostepny;
    przyc.onclick = () => uruchom(x);
    w.append(przyc);
    k.append(w);
  });
  $("bez-sterowania").hidden = s.sterowanie;
  // ostatnio
  $("ostatnie-k").hidden = !s.ostatnie.length;
  $("ostatnie").replaceChildren(...s.ostatnie.map(o =>
    el("div", "kom" + (o.blad ? " bl" : ""), `${ZADANIA[o.zadanie] || o.zadanie}: ${o.komunikat} ${o.blad}`.trim())));
  // przeglądarka
  const pr = s.przegladarka;
  $("prz-o").textContent = pr.trwa ? `skanuję… ${pr.wszystkie ? Math.round(100 * pr.zrobione / pr.wszystkie) + "%" : ""}`
    : pr.foldery ? `${pr.foldery} dysków/folderów` + (pr.komunikat ? " · " + pr.komunikat : "")
    : "dodaj dyski na komputerze";
  $("prz-skanuj").disabled = !s.sterowanie || pr.trwa || !pr.foldery;
}

async function uruchom(x) {
  if (x.zmienia_pliki && !confirm(x.klucz === "usuwanie"
      ? "Usunąć NA STAŁE pliki z folderów „Odłożone” (i puste foldery)? Tego nie da się cofnąć."
      : "Uporządkować pliki według propozycji (kopiowanie / przenoszenie na dysku)?")) return;
  await akcja(x.klucz, {potwierdzam: !!x.zmienia_pliki}, x.tytul + " — uruchomione");
}
async function akcja(nazwa, dane = {}, ok = "") {
  if (wysylam) return;
  wysylam = true;
  try { S = await api("/api/pilot/" + nazwa, dane); rysuj(); if (ok) toast(ok); }
  catch (e) { if (e.message !== "Podaj PIN") toast(e.message); }
  finally { wysylam = false; planuj(); }
}
$("przerwij").onclick = () => { if (confirm("Przerwać bieżące zadanie? Postęp zostanie zapisany.")) akcja("przerwij", {}, "Przerywam…"); };
$("projekt").onchange = e => akcja("projekt", {id: e.target.value}, "Otwarto projekt");
$("prz-skanuj").onclick = () => akcja("przegladarka", {}, "Skanuję dyski Przeglądarki");

// ---------- tego dnia w poprzednich latach (raz na wejście i przy zmianie projektu) ----------
let dzienDla = null;
async function tegoDnia() {
  const klucz = S.projekt.id + "|" + new Date().toDateString();
  if (dzienDla === klucz) return;
  dzienDla = klucz;
  for (const z of ["biblioteka", "wszystko", "przegladarka"]) {  // pierwszy zbiór, który ma zdjęcia z tego dnia
    let r;
    try { r = await api(`/api/g/tego-dnia?z=${z}`); } catch (e) { continue; }
    if (!r.razem) continue;
    const lata = r.lata.map(x => x.rok);
    $("dzien-o").textContent = `${r.razem} zdjęć i filmów z ${lata.length === 1 ? "roku" : "lat"}: ${lata.slice(0, 6).join(", ")}`;
    const m = $("dzien-min"); m.replaceChildren();
    const link = `/galeria?z=${z}&pilot=1&dzien=1`;
    r.pliki.filter(p => p.rodzaj === "zdjecie").slice(0, 8).forEach(p => {
      const a = el("a"); a.href = link;
      const im = new Image(); im.loading = "lazy"; im.alt = "";
      im.src = `/api/g/miniatura?id=${p.id}&z=${z}&t=${encodeURIComponent(TOKEN)}`;
      a.append(im, el("span", "", p.data.slice(0, 4))); m.append(a);
    });
    $("dzien-link").href = link;
    $("dzien-k").hidden = false;
    return;
  }
  $("dzien-k").hidden = true;
}

// ---------- odświeżanie ----------
async function odswiez() {
  clearTimeout(zegar);
  try { S = await api("/api/pilot"); $("brak").hidden = true; rysuj(); tegoDnia(); }
  catch (e) { if (e.message !== "Podaj PIN") $("brak").hidden = false; }
  planuj();
}
function planuj() {
  clearTimeout(zegar);
  if (document.hidden || !$("login").hidden) return;
  zegar = setTimeout(odswiez, S && (S.biezace || S.przegladarka.trwa) ? 2000 : 6000);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) odswiez(); });
if (!TOKEN) $("login").hidden = false; else odswiez();
