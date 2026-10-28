// Menu „＋ Nowe” w nagłówku: wczytanie pliku Google Timeline, odświeżenie danych i wycieczka ITAKA.
"use strict";
(function () {
  const przycisk = document.getElementById('btn-nowe');
  const lista = document.getElementById('menu-nowe');
  const modal = document.getElementById('nowe-plik-modal');
  if (!przycisk || !lista) return;

  const zamknijMenu = () => { lista.hidden = true; przycisk.setAttribute('aria-expanded', 'false'); };
  const zamknijModal = () => { if (modal) modal.hidden = true; };

  przycisk.addEventListener('click', (e) => {
    e.stopPropagation();
    lista.hidden = !lista.hidden;
    przycisk.setAttribute('aria-expanded', String(!lista.hidden));
  });
  document.addEventListener('click', (e) => { if (!lista.hidden && !lista.contains(e.target)) zamknijMenu(); });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    zamknijMenu(); zamknijModal();
  });
  // każda pozycja menu zamyka menu (jej własna akcja jest podpięta w app.js)
  lista.addEventListener('click', (e) => { if (e.target.closest('.np-poz')) setTimeout(zamknijMenu, 0); });

  const otworzPlik = document.getElementById('nowe-plik');
  if (otworzPlik && modal) otworzPlik.addEventListener('click', () => { modal.hidden = false; });
  const zamknij = document.getElementById('nowe-plik-zamknij');
  if (zamknij) zamknij.addEventListener('click', zamknijModal);
  if (modal) {
    modal.addEventListener('click', (e) => { if (e.target === modal) zamknijModal(); });
    const wejscie = document.getElementById('file-input');
    if (wejscie) wejscie.addEventListener('change', () => setTimeout(zamknijModal, 50));
    const karta = document.getElementById('upload-card');
    if (karta) karta.addEventListener('drop', () => setTimeout(zamknijModal, 50));
  }
})();
