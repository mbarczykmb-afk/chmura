// 🛟 Odzyskiwanie usuniętych plików: kosze Windows, kosz programu, kopia zapasowa, potem Windows File Recovery
"use strict";

const odz = {info: null, typ: "wszystko", zegar: null, wyniki: [], razem: 0, min: 0, wylaczone: new Set()};
const IKONY_ODZ = {zdjecia: "🖼️", filmy: "🎬", dokumenty: "📄", muzyka: "🎵", archiwa: "🗜", inne: "📦"};
const NAZWY_TYPOW = {wszystko: "wszystkie pliki", zdjecia: "zdjęcia", filmy: "filmy", dokumenty: "dokumenty", muzyka: "muzykę", archiwa: "archiwa"};
// formaty danego rodzaju: wszystkie włączone; klik wyłącza / włącza; „inne” — własne rozszerzenia
function rysujFormaty() {
  const box = $("odz-formaty"); box.replaceChildren();
  const lista = (odz.info && odz.info.typy && odz.info.typy[odz.typ]) || [];
  for (const e of lista) {
    const b = odzEl("button", {textContent: e.slice(1), className: odz.wylaczone.has(e) ? "" : "akt",
                               title: odz.wylaczone.has(e) ? "Pominięte — kliknij, żeby szukać" : "Kliknij, żeby pominąć ten format"});
    b.onclick = () => { odz.wylaczone.has(e) ? odz.wylaczone.delete(e) : odz.wylaczone.add(e); rysujFormaty(); odzOdswiez(); };
    box.append(b);
  }
  if (!lista.length) box.append(odzEl("span", {className: "info", textContent: "wszystkie rodzaje plików — albo wpisz konkretne obok"}));
}
// [] = cały rodzaj; lista = tylko te formaty
function wybraneFormaty() {
  const lista = (odz.info && odz.info.typy && odz.info.typy[odz.typ]) || [];
  const wlasne = $("odz-wlasne").value.split(/[\s,;]+/).map(x => x.trim().toLowerCase().replace(/^[*.]+/, "")).filter(x => /^[a-z0-9]{1,8}$/.test(x)).map(x => "." + x);
  const wl = lista.filter(e => !odz.wylaczone.has(e));
  if (!wlasne.length && wl.length === lista.length) return [];
  return [...new Set([...wl, ...wlasne])];
}
const opisFormatow = () => { const f = wybraneFormaty(); return f.length ? f.map(e => e.slice(1).toUpperCase()).join(", ") : NAZWY_TYPOW[odz.typ]; };
const kiedyTxt = d => d ? new Date(d).toLocaleString("pl-PL", {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"}) : "";
function odzEl(tag, wl = {}, ...dz) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(wl)) { if (k === "onclick") e.onclick = v; else e[k] = v; }
  e.append(...dz.filter(x => x != null)); return e;
}
const odzPrzycisk = (t, f, kl = "", tyt = "") => odzEl("button", {textContent: t, className: kl, title: tyt, onclick: f});

async function otworzOdzysk() {
  $("pomoc-menu").hidden = true;
  $("okno-odzysk").hidden = false;
  try { odz.info = await api("/api/odzysk"); } catch (e) { toast(e.message); return; }
  const sel = $("odz-skad"), poprz = sel.value; sel.replaceChildren();
  for (const f of odz.info.foldery) sel.append(odzEl("option", {value: f.sciezka, textContent: `📁 ${f.nazwa}`}));
  for (const d of odz.info.dyski) {
    const fs = d.system_plikow ? ` · ${d.system_plikow}` : "";
    sel.append(odzEl("option", {value: d.sciezka, textContent: `💽 Cały dysk ${d.sciezka.replace(/\\$/, "")}${d.etykieta ? " (" + d.etykieta + ")" : ""}${fs}${d.rodzaj === "wymienny" ? " — pendrive / karta" : ""}`}));
  }
  sel.append(odzEl("option", {value: "__inny", textContent: "📂 Inny folder…"}));
  if (poprz && [...sel.options].some(o => o.value === poprz)) sel.value = poprz;
  opisSkad(); rysujFormaty();
  if (odz.info.zadanie) { $("odz-gleboko").hidden = false; rysujGleboko(); }
}
function opisSkad() {
  const v = $("odz-skad").value;
  $("odz-skad-info").textContent = v && v !== "__inny" ? v : "";
}
$("odz-skad").onchange = () => {
  if ($("odz-skad").value !== "__inny") { opisSkad(); return; }
  $("okno-odzysk").hidden = true;
  otworzWyborFolderu("Z którego folderu zniknęły pliki?", "", f => {
    $("okno-odzysk").hidden = false;
    const sel = $("odz-skad");
    if (![...sel.options].some(o => o.value === f)) sel.insertBefore(odzEl("option", {value: f, textContent: `📁 ${f}`}), sel.lastChild);
    sel.value = f; opisSkad(); odzOdswiez();
  });
};
$("odz-typ").onclick = e => {
  const b = e.target.closest("button"); if (!b) return;
  odz.typ = b.dataset.t; odz.wylaczone.clear();
  $("odz-typ").querySelectorAll("button").forEach(x => x.classList.toggle("akt", x === b));
  rysujFormaty();
};
const odzTryb = () => document.querySelector('input[name="odz-tryb"]:checked').value === "1";
const odzRozmiar = b => rozmiar(b || 0);

