// 🛟 Odzyskiwanie usuniętych plików: kosze Windows, kosz programu, kopia zapasowa, potem Windows File Recovery
"use strict";

const odz = {info: null, typ: "wszystko", zegar: null, wyniki: [], razem: 0, min: 0};
const IKONY_ODZ = {zdjecia: "🖼️", filmy: "🎬", dokumenty: "📄", inne: "📦"};
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
  opisSkad();
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
  odz.typ = b.dataset.t;
  $("odz-typ").querySelectorAll("button").forEach(x => x.classList.toggle("akt", x === b));
};
const odzTryb = () => document.querySelector('input[name="odz-tryb"]:checked').value === "1";
const odzRozmiar = b => rozmiar(b || 0);

// --- 2. szybkie miejsca: kosze Windows, kosz programu, kopia zapasowa ---
$("odz-szukaj").onclick = async () => {
  const b = $("odz-szukaj"); b.disabled = true; b.textContent = "⏳ Szukam…";
  const l = $("odz-szybkie-lista"); l.replaceChildren(odzEl("div", {className: "info", textContent: "Sprawdzam kosze Windows na wszystkich dyskach, kosz programu" + (odz.info.kopia ? " i kopię zapasową (dysk sieciowy — może potrwać minutę)" : "") + "…"}));
  $("odz-szybkie").hidden = false;
  let w;
  try { w = await api("/api/odzysk/szybkie", {typ: odz.typ, fraza: $("odz-fraza").value.trim(), kopia: !!odz.info.kopia}); }
  catch (e) { l.replaceChildren(odzEl("div", {className: "uwaga", textContent: e.message})); b.disabled = false; b.textContent = "🔍 Szukaj"; return; }
  b.disabled = false; b.textContent = "🔍 Szukaj ponownie";
  l.replaceChildren();
  const grupa = (tytul, lista, opis, akcje) => {
    if (!lista || !lista.length) return 0;
    l.append(odzEl("div", {className: "odz-grupa", textContent: `${tytul} — ${lista.length}${lista.length >= 500 ? "+" : ""}`}));
    if (opis) l.append(odzEl("div", {className: "info", textContent: opis}));
    for (const x of lista.slice(0, 200)) {
      const el = odzEl("div", {className: "odz-el"}, odzEl("span", {className: "ik", textContent: IKONY_ODZ[x.rodzaj] || "📦"}),
        odzEl("div", {className: "op"}, odzEl("b", {textContent: x.nazwa, title: x.nazwa}),
              odzEl("span", {textContent: [x.oryginal || x.gdzie || "", odzRozmiar(x.rozmiar), x.usuniety ? "usunięty " + kiedyTxt(x.usuniety) : ""].filter(Boolean).join(" · ")})),
        odzEl("div", {className: "akcje"}, ...akcje(x, () => el)));
      l.append(el);
    }
    return lista.length;
  };
  const pokaz = x => odzPrzycisk("📂", () => api("/api/odzysk/pokaz", {sciezka: x.sciezka}).catch(e => toast(e.message)), "", "Pokaż w Eksploratorze");
  const przywrocBtn = (x, el, tekst) => odzPrzycisk(tekst, async () => {
    try {
      const r = await api("/api/odzysk/przywroc", {element: x});
      toast(`↺ Przywrócono: ${r.sciezka}`);
      el().replaceWith(odzEl("div", {className: "odz-el"}, odzEl("span", {className: "ik", textContent: "✅"}),
        odzEl("div", {className: "op"}, odzEl("b", {textContent: x.nazwa}), odzEl("span", {textContent: r.sciezka})), odzEl("span")));
    } catch (e) { toast(e.message); }
  }, "glowny");
  let n = 0;
  n += grupa("🗑 Kosze Windows", w.kosz_windows, "Także kosze na innych dyskach i pendrive'ach — przywracam na oryginalne miejsce.",
             (x, el) => [przywrocBtn(x, el, "↺ Przywróć"), pokaz(x)]);
  n += grupa("💾 Kopia zapasowa Katalogatora", w.kopia, "Pliki, których nie ma już w bibliotece — kopia niczego nie kasuje. Przywracam kopiując z powrotem do biblioteki." +
             (w.kopia_przerwane ? " (pokazuję pierwsze znalezione — zawęź nazwą albo rodzajem)" : ""),
             (x, el) => [przywrocBtn(x, el, "↺ Do biblioteki"), pokaz(x)]);
  n += grupa("🗑 Kosz programu (Odłożone)", w.kosz_programu, "Pliki odłożone w Katalogatorze — przywracasz w 🗑 Koszu (przycisk w nagłówku).",
             x => [odzPrzycisk("🗑 Kosz", () => { $("okno-odzysk").hidden = true; $("kosz-btn").click(); }), pokaz(x)]);
  if (!n) l.append(odzEl("div", {className: "info", textContent: "W koszach" + (odz.info.kopia ? " i w kopii zapasowej" : "") + " nic takiego nie ma — spróbuj głębokiego szukania niżej."}));
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
  const cele = i.dyski.filter(d => d.sciezka.slice(0, 2).toUpperCase() !== dysk).sort((a, b) => (b.wolne || 0) - (a.wolne || 0));
  if (z && z.zakonczone) t.append(odzEl("div", {className: "info", textContent: `Ostatnie odzyskiwanie: ${z.zrodlo} — ${kiedyTxt(z.start * 1000)}` + (z.kod ? ` (kod zakończenia ${z.kod})` : "")}),
                                  odzEl("div", {className: "odz-wiersz"}, odzPrzycisk("Pokaż odzyskane", () => pokazWyniki(true))));
  t.append(odzEl("div", {className: "info", textContent: `Szukam na dysku ${dysk}` +
    (zrodlo.length > 3 ? ` w folderze ${zrodlo.slice(2)}` : " (cały dysk)") +
    ` · ${({wszystko: "wszystkie pliki", zdjecia: "zdjęcia", filmy: "filmy", dokumenty: "dokumenty"})[odz.typ]}` +
    ($("odz-fraza").value.trim() ? ` z „${$("odz-fraza").value.trim()}” w nazwie` : "") +
    ` · tryb ${odzTryb() ? "dokładny — od kilkunastu minut do kilku godzin" : "szybki — kilka minut"}.`}));
  const ssdBox = odzEl("div"); t.append(ssdBox);
  api("/api/odzysk/ssd", {dysk}).then(r => {
    if (r.ssd) ssdBox.replaceChildren(odzEl("div", {className: "uwaga", textContent: `Dysk ${dysk} to SSD: po usunięciu Windows zwykle szybko czyści to miejsce (TRIM) — szanse na odzyskanie są małe, ale warto spróbować od razu. Dyski talerzowe, pendrive'y i karty pamięci — szanse znacznie większe.`}));
  }).catch(() => {});
  if (!cele.length) {
    t.append(odzEl("div", {className: "uwaga", textContent: `Odzyskane pliki muszą trafić na INNY dysk niż ${dysk} — podłącz pendrive albo dysk USB i kliknij „Odśwież”.`}),
             odzPrzycisk("⟳ Odśwież", otworzOdzysk));
    return;
  }
  const sel = odzEl("select", {id: "odz-cel"});
  for (const d of cele) sel.append(odzEl("option", {value: d.sciezka, textContent: `${d.sciezka.replace(/\\$/, "")} ${d.etykieta || ""} — wolne ${odzRozmiar(d.wolne)}`}));
  t.append(odzEl("div", {className: "odz-wiersz"}, odzEl("span", {className: "odz-et", textContent: "Zapisz odzyskane na"}), sel,
                 odzEl("span", {className: "info", textContent: "folder „Odzyskane przez Katalogator”"})));
  t.append(odzEl("div", {className: "odz-wiersz"}, odzPrzycisk("🛟 Zacznij odzyskiwanie", async e => {
    e.target.disabled = true;
    try {
      const r = await api("/api/odzysk/start", {zrodlo, cel: sel.value, typ: odz.typ, fraza: $("odz-fraza").value.trim(), dokladnie: odzTryb()});
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
  t.append(odzEl("div", {className: "odz-wiersz"}, odzEl("b", {textContent: `⏳ Odzyskiwanie trwa — ${z.zrodlo}`}),
                 odzEl("span", {className: "info", textContent: `od ${kiedyTxt(z.start * 1000)} · znalezione pliki: ${z.znalezione}`})));
  const p = odzEl("div", {className: "odz-pasek"}, odzEl("i")); p.firstChild.style.width = `${z.procent || 2}%`; t.append(p);
  t.append(odzEl("div", {className: "info", textContent: (z.procent != null ? `${z.procent}% · ` : "") + (z.komunikat || "Czekam na zgodę Windows (okienko „Czy zezwolić…” — kliknij Tak)…")}));
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
  try { r = await api(`/api/odzysk/wyniki?typ=${odz.typ}&min=${odz.min}&od=${odz.wyniki.length}&ile=200`); } catch (e) { toast(e.message); return; }
  odz.wyniki = odz.wyniki.concat(r.pliki); odz.razem = r.razem;
  const pasek = $("odz-wyniki-pasek"); pasek.replaceChildren();
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
  const s = $("odz-siatka"); if (odNowa) s.replaceChildren();
  s.querySelectorAll(".wiecej").forEach(x => x.remove());
  for (const p of r.pliki) {
    const ob = odzEl("div", {className: "ob", textContent: IKONY_ODZ[p.rodzaj] || "📦"});
    if (p.rodzaj === "zdjecia") {
      const im = new Image(); im.loading = "lazy"; im.alt = "";
      im.src = `/api/odzysk/min?t=${encodeURIComponent(TOKEN)}&p=${encodeURIComponent(p.sciezka)}`;
      im.onload = () => ob.replaceChildren(im);
    }
    s.append(odzEl("div", {className: "odz-k", title: `${p.gdzie}\\${p.nazwa}\nKliknij — pokaż w Eksploratorze`,
                           onclick: () => api("/api/odzysk/pokaz", {sciezka: p.sciezka}).catch(e => toast(e.message))},
                   ob, odzEl("div", {className: "op"}, odzEl("b", {textContent: p.nazwa}), odzEl("span", {textContent: odzRozmiar(p.rozmiar)}))));
  }
  if (odz.wyniki.length < odz.razem) s.append(odzPrzycisk(`Pokaż kolejne (zostało ${odz.razem - odz.wyniki.length})`, () => pokazWyniki(false), "wiecej"));
  if (!r.razem) s.append(odzEl("div", {className: "info", textContent: "Nic nie odzyskano z tymi filtrami. Spróbuj trybu „dokładnie”, całego dysku albo bez fragmentu nazwy."}));
}

// zmiana „co / gdzie / kiedy” — opis głębokiego szukania od razu aktualny
const odzOdswiez = () => { if (!$("odz-gleboko").hidden && odz.info && !(odz.info.zadanie && !odz.info.zadanie.zakonczone)) rysujGleboko(); };
$("odz-fraza").addEventListener("input", () => { clearTimeout(odz.wpis); odz.wpis = setTimeout(odzOdswiez, 400); });
$("odz-skad").addEventListener("change", odzOdswiez);
$("odz-typ").addEventListener("click", odzOdswiez);
document.querySelectorAll('input[name="odz-tryb"]').forEach(r => r.addEventListener("change", odzOdswiez));
$("odzysk-btn").onclick = otworzOdzysk;
$("m-odzysk").onclick = otworzOdzysk;
$("odz-zamknij").onclick = () => { $("okno-odzysk").hidden = true; clearTimeout(odz.zegar); };
$("okno-odzysk").addEventListener("click", e => { if (e.target.id === "okno-odzysk") $("odz-zamknij").click(); });
