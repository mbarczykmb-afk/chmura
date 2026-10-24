// ⚙ Ustawienia — zakładka w nagłówku: program (wygląd, start, telefon, most, aktualizacje, kopia), bieżący projekt,
// Przeglądarka i zapamiętane opcje Porządkowania i Sprzątania — wszystko w jednym miejscu, z możliwością zmiany
"use strict";

const ust = {d: null, zegar: null};
const dataCzas = t => t ? new Date(t * 1000).toLocaleString("pl-PL", {day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit"}) : "nigdy";

function el(tag, wlasc = {}, ...dzieci) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(wlasc)) {
    if (k === "on") for (const [z, f] of Object.entries(v)) e.addEventListener(z, f);
    else if (k in e) e[k] = v; else e.setAttribute(k, v);
  }
  e.append(...dzieci.filter(x => x !== null && x !== undefined));
  return e;
}
const sekcja = (tytul, ...tresc) => el("section", {}, el("h3", {textContent: tytul}), ...tresc);
const wiersz = (...tresc) => el("div", {className: "wiersz"}, ...tresc);
const pole = (tekst, zaznaczone, zmiana, tytul = "") => {
  const c = el("input", {type: "checkbox", checked: !!zaznaczone});
  c.onchange = async () => { try { await zmiana(c.checked); } catch (e) { c.checked = !c.checked; toast(e.message); } };
  return el("label", {title: tytul}, c, tekst);
};
const przyc = (tekst, akcja, klasa = "", tytul = "") => el("button", {textContent: tekst, className: klasa, title: tytul, on: {click: akcja}});