// --- 2. szybkie miejsca: kosze Windows, kosz programu, kopia zapasowa ---
$("odz-szukaj").onclick = async () => {
  const b = $("odz-szukaj"); b.disabled = true; b.textContent = "⏳ Szukam…";
  const l = $("odz-szybkie-lista"); l.replaceChildren(odzEl("div", {className: "info", textContent: "Sprawdzam kosze Windows na wszystkich dyskach, kosz programu" + (odz.info.kopia ? " i kopię zapasową (dysk sieciowy — może potrwać minutę)" : "") + "…"}));
  $("odz-szybkie").hidden = false;
  let w;
  try { w = await api("/api/odzysk/szybkie", {typ: odz.typ, formaty: wybraneFormaty(), fraza: $("odz-fraza").value.trim(), kopia: !!odz.info.kopia}); }
  catch (e) { l.replaceChildren(odzEl("div", {className: "uwaga", textContent: e.message})); b.disabled = false; b.textContent = "🔍 Szukaj"; return; }
  b.disabled = false; b.textContent = "🔍 Szukaj ponownie";
  l.replaceChildren();
  // dokąd przywracać: na oryginalne miejsce albo do wybranego folderu
  const dokad = odzEl("div", {className: "odz-wiersz"});
  const rysujDokad = () => {
    dokad.replaceChildren(odzEl("span", {className: "odz-et", textContent: "Przywróć do"}),
      odzPrzycisk("📍 na oryginalne miejsce", () => { odz.doFolderu = ""; rysujDokad(); }, odz.doFolderu ? "" : "glowny"),
      odzPrzycisk(odz.doFolderu ? `📁 ${odz.doFolderu}` : "📂 do wybranego folderu…", () => {
        $("okno-odzysk").hidden = true;
        otworzWyborFolderu("Dokąd przywrócić znalezione pliki?", odz.doFolderu || "", f => {
          $("okno-odzysk").hidden = false; odz.doFolderu = f; rysujDokad();
        });
      }, odz.doFolderu ? "glowny" : "", "Wybrany folder (ta sama nazwa pliku; gdy zajęta — „(odzyskane)”)"));
  };
  rysujDokad(); l.append(dokad);
  // zwiniete: grupa jako jedna linia „▸ … — 500 plików” (kosz programu — to nie są pliki usunięte w Windows)
  const grupa = (tytul, lista, opis, akcje, zwiniete = false) => {
    if (!lista || !lista.length) return 0;
    const nagl = `${tytul} — ${lista.length}${lista.length >= 500 ? "+" : ""}`;
    let box = l;
    if (zwiniete) {
      box = odzEl("details", {className: "odz-zwin"}, odzEl("summary", {className: "odz-grupa", textContent: nagl}));
      l.append(box);
    } else l.append(odzEl("div", {className: "odz-grupa", textContent: nagl}));
    if (opis) box.append(odzEl("div", {className: "info", textContent: opis}));
    for (const x of lista.slice(0, 200)) {
      const kiedy = x.usuniety ? "usunięty " + kiedyTxt(x.usuniety) : x.data ? "z " + kiedyTxt(x.data) : "";
      const el = odzEl("div", {className: "odz-el"}, odzEl("span", {className: "ik", textContent: IKONY_ODZ[x.rodzaj] || "📦"}),
        odzEl("div", {className: "op"}, odzEl("b", {textContent: x.nazwa, title: x.nazwa}),
              odzEl("span", {textContent: [x.oryginal || x.gdzie || "", odzRozmiar(x.rozmiar), kiedy].filter(Boolean).join(" · ")})),
        odzEl("div", {className: "akcje"}, ...akcje(x, () => el)));
      box.append(el);
    }
    return zwiniete ? 0 : lista.length;
  };
  const pokaz = x => odzPrzycisk("📂", () => api("/api/odzysk/pokaz", {sciezka: x.sciezka}).catch(e => toast(e.message)), "", "Pokaż w Eksploratorze");
  const przywrocBtn = (x, el, tekst) => odzPrzycisk(tekst, async () => {
    try {
      const r = await api("/api/odzysk/przywroc", {element: x, do: odz.doFolderu || ""});
      toast(`↺ Przywrócono: ${r.sciezka}`);
      el().replaceWith(odzEl("div", {className: "odz-el"}, odzEl("span", {className: "ik", textContent: "✅"}),
        odzEl("div", {className: "op"}, odzEl("b", {textContent: x.nazwa}), odzEl("span", {textContent: r.sciezka})), odzEl("span")));
    } catch (e) { toast(e.message); }
  }, "glowny");
  let n = 0;
  n += grupa("🗑 Kosze Windows", w.kosz_windows, "Także kosze na innych dyskach i pendrive'ach.",
             (x, el) => [przywrocBtn(x, el, "↺ Przywróć"), pokaz(x)]);
  n += grupa("💾 Kopia zapasowa Katalogatora", w.kopia, "Pliki, których nie ma już w bibliotece — kopia niczego nie kasuje (przywracam kopiując; w kopii zostają)." +
             (w.kopia_przerwane ? " (pokazuję pierwsze znalezione — zawęź nazwą albo rodzajem)" : ""),
             (x, el) => [przywrocBtn(x, el, "↺ Przywróć"), pokaz(x)]);
  n += grupa("🗑 Kosz programu (Odłożone)", w.kosz_programu, "Pliki odłożone w Katalogatorze — przywracasz w 🗑 Koszu (przycisk w nagłówku).",
             x => [odzPrzycisk("🗑 Kosz", () => { $("okno-odzysk").hidden = true; $("kosz-btn").click(); }), pokaz(x)], true);
  if (!n) l.append(odzEl("div", {className: "uwaga", textContent: "W koszach Windows" + (odz.info.kopia ? " i w kopii zapasowej" : "") + " nic takiego nie ma — użyj głębokiego szukania niżej (punkt 3): przeszuka sam dysk, także po opróżnieniu kosza."}));
  if (!odz.info.kopia) l.append(odzEl("div", {className: "info", textContent: "💡 Na przyszłość: ⚙ Ustawienia → 💾 Kopia zapasowa — wtedy usunięte zdjęcia zawsze znajdą się tutaj, nawet po latach."}));
  $("odz-gleboko").hidden = false; rysujGleboko();
};

