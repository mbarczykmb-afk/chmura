// ⚙ Ustawienia — jedno okno: wygląd, start z Windows, telefon, Przeglądarka, aktualizacje, kopia zapasowa
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

async function otworzUstawienia() {
  $("pomoc-menu").hidden = true;
  $("okno-ust").hidden = false;
  await rysujUstawienia();
}
async function rysujUstawienia() {
  let d;
  try { d = ust.d = await api("/api/ustawienia-programu"); } catch (e) { $("ust-tresc").textContent = e.message; return; }
  const t = $("ust-tresc"), przewin = t.scrollTop; t.replaceChildren();

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
    wiersz(telStan, tel.wlaczony ? przyc("Kod QR…", () => { $("okno-ust").hidden = true; $("telefon-btn").click(); }) : null,
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

  // 🔭 Przeglądarka
  const godz = el("select", {}, ...[1, 3, 6, 12, 24].map(h => el("option", {value: h, textContent: `co ${h} h`, selected: +d.przegladarka.co_godzin === h})));
  godz.onchange = () => api("/api/przegladarka/auto", {auto: d.przegladarka.auto, co_godzin: +godz.value}).then(rysujUstawienia).catch(e => toast(e.message));
  t.append(sekcja("🔭 Przeglądarka dysków",
    wiersz(pole("Odświeżaj samo (nowe zdjęcia na dyskach)", d.przegladarka.auto,
                async v => { await api("/api/przegladarka/auto", {auto: v, co_godzin: +godz.value}); d.przegladarka.auto = v; }), godz)));

  // ⟳ aktualizacje
  t.append(sekcja("⟳ Aktualizacje",
    wiersz(pole("Sprawdzaj automatycznie (raz na 12 godzin)", d.sprawdzaj_aktualizacje,
                v => api("/api/program/ustawienia", {sprawdzaj_aktualizacje: v})),
           el("span", {className: "info", textContent: `Wersja ${d.wersja}`}),
           przyc("Sprawdź teraz", () => { $("okno-ust").hidden = true; sprawdzAktualizacje(true); }))));

  // 💾 kopia zapasowa
  t.append(await sekcjaKopii(d.kopia));
  t.scrollTop = przewin;
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
                    $("okno-ust").hidden = true;
                    otworzWyborFolderu("Gdzie trzymać kopię biblioteki? (inny dysk / NAS)", k.folder || "", async f => {
                      $("okno-ust").hidden = false;
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
$("ust-btn").onclick = otworzUstawienia;
$("m-ustawienia").onclick = otworzUstawienia;
$("ust-zamknij").onclick = () => { $("okno-ust").hidden = true; };
$("okno-ust").addEventListener("click", e => { if (e.target.id === "okno-ust") $("okno-ust").hidden = true; });
// koniec kopii / sprawdzania przy otwartym oknie — odśwież sekcję
naStan.push(() => {
  const trwa = !!(stan.biezace && ["kopia", "sprawdzanie"].includes(stan.biezace.nazwa));
  if (ust.trwalo && !trwa && !$("okno-ust").hidden) rysujUstawienia();
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
  if (link) s.append(wiersz(przyc("🌍 Otwórz bibliotekę w domu", () => { $("okno-ust").hidden = true; otworzZdalna(link); }),
                            przyc("Usuń link", () => zapisz(""))));
  return s;
}