async function otworzUstawienia(czesc) {
  $("pomoc-menu").hidden = true;
  if (!$("galeria-nakladka").hidden) { zamknijGalerie(); trybGalerii = false; }
  $("strona-ust").hidden = false; trybUst = true; oznaczTryby();
  await rysujStroneUstawien();
  if (czesc) $(czesc).scrollIntoView();
}
const ustOtwarte = () => !$("strona-ust").hidden;
async function rysujStroneUstawien() {
  rysujUstProjekt(); rysujUstZakl();
  await Promise.all([rysujUstawienia(), rysujUstPrzeg()]);
}
async function rysujUstawienia() {
  let d;
  try { d = ust.d = await api("/api/ustawienia-programu"); } catch (e) { $("ust-tresc").textContent = e.message; return; }
  const t = $("ust-tresc"), strona = $("strona-ust"), przewin = strona.scrollTop; t.replaceChildren();

  // 🎨 wygląd
  const seg = el("span", {className: "seg"});
  for (const [m, n] of [["light", "☀ Jasny"], ["dark", "🌙 Ciemny"], ["auto", "🖥 Jak w Windows"]]) {
    seg.append(przyc(n, () => { ustawMotyw(m); rysujUstawienia(); }, wybranyMotyw === m ? "akt" : ""));
  }
  t.append(sekcja("🎨 Wygląd", wiersz(el("span", {className: "info", textContent: "Motyw okna, Przeglądarki i telefonu"}), seg)));

  // 🏠 co otwiera się po uruchomieniu
  const segS = el("span", {className: "seg"});
  for (const [m, n] of [["przegladarka", "🔭 Przeglądarka"], ["wybor", "Ekran wyboru"], ...(d.zdalna ? [["zdalna", "🌍 Biblioteka w domu"]] : [])]) {
    segS.append(przyc(n, () => { try { localStorage.setItem("kat_start", m); } catch (e) { /* bez pamięci */ } rysujUstawienia(); },
                      trybStartu() === m ? "akt" : ""));
  }
  t.append(sekcja("🏠 Po uruchomieniu", wiersz(el("span", {className: "info", textContent: "Co pokazać zaraz po starcie programu"}), segS)));

  // 🚀 start
  if (d.autostart_mozliwy) t.append(sekcja("🚀 Start",
    pole("Uruchamiaj Katalogator razem z Windows (w tle, bez okna) — telefon i automatyczna kopia działają od razu",
         d.autostart, async v => { const w = await api("/api/autostart", {wlacz: v}); d.autostart = w.autostart; })));

  // 📱 telefon
  const tel = d.telefon;
  const telStan = tel.wlaczony
    ? el("span", {className: "info"}, "Włączony — ", el("code", {textContent: (tel.adresy || [])[0] || ""}), ` · PIN ${tel.pin}` + (tel.wlasny_pin ? " (Twój, stały)" : " (losowy)"))
    : el("span", {className: "info", textContent: "Wyłączony — telefon nie ma dostępu do programu."});
  const telefonUst = async zmiany => {
    const w = await api("/api/telefon", {wlacz: tel.wlaczony, zakres: "biblioteka", sterowanie: tel.sterowanie, ...zmiany});
    if (w.blad) throw new Error(w.blad);
    rysujUstawienia();
  };
  t.append(sekcja("📱 Telefon i dostęp z innych urządzeń",
    wiersz(telStan, tel.wlaczony ? przyc("Kod QR…", () => { zamknijUstawienia(); $("telefon-btn").click(); }) : null,
           przyc(tel.wlaczony ? "Wyłącz" : "Włącz", () => telefonUst({wlacz: !tel.wlaczony}).catch(e => toast(e.message)), tel.wlaczony ? "" : "glowny")),
    pole("Pozwól sterować z telefonu (kolejne kroki, 🗑 usuwanie, 📍 miejsce, ✏ edycja, 📤 wysyłanie zdjęć)", tel.sterowanie,
         v => { tel.sterowanie = v; return tel.wlaczony ? telefonUst({sterowanie: v}) : null; }),
    wiersz(el("span", {className: "info", textContent: tel.wlasny_pin ? "Twój PIN jest stały — telefony nie muszą logować się po restarcie." : "PIN losowany przy każdym włączeniu."}),
           przyc("✎ Ustaw swój PIN", async () => {
             const n = await oknoWpisz("Twój PIN (4–12 cyfr) — zapamiętany na stałe.\nPuste = losowy przy każdym włączeniu.", "");
             if (n !== null) telefonUst({wlacz: true, pin: n.trim()}).catch(e => toast(e.message));
           }))));

  // 🌍 most do domu (ten komputer w domu) i zdalna biblioteka (komputer w pracy)
  t.append(sekcjaMostu(d.most), sekcjaZdalnej(d.zdalna));

  // ⟳ aktualizacje
  t.append(sekcja("⟳ Aktualizacje",
    wiersz(pole("Sprawdzaj automatycznie (raz na 12 godzin)", d.sprawdzaj_aktualizacje,
                v => api("/api/program/ustawienia", {sprawdzaj_aktualizacje: v})),
           el("span", {className: "info", textContent: `Wersja ${d.wersja}`}),
           przyc("Sprawdź teraz", () => sprawdzAktualizacje(true)))));

  // 💾 kopia zapasowa
  t.append(await sekcjaKopii(d.kopia));
  strona.scrollTop = przewin;
}

