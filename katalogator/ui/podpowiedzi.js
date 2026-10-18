// 💬 Podpowiedzi po najechaniu myszką: czytelny dymek zamiast systemowego „title” — szybciej, z wyróżnionym
// skrótem klawisza („Ulubione (F)”) i pierwszym zdaniem. Działa w oknie programu i w Przeglądarce (iframe),
// także dla przycisków dodanych później (nasłuch na całym dokumencie). Wyłączenie: ? → Pomoc → Podpowiedzi.
(() => {
  const KLUCZ = "kat_podp";
  // przyciski bez własnego opisu — dopisujemy go tutaj (selektor → podpowiedź)
  const DOPISZ = {
    "#tab-raport": "Raport — podsumowanie skanu: ile plików, jakich rodzajów, z których lat, ile duplikatów",
    "#tab-dup": "Duplikaty — identyczne pliki (porównane bajt po bajcie); zostaw jedną kopię, resztę odłóż",
    "#tab-dok": "Dokumenty — zdjęcia, które wyglądają na skany, paragony, zrzuty ekranu; trafią do „Dokumenty z RRRR” (2)",
    "#tab-pod": "Podobne — serie prawie takich samych zdjęć i najmniej ostre ujęcia; wybierz najlepsze",
    "#przerwij": "Przerwij skan — postęp zostaje zapisany, kolejny skan dokończy resztę",
    "#przerwij-dup": "Przerwij szukanie duplikatów — wyniki do tej pory zostają",
    "#cofnij": "Cofnij ostatnią zmianę w propozycji drzewa",
    "#cofnij-wyk": "Cofnij porządkowanie — przywraca pliki tam, gdzie były przed kopiowaniem / przeniesieniem",
    "#przych-dodaj": "Folder, do którego trafiają nowe zdjęcia (np. zrzuty z telefonu) — program dokłada je do biblioteki",
    "#przych-sprawdz": "Sprawdź, co nowego jest w folderach przychodzących, i pokaż, gdzie trafi w bibliotece",
    "#przych-harm": "Codziennie o wybranej godzinie (Harmonogram zadań Windows) — także gdy okno jest zamknięte",
    "#odswiez": "Wczytaj wyniki jeszcze raz",
    "#smieci-odloz": "Odłóż zaznaczone do kosza programu (Odłożone) — można przywrócić",
    "#pod-odloz": "Odłóż zaznaczone do kosza programu (Odłożone) — można przywrócić",
    "#nowy-folder": "Utwórz nowy folder w miejscu, które teraz oglądasz",
    "#raport-kopiuj": "Skopiuj raport do schowka — wklej go w wiadomości",
    "#raport-github": "Otwórz zgłoszenie na GitHubie z tym raportem (bez zawartości Twoich plików)",
    "#m-powitanie": "Krótki przewodnik: od czego zacząć",
    "#m-zglos": "Raport diagnostyczny do wysłania, gdy coś nie działa",
    "#m-odzysk": "Szukanie usuniętych zdjęć i filmów: kosze, kopia zapasowa, cały dysk / pendrive",
    "#kafel-mn": "Mniejsze miniatury",
    "#kafel-wi": "Większe miniatury",
    "#pelny-ekran": "Pełny ekran (F11) — Esc wraca",
    "#menu-pokaz": "Pokaz slajdów z bieżącej listy (P)",
    "#wyb-gora": "Folder wyżej",
    "#filtry-wyczysc": "Pokaż znowu wszystko — bez filtra aparatu i pory dnia",
    "#p-typ [data-t=z]": "To jest zdjęcie — w bibliotece trafi do „Zdjęcia z RRRR / miesiąc”",
    "#p-typ [data-t=d]": "To jest dokument — w bibliotece trafi do „Dokumenty z RRRR” (D)",
    ".filtr[data-r=podobne]": "Grupy prawie takich samych zdjęć (seria, ten sam kadr)",
    ".filtr[data-r=nieostre]": "Najmniej ostre zdjęcia — kandydaci do odłożenia",
    ".filtr[data-r=zdjecie]": "Tylko zdjęcia",
    ".filtr[data-r=film]": "Tylko filmy",
    ".filtr[data-r=muzyka]": "Tylko muzyka",
    ".filtr[data-r=inne]": "Pozostałe pliki (dokumenty, archiwa, programy…)",
  };
  let wl = true;
  try { wl = localStorage.getItem(KLUCZ) !== "0"; } catch (e) { /* bez pamięci — domyślnie włączone */ }

  const css = document.createElement("style");
  css.textContent = `
#podp{position:fixed;z-index:10000;max-width:340px;padding:7px 10px;border-radius:9px;font:13px/1.4 system-ui,"Segoe UI",sans-serif;
  background:#111827;color:#f3f4f6;box-shadow:0 8px 24px rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.1);pointer-events:none;
  opacity:0;transform:translateY(-3px);transition:opacity .12s,transform .12s;white-space:pre-line}
#podp.wid{opacity:1;transform:none}
#podp b{font-weight:600;color:#fff}
#podp .reszta{display:block;color:#cbd5e1;margin-top:2px}
#podp kbd{display:inline-block;min-width:16px;margin-left:6px;padding:0 5px;border-radius:5px;background:#374151;border:1px solid #4b5563;
  border-bottom-width:2px;color:#fff;font:600 11.5px/17px system-ui,sans-serif;text-align:center}
@media (prefers-reduced-motion:reduce){#podp{transition:none}}`;
  document.head.append(css);
  const dymek = document.createElement("div");
  dymek.id = "podp"; dymek.setAttribute("role", "tooltip"); dymek.hidden = true;

  function dopisz() {
    for (const [sel, t] of Object.entries(DOPISZ))
      for (const el of document.querySelectorAll(sel)) if (!el.getAttribute("title") && !el.dataset.podpTytul) el.title = t;
  }
  // „Ulubione (F)” → Ulubione [F];  „Usuń (Delete) — do kosza…” → Usuń [Delete] + reszta pod spodem
  const KLAWISZ = /^(?:(?:Ctrl|Shift|Alt)\+)?(?:[A-Z0-9]|F\d{1,2}|Esc|Delete|Enter|Spacja|Tab|[←→↑↓]|\d[–-]\d|1–4)$/;
  function rysuj(t) {
    dymek.replaceChildren();
    let glowa = t, reszta = "";
    const i = t.indexOf(" — ");
    if (i > 0 && i < 90) { glowa = t.slice(0, i); reszta = t.slice(i + 3); }
    let kl = null;  // pierwszy „(klawisz)” w pierwszym zdaniu — wycinamy go z tekstu i pokazujemy jako klawisz
    glowa = glowa.replace(/\s*\(([^()]{1,14})\)/, (c, k) => KLAWISZ.test(k) && !kl ? (kl = k, "") : c);
    const b = document.createElement(reszta || kl ? "b" : "span");
    b.textContent = glowa; dymek.append(b);
    if (kl) { const k = document.createElement("kbd"); k.textContent = kl; dymek.append(k); }
    if (reszta) { const r = document.createElement("span"); r.className = "reszta"; r.textContent = reszta[0].toUpperCase() + reszta.slice(1); dymek.append(r); }
  }
  function ustaw(el) {
    const r = el.getBoundingClientRect(); dymek.style.left = "0px"; dymek.style.top = "0px";
    const w = dymek.offsetWidth, h = dymek.offsetHeight;
    let top = r.bottom + 8;
    if (top + h > innerHeight - 6) top = Math.max(6, r.top - h - 8);  // nad elementem, gdy brak miejsca pod
    const left = Math.max(6, Math.min(innerWidth - w - 6, r.left + r.width / 2 - w / 2));
    dymek.style.left = left + "px"; dymek.style.top = top + "px";
  }

  let cel = null, zegar = null, ostatnio = 0;
  function pokaz(el) {
    const t = el.dataset.podpTytul;
    if (!t || !el.isConnected) return;
    if (!dymek.isConnected) document.body.append(dymek);
    rysuj(t); dymek.hidden = false; ustaw(el);
    requestAnimationFrame(() => dymek.classList.add("wid"));
  }
  function ukryj() {
    clearTimeout(zegar);
    if (cel) {  // systemowy „title” wraca (czytniki ekranu, kod, który go czyta)
      if (!cel.hasAttribute("title") && cel.dataset.podpTytul) cel.setAttribute("title", cel.dataset.podpTytul);
      delete cel.dataset.podpTytul;
      if (!dymek.hidden) ostatnio = Date.now();
      cel = null;
    }
    dymek.classList.remove("wid"); dymek.hidden = true;
  }
  document.addEventListener("pointerover", e => {
    if (!wl || e.pointerType === "touch") return;
    const el = e.target.closest && e.target.closest("[title]");
    if (el === cel) return;
    ukryj();
    if (!el || !el.getAttribute("title")) return;
    cel = el; el.dataset.podpTytul = el.getAttribute("title"); el.removeAttribute("title");  // bez podwójnego dymka
    // pierwszy dymek po chwili; przy przesuwaniu po pasku narzędzi — od razu
    zegar = setTimeout(() => pokaz(el), Date.now() - ostatnio < 700 ? 60 : 380);
  });
  document.addEventListener("pointerout", e => { if (cel && (!e.relatedTarget || !cel.contains(e.relatedTarget))) ukryj(); });
  for (const t of ["pointerdown", "keydown", "wheel"]) document.addEventListener(t, ukryj, true);
  addEventListener("scroll", ukryj, true); addEventListener("blur", ukryj);

  window.podpowiedzi = {
    wlaczone: () => wl,
    ustaw(v) { wl = !!v; try { localStorage.setItem(KLUCZ, wl ? "1" : "0"); } catch (e) { /* bez pamięci */ } if (!wl) ukryj(); },
    dopisz,
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", dopisz); else dopisz();
  setTimeout(dopisz, 1500);  // elementy dorysowane po starcie
})();