// --- 3. Windows File Recovery ---
async function rysujGleboko() {
  const t = $("odz-gleboko-tresc"); t.replaceChildren();
  const i = odz.info, z = i.zadanie;
  if (z && !z.zakonczone) return rysujPostep(z);
  if (!i.windows) { t.append(odzEl("div", {className: "uwaga", textContent: "Głębokie szukanie działa w Windows 10 i 11."})); return; }
  if (!i.winfr) {
    t.append(odzEl("div", {className: "info", innerHTML: "Do szukania usuniętych plików na dysku (także po opróżnieniu kosza, dawno temu, po formatowaniu, na kartach z aparatu) używam " +
      "<b>Windows File Recovery</b> — darmowego programu Microsoftu. Trzeba go raz zainstalować ze Sklepu Microsoft (ok. 1 MB)."}),
      odzEl("div", {className: "odz-wiersz"}, odzPrzycisk("⬇ Zainstaluj Windows File Recovery", async e => {
        e.target.disabled = true; e.target.textContent = "⏳ Instaluję…";
        try {
          const r = await api("/api/odzysk/instaluj", {});
          toast(r.sposob === "sklep" ? "Otworzyłem Sklep Microsoft — kliknij „Pobierz”, potem wróć tutaj." : "Instaluję w tle…");
          czekajNaWinfr(e.target);
        } catch (er) { toast(er.message); e.target.disabled = false; }
      }, "glowny")));
    return;
  }
  const zrodlo = $("odz-skad").value, dysk = zrodlo.slice(0, 2).toUpperCase();
  if (!zrodlo || zrodlo === "__inny") return;
  // dokąd: inny dysk niż przeszukiwany — także sieciowy (NAS); najpierw ten z największą ilością wolnego miejsca
  const cele = (i.cele || i.dyski).filter(d => d.sciezka.slice(0, 2).toUpperCase() !== dysk)
    .sort((a, b) => (b.rodzaj === "wymienny") - (a.rodzaj === "wymienny") || (b.wolne || 0) - (a.wolne || 0));  // pendrive / USB najpierw
  if (!odz.celWybor) try { odz.celWybor = localStorage.getItem("kat_odz_cel") || ""; } catch (e) { /* bez pamięci */ }
  if (z && z.zakonczone && z.kod) t.append(odzEl("div", {className: "uwaga", textContent: `Windows File Recovery zakończył się błędem (kod ${z.kod}). ` +
    (z.wskazowka || "Ostatnie komunikaty poniżej.")}), odzEl("div", {className: "odz-log", textContent: z.dziennik || "(pusty dziennik)"}));
  if (z && z.zakonczone) t.append(odzEl("div", {className: "info", textContent: `Ostatnie odzyskiwanie: ${z.zrodlo} — ${kiedyTxt(z.start * 1000)}` + (z.kod ? ` (kod zakończenia ${z.kod})` : "")}),
                                  odzEl("div", {className: "odz-wiersz"}, odzPrzycisk("Pokaż odzyskane", () => pokazWyniki(true))));
  t.append(odzEl("div", {className: "info", textContent: `Szukam na dysku ${dysk}` +
    (zrodlo.length > 3 ? ` w folderze ${zrodlo.slice(2)}` : " (cały dysk)") +
    ` · ${opisFormatow()}` +
    ($("odz-fraza").value.trim() ? ` z „${$("odz-fraza").value.trim()}” w nazwie` : "") +
    ` · tryb ${odzTryb() ? "dokładny — od kilkunastu minut do kilku godzin" : "szybki — kilka minut"}.`}));
  if (odzTryb() && (zrodlo.length > 3 || $("odz-fraza").value.trim())) t.append(odzEl("div", {className: "info", textContent:
    "💡 Dawno usunięte pliki często tracą nazwę i folder — wtedy filtr folderu (" + (zrodlo.length > 3 ? zrodlo : "") + ")" +
    ($("odz-fraza").value.trim() ? " i nazwy" : "") + " je pomija. Gdy nic nie znajdzie: „Gdzie był” → 💽 Cały dysk, bez fragmentu nazwy, " +
    "zostaw tylko rodzaj (np. 🎬 Filmy) — odzyskane pliki będą miały nazwy w rodzaju file_123.mp4."}));
  const ssdBox = odzEl("div"); t.append(ssdBox);
  api("/api/odzysk/ssd", {dysk}).then(r => {
    if (r.ssd) ssdBox.replaceChildren(odzEl("div", {className: "uwaga", textContent: `Dysk ${dysk} to SSD: po usunięciu Windows zwykle szybko czyści to miejsce (TRIM) — szanse na odzyskanie są małe, ale warto spróbować od razu. Dyski talerzowe, pendrive'y i karty pamięci — szanse znacznie większe.`}));
  }).catch(() => {});
  if (!cele.length) {
    t.append(odzEl("div", {className: "uwaga", textContent: `Odzyskane pliki muszą trafić na INNY dysk niż ${dysk} — podłącz pendrive albo dysk USB i kliknij „Odśwież” (dysków sieciowych Windows File Recovery nie obsługuje).`}),
             odzPrzycisk("⟳ Odśwież", otworzOdzysk));
    return;
  }
  // gdzie zapisać: dysk (folder „Odzyskane_Katalogator”) albo dowolny folder na innym dysku
  const sel = odzEl("select", {id: "odz-cel"});
  for (const d of cele) sel.append(odzEl("option", {value: d.sciezka, textContent: `${d.rodzaj === "wymienny" ? "🔌" : "💽"} ${d.sciezka.replace(/\\$/, "")} ${d.etykieta || ""}${d.rodzaj === "wymienny" ? " (pendrive / USB)" : ""} — wolne ${odzRozmiar(d.wolne)}`}));
  if (odz.celFolder && odz.celFolder.slice(0, 2).toUpperCase() !== dysk) sel.append(odzEl("option", {value: odz.celFolder, textContent: `📁 ${odz.celFolder}`}));
  sel.append(odzEl("option", {value: "__inny", textContent: "📂 Wybierz folder…"}));
  if (odz.celWybor && [...sel.options].some(o => o.value === odz.celWybor)) sel.value = odz.celWybor;
  const celInfo = odzEl("span", {className: "info"});
  const opisCelu = () => {
    const v = sel.value, dyskowy = /^[A-Za-z]:[\\/]?$/.test(v) || cele.some(d => d.sciezka === v);
    celInfo.textContent = dyskowy ? `→ ${v.replace(/[\\/]$/, "")}\\Odzyskane_Katalogator` : `→ ${v}`;
  };
  sel.onchange = () => {
    if (sel.value !== "__inny") { odz.celWybor = sel.value; try { localStorage.setItem("kat_odz_cel", sel.value); } catch (e) { /* — */ } opisCelu(); return; }
    $("okno-odzysk").hidden = true;
    otworzWyborFolderu(`Gdzie zapisać odzyskane pliki? (inny dysk niż ${dysk})`, odz.celFolder || "", f => {
      $("okno-odzysk").hidden = false;
      if (!/^[A-Za-z]:\\[A-Za-z0-9_.\-\\]*$/.test(f)) { toast("Ten folder ma spacje albo polskie litery — Windows File Recovery takich nie przyjmuje. Wybierz sam dysk albo folder w rodzaju D:\\Odzysk."); rysujGleboko(); return; }
      if (f.slice(0, 2).toUpperCase() === dysk) { toast(`Wybierz folder na innym dysku niż ${dysk} — inaczej odzyskane pliki nadpisałyby szukane.`); rysujGleboko(); return; }
      odz.celFolder = odz.celWybor = f; rysujGleboko();
    });
  };
  opisCelu();
  const odswiez = odzPrzycisk("⟳", async () => {  // właśnie podłączony pendrive
    try { const i2 = await api("/api/odzysk"); odz.info.dyski = i2.dyski; odz.info.cele = i2.cele; rysujGleboko(); } catch (e) { toast(e.message); }
  }, "", "Odśwież listę dysków (np. po podłączeniu pendrive'a)");
  t.append(odzEl("div", {className: "odz-wiersz"}, odzEl("span", {className: "odz-et", textContent: "Zapisz odzyskane w"}), sel, odswiez, celInfo),
           odzEl("div", {className: "info", textContent: "Pendrive albo dysk USB (dysków sieciowych Windows File Recovery nie obsługuje). Odzyskane pliki możesz potem przenieść na NAS."}));
  t.append(odzEl("div", {className: "odz-wiersz"}, odzPrzycisk("▶ Zacznij odzyskiwanie", async e => {
    e.target.disabled = true;
    try {
      if (sel.value === "__inny") return;
      const r = await api("/api/odzysk/start", {zrodlo, cel: sel.value, typ: odz.typ, formaty: wybraneFormaty(), fraza: $("odz-fraza").value.trim(), dokladnie: odzTryb()});
      odz.info.zadanie = r.zadanie; rysujPostep(r.zadanie);
    } catch (er) { toast(er.message); e.target.disabled = false; }
  }, "glowny"), odzEl("span", {className: "info", textContent: "Windows zapyta o zgodę (uprawnienia administratora) — kliknij „Tak”."})));
}
function czekajNaWinfr(btn, proby = 0) {
  setTimeout(async () => {
    try { const i = await api("/api/odzysk"); if (i.winfr) { odz.info = i; toast("✓ Windows File Recovery zainstalowany"); rysujGleboko(); return; } } catch (e) { /* jeszcze nie */ }
    if (proby < 60 && !$("okno-odzysk").hidden) czekajNaWinfr(btn, proby + 1);
    else if (btn) { btn.disabled = false; btn.textContent = "⬇ Zainstaluj Windows File Recovery"; }
  }, 5000);
}
function rysujPostep(z) {
  const t = $("odz-gleboko-tresc"); t.replaceChildren();
  if (z.nie_ruszylo) {  // po minucie brak dziennika: Windows nie uruchomił odzyskiwania (odmowa zgody, blokada)
    t.append(odzEl("div", {className: "uwaga", textContent: "Odzyskiwanie nie ruszyło. Windows powinien był zapytać o zgodę administratora " +
      "(okienko „Czy zezwolić tej aplikacji…” — czasem miga tylko na pasku zadań). Jeśli kliknąłeś „Nie” albo okienko się nie pojawiło — spróbuj jeszcze raz."}),
      odzEl("div", {className: "odz-wiersz"}, odzPrzycisk("↺ Spróbuj ponownie", async () => {
        try { await api("/api/odzysk/zapomnij", {}); odz.info.zadanie = null; rysujGleboko(); } catch (e) { toast(e.message); }
      }, "glowny")));
    return;
  }
  t.append(odzEl("div", {className: "odz-wiersz"}, odzEl("b", {textContent: `⏳ Odzyskiwanie trwa — ${z.zrodlo}`}),
                 odzEl("span", {className: "info", textContent: `od ${kiedyTxt(z.start * 1000)} · znalezione pliki: ${z.znalezione}`})));
  const p = odzEl("div", {className: "odz-pasek"}, odzEl("i")); p.firstChild.style.width = `${z.procent || 2}%`; t.append(p);
  const ETAPY = {"pass 1": "Etap 1 z 3: czytanie dysku", "pass 2": "Etap 2 z 3: szukanie fragmentów plików", "pass 3": "Etap 3 z 3: zapisywanie odzyskanych plików"};
  const etap = z.etap ? (ETAPY[z.etap.slice(0, 6).toLowerCase()] || z.etap) : "";
  t.append(odzEl("div", {className: "info", textContent: [etap, z.komunikat && z.komunikat !== z.etap ? z.komunikat : ""].filter(Boolean).join(" · ") ||
    "Czekam na zgodę Windows (okienko „Czy zezwolić…” — kliknij Tak)…"}));
  if (!z.znalezione) t.append(odzEl("div", {className: "info", textContent: "Pliki pojawiają się dopiero w ostatnim etapie — w pierwszym program tylko czyta dysk."}));
  if (z.dziennik) t.append(odzEl("div", {className: "odz-log", textContent: z.dziennik}));
  t.append(odzEl("div", {className: "info", textContent: "Możesz zamknąć to okno — odzyskiwanie działa dalej. Przerwać: zamknij okno „Katalogator - odzyskiwanie” na pasku zadań."}));
  clearTimeout(odz.zegar);
  odz.zegar = setTimeout(async () => {
    if ($("okno-odzysk").hidden) return;
    try {
      const r = await api("/api/odzysk/postep"); odz.info.zadanie = r.zadanie;
      if (r.zadanie && r.zadanie.zakonczone) { toast(`🛟 Odzyskiwanie zakończone — znalezione pliki: ${r.zadanie.znalezione}`); rysujGleboko(); pokazWyniki(true); }
      else if (r.zadanie) rysujPostep(r.zadanie);
    } catch (e) { /* spróbujemy za chwilę */ }
  }, 2000);
}