async function sekcjaKopii(k) {
  const trwa = stan.biezace && ["kopia", "sprawdzanie"].includes(stan.biezace.nazwa);
  const s = sekcja("💾 Kopia zapasowa i sprawdzanie plików");
  s.id = "ust-kopia";
  s.append(el("div", {className: "info", innerHTML: "Druga kopia biblioteki na <b>innym dysku albo NAS-ie</b>: kopiowane są tylko nowe i zmienione pliki, " +
    "a z kopii nic nie znika (zdjęcie skasowane przez pomyłkę zostaje w kopii). Folder „Odłożone” (kosz) jest pomijany."}));
  s.append(wiersz(el("span", {className: "info"}, "Biblioteka: ", el("code", {textContent: k.biblioteka || "— nie wybrano —"}))));
  s.append(wiersz(el("span", {className: "info"}, "Kopia: ", k.folder ? el("code", {textContent: k.folder}) : "nie wybrano",
                      k.folder && !k.dostepny ? el("b", {className: "zle", textContent: " — niedostępna (podłącz dysk)"}) : null),
                  przyc(k.folder ? "Zmień…" : "Wybierz folder…", () => {
                    otworzWyborFolderu("Gdzie trzymać kopię biblioteki? (inny dysk / NAS)", k.folder || "", async f => {
                      try { await api("/api/kopia/ustaw", {folder: f}); } catch (e) { toast(e.message); }
                      rysujUstawienia();
                    });
                  })));
  if (k.blad_miejsca) s.append(el("div", {className: "zle", textContent: k.blad_miejsca}));
  s.append(pole("Automatycznie: po każdym porządkowaniu i raz na dobę (gdy program działa)", k.auto,
                v => api("/api/kopia/ustaw", {auto: v})));
  const o = k.ostatnia;
  s.append(wiersz(el("span", {className: "info", textContent: "Ostatnia kopia: " + (o ? `${dataCzas(o.czas)} — ${o.skopiowane} plików skopiowanych, ${o.bez_zmian} bez zmian` +
    (o.liczba_bledow ? ` · błędy: ${o.liczba_bledow}` : "") : "jeszcze nie było")}),
    przyc("💾 Zrób kopię teraz", () => startKopii("/api/kopia/start"), "glowny", "Kopiuje nowe i zmienione pliki")));
  const sp = k.sprawdzanie;
  s.append(wiersz(el("span", {className: "info", textContent: "Sprawdzanie: " + (sp ? `${dataCzas(sp.czas)} — ${sp.sprawdzone} plików` : "jeszcze nie było") +
    ` · znane sumy: ${k.sprawdzonych_plikow.toLocaleString("pl-PL")} plików`}),
    przyc("🔍 Sprawdź pliki", () => startKopii("/api/kopia/sprawdz"), "",
          "Czyta każdy plik i porównuje z zapisaną sumą — wykrywa uszkodzenia dysku. Można przerwać i dokończyć później.")));
  if (trwa) s.append(el("div", {className: "info", textContent: `⏳ ${stan.biezace.tytul} trwa — postęp na pasku u góry okna.`}));
  if (k.problemy) {
    s.append(el("div", {className: "zle", innerHTML: `<b>⚠ Problemy: ${k.problemy}</b>`}));
    let p = [];
    try { p = (await api("/api/kopia/problemy")).problemy; } catch (e) { /* bez listy */ }
    for (const x of p.slice(0, 50)) {
      const akcje = [];
      if (x.rodzaj === "uszkodzony" && x.z_kopii) akcje.push(przyc("↺ Przywróć z kopii", () => problem(x, "przywroc"), "glowny"));
      if (x.rodzaj === "kopia") akcje.push(przyc("💾 Napraw kopię", () => problem(x, "napraw"), "glowny"));
      akcje.push(przyc(x.rodzaj === "uszkodzony" ? "To moja zmiana" : "Pomiń", () => problem(x, "przyjmij"), "",
                       "Uznaj obecny plik za dobry (problem zniknie z listy)"));
      s.append(el("div", {className: "problem"}, el("b", {textContent: x.sciezka}), ...akcje, el("span", {className: "info", textContent: x.opis})));
    }
  } else if (k.sprawdzanie) s.append(el("div", {className: "ok", textContent: "✓ Nie znaleziono uszkodzonych plików."}));
  return s;
}
async function startKopii(sciezka) {
  try { await api(sciezka, {}); toast(sciezka.endsWith("start") ? "💾 Kopia ruszyła — postęp na pasku u góry." : "🔍 Sprawdzanie ruszyło — postęp na pasku u góry."); }
  catch (e) { toast(e.message); }
  rysujUstawienia();
}
async function problem(x, akcja) {
  try { await api("/api/kopia/problem", {sciezka: x.sciezka, akcja}); toast(akcja === "przywroc" ? "↺ Przywrócono z kopii (uszkodzony plik w Odłożone/Uszkodzone)" : "✓ Gotowe"); }
  catch (e) { toast(e.message); }
  rysujUstawienia();
}
$("ust-btn").onclick = () => otworzUstawienia();
$("m-ustawienia").onclick = () => otworzUstawienia();
// koniec kopii / sprawdzania przy otwartym oknie — odśwież sekcję
naStan.push(() => {
  const trwa = !!(stan.biezace && ["kopia", "sprawdzanie"].includes(stan.biezace.nazwa));
  if (ust.trwalo && !trwa && ustOtwarte()) rysujUstawienia();
  ust.trwalo = trwa;
});

