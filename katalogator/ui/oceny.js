// ★ Ocena (1–5, klawisze 1–5) i 🏷 tagi w podglądzie zdjęcia. Zapisywane w bazie i — dla JPEG — w EXIF pliku
// (widać je w Eksploratorze Windows). Szukanie: „★4” (co najmniej 4 gwiazdki), „#wakacje”.
"use strict";
(function () {
  const ulub = document.getElementById("p-ulub");
  if (!ulub) return;
  const gw = document.createElement("span"); gw.id = "p-gwiazdki"; gw.hidden = true; gw.title = "Ocena (klawisze 1–5; kliknij tę samą, by usunąć)";
  for (let i = 1; i <= 5; i++) {
    const b = document.createElement("button"); b.type = "button"; b.dataset.o = i; b.textContent = "☆"; b.className = "gw";
    b.onclick = e => { e.stopPropagation(); const p = biezacy(); if (p) ocen(p, (p.ocena || 0) === i ? 0 : i); };
    gw.append(b);
  }
  const tg = document.createElement("button"); tg.id = "p-tagi"; tg.type = "button"; tg.hidden = true; tg.textContent = "🏷 Tagi";
  tg.title = "Tagi zdjęcia (np. wakacje, rodzina) — szukaj potem „#wakacje”";
  ulub.after(gw, tg);
  const css = document.createElement("style");
  css.textContent = `#p-gwiazdki{display:inline-flex;gap:0;margin:0 4px}#p-gwiazdki .gw{min-width:24px;padding:2px 3px;border:0;background:transparent;
    font-size:18px;line-height:1;color:#f5c542 !important;cursor:pointer}#p-gwiazdki .gw:hover{transform:scale(1.15)}`;
  document.head.append(css);

  async function ocen(p, o, dane = {}) {
    try {
      const w = await post("/api/g/ocena", {ids: [p.id], ...(o === null ? {} : {ocena: o}), ...dane});
      if (o !== null) p.ocena = o;
      if (dane.dodaj) p.tagi = [...new Set([...(p.tagi || []), ...dane.dodaj])];
      if (dane.usun) p.tagi = (p.tagi || []).filter(t => !dane.usun.includes(t));
      window.ocenyPelnego(p);
      if ((w.bledy || []).length) toastG("Zapisano w programie, ale nie w pliku: " + w.bledy[0]);
      else if (o !== null) toastG(o ? `★ Ocena: ${"★".repeat(o)}` + (w.w_pliku ? " (także w pliku)" : "") : "Ocena usunięta");
    } catch (e) { toastG(e.message); }
  }
  window.ocenBiezacy = o => { const p = biezacy(); if (p && p.rodzaj === "zdjecie") ocen(p, (p.ocena || 0) === o ? 0 : o); };
  window.ocenyPelnego = p => {
    const widac = W_PROGRAMIE && p && p.rodzaj === "zdjecie";
    gw.hidden = tg.hidden = !widac;
    if (!widac) return;
    gw.querySelectorAll(".gw").forEach(b => { b.textContent = +b.dataset.o <= (p.ocena || 0) ? "★" : "☆"; });
    tg.textContent = (p.tagi || []).length ? "🏷 " + p.tagi.slice(0, 3).join(", ") + (p.tagi.length > 3 ? "…" : "") : "🏷 Tagi";
  };
  tg.onclick = async e => {
    e.stopPropagation();
    const p = biezacy(); if (!p) return;
    let znane = [];
    try { znane = (await api("/api/g/tagi")).tagi; } catch (err) { /* bez podpowiedzi */ }
    const wpis = await oknoPytania("Tagi zdjęcia — oddziel przecinkami" + (znane.length ? `\n\nUżywane: ${znane.slice(0, 15).join(", ")}` : ""),
                                   {wpis: (p.tagi || []).join(", "), ok: "Zapisz"});
    if (wpis === null || wpis === undefined || wpis === false) return;
    const nowe = String(wpis).split(",").map(t => t.trim()).filter(Boolean);
    const stare = p.tagi || [];
    await ocen(p, null, {dodaj: nowe.filter(t => !stare.includes(t)), usun: stare.filter(t => !nowe.includes(t))});
  };
})();
