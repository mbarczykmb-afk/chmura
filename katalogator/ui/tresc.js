// 🧠 Wyszukiwanie po treści (CLIP, lokalnie): przycisk przy polu szukania → okno z modelem i przygotowaniem.
// Samo wyszukiwanie działa w zwykłym polu „Szukaj” — słowa, których nie ma w nazwach plików, dają zdjęcia podobne treścią.
"use strict";
(function () {
  const pole = document.getElementById("szukaj");
  if (!pole) return;
  const btn = document.createElement("button");
  btn.id = "tresc-btn"; btn.type = "button"; btn.textContent = "🧠"; btn.className = "maly";
  btn.title = "Szukanie po treści zdjęcia (np. „plaża”, „pies”, „tort”) — działa w całości na tym komputerze";
  pole.after(btn);
  const okno = document.createElement("div");
  okno.className = "tresc-okno"; okno.hidden = true;
  okno.innerHTML = `<div class="tresc-karta"><button class="tresc-x" aria-label="Zamknij">✕</button>
    <h3>🧠 Szukanie po treści zdjęcia</h3>
    <p class="tresc-opis">Wpisz w polu „Szukaj” to, co jest na zdjęciu — <i>plaża</i>, <i>pies na śniegu</i>, <i>tort urodzinowy</i>,
      <i>zachód słońca</i>. Program rozpoznaje treść zdjęć sam, na tym komputerze (nic nie jest wysyłane).
      Działa też razem z datą: <i>plaża 2023</i>.</p>
    <div class="tresc-stan"></div><div class="tresc-pasek" hidden><i></i></div><div class="tresc-akcje"></div></div>`;
  document.body.append(okno);
  const css = document.createElement("style");
  css.textContent = `#tresc-btn{margin-left:4px;height:34px;border-radius:999px}
.tresc-okno{position:fixed;inset:0;z-index:60;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45)}
.tresc-okno[hidden]{display:none}
.tresc-karta{position:relative;width:min(520px,94vw);background:var(--panel);color:var(--fg,inherit);border:1px solid var(--lin);border-radius:14px;padding:18px 20px}
.tresc-karta h3{margin:0 0 8px}.tresc-opis{font-size:13px;color:var(--mut);line-height:1.5}
.tresc-stan{margin:10px 0;font-size:13px}.tresc-akcje{display:flex;gap:8px;flex-wrap:wrap}
.tresc-pasek{height:6px;border-radius:3px;background:var(--lin);overflow:hidden;margin:6px 0 10px}.tresc-pasek i{display:block;height:100%;background:var(--akc)}
.tresc-x{position:absolute;right:10px;top:10px;border:0;background:transparent;color:var(--mut);font-size:16px;cursor:pointer}`;
  document.head.append(css);
  let odpytuj = null;
  const el = (t, p, tekst) => { const e = document.createElement(t); Object.assign(e, p || {}); if (tekst) e.textContent = tekst; return e; };
  async function rysuj() {
    let s;
    try { s = await api("/api/g/tresc"); } catch (e) { okno.querySelector(".tresc-stan").textContent = e.message; return; }
    const st = okno.querySelector(".tresc-stan"), ak = okno.querySelector(".tresc-akcje"), pas = okno.querySelector(".tresc-pasek");
    const ile = s.zindeksowane || 0, zdj = s.zdjec || 0;
    st.textContent = s.blad ? "⚠ " + s.blad : s.trwa ? (s.komunikat || "Pracuję…") + (s.wszystkie ? ` ${s.zrobione} / ${s.wszystkie}${s.etap === "pobieranie" ? " MB" : ""}` : "")
      : !s.pobrany ? "Model rozpoznawania treści nie jest jeszcze pobrany (ok. 230 MB, jednorazowo)."
      : `Przygotowane zdjęcia: ${ile.toLocaleString("pl-PL")}` + (zdj ? ` z ${zdj.toLocaleString("pl-PL")} w tym widoku` : "") +
        (s.komunikat ? ` · ${s.komunikat}` : "");
    pas.hidden = !(s.trwa && s.wszystkie);
    if (!pas.hidden) pas.firstElementChild.style.width = Math.min(100, 100 * s.zrobione / s.wszystkie) + "%";
    ak.replaceChildren();
    const akcja = (tekst, sciezka, glowny) => {
      const b = el("button", {className: glowny ? "glowny maly" : "maly"}, tekst);
      b.onclick = async () => { try { await post(sciezka, {}); } catch (e) { toastG(e.message); } rysuj(); };
      ak.append(b);
    };
    if (s.trwa) akcja("Przerwij", "/api/g/tresc/przerwij");
    else if (!s.pobrany) akcja("⬇ Pobierz model (230 MB)", "/api/g/tresc/pobierz", true);
    else akcja(ile ? "Przygotuj nowe zdjęcia" : "Przygotuj wyszukiwanie", "/api/g/tresc/indeksuj", true);
    clearTimeout(odpytuj);
    if (!okno.hidden && s.trwa) odpytuj = setTimeout(rysuj, 1000);
  }
  btn.onclick = () => { okno.hidden = false; rysuj(); };
  okno.addEventListener("click", e => { if (e.target === okno || e.target.classList.contains("tresc-x")) { okno.hidden = true; clearTimeout(odpytuj); } });
})();