// ---------- 🌍 most do domu: zdalna Przeglądarka bez VPN-u na komputerze w pracy ----------
const kopiujTekst = async (tekst, co) => {
  try { await navigator.clipboard.writeText(tekst); toast("Skopiowano " + co + "."); }
  catch (e) { await oknoWpisz("Skopiuj " + co + " (Ctrl+C):", tekst); }
};
function sekcjaMostu(m) {
  const s = sekcja("🌍 Most do domu — przeglądanie z pracy bez VPN-u");
  s.append(el("div", {className: "info", innerHTML: "Na innym komputerze (np. w pracy) otworzysz swoją bibliotekę jak tutaj — <b>bez Tailscale i bez VPN-u " +
    "na tamtym komputerze</b>. Ten komputer wystawia samą Przeglądarkę pod stałym adresem <code>https://….ts.net</code> " +
    "(Tailscale Funnel). Wejście tylko z długim kluczem, <b>tylko do oglądania</b> — bez usuwania, pilota i pełnego programu. " +
    "Ten komputer musi być włączony."}));
  if (!m.tailscale && !m.wlaczony) {
    s.append(wiersz(el("span", {className: "info"}, "Potrzebny jest Tailscale na tym komputerze (tylko tutaj, w domu): ",
                       el("code", {textContent: "tailscale.com/download"}))));
    return s;
  }
  const wynik = el("div", {className: "info"});
  const wlacz = async (zmiany) => {
    wynik.textContent = "Chwilę…";
    let w;
    try { w = await api("/api/most", zmiany); } catch (e) { wynik.textContent = e.message; return; }
    if (w.blad) {
      wynik.replaceChildren(el("b", {className: "zle", textContent: w.blad}));
      if (w.link) wynik.append(" ", el("code", {textContent: w.link}), " ", przyc("Kopiuj link", () => kopiujTekst(w.link, "link")));
      if (w.link) try { window.open(w.link, "_blank"); } catch (e) { /* okno programu bez nowych kart */ }
      return;
    }
    rysujUstawienia();
  };
  if (m.wlaczony) {
    s.append(
      wiersz(el("span", {className: "info"}, "Adres: ", el("code", {textContent: m.adres}))),
      wiersz(el("span", {className: "info"}, "Klucz: ", el("code", {textContent: m.klucz})), przyc("Kopiuj klucz", () => kopiujTekst(m.klucz, "klucz"))),
      wiersz(el("span", {className: "info", innerHTML: "<b>Link do komputera w pracy</b> (adres z kluczem) — wklej go tam w ⚙ Ustawienia → 🌍 Zdalna biblioteka " +
                                                          "albo otwórz w dowolnej przeglądarce:"})),
      wiersz(el("code", {textContent: m.link, style: "overflow-wrap:anywhere"}), przyc("Kopiuj link", () => kopiujTekst(m.link, "link"), "glowny")),
      wiersz(przyc("Nowy klucz", async () => {
               if (await oknoTak("Utworzyć nowy klucz mostu?\n\nKomputery, które łączyły się starym kluczem, trzeba będzie połączyć od nowa (nowym linkiem)."))
                 wlacz({wlacz: true, nowy_klucz: true});
             }, "", "Gdy klucz trafił do niewłaściwej osoby"),
             przyc("Wyłącz most", () => wlacz({wlacz: false}))),
      wynik);
  } else {
    s.append(wiersz(el("span", {className: "info", textContent: "Wyłączony."}), przyc("Włącz most", () => wlacz({wlacz: true}), "glowny")), wynik);
  }
  return s;
}
function sekcjaZdalnej(link) {
  const s = sekcja("🌍 Zdalna biblioteka (na komputerze poza domem)");
  s.append(el("div", {className: "info", textContent: "Tu wklej link mostu skopiowany z Katalogatora w domu. Biblioteka otworzy się przyciskiem 🌍 Dom " +
    "u góry okna (albo od razu po uruchomieniu — wybierz to w „Po uruchomieniu”)."}));
  const pole = el("input", {type: "text", id: "zdalna-link", value: link || "", placeholder: "https://komputer.tailxxxx.ts.net/#k=…", style: "flex:1;min-width:0"});
  const zapisz = async v => {
    try { const w = await api("/api/zdalna", {link: v}); ustawZdalna(w.zdalna); toast(w.zdalna ? "Zapisano link do biblioteki w domu." : "Usunięto link."); rysujUstawienia(); }
    catch (e) { toast(e.message); }
  };
  s.append(wiersz(pole, przyc("Zapisz", () => zapisz(pole.value.trim()), "glowny")));
  if (link) s.append(wiersz(przyc("🌍 Otwórz bibliotekę w domu", () => otworzZdalna(link)),
                            przyc("Usuń link", () => zapisz(""))));
  return s;
}

