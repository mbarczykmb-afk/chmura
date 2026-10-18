// 🪟 Pytania, wpisywanie i komunikaty w oknie programu zamiast systemowych confirm / prompt / alert
// (te były białe, z nagłówkiem „Komunikat z witryny 127.0.0.1…” i ginęły na tle zdjęć).
// oknoTak(tekst) → Promise<true|false>, oknoWpisz(tekst, domyślna) → Promise<tekst|null>, oknoInfo(tekst) → Promise.
// Pierwszy akapit tekstu (do pustej linii) to pytanie, reszta — wyjaśnienie pod spodem.
// Enter = OK, Esc = Anuluj. Operacje „NA STAŁE” mają czerwony przycisk.
"use strict";

function oknoPytania(tekst, {wpis = null, tylkoOk = false, ok = "OK", anuluj = "Anuluj"} = {}) {
  return new Promise(gotowe => {
    const t = String(tekst ?? ""), i = t.indexOf("\n\n");
    let glowne = i >= 0 ? t.slice(0, i) : t, reszta = i >= 0 ? t.slice(i + 2) : "";
    const m = !reszta && t.match(/^([^\n]{3,140}?\?)\s+([\s\S]+)$/);  // „Usunąć 3 zdjęcia? Trafią do kosza…”
    if (m) { glowne = m[1]; reszta = m[2]; }
    const tlo = document.createElement("div"); tlo.className = "dlg-pyt"; tlo.setAttribute("role", "dialog");
    tlo.setAttribute("aria-modal", "true");
    const o = document.createElement("div"); o.className = "okno";
    const ik = tylkoOk ? "ℹ️" : wpis !== null ? "✏️" : "❓";
    const h = document.createElement("div"); h.className = "pyt-gl";
    const ikona = document.createElement("span"); ikona.className = "pyt-ik"; ikona.textContent = ik;
    const tg = document.createElement("div"); tg.className = "pyt-tekst"; tg.textContent = glowne;
    h.append(ikona, tg); o.append(h);
    if (reszta) { const r = document.createElement("div"); r.className = "pyt-reszta"; r.textContent = reszta; o.append(r); }
    let pole = null;
    if (wpis !== null) {
      pole = document.createElement("input"); pole.type = "text"; pole.className = "pyt-pole"; pole.value = wpis;
      o.append(pole);
    }
    const dol = document.createElement("div"); dol.className = "pyt-dol";
    const bOk = document.createElement("button"); bOk.className = "pyt-ok"; bOk.textContent = ok;
    if (/NA STAŁE|nieodwracaln/i.test(t)) bOk.classList.add("grozne");
    const bNie = document.createElement("button"); bNie.className = "pyt-nie"; bNie.textContent = anuluj;
    if (!tylkoOk) dol.append(bNie);
    dol.append(bOk); o.append(dol); tlo.append(o);
    const poprzedni = document.activeElement;
    const koniec = w => {
      document.removeEventListener("keydown", klaw, true); tlo.remove();
      try { if (poprzedni && poprzedni.focus) poprzedni.focus(); } catch (e) { /* element zniknął */ }
      gotowe(w);
    };
    const tak = () => koniec(wpis !== null ? pole.value : true);
    const nie = () => koniec(wpis !== null ? null : (tylkoOk ? undefined : false));
    bOk.onclick = tak; bNie.onclick = nie;
    tlo.addEventListener("mousedown", e => { if (e.target === tlo && !tylkoOk) nie(); });
    function klaw(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); tylkoOk ? tak() : nie(); }
      else if (e.key === "Enter" && !(e.target && e.target.tagName === "BUTTON" && e.target !== bOk)) { e.preventDefault(); e.stopPropagation(); tak(); }
      else e.stopPropagation();  // klawisze nie trafiają do podglądu zdjęcia pod spodem (strzałki, Delete…)
    }
    document.addEventListener("keydown", klaw, true);
    document.body.append(tlo);
    setTimeout(() => { if (pole) { pole.focus(); pole.select(); } else bOk.focus(); }, 0);
  });
}
const oknoTak = (tekst, opcje = {}) => oknoPytania(tekst, opcje);
const oknoWpisz = (tekst, domyslna = "", opcje = {}) => oknoPytania(tekst, {...opcje, wpis: domyslna == null ? "" : String(domyslna)});
const oknoInfo = tekst => oknoPytania(tekst, {tylkoOk: true});