// --- wyniki: miniatury odzyskanych plików ---
async function pokazWyniki(odNowa) {
  const w = $("odz-wyniki"); w.hidden = false;
  if (odNowa) odz.wyniki = [];
  let r;
  try { r = await api(`/api/odzysk/wyniki?typ=${odz.typ}&f=${encodeURIComponent(wybraneFormaty().join(","))}&min=${odz.min}&od=${odz.wyniki.length}&ile=200`); } catch (e) { toast(e.message); return; }
  odz.wyniki = odz.wyniki.concat(r.pliki); odz.razem = r.razem;
  const pasek = $("odz-wyniki-pasek"); pasek.replaceChildren(); if ($("odz-stany")) $("odz-stany").remove();
  const minSel = odzEl("select");
  for (const [v, n] of [[0, "wszystkie rozmiary"], [10, "≥ 10 KB"], [100, "≥ 100 KB (bez miniaturek)"], [1024, "≥ 1 MB"]]) minSel.append(odzEl("option", {value: v, textContent: n, selected: odz.min === v}));
  minSel.onchange = () => { odz.min = +minSel.value; pokazWyniki(true); };
  pasek.append(odzEl("b", {textContent: `${r.razem.toLocaleString("pl-PL")} plików`}), minSel,
    odzPrzycisk("📂 Otwórz folder", () => api("/api/odzysk/pokaz", {sciezka: r.folder}).catch(e => toast(e.message))),
    odzPrzycisk("🔭 Przeglądaj na osi czasu", async () => {
      try {
        const o = await api("/api/przegladarka");
        if (!o.foldery.includes(r.folder)) await api("/api/przegladarka/foldery", {foldery: [...o.foldery, r.folder]});
        await api("/api/przegladarka/skanuj", {}).catch(() => {});
        $("okno-odzysk").hidden = true; otworzGalerie("przegladarka");
      } catch (e) { toast(e.message); }
    }, "", "Dodaje folder z odzyskanymi plikami do Przeglądarki — oś czasu, miniatury, podgląd"));
  const st = r.stany || {};
  if (odNowa && (st.pusty || st.uszkodzony)) {  // SSD (TRIM): wpisy o plikach są, ale treść wyczyszczona
    pasek.after(odzEl("div", {className: "uwaga", id: "odz-stany", textContent:
      `Działa ${st.ok || 0} z ${r.razem}. ` + (st.pusty ? `Puste (same zera): ${st.pusty} — dysk SSD już wyczyścił ich zawartość (TRIM), tych nie da się odzyskać żadnym programem. ` : "") +
      (st.uszkodzony ? `Uszkodzone (zły początek pliku): ${st.uszkodzony} — czasem otworzy je VLC, zwykle są niekompletne.` : "")}));
  }
  const s = $("odz-siatka"); if (odNowa) s.replaceChildren();
  s.querySelectorAll(".wiecej").forEach(x => x.remove());
  for (const p of r.pliki) {
    const ob = odzEl("div", {className: "ob", textContent: IKONY_ODZ[p.rodzaj] || "📦"});
    if (p.rodzaj === "zdjecia") {
      const im = new Image(); im.loading = "lazy"; im.alt = "";
      im.src = `/api/odzysk/min?t=${encodeURIComponent(TOKEN)}&p=${encodeURIComponent(p.sciezka)}`;
      im.onload = () => ob.replaceChildren(im);
    }
    const STANY = {pusty: "∅ pusty — SSD wyczyścił zawartość", uszkodzony: "⚠ uszkodzony"};
    if (STANY[p.stan]) ob.append(odzEl("span", {className: "odz-stan " + p.stan, textContent: STANY[p.stan]}));
    s.append(odzEl("div", {className: "odz-k" + (p.stan === "pusty" ? " pusty" : ""), title: `${p.gdzie}\\${p.nazwa}\nKliknij — pokaż w Eksploratorze`,
                           onclick: () => api("/api/odzysk/pokaz", {sciezka: p.sciezka}).catch(e => toast(e.message))},
                   ob, odzEl("div", {className: "op"}, odzEl("b", {textContent: p.nazwa}), odzEl("span", {textContent: odzRozmiar(p.rozmiar)}))));
  }
  if (odz.wyniki.length < odz.razem) s.append(odzPrzycisk(`Pokaż kolejne (zostało ${odz.razem - odz.wyniki.length})`, () => pokazWyniki(false), "wiecej"));
  if (!r.razem) s.append(odzEl("div", {className: "info", textContent: "Nic nie odzyskano z tymi filtrami. Spróbuj trybu „dokładnie”, całego dysku albo bez fragmentu nazwy."}));
}

// zmiana „co / gdzie / kiedy” — opis głębokiego szukania od razu aktualny
const odzOdswiez = () => { if (!$("odz-gleboko").hidden && odz.info && !(odz.info.zadanie && !odz.info.zadanie.zakonczone)) rysujGleboko(); };
$("odz-fraza").addEventListener("input", () => { clearTimeout(odz.wpis); odz.wpis = setTimeout(odzOdswiez, 400); });
$("odz-wlasne").addEventListener("input", () => { clearTimeout(odz.wpis); odz.wpis = setTimeout(odzOdswiez, 400); });
$("odz-skad").addEventListener("change", odzOdswiez);
$("odz-typ").addEventListener("click", odzOdswiez);
document.querySelectorAll('input[name="odz-tryb"]').forEach(r => r.addEventListener("change", odzOdswiez));
$("odzysk-btn").onclick = otworzOdzysk;
$("m-odzysk").onclick = otworzOdzysk;
$("odz-zamknij").onclick = () => { $("okno-odzysk").hidden = true; clearTimeout(odz.zegar); };
$("okno-odzysk").addEventListener("click", e => { if (e.target.id === "okno-odzysk") $("odz-zamknij").click(); });