// ---------- 📁 bieżący projekt: źródła, cel, dom, notatki, foldery przychodzące, harmonogram ----------
const etyk = tekst => el("span", {className: "etyk", textContent: tekst});
const sciezkaEl = s => el("span", {className: "sciezka", title: s, textContent: "‎" + s + "‎"});
const pustoEl = tekst => el("div", {className: "pusto", textContent: tekst});
const kluczProjektu = () => JSON.stringify([stan.projekt, stan.zrodla, stan.cel, sprzatanie(), stan.windows]);
async function zmienProjekt(zmiany, komunikat) {
  try { await api("/api/projekty/zmien", zmiany); stan = await api("/api/stan"); rysuj(); toast(komunikat); }
  catch (e) { toast(e.message); }
}
function rysujUstProjekt() {
  const t = $("ust-projekt"), p = stan.projekt || {}, sprz = sprzatanie();
  ust.projekt = kluczProjektu();
  t.replaceChildren();

  const nazwa = el("input", {type: "text", value: p.nazwa || ""});
  nazwa.onchange = () => { const n = nazwa.value.trim(); if (n && n !== p.nazwa) zmienProjekt({nazwa: n}, "Zapisano nazwę projektu."); };
  const notatki = el("textarea", {value: p.notatki || "", placeholder: "Notatki do projektu — co zrobione, co dalej…"});
  notatki.onchange = () => zmienProjekt({notatki: notatki.value}, "Zapisano notatki.");
  t.append(sekcja("📁 Projekt",
    el("div", {className: "info", textContent: "Ustawienia bieżącego projektu. Każdy projekt ma własne — po zmianie projektu ta część pokaże jego ustawienia."}),
    wiersz(etyk("Nazwa"), nazwa, przyc("Zmień projekt…", () => { zamknijUstawienia(); $("projekt-btn").click(); })),
    wiersz(etyk("Rodzaj"), el("span", {className: "info", textContent: sprz
      ? "🧹 Sprzątanie — duplikaty i śmieci na miejscu, bez kopiowania (przełączasz zakładką Sprzątanie u góry)"
      : "🗂 Porządkowanie — kopiowanie / przenoszenie do biblioteki (przełączasz zakładką Porządkowanie u góry)"})),
    notatki));

  const zr = sekcja(sprz ? "📂 Co sprzątamy" : "📂 Co porządkujemy (źródła)");
  if (!sprz) zr.append(el("div", {className: "info", innerHTML: "<b>K — Kopiuj</b>: oryginały zostają · <b>P — Przenieś</b>: oryginały znikają ze źródła po sprawdzeniu kopii."}));
  if (!stan.zrodla.length) zr.append(pustoEl("Nie wybrano folderów."));
  for (const z of stan.zrodla) {
    const seg = sprz ? null : el("span", {className: "seg"});
    if (seg) for (const [k, n] of [["kopiuj", "K — Kopiuj"], ["przenies", "P — Przenieś"]])
      seg.append(przyc(n, () => { if (z.tryb !== k) ustawZrodlo(z.sciezka, k); }, z.tryb === k ? "akt" : ""));
    zr.append(wiersz(sciezkaEl(z.sciezka), seg, przyc("✕", () => ustawZrodlo(z.sciezka, null), "", "Usuń z listy")));
  }
  zr.append(wiersz(przyc("+ Dodaj folder…", () => otworzWyborFolderu("Dodaj folder do projektu", "", f => {
    if (!stan.zrodla.some(z => norm(z.sciezka) === norm(f))) zapisz({zrodla: [...stan.zrodla, {sciezka: f, tryb: "kopiuj"}], cel: stan.cel});
  }))));
  t.append(zr);
  if (sprz) return;

  t.append(sekcja("🎯 Dokąd (biblioteka)",
    el("div", {className: "info", textContent: "Miejsce docelowe — tu powstaje uporządkowane drzewo Rok → Miesiąc → Miejsce. Pliki, które już tu są, zostają na miejscu."}),
    wiersz(stan.cel ? sciezkaEl(stan.cel) : pustoEl("Nie wybrano."),
           przyc(stan.cel ? "Zmień…" : "Wybierz…", () => otworzWyborFolderu("Wybierz miejsce docelowe", stan.cel, f => zapisz({zrodla: stan.zrodla, cel: f}))),
           stan.cel ? przyc("✕", () => zapisz({zrodla: stan.zrodla, cel: ""}), "", "Usuń") : null)));

  const dom = el("input", {type: "text", value: p.dom || "", placeholder: "np. Olkusz — puste: program wykryje sam"});
  dom.onchange = () => zmienProjekt({dom: dom.value.trim()}, "Zapisano miejsce zamieszkania.");
  t.append(sekcja("🏠 Mieszkam w",
    el("div", {className: "info", textContent: "Miejscowość zamieszkania — pomaga odróżnić zdjęcia z domu od wyjazdów przy nazywaniu folderów. Puste: najczęstsze miejsce na zdjęciach."}),
    wiersz(dom)));

  const lista = p.przychodzace || [];
  const prz = sekcja("📥 Nowe pliki — foldery przychodzące",
    el("div", {className: "info", textContent: "Np. zdjęcia z telefonu: nowe pliki są przenoszone do biblioteki według tych samych zasad."}));
  if (!lista.length) prz.append(pustoEl("Brak folderów przychodzących."));
  for (const f of lista)
    prz.append(wiersz(sciezkaEl(f), przyc("✕", () => zapisz({zrodla: stan.zrodla, cel: stan.cel, przychodzace: lista.filter(x => x !== f)}), "", "Usuń z listy")));
  prz.append(wiersz(przyc("+ Dodaj folder…", () => otworzWyborFolderu("Wybierz folder przychodzący", "", f => {
    if (!lista.includes(f)) zapisz({zrodla: stan.zrodla, cel: stan.cel, przychodzace: [...lista, f]});
  }))));
  const godz = el("input", {type: "time", value: p.harmonogram || ""});
  const moznaHarm = lista.length && stan.cel && stan.windows;
  prz.append(wiersz(etyk("Codziennie o"), godz,
    przyc("Ustaw", () => godz.value ? ustawHarmonogram(godz.value) : toast("Wybierz godzinę.")),
    p.harmonogram ? przyc("Wyłącz", () => ustawHarmonogram("")) : null,
    el("span", {className: "info", textContent: p.harmonogram ? `Włączony: codziennie o ${p.harmonogram}`
      : !stan.windows ? "Harmonogram działa tylko w Windows." : !moznaHarm ? "Najpierw dodaj folder przychodzący i wybierz bibliotekę." : "Wyłączony."})));
  t.append(prz);
}
naStan.push(() => {  // zmiana projektu, źródeł, celu… — odśwież część Projekt (nie w trakcie pisania)
  if (ustOtwarte() && kluczProjektu() !== ust.projekt && !$("ust-projekt").contains(document.activeElement)) rysujUstProjekt();
});

// ---------- 🔭 Przeglądarka: dyski i foldery, odświeżanie, zapamiętany wygląd ----------
const lsCzytaj = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } };
const lsZapisz = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* bez pamięci */ } };
function wybor(opcje, akt, zmiana) {
  const s = el("span", {className: "seg"});
  for (const [v, n] of opcje) s.append(przyc(n, () => zmiana(v), v === akt ? "akt" : ""));
  return s;
}
const poleLs = (tekst, klucz, domyslnie, tytul) =>
  pole(tekst, lsCzytaj(klucz, domyslnie) === "1", v => lsZapisz(klucz, v ? "1" : "0"), tytul);
async function zmienPrzeg(sciezka, dane) {
  try { const w = await api(sciezka, dane); if (w && w.blad) toast(w.blad); } catch (e) { toast(e.message); }
  rysujUstPrzeg();
}
async function rysujUstPrzeg() {
  const t = $("ust-przeg");
  let d;
  try { d = await api("/api/przegladarka"); } catch (e) { t.textContent = e.message; return; }
  t.replaceChildren();

  const zestaw = el("select", {}, ...(d.zestawy || []).map(z => el("option", {value: z.id, textContent: `${z.nazwa} (${z.n})`, selected: z.id === d.aktywny})));
  zestaw.onchange = () => zmienPrzeg("/api/przegladarka/zestaw", {akcja: "wybierz", id: +zestaw.value});
  const dy = sekcja("💽 Dyski i foldery",
    el("div", {className: "info", textContent: "Co pokazuje Przeglądarka. Zestaw to zapamiętana lista folderów — można mieć kilka i przełączać."}),
    wiersz(etyk("Zestaw"), zestaw));
  if (!d.foldery.length) dy.append(pustoEl("Brak folderów — Przeglądarka pokaże bibliotekę projektu."));
  for (const f of d.foldery)
    dy.append(wiersz(sciezkaEl(f), przyc("✕", () => zmienPrzeg("/api/przegladarka/foldery", {foldery: d.foldery.filter(x => x !== f)}), "", "Usuń z zestawu")));
  dy.append(wiersz(
    przyc("+ Dodaj folder…", () => otworzWyborFolderu("Dodaj folder do Przeglądarki", "", f => {
      if (!d.foldery.includes(f)) zmienPrzeg("/api/przegladarka/foldery", {foldery: [...d.foldery, f]});
    })),
    przyc("⟳ Skanuj teraz", () => zmienPrzeg("/api/przegladarka/skanuj", {}), "", "Dopisuje nowe zdjęcia z tych folderów"),
    el("span", {className: "info", textContent: d.trwa ? "⏳ Skan trwa…" : "Ostatni skan: " + dataCzas(d.ostatni_skan)})));

  const godz = el("select", {}, ...[1, 3, 6, 12, 24].map(h => el("option", {value: h, textContent: `co ${h} h`, selected: +d.co_godzin === h})));
  godz.onchange = () => zmienPrzeg("/api/przegladarka/auto", {auto: d.auto, co_godzin: +godz.value});
  const od = sekcja("⟳ Odświeżanie",
    wiersz(pole("Odświeżaj samo (nowe zdjęcia na dyskach)", d.auto, v => zmienPrzeg("/api/przegladarka/auto", {auto: v, co_godzin: +godz.value})), godz));

  const odswiez = () => rysujUstPrzeg();
  const wy = sekcja("🖼 Wygląd Przeglądarki",
    el("div", {className: "info", textContent: "Zapamiętane na tym komputerze. Zmiany widać po następnym otwarciu Przeglądarki."}),
    wiersz(etyk("Kolejność"), wybor([["nowe", "Od najnowszych"], ["stare", "Od najstarszych"]], lsCzytaj("kat_g_kol", "nowe"),
                                     v => { lsZapisz("kat_g_kol", v); odswiez(); })),
    wiersz(etyk("Pokaż"), wybor([["", "Wszystko"], ["zdjecie", "Zdjęcia"], ["film", "Filmy"], ["dokument", "Dokumenty"]], lsCzytaj("kat_g_rodzaj", ""),
                                v => { lsZapisz("kat_g_rodzaj", v); odswiez(); })),
    poleLs("Wykres lat i miesięcy nad zdjęciami", "kat_g_wykres", innerWidth > 760 ? "1" : "0"),
    poleLs("Pasek dysków nad zdjęciami", "kat_g_dyski", "0"),
    poleLs("Schowany pasek narzędzi (więcej miejsca na zdjęcia)", "kat_g_pasek", "0"),
    poleLs("Panel ℹ Właściwości w podglądzie zdjęcia", "kat_wl", "0"),
    poleLs("Tryb edycji (obrót i edycja na miniaturach)", "kat_edycja", "0"));
  t.append(dy, od, wy);
}

// ---------- 🗂 Porządkowanie i Sprzątanie: zapamiętane opcje zakładek ----------
function rysujUstZakl() {
  const t = $("ust-zakl"); t.replaceChildren();
  t.append(sekcja("🧭 Okno programu",
    pole("Schowany pasek u góry (więcej miejsca; wraca listwą „▾ Menu Katalogatora”)", lsCzytaj("kat_nagl_ukryty", "0") === "1", v => ustawNaglowek(v)),
    pole("Podpowiedzi po najechaniu myszką", !window.podpowiedzi || window.podpowiedzi.wlaczone(), v => window.podpowiedzi && window.podpowiedzi.ustaw(v))));
  const dup = $("dup-trwale");
  t.append(sekcja("♊ Duplikaty",
    pole("Od razu usuń na stałe, bez kosza", dup.checked, v => { dup.checked = v; dup.dispatchEvent(new Event("change")); },
         "Dotyczy tylko identycznych kopii (sprawdzonych bajt w bajt) — oryginał zawsze zostaje. Bez zaznaczenia kopie trafiają do Odłożone\\Duplikaty i można je cofnąć."),
    el("div", {className: "uwaga-ust", textContent: "Bez zaznaczenia kopie trafiają do kosza programu (Odłożone\\Duplikaty) i można je cofnąć."})));
  t.append(sekcja("🔀 Podobne",
    pole("Jedna grupa na ekran (Enter — zatwierdź i następna, S — zostaw wszystkie)", lsCzytaj("kat_pod_jedna", "0") === "1",
         v => { if (an.jedna !== v) $("pod-jedna").click(); })));
  t.append(sekcja("📷 Nie z aparatu",
    wiersz(etyk("Widok"), wybor([["grupy", "▦ Grupy według folderu"], ["pojedynczo", "Pojedynczo"]], lsCzytaj("kat_inne_tryb", "grupy"),
                                v => { document.querySelector(`#inne-tryb button[data-t="${v}"]`).click(); rysujUstZakl(); }))));
}

// spis części: podświetl tę, która jest na ekranie
$("strona-ust").addEventListener("scroll", () => {
  const s = $("strona-ust"), gora = s.getBoundingClientRect().top + 80;
  let akt = null;
  for (const g of s.querySelectorAll(".ust-grupa")) if (g.getBoundingClientRect().top <= gora) akt = g.id;
  s.querySelectorAll(".ust-spis a").forEach(a => a.classList.toggle("akt", a.getAttribute("href") === "#" + (akt || "ust-g-program")));
});
$("strona-ust").querySelectorAll(".ust-spis a").forEach(a => a.onclick = e => {
  e.preventDefault(); $(a.getAttribute("href").slice(1)).scrollIntoView({behavior: "smooth"});
});
