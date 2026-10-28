// Google Timeline Travel Summarizer & Master-Detail Explorer
// With Photo Matcher, Booking & Email Parser, and Google KML / CSV / ICS Exporters

// Global State
let allParsedEvents = [];
let detectedTrips = [];
let currentTripIndex = 0;
let currentActiveDayFilter = 'all'; // 'all' or day number (1, 2, ...)

let selectedYearFilter = 'all';
let searchQuery = '';
let currentSort = 'date-desc';
let currentGalleryDayFilter = 'all';

// Leaflet Map state (Detail View)
let map = null;
let mapMarkers = [];
let mapPhotoMarkers = [];
let mapRouteLine = null;
let mapGpsTrackLayers = [];
let mapGpsHoverMarker = null;
let showGpsTracks = true;
let currentElevationTracks = [];
let activeElevationTrackIndex = 0;
let isElevationChartCollapsed = false;
let currentChartHoverPt = null;

// Leaflet Map state (Catalog / All Trips Overview Map)
let catalogMap = null;
let catalogMapMarkers = [];
let catalogMapLines = [];

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  initCatalogMap();
  setupEventListeners();
  loadDemoData();
  initVersionWatcher();
});

// Map Initialization (Detail View) - 100% Free OpenStreetMap & Satellite Layers (No API Key Required)
function initMap() {
  const mapElement = document.getElementById('map');
  if (!mapElement || map) return;

  map = L.map('map', {
    zoomControl: true,
    scrollWheelZoom: true
  }).setView([32.74, -16.96], 11);

  // 1. Standard OpenStreetMap (OpenMaps)
  const osmStandard = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
    maxZoom: 19,
    subdomains: ['a', 'b', 'c']
  });

  // 2. Esri World Imagery (HD Satellite Aerial View)
  const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    maxZoom: 19
  });

  // 3. OpenTopoMap - topographic mountain & levada map
  const osmTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors, SRTM | &copy; <a href="https://opentopomap.org" target="_blank">OpenTopoMap</a>',
    maxZoom: 17,
    subdomains: ['a', 'b', 'c']
  });

  // 4. CartoDB Dark Matter - sleek dark travel theme
  const cartoDark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19,
    subdomains: ['a', 'b', 'c', 'd']
  });

  // Add default OpenStreetMap layer
  osmStandard.addTo(map);

  // Layer Switcher Control for the user
  const baseLayers = {
    '🗺️ Standard OpenStreetMap': osmStandard,
    '🛰️ Satelita HD (Esri World Imagery)': esriSatellite,
    '🏔️ Góry & Szlaki (OpenTopoMap)': osmTopo,
    '🌙 Ciemna Elegancja (CartoDB Dark)': cartoDark
  };
  L.control.layers(baseLayers, null, { position: 'topright' }).addTo(map);

  // ResizeObserver guarantees map renders properly regardless of tab visibility
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => {
      if (map) map.invalidateSize();
    });
    ro.observe(mapElement);
  }
  window.map = map;
}

// Map Initialization (Catalog / All Trips Map) - 100% Free OpenStreetMap & Satellite
function initCatalogMap() {
  const mapElement = document.getElementById('catalog-map');
  if (!mapElement || catalogMap) return;

  catalogMap = L.map('catalog-map', {
    zoomControl: true,
    scrollWheelZoom: true
  }).setView([40.0, 5.0], 4);

  const catalogOsm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
    maxZoom: 19,
    subdomains: ['a', 'b', 'c']
  });

  const catalogSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri',
    maxZoom: 19
  });

  const catalogDark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 19,
    subdomains: ['a', 'b', 'c', 'd']
  });

  catalogOsm.addTo(catalogMap);

  const baseLayers = {
    '🗺️ OpenStreetMap': catalogOsm,
    '🛰️ Satelita HD': catalogSatellite,
    '🌙 Dark Matter': catalogDark
  };
  L.control.layers(baseLayers, null, { position: 'topright' }).addTo(catalogMap);

  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => {
      if (catalogMap) catalogMap.invalidateSize();
    });
    ro.observe(mapElement);
  }
}

// Auto-Sync and Polling Watcher
let lastKnownVersion = null;
function initVersionWatcher() {
  setInterval(async () => {
    try {
      const res = await fetch('api/version');
      if (!res.ok) return;
      const data = await res.json();
      if (lastKnownVersion && data.version && data.version !== lastKnownVersion) {
        console.log('[Auto-Watcher] Wykryto nową wersję danych podróży:', data.version);
        lastKnownVersion = data.version;
        // Reload trips seamlessly
        const tripsRes = await fetch('sample-trips.json?t=' + Date.now());
        if (tripsRes.ok) {
          const tripsData = await tripsRes.json();
          const trips = tripsData.trips || tripsData;
          loadPreparsedTrips(trips);
          showToast(`✨ Zaktualizowano! Załadowano ${trips.length} podróży z aktualnymi zdjęciami.`);
        }
      } else if (!lastKnownVersion && data.version) {
        lastKnownVersion = data.version;
      }
    } catch (e) {
      // Offline / sandboxed mode
    }
  }, 8000);
}

function showToast(msg) {
  let toast = document.getElementById('app-notification-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'app-notification-toast';
    toast.className = 'fixed bottom-6 right-6 z-50 bg-teal-900/90 text-teal-100 border border-teal-500/40 px-4 py-3 rounded-2xl shadow-2xl backdrop-blur-md flex items-center gap-2.5 text-xs font-bold transition-all duration-300 transform translate-y-10 opacity-0 pointer-events-none';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<span>⚡</span> <span>${msg}</span>`;
  toast.classList.remove('translate-y-10', 'opacity-0', 'pointer-events-none');
  setTimeout(() => {
    toast.classList.add('translate-y-10', 'opacity-0', 'pointer-events-none');
  }, 4500);
}

// Event Listeners
function setupEventListeners() {
  // Timeline File Upload
  const fileInput = document.getElementById('file-input');
  if (fileInput) {
    fileInput.addEventListener('change', handleFileSelect);
  }

  // Upload card drag and drop
  const uploadCard = document.getElementById('upload-card');
  if (uploadCard) {
    ['dragenter', 'dragover'].forEach(eventName => {
      uploadCard.addEventListener(eventName, (e) => {
        e.preventDefault();
        uploadCard.classList.add('border-emerald-500', 'bg-emerald-50/20');
      });
    });
    ['dragleave', 'drop'].forEach(eventName => {
      uploadCard.addEventListener(eventName, (e) => {
        e.preventDefault();
        uploadCard.classList.remove('border-emerald-500', 'bg-emerald-50/20');
      });
    });
  }

  // Demo buttons
  const btnDemoHeader = document.getElementById('btn-load-demo');
  if (btnDemoHeader) btnDemoHeader.addEventListener('click', () => loadDemoData());
  const btnDemoHero = document.getElementById('btn-load-demo-hero');
  if (btnDemoHero) btnDemoHero.addEventListener('click', () => loadDemoData());

  // Navigation
  const headerBrand = document.getElementById('header-brand');
  if (headerBrand) headerBrand.addEventListener('click', showCatalogView);
  const btnBack = document.getElementById('btn-back-to-catalog');
  if (btnBack) btnBack.addEventListener('click', showCatalogView);

  // Toggle Catalog Map button
  const btnToggleCatalogMap = document.getElementById('btn-toggle-catalog-map');
  const catalogMapWrapper = document.getElementById('catalog-map-wrapper');
  const textToggleMap = document.getElementById('text-toggle-map');
  if (btnToggleCatalogMap && catalogMapWrapper) {
    btnToggleCatalogMap.addEventListener('click', () => {
      const isHidden = catalogMapWrapper.classList.toggle('hidden');
      if (textToggleMap) {
        textToggleMap.textContent = isHidden ? 'Pokaż mapę' : 'Zwiń / Rozwiń mapę';
      }
      if (!isHidden && catalogMap) {
        setTimeout(() => catalogMap.invalidateSize(), 150);
      }
    });
  }

  // Toggle GPS Tracks button in Map Control Bar & Floating On-Map Button
  const btnToggleGpsTracks = document.getElementById('btn-toggle-gps-tracks');
  if (btnToggleGpsTracks) {
    btnToggleGpsTracks.addEventListener('click', () => {
      toggleGpsTracks();
    });
  }

  const btnFloatingGpsToggle = document.getElementById('btn-floating-gps-toggle');
  if (btnFloatingGpsToggle) {
    btnFloatingGpsToggle.addEventListener('click', () => {
      toggleGpsTracks();
    });
  }

  // Catalog Map GPS Filter Button
  const btnCatalogGpsFilter = document.getElementById('btn-catalog-gps-filter');
  if (btnCatalogGpsFilter) {
    btnCatalogGpsFilter.addEventListener('click', () => {
      // Find trips that have mountain GPS tracks
      const gpsTrips = detectedTrips.filter(t => {
        let hasTrack = false;
        (t.days || []).forEach(d => {
          if ((d.mountainTracks || []).some(tr => tr.polyline && tr.polyline.length > 0)) hasTrack = true;
        });
        return hasTrack;
      });

      if (gpsTrips.length > 0) {
        // Open the premier mountain trip: Tatry i Zakopane (Sierpień 2026) or first GPS trip
        const premierIdx = detectedTrips.findIndex(t => t.title && t.title.toLowerCase().includes('tatry') && t.title.includes('2026'));
        const targetIdx = premierIdx >= 0 ? premierIdx : detectedTrips.indexOf(gpsTrips[0]);
        openTripDetail(targetIdx >= 0 ? targetIdx : 0);
      }
    });
  }

  // Toggle Elevation Profile Chart Collapse
  const btnToggleElevation = document.getElementById('btn-toggle-elevation-chart');
  if (btnToggleElevation) {
    btnToggleElevation.addEventListener('click', () => {
      toggleElevationChartCollapse();
    });
  }

  // ResizeObserver for elevation canvas to stay perfectly sharp on layout changes
  const eleChartWrapper = document.getElementById('elevation-chart-wrapper');
  if (eleChartWrapper && window.ResizeObserver) {
    const roEle = new ResizeObserver(() => {
      if (currentElevationTracks.length > 0 && !isElevationChartCollapsed) {
        renderElevationProfile();
      }
    });
    roEle.observe(eleChartWrapper);
  }

  // Help Modal
  const helpModal = document.getElementById('help-modal');
  const btnHelp = document.getElementById('btn-help');
  const btnCloseHelp = document.getElementById('btn-close-help');
  const btnCloseHelp2 = document.getElementById('btn-close-help-2');

  if (btnHelp && helpModal) btnHelp.addEventListener('click', () => helpModal.classList.remove('hidden'));
  if (btnCloseHelp && helpModal) btnCloseHelp.addEventListener('click', () => helpModal.classList.add('hidden'));
  if (btnCloseHelp2 && helpModal) btnCloseHelp2.addEventListener('click', () => helpModal.classList.add('hidden'));

  // Encrypted Timeline Modal
  const encryptedModal = document.getElementById('encrypted-timeline-modal');
  const btnCloseEncrypted = document.getElementById('btn-close-encrypted-modal');
  const btnCloseEncrypted2 = document.getElementById('btn-close-encrypted-modal-2');
  const btnOpenMadeiraFromModal = document.getElementById('btn-open-madeira-from-modal');

  if (btnCloseEncrypted && encryptedModal) btnCloseEncrypted.addEventListener('click', () => encryptedModal.classList.add('hidden'));
  if (btnCloseEncrypted2 && encryptedModal) btnCloseEncrypted2.addEventListener('click', () => encryptedModal.classList.add('hidden'));
  if (btnOpenMadeiraFromModal && encryptedModal) {
    btnOpenMadeiraFromModal.addEventListener('click', () => {
      encryptedModal.classList.add('hidden');
      showDetailView(0);
    });
  }

  // Search input
  const searchInput = document.getElementById('trip-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value.toLowerCase().trim();
      renderCatalogGrid();
    });
  }

  // Sort selector
  const sortSelector = document.getElementById('sort-selector');
  if (sortSelector) {
    sortSelector.addEventListener('change', (e) => {
      currentSort = e.target.value;
      renderCatalogGrid();
    });
  }

  // Quick Destination Filter Buttons
  document.querySelectorAll('.dest-filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.dest-filter-btn').forEach(b => {
        b.className = 'dest-filter-btn px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition';
      });
      btn.className = 'dest-filter-btn px-2.5 py-1 rounded-lg bg-teal-600 text-white font-bold transition shadow-xs';
      const targetDest = btn.getAttribute('data-dest');
      if (!targetDest || targetDest === 'all') {
        searchQuery = '';
        if (searchInput) searchInput.value = '';
      } else {
        searchQuery = targetDest.toLowerCase();
        if (searchInput) searchInput.value = targetDest;
      }
      renderCatalogGrid();
    });
  });

  // Odśwież dane podróży (przycisk)
  const btnReindexAll = document.getElementById('btn-reindex-all');
  if (btnReindexAll) {
    btnReindexAll.addEventListener('click', async () => {
      btnReindexAll.disabled = true;
      btnReindexAll.innerHTML = '<span class="animate-spin">⏳</span> Odświeżanie...';
      try {
        const res = await fetch('api/reindex', { method: 'POST' });
        if (res.ok) {
          showToast('⚡ Odświeżono dane podróży.');
          const tripsRes = await fetch('sample-trips.json?t=' + Date.now());
          if (tripsRes.ok) {
            const data = await tripsRes.json();
            loadPreparsedTrips(data.trips || data);
          }
        } else {
          showToast('Odświeżono dane lokalne.');
        }
      } catch (e) {
        showToast('Trwa sprawdzanie w tle...');
      } finally {
        btnReindexAll.disabled = false;
        btnReindexAll.innerHTML = '<span>⚡</span> <span class="hidden lg:inline">Odśwież dane</span><span class="lg:hidden">Zdjęcia</span>';
      }
    });
  }

  // Title edit controls
  const btnEditTitle = document.getElementById('btn-edit-title');
  const formEditTitle = document.getElementById('title-edit-form');
  const inputEditTitle = document.getElementById('input-edit-title');
  const btnSaveTitle = document.getElementById('btn-save-title');
  const btnCancelTitle = document.getElementById('btn-cancel-title');

  if (btnEditTitle) {
    btnEditTitle.addEventListener('click', () => {
      const trip = detectedTrips[currentTripIndex];
      if (!trip) return;
      inputEditTitle.value = trip.title;
      formEditTitle.classList.remove('hidden');
      inputEditTitle.focus();
    });
  }

  if (btnSaveTitle) btnSaveTitle.addEventListener('click', saveTripTitleEdit);

  if (inputEditTitle) {
    inputEditTitle.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') saveTripTitleEdit();
      else if (e.key === 'Escape') formEditTitle.classList.add('hidden');
    });
  }

  if (btnCancelTitle) {
    btnCancelTitle.addEventListener('click', () => {
      formEditTitle.classList.add('hidden');
    });
  }

  // ==========================================
  // EXPORT ACTIONS & DROPDOWN
  // ==========================================
  const btnExportDropdown = document.getElementById('btn-export-dropdown');
  const exportDropdownMenu = document.getElementById('export-dropdown-menu');

  if (btnExportDropdown && exportDropdownMenu) {
    btnExportDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
      exportDropdownMenu.classList.toggle('hidden');
    });

    document.addEventListener('click', () => {
      if (!exportDropdownMenu.classList.contains('hidden')) {
        exportDropdownMenu.classList.add('hidden');
      }
    });
  }

  // Export to KML (Google My Maps & Earth)
  const btnExportKml = document.getElementById('btn-export-kml');
  if (btnExportKml) {
    btnExportKml.addEventListener('click', () => {
      const trip = detectedTrips[currentTripIndex];
      if (trip && window.exportManager) {
        window.exportManager.exportToKml(trip);
      }
    });
  }

  // Export to CSV (Google Sheets & Excel)
  const btnExportCsv = document.getElementById('btn-export-csv');
  if (btnExportCsv) {
    btnExportCsv.addEventListener('click', () => {
      const trip = detectedTrips[currentTripIndex];
      if (trip && window.exportManager) {
        window.exportManager.exportToCsv(trip);
      }
    });
  }

  // Export to ICS (Google Calendar)
  const btnExportIcs = document.getElementById('btn-export-ics');
  if (btnExportIcs) {
    btnExportIcs.addEventListener('click', () => {
      const trip = detectedTrips[currentTripIndex];
      if (trip && window.exportManager) {
        window.exportManager.exportToIcs(trip);
      }
    });
  }

  // Markdown copy & download
  const btnCopyMd = document.getElementById('btn-copy-md');
  if (btnCopyMd) {
    btnCopyMd.addEventListener('click', () => {
      const textarea = document.getElementById('raw-markdown-output');
      if (!textarea) return;
      navigator.clipboard.writeText(textarea.value).then(() => {
        const originalText = btnCopyMd.innerHTML;
        btnCopyMd.innerHTML = '✅ Skopiowano!';
        setTimeout(() => btnCopyMd.innerHTML = originalText, 2000);
      });
    });
  }

  const btnDownloadMd = document.getElementById('btn-download-md');
  if (btnDownloadMd) {
    btnDownloadMd.addEventListener('click', () => {
      const text = document.getElementById('raw-markdown-output').value;
      const trip = detectedTrips[currentTripIndex];
      const filename = `${trip ? trip.title.replace(/[^a-zA-Z0-9_\-\u00A0-\u024F]/g, '_') : 'podroz'}.md`;
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  const btnPrintPlan = document.getElementById('btn-print-plan');
  if (btnPrintPlan) {
    btnPrintPlan.addEventListener('click', () => window.print());
  }

  const btnToggleRaw = document.getElementById('btn-toggle-raw');
  if (btnToggleRaw) {
    btnToggleRaw.addEventListener('click', () => {
      const textarea = document.getElementById('raw-markdown-output');
      if (textarea.rows === 4) {
        textarea.rows = 16;
        btnToggleRaw.textContent = 'Zwiń podgląd';
      } else {
        textarea.rows = 4;
        btnToggleRaw.textContent = 'Rozwiń podgląd';
      }
    });
  }

  // ==========================================
  // PHOTO MATCHER CONTROLS (Direct & Modal)
  // ==========================================
  const photoModal = document.getElementById('photo-upload-modal');
  const btnOpenPhotoMatcher = document.getElementById('btn-open-photo-matcher');
  const btnClosePhotoModal = document.getElementById('btn-close-photo-modal');
  const btnClosePhotoModal2 = document.getElementById('btn-close-photo-modal-2');
  const directPhotoInput = document.getElementById('direct-photo-input');
  const modalPhotoInput = document.getElementById('modal-photo-file-input');
  const btnModalTrigger = document.getElementById('btn-modal-trigger-file');
  const btnLoadSamplePhotosOpt = document.getElementById('btn-load-sample-photos-opt');

  function openPhotoModal() {
    if (!photoModal) return;
    photoModal.classList.remove('hidden');
    renderPhotoMatcherModalList();
  }

  if (btnOpenPhotoMatcher) btnOpenPhotoMatcher.addEventListener('click', openPhotoModal);
  if (btnClosePhotoModal) btnClosePhotoModal.addEventListener('click', () => photoModal.classList.add('hidden'));
  if (btnClosePhotoModal2) btnClosePhotoModal2.addEventListener('click', () => photoModal.classList.add('hidden'));
  if (btnModalTrigger && modalPhotoInput) btnModalTrigger.addEventListener('click', () => modalPhotoInput.click());

  async function handleUserPhotoFiles(files) {
    if (!files || files.length === 0) return;
    const trip = detectedTrips[currentTripIndex];
    if (trip && window.photoMatcher) {
      await window.photoMatcher.processFiles(files, trip);
      trip.photos = trip.photos || [];
      window.photoMatcher.photos.forEach(p => {
        if (!trip.photos.some(existing => existing.id === p.id)) {
          trip.photos.push(p);
        }
      });
      renderTripDetail(trip);
      renderPhotoMatcherModalList();
      alert(`Wczytano i dopasowano ${files.length} Twoich zdjęć do dni wyjazdu!`);
    }
  }

  const btnLoadUPhotos = document.getElementById('btn-load-u-photos');
  const folderPhotoInput = document.getElementById('folder-photo-input');
  const btnToggleGalleryGrid = document.getElementById('btn-toggle-gallery-grid');
  const gallerySearchInput = document.getElementById('gallery-search-input');

  if (btnLoadUPhotos) {
    btnLoadUPhotos.addEventListener('click', () => {
      loadUserPhotosFromIndex();
    });
  }

  if (folderPhotoInput) {
    folderPhotoInput.addEventListener('change', (e) => handleUserPhotoFiles(e.target.files));
  }

  if (directPhotoInput) {
    directPhotoInput.addEventListener('change', (e) => handleUserPhotoFiles(e.target.files));
  }
  if (modalPhotoInput) {
    modalPhotoInput.addEventListener('change', (e) => handleUserPhotoFiles(e.target.files));
  }
  if (btnLoadSamplePhotosOpt) {
    btnLoadSamplePhotosOpt.addEventListener('click', () => {
      loadUserPhotosFromIndex();
    });
  }

  if (btnToggleGalleryGrid) {
    btnToggleGalleryGrid.addEventListener('click', () => {
      const gridWrapper = document.getElementById('trip-photos-grid-wrapper');
      const textEl = document.getElementById('btn-toggle-gallery-grid-text');
      const iconEl = document.getElementById('btn-toggle-gallery-grid-icon');
      if (!gridWrapper) return;
      const isHidden = gridWrapper.classList.contains('hidden');
      if (isHidden) {
        gridWrapper.classList.remove('hidden');
        if (textEl) textEl.textContent = 'Ukryj siatkę kafelków';
        if (iconEl) iconEl.textContent = '⊟';
      } else {
        gridWrapper.classList.add('hidden');
        if (textEl) textEl.textContent = 'Pokaż siatkę kafelków';
        if (iconEl) iconEl.textContent = '⊞';
      }
    });
  }

  if (gallerySearchInput) {
    gallerySearchInput.addEventListener('input', () => {
      const trip = detectedTrips[currentTripIndex];
      if (trip) renderPhotoGalleryStrip(trip);
    });
  }

  // Day filter buttons for photo gallery
  document.querySelectorAll('.gallery-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.gallery-filter-btn').forEach(b => {
        b.className = 'gallery-filter-btn px-2 py-1 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 transition';
      });
      btn.className = 'gallery-filter-btn px-2.5 py-1 rounded-lg text-xs font-bold bg-cyan-500 text-slate-950 shadow-[0_0_10px_rgba(0,240,255,0.4)] transition';
      currentGalleryDayFilter = btn.getAttribute('data-day') || 'all';
      const trip = detectedTrips[currentTripIndex];
      if (trip) {
        renderPhotoGalleryStrip(trip);
        if (window.photoMatcher && window.map) {
          renderMapPoints(window.lastRenderedPoints || [], trip.photos || []);
        }
      }
    });
  });

  // ==========================================
  // BOOKING PARSER MODAL & CONTROLS
  // ==========================================
  const bookingModal = document.getElementById('booking-modal');
  const btnOpenBookingParser = document.getElementById('btn-open-booking-parser');
  const btnAddAnotherBooking = document.getElementById('btn-add-another-booking');
  const btnCloseBookingModal = document.getElementById('btn-close-booking-modal');
  const bookingInputText = document.getElementById('booking-input-text');
  const bookingFileInput = document.getElementById('booking-file-input');
  const btnClearBooking = document.getElementById('btn-clear-booking-input');
  const btnParseBooking = document.getElementById('btn-parse-and-attach-booking');

  function openBookingModal() {
    if (!bookingModal) return;
    bookingModal.classList.remove('hidden');
    document.getElementById('booking-parsed-preview').classList.add('hidden');
  }

  if (btnOpenBookingParser) btnOpenBookingParser.addEventListener('click', openBookingModal);
  if (btnAddAnotherBooking) btnAddAnotherBooking.addEventListener('click', openBookingModal);
  if (btnCloseBookingModal) btnCloseBookingModal.addEventListener('click', () => bookingModal.classList.add('hidden'));

  // Quick sample template buttons
  document.querySelectorAll('.btn-sample-booking').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const templateId = e.currentTarget.dataset.template;
      const template = window.bookingParser?.sampleTemplates?.find(t => t.id === templateId);
      if (template && bookingInputText) {
        bookingInputText.value = template.text;
        bookingInputText.focus();
      }
    });
  });

  if (bookingFileInput) {
    bookingFileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (file && bookingInputText) {
        const text = await file.text();
        bookingInputText.value = text;
      }
    });
  }

  if (btnClearBooking && bookingInputText) {
    btnClearBooking.addEventListener('click', () => {
      bookingInputText.value = '';
      document.getElementById('booking-parsed-preview').classList.add('hidden');
    });
  }

  if (btnParseBooking) {
    btnParseBooking.addEventListener('click', () => {
      const raw = bookingInputText ? bookingInputText.value.trim() : '';
      if (!raw) {
        alert('Wklej najpierw treść e-maila lub wybierz jeden z przycisków demonstracyjnych.');
        return;
      }

      const parsed = window.bookingParser.parseEmailText(raw);
      if (!parsed) {
        alert('Nie udało się automatycznie rozpoznać szczegółów rezerwacji. Sprawdź poprawność tekstu.');
        return;
      }

      const trip = detectedTrips[currentTripIndex];
      if (trip) {
        window.bookingParser.enrichTrip(trip, parsed);
        renderTripDetail(trip);

        // Show success preview inside modal
        const previewEl = document.getElementById('booking-parsed-preview');
        previewEl.innerHTML = `
          <div class="flex items-center gap-2 font-bold text-emerald-900">
            <span>✅ Pomyślnie rozpoznano:</span> <span>${parsed.title}</span>
          </div>
          <div class="text-emerald-800 text-xs">
            Nr rezerwacji: <b>${parsed.bookingNumber}</b> • Kategoria: <b>${parsed.categoryLabel}</b> • Koszt: <b>${parsed.price || 'N/A'}</b>
          </div>
          <div class="text-2xs text-emerald-700">
            Rezerwacja została powiązana z osią czasu i dodana do podsumowania podróży.
          </div>
        `;
        previewEl.classList.remove('hidden');

        setTimeout(() => {
          bookingModal.classList.add('hidden');
        }, 1500);
      }
    });
  }

  // Setup Mobile UX, Bottom Navigation Bar, and PWA integration
  setupMobileAndPwaListeners();
}

// Mobile, Bottom Navigation & PWA Handling
let deferredInstallPrompt = null;

function setupMobileAndPwaListeners() {
  // Capture PWA install prompt event
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    const promptContainer = document.getElementById('pwa-prompt-container');
    if (promptContainer) promptContainer.classList.remove('hidden');
    console.log('[PWA] beforeinstallprompt captured and ready');
  });

  window.addEventListener('appinstalled', () => {
    console.log('[PWA] Aplikacja zainstalowana pomyślnie!');
    deferredInstallPrompt = null;
    const banner = document.getElementById('android-pwa-banner');
    if (banner) banner.classList.add('hidden');
  });

  const btnPwaInstall = document.getElementById('btn-pwa-install');
  const btnBannerInstall = document.getElementById('btn-banner-install');
  const btnTriggerPwaInstall = document.getElementById('btn-trigger-pwa-install');
  const pwaModal = document.getElementById('pwa-install-modal');
  const btnClosePwa = document.getElementById('btn-close-pwa-modal');
  const btnClosePwaFooter = document.getElementById('btn-close-pwa-modal-footer');
  const btnBannerClose = document.getElementById('btn-banner-close');
  const androidPwaBanner = document.getElementById('android-pwa-banner');

  const openInstallModal = () => {
    if (pwaModal) pwaModal.classList.remove('hidden');
  };

  if (btnPwaInstall) btnPwaInstall.addEventListener('click', openInstallModal);
  if (btnBannerInstall) btnBannerInstall.addEventListener('click', openInstallModal);

  if (btnTriggerPwaInstall) {
    btnTriggerPwaInstall.addEventListener('click', async () => {
      if (deferredInstallPrompt) {
        deferredInstallPrompt.prompt();
        const choice = await deferredInstallPrompt.userChoice;
        if (choice.outcome === 'accepted') {
          console.log('[PWA] User accepted install prompt');
          if (pwaModal) pwaModal.classList.add('hidden');
        }
        deferredInstallPrompt = null;
      } else {
        alert('Aby zainstalować aplikację na Androidzie:\n1. Otwórz menu Chrome (⋮ w prawym górnym rogu)\n2. Wybierz „Zainstaluj aplikację” lub „Dodaj do ekranu głównego”.\n\nMożesz też użyć gotowego projektu natywnego z folderu android/!');
      }
    });
  }

  if (btnBannerClose && androidPwaBanner) {
    btnBannerClose.addEventListener('click', () => {
      androidPwaBanner.classList.add('hidden');
    });
  }
  if (btnClosePwa && pwaModal) {
    btnClosePwa.addEventListener('click', () => pwaModal.classList.add('hidden'));
  }
  if (btnClosePwaFooter && pwaModal) {
    btnClosePwaFooter.addEventListener('click', () => pwaModal.classList.add('hidden'));
  }

  // Mobile Bottom Navigation Bar Buttons
  const navBtnTrips = document.getElementById('nav-btn-trips');
  const navBtnMap = document.getElementById('nav-btn-map');
  const navBtnUpload = document.getElementById('nav-btn-upload');
  const navBtnPhotos = document.getElementById('nav-btn-photos');
  const navBtnBookings = document.getElementById('nav-btn-bookings');

  if (navBtnTrips) {
    navBtnTrips.addEventListener('click', () => {
      showCatalogView();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  if (navBtnMap) {
    navBtnMap.addEventListener('click', () => {
      const detailView = document.getElementById('detail-view');
      if (detailView && !detailView.classList.contains('hidden')) {
        const mapEl = document.getElementById('map');
        if (mapEl) {
          mapEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
          if (map) setTimeout(() => map.invalidateSize(), 200);
        }
      } else {
        const mapWrapper = document.getElementById('catalog-map-wrapper');
        const textToggleMap = document.getElementById('text-toggle-map');
        if (mapWrapper && mapWrapper.classList.contains('hidden')) {
          mapWrapper.classList.remove('hidden');
          if (textToggleMap) textToggleMap.textContent = 'Zwiń / Rozwiń mapę';
        }
        const catalogMapSection = document.getElementById('catalog-map-section');
        if (catalogMapSection) {
          catalogMapSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          if (catalogMap) setTimeout(() => catalogMap.invalidateSize(), 200);
        }
      }
    });
  }

  if (navBtnUpload) {
    navBtnUpload.addEventListener('click', () => {
      const fileInput = document.getElementById('file-input');
      if (fileInput) fileInput.click();
    });
  }

  if (navBtnPhotos) {
    navBtnPhotos.addEventListener('click', () => {
      const photoModal = document.getElementById('photo-upload-modal');
      if (photoModal) photoModal.classList.remove('hidden');
    });
  }

  if (navBtnBookings) {
    navBtnBookings.addEventListener('click', () => {
      const bookingModal = document.getElementById('booking-modal');
      if (bookingModal) bookingModal.classList.remove('hidden');
    });
  }

  // Setup Mobile Segmented Tabs (Plan / Map / Photos)
  setupMobileSegmentedTabs();

}

// Mobile Segmented Tabs Switching (Plan / Map / Photos)
function setupMobileSegmentedTabs() {
  const tabConfigs = [
    {
      selectors: ['#mobile-tab-itinerary', '#tab-btn-plan'],
      type: 'plan',
      action: () => {
        const target = document.getElementById('detail-itinerary-col') || document.getElementById('days-container');
        if (target) {
          target.classList.remove('hidden');
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    },
    {
      selectors: ['#mobile-tab-map', '#tab-btn-map'],
      type: 'map',
      action: () => {
        const target = document.getElementById('map-container') || document.getElementById('map');
        if (target) {
          target.classList.remove('hidden');
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        if (map) {
          setTimeout(() => {
            map.invalidateSize();
            const trip = detectedTrips[currentTripIndex];
            if (trip) {
              const pts = [];
              trip.days.forEach(d => {
                d.events.filter(e => e.type === 'place' && e.lat && e.lon).forEach(p => {
                  pts.push({ lat: p.lat, lon: p.lon });
                });
              });
              if (pts.length > 0) {
                smartCenterMap(pts, { padding: [40, 40], maxZoom: 15, isolateDestination: true });
              }
            }
          }, 150);
        }
      }
    },
    {
      selectors: ['#mobile-tab-photos', '#tab-btn-photos'],
      type: 'photos',
      action: () => {
        const target = document.getElementById('user-photos-section');
        if (target) {
          target.classList.remove('hidden');
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    }
  ];

  tabConfigs.forEach(tc => {
    tc.selectors.forEach(sel => {
      const btn = document.querySelector(sel);
      if (btn) {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          // Reset all mobile tab buttons
          document.querySelectorAll('.mobile-tab-btn, #tab-btn-plan, #tab-btn-map, #tab-btn-photos').forEach(b => {
            b.classList.remove('bg-teal-500', 'text-slate-950', 'shadow-md');
            b.classList.add('text-slate-300', 'hover:text-white', 'hover:bg-slate-800/60');
          });
          // Activate clicked button
          btn.classList.add('bg-teal-500', 'text-slate-950', 'shadow-md');
          btn.classList.remove('text-slate-300', 'hover:text-white', 'hover:bg-slate-800/60');

          tc.action();
        });
      }
    });
  });
}

// Global Android Back Button Handler (Invoked by Android native MainActivity.kt)
window.handleAndroidBack = function() {
  // 1. Close any visible modal first
  const modals = [
    document.getElementById('pwa-install-modal'),
    document.getElementById('photo-upload-modal'),
    document.getElementById('booking-modal'),
    document.getElementById('help-modal')
  ];

  for (const m of modals) {
    if (m && !m.classList.contains('hidden')) {
      m.classList.add('hidden');
      return true; // Handled
    }
  }

  // 2. If in Detail View, navigate back to Catalog View
  const detailView = document.getElementById('detail-view');
  if (detailView && !detailView.classList.contains('hidden')) {
    showCatalogView();
    return true; // Handled
  }

  // 3. At root Catalog with no open modals -> return false to let Android exit or minimize
  return false;
};

function saveTripTitleEdit() {
  const trip = detectedTrips[currentTripIndex];
  const inputEditTitle = document.getElementById('input-edit-title');
  const formEditTitle = document.getElementById('title-edit-form');
  if (!trip || !inputEditTitle) return;

  const newTitle = inputEditTitle.value.trim();
  if (newTitle) {
    trip.title = newTitle;
    document.getElementById('detail-title').textContent = newTitle;
    document.getElementById('breadcrumb-title').textContent = newTitle;
    formEditTitle.classList.add('hidden');
    generateMarkdownForTrip(trip);
  }
}

// File Upload Processing
async function handleFileSelect(e) {
  const files = e.target.files;
  if (!files || files.length === 0) return;

  allParsedEvents = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    if (file.name.endsWith('.zip')) {
      await processZipFile(file);
    } else if (file.name.endsWith('.json')) {
      await processJsonFile(file);
    }
  }

  if (allParsedEvents.length === 0) {
    const encModal = document.getElementById('encrypted-timeline-modal');
    if (encModal && !encModal.classList.contains('hidden')) {
      // Modal is already actively guiding the user for their Samsung phone
      return;
    }
    alert('Nie znaleziono zdarzeń osi czasu w wybranym pliku. Upewnij się, że plik zawiera Semantic Location History lub Timeline.json.');
    return;
  }

  clusterAndDisplayTrips();
}

async function processJsonFile(file) {
  const loadingIndicator = document.getElementById('upload-loading-indicator');
  const loadingText = document.getElementById('upload-loading-text');
  const progressBar = document.getElementById('upload-progress-bar');

  const updateProgress = (pct, msg) => {
    if (loadingIndicator) loadingIndicator.classList.remove('hidden');
    if (loadingText) loadingText.textContent = msg;
    if (progressBar) progressBar.style.width = `${pct}%`;
  };

  try {
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
    updateProgress(10, `Wczytywanie pliku ${file.name} (${sizeMb} MB)...`);
    await new Promise(r => setTimeout(r, 40));

    // For files > 2 MB, use Web Worker if supported (zero main-thread blocking)
    if (window.Worker && file.size > 2 * 1024 * 1024) {
      updateProgress(20, `Przesyłanie ${sizeMb} MB do silnika przetwarzania w tle...`);
      const text = await file.text();

      await new Promise((resolve, reject) => {
        const worker = new Worker('timeline-worker.js');
        worker.onmessage = (e) => {
          const res = e.data;
          if (res.type === 'progress') {
            updateProgress(res.percent, res.message);
          } else if (res.type === 'done') {
            detectedTrips = res.trips;
            allParsedEvents = [];
            res.trips.forEach(t => allParsedEvents.push(...t.events));
            attachPreloadedSampleData();
            updateGlobalStats();
            renderYearFilters();
            renderCatalogGrid();
            showCatalogView();
            setTimeout(() => {
              if (catalogMap) {
                catalogMap.invalidateSize();
                renderCatalogMap();
              }
            }, 250);
            updateProgress(100, `Ukończono! Wykryto ${res.trips.length} wypraw z ${res.totalEvents.toLocaleString('pl-PL')} zdarzeń.`);
            setTimeout(() => {
              if (loadingIndicator) loadingIndicator.classList.add('hidden');
            }, 1200);
            worker.terminate();
            resolve();
          } else if (res.type === 'error') {
            worker.terminate();
            reject(new Error(res.error));
          }
        };
        worker.onerror = (err) => {
          worker.terminate();
          reject(err);
        };
        worker.postMessage({ rawText: text });
      });
      return;
    }

    // Direct mode for small / demo files
    updateProgress(35, `Analizowanie danych osi czasu...`);
    const text = await file.text();
    const data = JSON.parse(text);
    ingestTimelineData(data);
    clusterAndDisplayTrips();
    updateProgress(100, `Gotowe!`);
    setTimeout(() => {
      if (loadingIndicator) loadingIndicator.classList.add('hidden');
    }, 800);
  } catch (err) {
    if (loadingIndicator) loadingIndicator.classList.add('hidden');
    console.error('Błąd parsowania JSON:', err);
    alert('Błąd odczytu pliku: ' + err.message);
  }
}

async function processZipFile(file) {
  try {
    const zip = await JSZip.loadAsync(file);
    let foundEncryptedBackup = false;
    let deviceName = 'Samsung Galaxy (Android)';

    // 1. Check for 2024/2025/2026 Google Takeout Encrypted Backup format
    for (const [filename, zipEntry] of Object.entries(zip.files)) {
      if (filename.includes('Encrypted Backups.txt') || filename.includes('Settings.json')) {
        foundEncryptedBackup = true;
        if (filename.includes('Settings.json')) {
          try {
            const content = await zipEntry.async('text');
            const settings = JSON.parse(content);
            if (settings.deviceSettings && settings.deviceSettings.length > 0) {
              const dev = settings.deviceSettings[0];
              const brand = dev.deviceSpec?.manufacturer || 'Samsung';
              const model = dev.devicePrettyName || dev.deviceSpec?.model || 'Galaxy';
              deviceName = `${brand} ${model}`.trim();
            }
          } catch (e) {}
        }
      }
    }

    // 2. Try parsing all valid JSON files inside the ZIP (not just strict names)
    for (const [filename, zipEntry] of Object.entries(zip.files)) {
      if (filename.endsWith('.json') && !filename.includes('Settings.json')) {
        try {
          const content = await zipEntry.async('text');
          const data = JSON.parse(content);
          ingestTimelineData(data);
        } catch (e) {
          console.warn('Nie udało się wczytać pliku z zip:', filename, e);
        }
      }
    }

    // If no events found and it was an encrypted Takeout backup, guide the user
    if (foundEncryptedBackup && allParsedEvents.length === 0) {
      showEncryptedTimelineModal(deviceName);
    }
  } catch (err) {
    console.error('Błąd otwierania ZIP:', err);
    alert('Błąd podczas odczytu pliku ZIP.');
  }
}

function showEncryptedTimelineModal(deviceName) {
  const modal = document.getElementById('encrypted-timeline-modal');
  const label = document.getElementById('detected-device-label');
  if (label && deviceName) label.textContent = `Wykryto urządzenie: ${deviceName}`;
  if (modal) modal.classList.remove('hidden');
}

// Helper for coordinate parsing (removes °, handles geo:, objects, strings)
function parseCoordsHelper(val) {
  if (!val) return null;
  if (typeof val === 'object') {
    if (val.latLng) return parseCoordsHelper(val.latLng);
    if (val.latitude && val.longitude) return [val.latitude, val.longitude];
    if (val.latitudeE7 && val.longitudeE7) return [val.latitudeE7 / 1e7, val.longitudeE7 / 1e7];
  }
  if (typeof val === 'string') {
    const cleaned = val.replace(/°/g, '').replace(/^geo:/, '').trim();
    const parts = cleaned.split(',').map(s => parseFloat(s.trim()));
    if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
      if (parts[0] >= -90 && parts[0] <= 90 && parts[1] >= -180 && parts[1] <= 180) {
        return parts;
      }
    }
  }
  return null;
}

// Ingest Timeline Data Objects
function ingestTimelineData(data) {
  let objects = [];
  if (Array.isArray(data)) {
    objects = data;
  } else if (data && typeof data === 'object') {
    // Android Timeline.json prioritizes semanticSegments (skips heavy rawSignals)
    if (Array.isArray(data.semanticSegments)) objects = data.semanticSegments;
    else if (Array.isArray(data.timelineObjects)) objects = data.timelineObjects;
    else if (Array.isArray(data.rawSignals)) objects = data.rawSignals;
  }

  objects.forEach(obj => {
    // Extract timelinePath points if present
    const path = [];
    if (obj.timelinePath && obj.timelinePath.length > 0) {
      obj.timelinePath.forEach(tp => {
        const pt = parseCoordsHelper(tp.point);
        if (pt) path.push(pt);
      });
    }

    // 1. Classic Google Takeout placeVisit
    if (obj.placeVisit) {
      const pv = obj.placeVisit;
      const loc = pv.location || {};
      const c = parseCoordsHelper(loc);
      const lat = c ? c[0] : 0;
      const lon = c ? c[1] : 0;
      const start = parseTimestamp(pv.duration?.startTimestamp);
      const end = parseTimestamp(pv.duration?.endTimestamp);
      const name = loc.name || loc.address || 'Nieznana lokalizacja';
      const address = loc.address || '';

      if (start) {
        allParsedEvents.push({
          type: 'place',
          start,
          end,
          name,
          address,
          lat,
          lon,
          category: classifyPlace(name, address),
          semanticType: loc.semanticType || '',
          path
        });
      }
    } 
    // 2. Classic Google Takeout activitySegment
    else if (obj.activitySegment) {
      const act = obj.activitySegment;
      const start = parseTimestamp(act.duration?.startTimestamp);
      const end = parseTimestamp(act.duration?.endTimestamp);
      const actType = act.activityType || 'UNKNOWN';
      const distance = act.distance || 0;

      const startC = parseCoordsHelper(act.startLocation);
      const startLat = startC ? startC[0] : 0;
      const startLon = startC ? startC[1] : 0;
      const endC = parseCoordsHelper(act.endLocation);
      const endLat = endC ? endC[0] : 0;
      const endLon = endC ? endC[1] : 0;

      if (start) {
        allParsedEvents.push({
          type: 'activity',
          start,
          end,
          activityType: actType,
          distanceMeters: distance,
          startLat,
          startLon,
          endLat,
          endLon,
          path
        });
      }
    }
    // 3. Android Timeline.json on-device export (visit)
    else if (obj.visit) {
      const v = obj.visit;
      const top = v.topCandidate || {};
      const loc = top.placeLocation || top.location || {};
      const c = parseCoordsHelper(loc);
      const lat = c ? c[0] : 0;
      const lon = c ? c[1] : 0;

      const start = parseTimestamp(obj.startTime || obj.duration?.startTimestamp);
      const end = parseTimestamp(obj.endTime || obj.duration?.endTimestamp);
      const name = top.placeLocation?.name || top.name || top.semanticType || 'Odwiedzone miejsce';
      const address = top.placeLocation?.address || '';

      if (start) {
        allParsedEvents.push({
          type: 'place',
          start,
          end,
          name,
          address,
          lat,
          lon,
          category: classifyPlace(name, address),
          semanticType: top.semanticType || '',
          path
        });
      }
    }
    // 4. Android Timeline.json on-device export (activity)
    else if (obj.activity) {
      const a = obj.activity;
      const top = a.topCandidate || {};
      const start = parseTimestamp(obj.startTime || obj.duration?.startTimestamp);
      const end = parseTimestamp(obj.endTime || obj.duration?.endTimestamp);
      const actType = top.type || 'UNKNOWN';
      const distance = a.distanceMeters || a.distance || 0;

      const startC = parseCoordsHelper(a.start);
      const startLat = startC ? startC[0] : 0;
      const startLon = startC ? startC[1] : 0;
      const endC = parseCoordsHelper(a.end);
      const endLat = endC ? endC[0] : 0;
      const endLon = endC ? endC[1] : 0;

      if (start) {
        allParsedEvents.push({
          type: 'activity',
          start,
          end,
          activityType: actType,
          distanceMeters: distance,
          startLat,
          startLon,
          endLat,
          endLon,
          path
        });
      }
    }
    // 5. Standalone timelinePath segment
    else if (path.length > 0) {
      const start = parseTimestamp(obj.startTime);
      const end = parseTimestamp(obj.endTime);
      if (start) {
        allParsedEvents.push({
          type: 'activity',
          start,
          end: end || start,
          activityType: 'IN_PASSENGER_VEHICLE',
          distanceMeters: 0,
          startLat: path[0][0],
          startLon: path[0][1],
          endLat: path[path.length - 1][0],
          endLon: path[path.length - 1][1],
          path
        });
      }
    }
  });

  // Check if sample data has attached bookings & photos
  if (data && data.sampleBookings) {
    window._preloadedSampleBookings = data.sampleBookings;
  }
  if (data && data.samplePhotos) {
    window._preloadedSamplePhotos = data.samplePhotos;
  }
}

function parseTimestamp(ts) {
  if (!ts) return null;
  if (typeof ts === 'number') return new Date(ts);
  const d = new Date(ts);
  return isNaN(d.getTime()) ? null : d;
}

function categorizePlace(name = '', semanticType = '', address = '') {
  const n = String(name || '');
  const s = String(semanticType || '');
  const a = String(address || '');
  const combined = `${n} ${s} ${a}`.toLowerCase();

  // 1. Peak / Mountain Summit check (Fixing "Nosal is a peak, not a hotel!")
  const peakRegex = /nosal|kasprowy|giewont|rysy|kościelec|świnica|szpiglas|czerwone wierch|pico|arieiro|ruivo|ślęż|szrenic|śnieżk|turnia|wierch|kopa|czub|szczyt|m n\.p\.m\./i;
  if (peakRegex.test(n) || peakRegex.test(combined)) {
    return {
      category: 'peak',
      icon: '⛰️',
      label: 'Zdobyty szczyt / Punkt widokowy',
      toString() { return this.category; }
    };
  }

  // 2. Food & Dining
  const foodKeywords = ['restaurant', 'restauracja', 'cafe', 'kawiarnia', 'bistro', 'bar', 'pizzeria', 'tasca', 'taberna', 'grill', 'marisqueira', 'pub', 'gelateria', 'lody', 'karczma', 'gospoda', 'trattoria', 'osteria', 'pizzarium', 'food', 'dining'];
  if (foodKeywords.some(k => combined.includes(k)) || s.toLowerCase().includes('food')) {
    return {
      category: 'food',
      icon: '🍽️',
      label: 'Restauracja / Posiłek',
      toString() { return this.category; }
    };
  }

  // 3. Lodging & Accommodation
  const lodgingKeywords = ['hotel', 'hostel', 'resort', 'apartament', 'apartment', 'pousada', 'guest house', 'villa', 'bnb', 'stay', 'schronisko', 'nocleg', 'lodging', 'pensjonat', 'dom wypoczynkowy', 'kwatera', 'agroturystyka', 'pokoje'];
  if (lodgingKeywords.some(k => combined.includes(k)) || s.toLowerCase().includes('lodging') || s.toLowerCase().includes('home')) {
    return {
      category: 'lodging',
      icon: '🏨',
      label: 'Baza noclegowa / Hotel',
      toString() { return this.category; }
    };
  }

  // Airport & Transfer
  const airportKeywords = ['airport', 'lotnisko', 'aeroporto', 'terminal'];
  if (airportKeywords.some(k => combined.includes(k)) || s.toLowerCase().includes('airport')) {
    return {
      category: 'airport',
      icon: '✈️',
      label: 'Lotnisko / Port lotniczy',
      toString() { return this.category; }
    };
  }

  // 4. Attractions & Trails
  const attractionKeywords = [
    'miradouro', 'punkt widokowy', 'viewpoint', 'szlak', 'levada', 'trail', 
    'praia', 'plaża', 'beach', 'muzeum', 'museum', 'ogród', 'garden', 'baseny', 
    'piscinas', 'castle', 'zamek', 'skywalk', 'koloseum', 'colosseo', 'forum', 'palatyn', 
    'panteon', 'pantheon', 'watykan', 'vatican', 'schody', 'krupówki', 'morskie oko', 'staw',
    'dolina', 'wodospad', 'waterfall', 'park', 'rezerwat', 'jaskinia', 'cave', 'skansen'
  ];
  if (attractionKeywords.some(k => combined.includes(k)) || s.toLowerCase().includes('attraction')) {
    return {
      category: 'attraction',
      icon: '🌲',
      label: 'Szlak / Atrakcja',
      toString() { return this.category; }
    };
  }

  return {
    category: 'other',
    icon: '📍',
    label: 'Inne miejsce',
    toString() { return this.category; }
  };
}

function classifyPlace(name, address) {
  return categorizePlace(name, '', address).category;
}

function getDestinationMeta(title) {
  const lower = (title || '').toLowerCase();
  
  // International destinations
  if (lower.includes('cabo verde') || lower.includes('zieloneg') || lower.includes('sal') || lower.includes('santa maria')) {
    return { icon: '🇨🇻', badge: 'Cabo Verde • Sal', country: 'Wyspy Zielonego Przylądka', gradient: 'from-amber-500 to-teal-700' };
  }
  if (lower.includes('mader') || lower.includes('funchal') || lower.includes('portugal')) {
    return { icon: '🇵🇹', badge: 'Madera • Portugalia', country: 'Portugalia', gradient: 'from-teal-600 to-emerald-700' };
  }
  if (lower.includes('marok') || lower.includes('agadir')) {
    return { icon: '🇲🇦', badge: 'Agadir & Maroko', country: 'Maroko', gradient: 'from-orange-600 to-red-700' };
  }
  if (lower.includes('cypr')) {
    return { icon: '🇨🇾', badge: 'Cypr (Morze Śródziemne)', country: 'Cypr', gradient: 'from-amber-600 to-yellow-700' };
  }
  if (lower.includes('turcj')) {
    return { icon: '🇹🇷', badge: 'Turcja (Riwiera)', country: 'Turcja', gradient: 'from-red-600 to-rose-700' };
  }
  if (lower.includes('bułgar') || lower.includes('burgas') || lower.includes('słoneczn')) {
    return { icon: '🇧🇬', badge: 'Bułgaria (Riwiera Morza Czarnego)', country: 'Bułgaria', gradient: 'from-emerald-600 to-teal-700' };
  }
  if (lower.includes('alban') || lower.includes('tiran') || lower.includes('durres')) {
    return { icon: '🇦🇱', badge: 'Albania (Riwiera Bałkańska)', country: 'Albania', gradient: 'from-red-700 to-slate-900' };
  }
  if (lower.includes('grecj') || lower.includes('korfu') || lower.includes('rodos') || lower.includes('kret')) {
    return { icon: '🇬🇷', badge: 'Grecja & Wyspy', country: 'Grecja', gradient: 'from-sky-600 to-blue-700' };
  }
  if (lower.includes('paryż') || lower.includes('francj')) {
    return { icon: '🇫🇷', badge: 'Francja & Paryż', country: 'Francja', gradient: 'from-blue-600 to-indigo-700' };
  }
  if (lower.includes('szwajcar') || lower.includes('alpy')) {
    return { icon: '🇨🇭', badge: 'Szwajcaria & Alpy', country: 'Szwajcaria', gradient: 'from-red-600 to-rose-800' };
  }
  if (lower.includes('niemc') || lower.includes('berlin') || lower.includes('drezno')) {
    return { icon: '🇩🇪', badge: 'Niemcy', country: 'Niemcy', gradient: 'from-amber-600 to-slate-800' };
  }
  if (lower.includes('holand') || lower.includes('amsterdam')) {
    return { icon: '🇳🇱', badge: 'Holandia & Amsterdam', country: 'Holandia', gradient: 'from-orange-500 to-amber-700' };
  }
  if (lower.includes('belgi') || lower.includes('namur') || lower.includes('waloni') || lower.includes('bruksel')) {
    return { icon: '🇧🇪', badge: 'Belgia (Namur & Walonia)', country: 'Belgia', gradient: 'from-yellow-600 to-red-800' };
  }
  if (lower.includes('czech') || lower.includes('prag')) {
    return { icon: '🇨🇿', badge: 'Czechy & Praga', country: 'Czechy', gradient: 'from-blue-600 to-red-700' };
  }
  if (lower.includes('chorwacj') || lower.includes('dalmacj') || lower.includes('split')) {
    return { icon: '🇭🇷', badge: 'Chorwacja (Adriatyk)', country: 'Chorwacja', gradient: 'from-sky-500 to-indigo-700' };
  }
  if (lower.includes('rzym') || lower.includes('watykan') || lower.includes('włoch')) {
    return { icon: '🇮🇹', badge: 'Włochy & Rzym', country: 'Włochy', gradient: 'from-emerald-600 to-red-600' };
  }
  if (lower.includes('chin') || lower.includes('pekin')) {
    return { icon: '🇨🇳', badge: 'Chiny (Azja)', country: 'Chiny', gradient: 'from-red-600 to-yellow-600' };
  }
  if (lower.includes('korea')) {
    return { icon: '🇰🇷', badge: 'Korea Południowa', country: 'Korea Południowa', gradient: 'from-blue-600 to-rose-600' };
  }

  // Poland regional destinations
  if (lower.includes('tatry') || lower.includes('zakopan') || lower.includes('kościelisk') || lower.includes('bukowin')) {
    return { icon: '🏔️', badge: 'Tatry & Zakopane (Polska)', country: 'Polska', gradient: 'from-blue-600 to-indigo-700' };
  }
  if (lower.includes('pienin') || lower.includes('szczawnic')) {
    return { icon: '⛰️', badge: 'Pieniny & Szczawnica (Polska)', country: 'Polska', gradient: 'from-teal-600 to-emerald-700' };
  }
  if (lower.includes('bieszczad') || lower.includes('solin')) {
    return { icon: '🌲', badge: 'Bieszczady & Solina (Polska)', country: 'Polska', gradient: 'from-emerald-700 to-green-900' };
  }
  if (lower.includes('karpacz') || lower.includes('karkonosz') || lower.includes('szklarsk')) {
    return { icon: '🏔️', badge: 'Karkonosze & Karpacz (Polska)', country: 'Polska', gradient: 'from-indigo-600 to-blue-800' };
  }
  if (lower.includes('mazur') || lower.includes('ostród') || lower.includes('mikołajk')) {
    return { icon: '⛵', badge: 'Mazury & Pojezierze (Polska)', country: 'Polska', gradient: 'from-cyan-600 to-blue-700' };
  }
  if (lower.includes('bałtyk') || lower.includes('gdańsk') || lower.includes('sopot') || lower.includes('mielno') || lower.includes('morze')) {
    return { icon: '🌊', badge: 'Bałtyk & Pomorze (Polska)', country: 'Polska', gradient: 'from-blue-500 to-cyan-700' };
  }
  if (lower.includes('poznań')) {
    return { icon: '🏛️', badge: 'Poznań & Wielkopolska (Polska)', country: 'Polska', gradient: 'from-amber-600 to-emerald-700' };
  }
  if (lower.includes('wrocław')) {
    return { icon: '🏰', badge: 'Wrocław & Dolny Śląsk (Polska)', country: 'Polska', gradient: 'from-rose-600 to-purple-700' };
  }
  if (lower.includes('sobótk') || lower.includes('ślęż')) {
    return { icon: '⛰️', badge: 'Sobótka (Masyw Ślęży)', country: 'Polska', gradient: 'from-stone-600 to-emerald-700' };
  }
  if (lower.includes('gniezno')) {
    return { icon: '🦅', badge: 'Gniezno (Pierwsza Stolica Polski)', country: 'Polska', gradient: 'from-red-600 to-slate-800' };
  }
  if (lower.includes('przemyśl') || lower.includes('krasiczyn')) {
    return { icon: '🏰', badge: 'Przemyśl & Zamek Krasiczyn', country: 'Polska', gradient: 'from-purple-600 to-indigo-800' };
  }
  if (lower.includes('kraków') || lower.includes('wieliczk')) {
    return { icon: '👑', badge: 'Kraków & Małopolska (Polska)', country: 'Polska', gradient: 'from-amber-500 to-red-700' };
  }
  if (lower.includes('warszaw')) {
    return { icon: '🏙️', badge: 'Warszawa (Mazowsze)', country: 'Polska', gradient: 'from-sky-600 to-indigo-800' };
  }
  if (lower.includes('jur') || lower.includes('ogrodzieniec') || lower.includes('olkusz') || lower.includes('bolesław')) {
    return { icon: '🏰', badge: 'Jura & Szlak Orlich Gniazd', country: 'Polska', gradient: 'from-amber-600 to-stone-700' };
  }

  // Clean fallback: Extract city name from title
  const cleanTitle = (title || 'Podróż').split('(')[0].trim();
  return { icon: '🧭', badge: `${cleanTitle} (Polska)`, country: 'Polska', gradient: 'from-slate-700 to-teal-900' };
}

// Trip Clustering Algorithm with Smart Away-From-Home & Vacation Detection
function clusterAndDisplayTrips() {
  allParsedEvents.sort((a, b) => a.start - b.start);
  detectedTrips = [];

  if (allParsedEvents.length === 0) {
    updateGlobalStats();
    renderYearFilters();
    renderCatalogGrid();
    showCatalogView();
    return;
  }

  // 1. Detect Home / Primary Base Centroid
  const locBuckets = {};
  allParsedEvents.forEach(ev => {
    if (ev.lat && ev.lon && (ev.lat !== 0 || ev.lon !== 0)) {
      const bKey = `${Math.round(ev.lat * 20) / 20},${Math.round(ev.lon * 20) / 20}`;
      const weight = (ev.semanticType === 'HOME' || (ev.name && ev.name.includes('Dom'))) ? 50 : 1;
      locBuckets[bKey] = (locBuckets[bKey] || 0) + weight;
    }
  });

  const sortedBuckets = Object.entries(locBuckets).sort((a, b) => b[1] - a[1]);
  let homeLat = 50.2839; // Olkusz default
  let homeLon = 19.5657;
  if (sortedBuckets.length > 0) {
    const coords = sortedBuckets[0][0].split(',').map(Number);
    homeLat = coords[0];
    homeLon = coords[1];
  }

  function getDistFromHome(lat, lon) {
    if (!lat || !lon) return 0;
    const R = 6371;
    const dLat = (lat - homeLat) * Math.PI / 180;
    const dLon = (lon - homeLon) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(homeLat * Math.PI / 180) * Math.cos(lat * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  // 2. Identify Vacation & Away-from-home events
  const travelEvents = [];
  allParsedEvents.forEach(ev => {
    const isFlight = (ev.activityType === 'FLYING');
    const isAirport = (ev.category === 'airport');
    const dist = getDistFromHome(ev.lat, ev.lon);
    const isMadera = (ev.lat >= 32.3 && ev.lat <= 33.3 && ev.lon >= -17.6 && ev.lon <= -16.3);
    const isForeign = isMadera || (dist > 90);

    if (isFlight || isAirport || isForeign) {
      travelEvents.push({
        ...ev,
        distFromHome: dist,
        isMadera
      });
    }
  });

  // 3. Cluster travel events into trips (gap <= 2.5 days)
  const rawClusters = [];
  let currentCluster = [];

  travelEvents.forEach(ev => {
    if (currentCluster.length === 0) {
      currentCluster.push(ev);
    } else {
      const prevEv = currentCluster[currentCluster.length - 1];
      const gapDays = (ev.start - prevEv.start) / (1000 * 60 * 60 * 24);
      if (gapDays <= 2.5) {
        currentCluster.push(ev);
      } else {
        if (currentCluster.length >= 3 || currentCluster.some(e => e.activityType === 'FLYING')) {
          rawClusters.push(currentCluster);
        }
        currentCluster = [ev];
      }
    }
  });

  if (currentCluster.length >= 3 || currentCluster.some(e => e.activityType === 'FLYING')) {
    rawClusters.push(currentCluster);
  }

  // 4. Build rich trip objects
  rawClusters.forEach(cluster => {
    const tripObj = buildTripFromCluster(cluster);
    if (tripObj) {
      detectedTrips.push(tripObj);
    }
  });

  // Sort newest first, with Madeira Dec 2025 at top
  detectedTrips.sort((a, b) => b.startDate - a.startDate);
  const decTripIdx = detectedTrips.findIndex(t => t.title.includes('ITAKA') || (t.title.includes('Mader') && t.startDate.getFullYear() === 2025 && t.startDate.getMonth() === 11));
  if (decTripIdx > 0) {
    const decTrip = detectedTrips.splice(decTripIdx, 1)[0];
    detectedTrips.unshift(decTrip);
  }

  // Attach preloaded sample bookings & photos if available
  attachPreloadedSampleData();

  updateGlobalStats();
  renderYearFilters();
  renderCatalogGrid();
  showCatalogView();

  setTimeout(() => {
    if (catalogMap) {
      catalogMap.invalidateSize();
      renderCatalogMap();
    }
  }, 250);
}

function buildTripFromCluster(clusterEvents) {
  clusterEvents.sort((a, b) => a.start - b.start);
  const startDate = clusterEvents[0].start;
  const endDate = clusterEvents[clusterEvents.length - 1].end || clusterEvents[clusterEvents.length - 1].start;
  const durationDays = Math.max(1, Math.round((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1);

  // Dominant location
  const validPlaces = clusterEvents.filter(e => e.type === 'place' && e.lat && e.lon);
  let avgLat = 0, avgLon = 0;
  if (validPlaces.length > 0) {
    avgLat = validPlaces.reduce((sum, p) => sum + p.lat, 0) / validPlaces.length;
    avgLon = validPlaces.reduce((sum, p) => sum + p.lon, 0) / validPlaces.length;
  } else {
    avgLat = clusterEvents[0].lat || 0;
    avgLon = clusterEvents[0].lon || 0;
  }

  let meta = { title: 'Wyprawa', icon: '🗺️', badge: 'Podróż', gradient: 'from-slate-700 to-slate-900' };
  if (avgLat >= 32.3 && avgLat <= 33.3 && avgLon >= -17.6 && avgLon <= -16.4) {
    meta = { title: 'Madera (Portugalia)', icon: '🌴', badge: 'Madera • Portugalia', gradient: 'from-teal-600 to-emerald-700' };
  } else if (avgLat >= 30.0 && avgLat <= 32.0 && avgLon >= -10.5 && avgLon <= -8.0) {
    meta = { title: 'Agadir i Maroko', icon: '🐪', badge: 'Maroko • Afryka', gradient: 'from-amber-600 to-orange-700' };
  } else if (avgLat >= 42.0 && avgLat <= 43.5 && avgLon >= 27.0 && avgLon <= 28.5) {
    meta = { title: 'Burgas i Wybrzeże Morza Czarnego', icon: '🏖️', badge: 'Bułgaria • Morze Czarne', gradient: 'from-blue-600 to-cyan-700' };
  } else if (avgLat >= 40.5 && avgLat <= 42.5 && avgLon >= 19.0 && avgLon <= 21.0) {
    meta = { title: 'Albania (Tirana i Wybrzeże)', icon: '🇦🇱', badge: 'Albania • Bałkany', gradient: 'from-red-600 to-rose-700' };
  } else if (avgLat >= 36.5 && avgLat <= 37.5 && avgLon >= 30.0 && avgLon <= 32.0) {
    meta = { title: 'Antalya i Riwiera Turecka', icon: '☀️', badge: 'Turcja • Riwiera', gradient: 'from-amber-500 to-yellow-600' };
  } else if (avgLat >= 39.3 && avgLat <= 40.0 && avgLon >= 19.6 && avgLon <= 20.2) {
    meta = { title: 'Korfu (Grecja)', icon: '🇬🇷', badge: 'Korfu • Grecja', gradient: 'from-sky-600 to-indigo-700' };
  } else if (avgLat >= 48.7 && avgLat <= 49.3 && avgLon >= 2.1 && avgLon <= 2.6) {
    meta = { title: 'Paryż i Francja', icon: '🗼', badge: 'Paryż • Francja', gradient: 'from-purple-600 to-pink-700' };
  } else if (avgLat >= 49.1 && avgLat <= 49.4 && avgLon >= 19.8 && avgLon <= 20.3) {
    meta = { title: 'Tatry i Zakopane', icon: '⛰️', badge: 'Tatry • Zakopane', gradient: 'from-emerald-600 to-teal-700' };
  } else if (avgLat >= 54.2 && avgLat <= 54.8 && avgLon >= 18.3 && avgLon <= 19.0) {
    meta = { title: 'Bałtyk i Trójmiasto', icon: '🌊', badge: 'Bałtyk • Pomorze', gradient: 'from-blue-500 to-slate-700' };
  }

  const monthName = startDate.toLocaleDateString('pl-PL', { month: 'long', year: 'numeric' });
  let title = `${meta.title} (${monthName.charAt(0).toUpperCase() + monthName.slice(1)})`;

  const dayGroups = new Map();
  clusterEvents.forEach(ev => {
    const dk = ev.start.toISOString().split('T')[0];
    if (!dayGroups.has(dk)) dayGroups.set(dk, []);
    dayGroups.get(dk).push(ev);
  });

  const sortedDayKeys = Array.from(dayGroups.keys()).sort();
  let totalWalkM = 0;
  let totalDriveM = 0;
  let flightCount = 0;
  let placesCount = 0;
  const highlights = [];
  const seenHighlights = new Set();

  clusterEvents.forEach(e => {
    if (e.type === 'place') {
      placesCount++;
      if (e.name && !e.name.includes('Dom') && !e.name.includes('Odwiedzone') && !seenHighlights.has(e.name)) {
        seenHighlights.add(e.name);
        highlights.push(e.name);
      }
    } else if (e.type === 'activity') {
      const type = e.activityType || '';
      if (type.includes('WALK') || type.includes('FOOT') || type.includes('HIKE')) {
        totalWalkM += e.distanceMeters || 0;
      } else if (type.includes('VEHICLE') || type.includes('CAR') || type.includes('BUS') || type.includes('TRAIN')) {
        totalDriveM += e.distanceMeters || 0;
      } else if (type.includes('FLYING')) {
        flightCount++;
      }
    }
  });

  const days = sortedDayKeys.map((dk, idx) => ({
    dayNumber: idx + 1,
    date: dk,
    events: dayGroups.get(dk),
    bookings: []
  }));

  const tripObj = {
    title,
    startDate,
    endDate,
    year: startDate.getFullYear(),
    events: clusterEvents,
    bookings: [],
    photos: [],
    stats: {
      days: days.length,
      placesCount,
      attractionCount: highlights.length,
      foodCount: clusterEvents.filter(e => e.category === 'food').length,
      flightCount,
      walkKm: totalWalkM / 1000,
      driveKm: totalDriveM / 1000,
    },
    highlights: highlights.slice(0, 6),
    days
  };

  return tripObj;
}

function attachPreloadedSampleData() {
  const madeiraTrip = detectedTrips.find(t => t.title.toLowerCase().includes('mader'));
  if (madeiraTrip) {
    // Attach sample bookings
    if (window._preloadedSampleBookings && Array.isArray(window._preloadedSampleBookings)) {
      window._preloadedSampleBookings.forEach(sb => {
        // Convert ISO string dates to Date objects
        const b = { ...sb };
        if (b.pickupDate) b.pickupDate = new Date(b.pickupDate);
        if (b.returnDate) b.returnDate = new Date(b.returnDate);
        if (b.checkInDate) b.checkInDate = new Date(b.checkInDate);
        if (b.checkOutDate) b.checkOutDate = new Date(b.checkOutDate);
        if (b.departureDate) b.departureDate = new Date(b.departureDate);
        if (b.arrivalDate) b.arrivalDate = new Date(b.arrivalDate);
        if (b.visitDate) b.visitDate = new Date(b.visitDate);

        window.bookingParser.enrichTrip(madeiraTrip, b);
      });
    }

    // Attach or sync photos
    if (madeiraTrip.photos && Array.isArray(madeiraTrip.photos) && madeiraTrip.photos.length > 0) {
      window.photoMatcher.photos = madeiraTrip.photos.map(p => ({
        ...p,
        timestamp: p.timestamp instanceof Date ? p.timestamp : new Date(p.timestamp)
      }));
    } else if (window.USER_PHOTOS_INDEX && Array.isArray(window.USER_PHOTOS_INDEX) && window.USER_PHOTOS_INDEX.length > 0) {
      madeiraTrip.photos = window.USER_PHOTOS_INDEX.map(p => ({
        ...p,
        timestamp: p.timestamp instanceof Date ? p.timestamp : new Date(p.timestamp)
      }));
      window.photoMatcher.photos = madeiraTrip.photos;
    } else if (window._preloadedSamplePhotos && Array.isArray(window._preloadedSamplePhotos)) {
      madeiraTrip.photos = [];
      window._preloadedSamplePhotos.forEach(sp => {
        const photo = {
          ...sp,
          timestamp: new Date(sp.timestamp)
        };
        window.photoMatcher.matchPhotoToTrip(photo, madeiraTrip);
        madeiraTrip.photos.push(photo);
        if (!window.photoMatcher.photos.some(existing => existing.id === photo.id)) {
          window.photoMatcher.photos.push(photo);
        }
      });
    }
  }
}

function createTripObject(dateKeys, dayMap) {
  const events = [];
  dateKeys.forEach(dk => {
    events.push(...dayMap.get(dk));
  });

  const placeNames = {};
  events.filter(e => e.type === 'place' && e.name).forEach(e => {
    let candidate = e.name;
    const text = `${e.name} ${e.address || ''}`.toLowerCase();
    if (text.includes('madeira') || text.includes('madera') || text.includes('funchal')) {
      placeNames['Madera'] = (placeNames['Madera'] || 0) + 10;
    } else if (text.includes('roma') || text.includes('rzym') || text.includes('watykan') || text.includes('colosseo')) {
      placeNames['Rzym i Watykan'] = (placeNames['Rzym i Watykan'] || 0) + 10;
    } else if (text.includes('tatry') || text.includes('zakopane') || text.includes('krupówki')) {
      placeNames['Tatry i Zakopane'] = (placeNames['Tatry i Zakopane'] || 0) + 10;
    } else {
      if (e.address) {
        const parts = e.address.split(',').map(s => s.trim()).filter(Boolean);
        if (parts.length >= 2) candidate = parts[parts.length - 2];
      }
      placeNames[candidate] = (placeNames[candidate] || 0) + 1;
    }
  });

  let topPlace = Object.entries(placeNames).sort((a, b) => b[1] - a[1])[0]?.[0] || 'Podróż';
  
  const startDate = new Date(dateKeys[0]);
  const endDate = new Date(dateKeys[dateKeys.length - 1]);
  const monthName = startDate.toLocaleDateString('pl-PL', { month: 'long', year: 'numeric' });
  const title = `${topPlace} - ${monthName.charAt(0).toUpperCase() + monthName.slice(1)}`;

  let totalWalkM = 0;
  let totalDriveM = 0;
  let flightCount = 0;
  let foodCount = 0;
  let placesCount = 0;
  let attractionCount = 0;

  events.forEach(e => {
    if (e.type === 'place') {
      placesCount++;
      if (e.category === 'food') foodCount++;
      if (e.category === 'attraction') attractionCount++;
    } else if (e.type === 'activity') {
      const type = e.activityType || '';
      if (type.includes('WALK') || type.includes('FOOT') || type.includes('HIKE')) {
        totalWalkM += e.distanceMeters || 0;
      } else if (type.includes('VEHICLE') || type.includes('CAR') || type.includes('BUS') || type.includes('TRAIN')) {
        totalDriveM += e.distanceMeters || 0;
      } else if (type.includes('FLYING')) {
        flightCount++;
      }
    }
  });

  const highlights = [];
  const seenHighlights = new Set();
  events.filter(e => e.type === 'place').forEach(p => {
    if (p.category === 'attraction' || (p.category === 'other' && !p.name.includes('Hotel') && !p.name.includes('Airport') && !p.name.includes('Lotnisko'))) {
      const clean = p.name.split('(')[0].trim();
      if (clean && !seenHighlights.has(clean)) {
        seenHighlights.add(clean);
        highlights.push(clean);
      }
    }
  });

  const routePoints = [];
  events.forEach(e => {
    if (e.path && e.path.length > 0) {
      routePoints.push(...e.path);
    }
  });

  return {
    title,
    dateKeys,
    startDate,
    endDate,
    year: startDate.getFullYear(),
    events,
    routePoints,
    bookings: [],
    photos: [],
    stats: {
      days: dateKeys.length,
      placesCount,
      attractionCount,
      foodCount,
      flightCount,
      walkKm: totalWalkM / 1000,
      driveKm: totalDriveM / 1000,
    },
    highlights: highlights.slice(0, 4),
    days: dateKeys.map(dk => ({
      date: dk,
      events: dayMap.get(dk),
      bookings: []
    }))
  };
}

// Master-Detail Navigation
function showCatalogView() {
  document.getElementById('catalog-view').classList.remove('hidden');
  document.getElementById('detail-view').classList.add('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });

  setTimeout(() => {
    if (catalogMap) {
      catalogMap.invalidateSize();
      renderCatalogMap();
    }
  }, 100);
}

window.showCatalogView = showCatalogView;

function showDetailView(tripIndex) {
  currentTripIndex = tripIndex;
  const trip = detectedTrips[currentTripIndex];
  if (!trip) return;

  currentGalleryDayFilter = 'all';
  const searchInput = document.getElementById('gallery-search-input');
  if (searchInput) searchInput.value = '';

  document.getElementById('catalog-view').classList.add('hidden');
  document.getElementById('detail-view').classList.remove('hidden');

  renderTripDetail(trip);
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Multi-pass invalidateSize & smart centering guarantees Leaflet renders all tiles cleanly
  if (map) {
    map.invalidateSize();
    setTimeout(() => {
      if (map) {
        map.invalidateSize();
        const trip = detectedTrips[currentTripIndex];
        if (trip) {
          const allMapPoints = [];
          (trip.days || []).forEach((d, idx) => {
            (d.places || []).forEach(p => {
              if (p.lat && p.lon) allMapPoints.push([p.lat, p.lon]);
            });
            (d.mountainTracks || []).forEach(tr => {
              if (tr.polyline && tr.polyline.length > 0) {
                const step = Math.max(1, Math.floor(tr.polyline.length / 20));
                for (let k = 0; k < tr.polyline.length; k += step) {
                  const pt = tr.polyline[k];
                  if (pt.lat && pt.lon) allMapPoints.push([pt.lat, pt.lon]);
                }
              }
            });
          });
          (trip.photos || []).forEach(p => {
            if (p.lat && p.lon) allMapPoints.push([p.lat, p.lon]);
          });
          if (allMapPoints.length > 0) {
            smartCenterMap(allMapPoints, { isolateDestination: true, padding: [45, 45], maxZoom: 14 });
          }
        }
      }
    }, 250);
    setTimeout(() => { if (map) map.invalidateSize(); }, 500);
  }
}

window.showDetailView = showDetailView;

// Global Stats & Catalog Rendering
function updateGlobalStats() {
  const totalTrips = detectedTrips.length;
  let totalDays = 0;
  let totalPlaces = 0;
  let totalWalkKm = 0;
  let totalPhotos = 0;

  detectedTrips.forEach(t => {
    totalDays += (t.stats && t.stats.days) ? t.stats.days : (t.days ? t.days.length : 1);
    totalPlaces += (t.stats && t.stats.placesCount) ? t.stats.placesCount : 0;
    totalWalkKm += (t.stats && t.stats.walkKm) ? t.stats.walkKm : 0;
    if (t.photos && Array.isArray(t.photos)) {
      totalPhotos += t.photos.length;
    }
  });

  const elTrips = document.getElementById('stat-total-trips');
  if (elTrips) elTrips.textContent = totalTrips;
  const elDays = document.getElementById('stat-total-days');
  if (elDays) elDays.textContent = totalDays;
  const elPlaces = document.getElementById('stat-total-places');
  if (elPlaces) elPlaces.textContent = totalPlaces;
  const elWalk = document.getElementById('stat-total-walk');
  if (elWalk) elWalk.textContent = totalWalkKm.toFixed(1) + ' km';
  const elPhotos = document.getElementById('stat-total-photos');
  if (elPhotos) elPhotos.textContent = totalPhotos.toLocaleString('pl-PL');

  const elHeaderBadge = document.getElementById('header-trips-count-badge');
  if (elHeaderBadge) {
    elHeaderBadge.textContent = `${totalTrips} Podróży • ${totalPhotos.toLocaleString('pl-PL')} Zdjęć`;
  }

  renderCatalogMap();
}

function renderYearFilters() {
  const container = document.getElementById('year-filter-container');
  if (!container) return;

  const years = Array.from(new Set(detectedTrips.map(t => t.year))).sort((a, b) => b - a);

  let html = `<button data-year="all" class="year-filter-btn px-3 py-1.5 text-xs font-semibold rounded-lg transition ${selectedYearFilter === 'all' ? 'bg-emerald-600 text-white shadow-2xs' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">Wszystkie</button>`;

  years.forEach(yr => {
    const isActive = selectedYearFilter === yr.toString();
    html += `<button data-year="${yr}" class="year-filter-btn px-3 py-1.5 text-xs font-semibold rounded-lg transition ${isActive ? 'bg-emerald-600 text-white shadow-2xs' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">${yr}</button>`;
  });

  container.innerHTML = html;

  container.querySelectorAll('.year-filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      selectedYearFilter = e.target.dataset.year;
      renderYearFilters();
      renderCatalogGrid();
    });
  });
}

function renderCatalogGrid() {
  const grid = document.getElementById('trips-grid');
  const emptyState = document.getElementById('empty-state');

  if (detectedTrips.length === 0) {
    grid.classList.add('hidden');
    emptyState.classList.remove('hidden');
    return;
  }

  emptyState.classList.add('hidden');
  grid.classList.remove('hidden');

  let filtered = detectedTrips.filter((trip) => {
    if (selectedYearFilter !== 'all' && trip.year.toString() !== selectedYearFilter) {
      return false;
    }
    if (searchQuery) {
      const matchTitle = trip.title.toLowerCase().includes(searchQuery);
      const matchHighlights = trip.highlights.some(h => h.toLowerCase().includes(searchQuery));
      const matchDates = `${trip.startDate.toLocaleDateString('pl-PL')} ${trip.endDate.toLocaleDateString('pl-PL')}`.toLowerCase().includes(searchQuery);
      if (!matchTitle && !matchHighlights && !matchDates) return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    if (currentSort === 'date-desc') return b.startDate - a.startDate;
    if (currentSort === 'date-asc') return a.startDate - b.startDate;
    if (currentSort === 'days-desc') return b.stats.days - a.stats.days;
    if (currentSort === 'walk-desc') return b.stats.walkKm - a.stats.walkKm;
    return 0;
  });

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full bg-white p-8 rounded-2xl text-center border border-slate-200 text-slate-500">
        Brak podróży spełniających kryteria wyszukiwania.
      </div>
    `;
    return;
  }

  grid.innerHTML = '';

  filtered.forEach(trip => {
    const originalIndex = detectedTrips.indexOf(trip);
    const meta = getDestinationMeta(trip.title);
    const startStr = trip.startDate.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const endStr = trip.endDate.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });

    const card = document.createElement('div');
    card.className = 'travel-card rounded-2xl border border-slate-800 hover:border-teal-500/50 shadow-sm hover:shadow-lg transition duration-200 flex flex-col justify-between overflow-hidden cursor-pointer relative bg-slate-900';

    const photoBadge = (trip.photos && trip.photos.length > 0)
      ? `<span class="bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-md font-bold text-xs flex items-center gap-1"><span>📷</span> <span>${trip.photos.length} zdjęć</span></span>`
      : '';

    let gpsCount = 0;
    (trip.days || []).forEach(d => {
      (d.mountainTracks || []).forEach(tr => {
        if (tr.polyline && tr.polyline.length > 0) gpsCount++;
      });
    });

    const gpsBadge = gpsCount > 0
      ? `<span class="bg-emerald-950/90 text-emerald-300 border border-emerald-500/50 px-2.5 py-0.5 rounded-md font-bold text-xs flex items-center gap-1 shadow-[0_0_10px_rgba(16,185,129,0.35)]"><span>🥾</span> <span>${gpsCount} ${gpsCount === 1 ? 'ślad GPS' : 'ślady GPS'}</span></span>`
      : '';

    const peakBadge = (trip.highestElevation && trip.highestElevation > 0)
      ? `<span class="bg-cyan-950/90 text-cyan-300 border border-cyan-500/50 px-2.5 py-0.5 rounded-md font-bold text-xs flex items-center gap-1 shadow-[0_0_10px_rgba(6,182,212,0.25)]"><span>⛰️</span> <span>${trip.peaksCount || 1} szczytów (max ${Math.round(trip.highestElevation)}m)</span></span>`
      : '';

    const bookingBadge = (trip.bookings && trip.bookings.length > 0)
      ? `<span class="bg-blue-500/20 text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded-md font-medium text-xs">📬 ${trip.bookings.length} vouchery ITAKA</span>`
      : '';

    const topBanner = `
      <div class="p-5 pb-4 border-b border-slate-800 flex items-start justify-between gap-3 bg-gradient-to-r ${meta.gradient || 'from-slate-850 to-slate-900'} bg-opacity-20 backdrop-blur-xs">
        <div class="flex items-start gap-3.5">
          <span class="text-3xl p-2.5 bg-slate-900/80 border border-slate-700/80 rounded-2xl shrink-0 shadow-inner">${meta.icon}</span>
          <div>
            <div class="flex items-center gap-2 flex-wrap mb-1">
              <span class="inline-block text-3xs uppercase tracking-wider font-bold text-teal-300 bg-teal-500/20 px-2 py-0.5 rounded-full border border-teal-500/30">
                ${meta.badge}
              </span>
              ${meta.country ? `<span class="text-3xs font-semibold text-slate-300 bg-slate-800/90 px-2 py-0.5 rounded-full border border-slate-700">🌍 ${meta.country}</span>` : ''}
            </div>
            <h3 class="font-bold text-slate-100 text-lg group-hover:text-teal-300 transition line-clamp-1">
              ${trip.title}
            </h3>
            <p class="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
              <span>📅 ${startStr} – ${endStr}</span>
              <span>&bull;</span>
              <span class="font-bold text-teal-400">${trip.stats.days} ${trip.stats.days === 1 ? 'dzień' : 'dni'}</span>
            </p>
          </div>
        </div>
      </div>
    `;

    // Miniature photo preview thumbnails for trips that have authentic photos
    let photoStripHtml = '';
    if (trip.photos && trip.photos.length > 0) {
      const previewPhotos = trip.photos.slice(0, 5);
      photoStripHtml = `
        <div class="px-5 py-2.5 bg-slate-950/70 border-b border-slate-800/80 flex items-center gap-2 overflow-hidden">
          <span class="text-3xs uppercase tracking-wider font-bold text-amber-400 shrink-0">Twoje zdjęcia:</span>
          <div class="flex items-center gap-1.5 overflow-hidden">
            ${previewPhotos.map(p => `
              <img src="${p.thumbnailUrl || p.url}" alt="${p.name}" class="w-10 h-10 object-cover rounded-lg border border-amber-500/30 hover:scale-110 transition shadow-xs" onerror="this.style.display='none'">
            `).join('')}
            ${trip.photos.length > 5 ? `<span class="text-3xs text-amber-300/80 font-bold bg-amber-950/40 border border-amber-500/30 px-1.5 py-2.5 rounded-lg">+${trip.photos.length - 5}</span>` : ''}
          </div>
        </div>
      `;
    }

    const statsPills = `
      <div class="px-5 py-3 flex flex-wrap gap-1.5 text-xs text-slate-300 bg-slate-900 border-b border-slate-800">
        ${trip.stats.flightCount > 0 ? `<span class="bg-sky-500/20 text-sky-300 border border-sky-500/30 px-2 py-0.5 rounded-md font-medium">✈️ Czarter ITAKA</span>` : ''}
        ${bookingBadge}
        ${gpsBadge}
        ${peakBadge}
        ${photoBadge}
        <span class="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-md font-medium">🥾 ${trip.stats.walkKm.toFixed(1)} km pieszo</span>
        <span class="bg-blue-500/20 text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded-md font-medium">🚗 ${trip.stats.driveKm.toFixed(0)} km autem</span>
        <span class="bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded-md font-medium">📍 ${trip.stats.placesCount} miejsc</span>
      </div>
    `;

    let highlightsHtml = '';
    if (trip.highlights.length > 0) {
      highlightsHtml = `
        <div class="px-5 py-3.5 flex-1 bg-slate-900/60">
          <div class="text-3xs font-bold uppercase tracking-wider text-slate-400 mb-2">Główne atrakcje trasy</div>
          <div class="flex flex-wrap gap-1.5">
            ${trip.highlights.map(h => `<span class="bg-slate-800 text-slate-200 text-xs px-2.5 py-1 rounded-lg border border-slate-700">${h}</span>`).join('')}
          </div>
        </div>
      `;
    } else {
      highlightsHtml = '<div class="flex-1 bg-slate-900"></div>';
    }

    const footer = `
      <div class="p-4 pt-3 border-t border-slate-800 bg-slate-850 flex items-center justify-between">
        <span class="text-xs text-slate-400">Plan dzień po dniu & mapa</span>
        <button class="px-3.5 py-1.5 text-xs font-bold bg-teal-600 hover:bg-teal-500 text-white rounded-xl transition flex items-center gap-1.5 shadow-sm">
          <span>Otwórz wyjazd</span>
          <span>&rarr;</span>
        </button>
      </div>
    `;

    card.innerHTML = topBanner + photoStripHtml + statsPills + highlightsHtml + footer;
    card.addEventListener('click', () => showDetailView(originalIndex));
    grid.appendChild(card);
  });
}

// Render Interactive Catalog Map (All Trips World Map)
function renderCatalogMap() {
  if (!catalogMap) return;

  catalogMapMarkers.forEach(m => catalogMap.removeLayer(m));
  catalogMapMarkers = [];
  catalogMapLines.forEach(l => catalogMap.removeLayer(l));
  catalogMapLines = [];

  const badgeEl = document.getElementById('catalog-map-badge');
  if (badgeEl) {
    badgeEl.textContent = `${detectedTrips.length} ${detectedTrips.length === 1 ? 'kierunek' : 'kierunki'}`;
  }

  if (detectedTrips.length === 0) return;

  const allPoints = [];
  const homePoint = [52.1657, 20.9671]; // Warsaw / Poland home base

  detectedTrips.forEach((trip, idx) => {
    const validPlaces = trip.events.filter(e => e.type === 'place' && e.lat && e.lon && (e.lat !== 0 || e.lon !== 0));
    if (validPlaces.length === 0) return;

    let avgLat = validPlaces.reduce((sum, p) => sum + p.lat, 0) / validPlaces.length;
    let avgLon = validPlaces.reduce((sum, p) => sum + p.lon, 0) / validPlaces.length;
    allPoints.push([avgLat, avgLon]);

    const meta = getDestinationMeta(trip.title);
    const startStr = trip.startDate.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const endStr = trip.endDate.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });

    // Flight route line from home base if foreign or flights detected
    const flights = trip.events.filter(e => e.activityType === 'FLYING');
    if (flights.length > 0 || avgLon < 14 || avgLat < 48) {
      allPoints.push(homePoint);
      const flightLine = L.polyline([homePoint, [avgLat, avgLon]], {
        color: '#00f0ff',
        weight: 2.5,
        opacity: 0.8,
        dashArray: '8, 8'
      }).addTo(catalogMap);
      catalogMapLines.push(flightLine);
    }

    const isDomestic = trip.title.toLowerCase().includes('tatry') || trip.title.toLowerCase().includes('zakopane') || trip.title.toLowerCase().includes('polska');
    const borderColor = isDomestic ? '#10b981' : '#00f0ff';
    const glowColor = isDomestic ? 'rgba(16,185,129,0.5)' : 'rgba(0,240,255,0.5)';

    const iconHtml = `
      <div style="position:relative; width:42px; height:42px; display:flex; align-items:center; justify-content:center; cursor:pointer;">
        <span style="position:absolute; width:100%; height:100%; border-radius:50%; background:${glowColor}; opacity:0.3; transform:scale(1.2); filter:blur(4px);"></span>
        <span style="width:34px; height:34px; border-radius:12px; background:#0c1322; border:2px solid ${borderColor}; box-shadow:0 0 14px ${glowColor}; display:flex; align-items:center; justify-content:center; font-size:16px;">
          ${meta.icon}
        </span>
      </div>
    `;

    const markerIcon = L.divIcon({
      className: 'catalog-map-marker',
      html: iconHtml,
      iconSize: [42, 42],
      iconAnchor: [21, 21],
      popupAnchor: [0, -22]
    });

    const marker = L.marker([avgLat, avgLon], { icon: markerIcon }).addTo(catalogMap);

    const popupHtml = `
      <div style="font-size:12px; font-family:sans-serif; min-width:210px; background:#0c1322; color:#f1f5f9; padding:12px; border-radius:12px; border:1px solid ${borderColor}; box-shadow:0 6px 25px rgba(0,0,0,0.7);">
        <span style="display:inline-block; font-size:10px; font-weight:800; text-transform:uppercase; background:rgba(0,240,255,0.15); color:${borderColor}; padding:2px 8px; border-radius:10px; margin-bottom:5px; border:1px solid ${borderColor};">
          ${meta.badge}
        </span><br>
        <b style="color:#ffffff; font-size:14px; line-height:1.2;">${trip.title}</b><br>
        <span style="color:#94a3b8; font-size:11px;">📅 ${startStr} – ${endStr} (${trip.stats.days} dni)</span><br>
        <div style="margin-top:8px; display:flex; gap:8px; font-size:11px; color:#cbd5e1; border-top:1px solid #1e293b; padding-top:6px;">
          <span>🥾 <b>${trip.stats.walkKm.toFixed(1)} km</b></span>
          <span>📍 <b>${trip.stats.placesCount}</b> miejsc</span>
          <span>📷 <b>${(trip.photos || []).length}</b> zdjęć</span>
        </div>
        <button onclick="showDetailView(${idx})" style="margin-top:10px; width:100%; padding:7px 10px; font-size:11px; font-weight:800; background:linear-gradient(to right, #00f0ff, #10b981); color:#070b14; border:none; border-radius:8px; cursor:pointer; box-shadow:0 0 10px rgba(0,240,255,0.4);">
          Zobacz szczegóły wyprawy →
        </button>
      </div>
    `;

    marker.bindPopup(popupHtml);
    catalogMapMarkers.push(marker);
  });

  if (allPoints.length > 1) {
    catalogMap.invalidateSize();
    catalogMap.fitBounds(L.latLngBounds(allPoints), { padding: [45, 45], maxZoom: 8 });
    setTimeout(() => { if (catalogMap) catalogMap.invalidateSize(); }, 200);
  } else if (allPoints.length === 1) {
    catalogMap.invalidateSize();
    catalogMap.setView(allPoints[0], 6);
  }
}

function renderItakaCards(details) {
  if (!details) return '';
  return `
    <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-700/80 space-y-1">
      <div class="text-slate-400 font-semibold flex items-center gap-1.5">
        <span>✈️</span> <span>Przelot czarterowy</span>
      </div>
      <div class="font-bold text-slate-100 text-sm">${details.flightRoute || 'Katowice (KTW) ↔ Funchal (FNC)'}</div>
      <div class="text-3xs text-slate-400">${details.flightNumberOut || 'Czarter Enter Air'} • Bagaż 20kg</div>
    </div>
    <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-700/80 space-y-1">
      <div class="text-slate-400 font-semibold flex items-center gap-1.5">
        <span>🏨</span> <span>Baza noclegowa & Hotel</span>
      </div>
      <div class="font-bold text-slate-100 text-sm">${details.hotel || '—'}</div>
      <div class="text-3xs text-teal-300">${details.board || 'Widok na ocean • Wyżywienie HB / All Inclusive'}</div>
    </div>
    <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-700/80 space-y-1">
      <div class="text-slate-400 font-semibold flex items-center gap-1.5">
        <span>🚌</span> <span>Transfer & Rezydent</span>
      </div>
      <div class="font-bold text-slate-100 text-sm">${details.tourOperator ? details.tourOperator + ' + Rezydent' : 'Autokar ITAKA + Rezydent'}</div>
      <div class="text-3xs text-sky-300">Transfer lotnisko ↔ hotel • Polskojęzyczna opieka na wyspie</div>
    </div>
    <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-700/80 space-y-1">
      <div class="text-slate-400 font-semibold flex items-center gap-1.5">
        <span>🚗</span> <span>Wynajem samochodu</span>
      </div>
      <div class="font-bold text-slate-100 text-sm">${details.carModel || 'Renault Clio / VW Polo'}</div>
      <div class="text-3xs text-amber-300">${details.carRental || 'Madeira Car Rental • Pełne ubezpieczenie (Zero Excess)'}</div>
    </div>
  `;
}

// Render Trip Detail View
function renderTripDetail(trip) {
  const meta = getDestinationMeta(trip.title);

  const bcTitle = document.getElementById('breadcrumb-title');
  if (bcTitle) bcTitle.textContent = trip.title;

  const dtTitle = document.getElementById('detail-title');
  if (dtTitle) dtTitle.textContent = trip.title;

  const dtIcon = document.getElementById('detail-icon');
  if (dtIcon) dtIcon.textContent = meta.icon;

  const dtBadge = document.getElementById('detail-destination-badge');
  if (dtBadge) dtBadge.textContent = meta.badge;

  const startStr = trip.startDate.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const endStr = trip.endDate.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const dtDates = document.getElementById('detail-dates');
  if (dtDates) dtDates.textContent = `${startStr} – ${endStr}`;

  const dtDuration = document.getElementById('detail-duration-badge');
  if (dtDuration) dtDuration.textContent = `${trip.stats.days} ${trip.stats.days === 1 ? 'dzień' : 'dni'}`;

  // Travel Storytelling Hero Cover photo update & integration
  const heroImg = document.getElementById('trip-hero-img');
  const heroCover = document.getElementById('trip-hero-cover');

  if (trip.photos && trip.photos.length > 0) {
    // Select best photo: either coverPhoto, or a scenic highlight/viewpoint photo, or the first photo
    const bestPhoto = trip.coverPhoto ||
      trip.photos.find(p => p.matchedPlace && !p.matchedPlace.toLowerCase().includes('hotel') && !p.matchedPlace.toLowerCase().includes('lotnisk')) ||
      trip.photos[0];

    const photoUrl = bestPhoto ? (bestPhoto.url || bestPhoto.path) : null;
    if (photoUrl) {
      if (heroImg) {
        heroImg.hidden = false;
        heroImg.src = photoUrl;
        heroImg.alt = trip.title;
        heroImg.classList.remove('opacity-40');
        heroImg.classList.add('opacity-55');
      }
      if (heroCover) {
        heroCover.dataset.hasPhotoCover = 'true';
      }
    }
  } else {
    // Bez zdjęcia okładki: sam gradient (bez obrazów z internetu — program działa offline)
    if (heroImg) {
      heroImg.removeAttribute('src');
      heroImg.hidden = true;
    }
  }

  // Quick stats
  const statWalk = document.getElementById('detail-stat-walk');
  if (statWalk) statWalk.textContent = `${trip.stats.walkKm.toFixed(1)} km`;

  const statDrive = document.getElementById('detail-stat-drive');
  if (statDrive) statDrive.textContent = `${trip.stats.driveKm.toFixed(0)} km`;

  const statPlaces = document.getElementById('detail-stat-places');
  if (statPlaces) statPlaces.textContent = `${trip.stats.placesCount}`;

  const photoCount = (trip.photos || []).length;
  const statPhotos = document.getElementById('detail-stat-photos');
  if (statPhotos) statPhotos.textContent = `${photoCount}`;

  // Badges in action bar
  const badgePhotoCount = document.getElementById('badge-photo-count');
  if (badgePhotoCount) badgePhotoCount.textContent = photoCount;

  const bookingCount = (trip.bookings || []).length;
  const badgeBookingCount = document.getElementById('badge-booking-count');
  if (badgeBookingCount) badgeBookingCount.textContent = bookingCount;

  // Handle ITAKA package isolation (Show strictly ONLY on ITAKA Madeira trips)
  const itakaBadge = document.getElementById('itaka-badge');
  const itakaSubtitle = document.getElementById('itaka-subtitle');
  const itakaCardContainer = document.getElementById('itaka-card-container');
  const dayProgTitle = document.getElementById('detail-day-program-title');
  const daysCountBadge = document.getElementById('detail-days-count-badge');
  const photoSourceBadge = document.getElementById('trip-photo-source-badge');
  const photoSourceDesc = document.getElementById('trip-photo-source-desc');

  const isItaka = !!trip.itakaDetails && (trip.title && (trip.title.toLowerCase().includes('itaka') || trip.title.toLowerCase().includes('madera')));

  if (isItaka && trip.itakaDetails) {
    if (itakaBadge) {
      itakaBadge.style.removeProperty('display');
      itakaBadge.style.display = 'inline-flex';
    }
    if (itakaSubtitle) {
      itakaSubtitle.style.removeProperty('display');
      itakaSubtitle.style.display = 'block';
      itakaSubtitle.innerHTML = `Organizator: <b>${trip.itakaDetails.tourOperator || 'Biuro Podróży ITAKA S.A.'}</b> • Umowa/Voucher: <code class="font-mono text-teal-300 font-bold bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700">${trip.itakaDetails.reservationNumber || '—'}</code>`;
    }
    if (itakaCardContainer) {
      itakaCardContainer.style.removeProperty('display');
      itakaCardContainer.style.display = 'grid';
      itakaCardContainer.innerHTML = renderItakaCards(trip.itakaDetails);
    }
  } else {
    if (itakaBadge) {
      itakaBadge.style.setProperty('display', 'none', 'important');
    }
    if (itakaSubtitle) {
      itakaSubtitle.style.setProperty('display', 'none', 'important');
      itakaSubtitle.innerHTML = '';
    }
    if (itakaCardContainer) {
      itakaCardContainer.style.setProperty('display', 'none', 'important');
      itakaCardContainer.innerHTML = '';
    }
  }

  // Update Program Dzień po Dniu title & badge
  if (dayProgTitle) {
    dayProgTitle.textContent = `Program Dzień po Dniu (${trip.title})`;
  }
  if (daysCountBadge) {
    daysCountBadge.textContent = `${trip.days.length} ${trip.days.length === 1 ? 'zaplanowany dzień' : 'zaplanowanych dni'}`;
  }

  // Zdjęcia pochodzą z biblioteki Katalogatora (foldery ustawione w Przeglądarce)
  if (photoSourceBadge && photoSourceDesc) {
    photoSourceBadge.classList.add('hidden');
    photoSourceDesc.textContent = `Zdjęcia dopasowane automatycznie do dni i miejsc na trasie na podstawie daty i koordynatów GPS.`;
  }

  // Header enriched badges
  const enrichedBadgesContainer = document.getElementById('detail-enriched-badges');
  if (enrichedBadgesContainer) {
    enrichedBadgesContainer.innerHTML = '';
    if (trip.highestElevation && trip.highestElevation > 0) {
      const peakBadge = document.createElement('span');
      peakBadge.className = 'text-2xs font-bold px-2.5 py-1 rounded-lg border flex items-center gap-1.5 shadow-2xs bg-cyan-950/80 text-cyan-300 border-cyan-500/40 backdrop-blur-md';
      peakBadge.innerHTML = `<span>⛰️</span> <span>Szczyty: <b>${trip.peaksCount || 1}</b> • Max: <b>${Math.round(trip.highestElevation)} m n.p.m.</b></span>`;
      enrichedBadgesContainer.appendChild(peakBadge);
    }
    if (trip.bookings && trip.bookings.length > 0) {
      trip.bookings.forEach(b => {
        const badge = document.createElement('span');
        badge.className = 'text-2xs font-semibold px-2.5 py-1 rounded-lg border flex items-center gap-1 shadow-2xs bg-white text-slate-800 border-slate-200';
        badge.innerHTML = `<span>${b.icon || '📌'}</span> <span>${b.title}</span>`;
        enrichedBadgesContainer.appendChild(badge);
      });
    }
  }

  // Render Bookings Section
  renderBookingsSection(trip);

  // Render Photo Gallery Strip
  renderPhotoGalleryStrip(trip);

  // Flight Banner
  const flightBanner = document.getElementById('flights-banner');
  if (flightBanner) {
    const flights = trip.events.filter(e => e.activityType === 'FLYING');
    if (flights.length > 0) {
      flightBanner.classList.remove('hidden');
      let flightText = `
        <div class="flex items-center gap-2 font-bold mb-1">
          <span>✈️</span> Przeloty & Transfery lotnicze:
        </div>
        <ul class="list-disc list-inside space-y-1">
      `;
      flights.forEach(f => {
        const durMin = f.end ? Math.round((f.end - f.start) / 60000) : 0;
        const distKm = Math.round((f.distanceMeters || 0) / 1000);
        flightText += `<li><b>Lot</b>: ${f.start.toLocaleDateString('pl-PL')} o ${f.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})} (czas trwania: ok. ${Math.floor(durMin/60)}h ${durMin%60}m, dystans: ~${distKm} km)</li>`;
      });
      flightText += `</ul>`;
      flightBanner.innerHTML = flightText;
    } else {
      flightBanner.classList.add('hidden');
    }
  }

  // Days list rendering
  const daysContainer = document.getElementById('days-container');
  daysContainer.innerHTML = '';

  const allMapPoints = [];

  trip.days.forEach((day, index) => {
    const dayNumber = index + 1;
    const dateObj = new Date(day.date);
    const dateStr = dateObj.toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    const places = day.events.filter(e => e.type === 'place');
    const activities = day.events.filter(e => e.type === 'activity');
    const dayPhotos = (trip.photos || []).filter(p => p.dayNumber === dayNumber);
    const dayBookings = (trip.bookings || []).filter(b => {
      const bDate = b.pickupDate || b.checkInDate || b.departureDate || b.visitDate;
      return bDate && bDate.toISOString().split('T')[0] === day.date;
    });

    const card = document.createElement('div');
    card.className = 'day-itinerary-card rounded-2xl border border-slate-800 bg-slate-900 p-5 sm:p-6 shadow-sm space-y-4 hover:border-slate-700 transition duration-200 break-inside-avoid';
    card.dataset.day = dayNumber;

    const cardHeader = `
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div class="flex items-center gap-3">
          <span class="w-9 h-9 rounded-xl bg-teal-500/10 border border-teal-500/20 text-teal-400 font-bold flex items-center justify-center text-sm">
            D${dayNumber}
          </span>
          <div>
            <h4 class="font-bold text-slate-100 text-base capitalize">${dateStr}</h4>
            <p class="text-xs text-slate-400">${places.length} punktów &bull; ${activities.length} tras &bull; ${dayPhotos.length} zdjęć</p>
          </div>
        </div>
        <button class="btn-focus-day px-2.5 py-1 text-xs font-bold text-teal-300 bg-slate-800 hover:bg-slate-700 rounded-xl border border-slate-700 transition shadow-xs" data-day="${dayNumber}">
          Pokaż na mapie 🗺️
        </button>
      </div>
    `;

    // Booking notification banner inside day card
    let bookingBannerHtml = '';
    if (dayBookings.length > 0) {
      bookingBannerHtml = `
        <div class="p-2.5 bg-blue-950/40 border border-blue-500/30 rounded-xl space-y-1">
          ${dayBookings.map(b => `
            <div class="flex items-center justify-between text-xs text-blue-300">
              <span class="font-bold flex items-center gap-1.5"><span>${b.icon}</span> <span>${b.title}</span></span>
              <span class="text-3xs bg-slate-950 text-blue-200 px-2 py-0.5 rounded font-mono font-bold border border-blue-500/30">Nr: ${b.bookingNumber}</span>
            </div>
          `).join('')}
        </div>
      `;
    }

    // Re-categorize all places with updated semantic intelligence (catching mountain summits like Nosal)
    places.forEach(p => {
      const catInfo = categorizePlace(p.name, p.semanticType || p.category, p.address || '');
      p.category = catInfo.category;
      p.categoryIcon = catInfo.icon;
      p.categoryLabel = catInfo.label;
    });

    // Start location determination
    let startLocation = places[0] ? places[0].name : 'Początek trasy';
    const firstPlace = places[0];
    const isStartPeak = firstPlace && firstPlace.category === 'peak';
    const startChip = isStartPeak
      ? `<span class="chip-place chip-viewpoint text-3xs py-0.5 px-2 font-bold shrink-0">⛰️ Start: Szczyt</span>`
      : (firstPlace && firstPlace.category === 'lodging'
        ? `<span class="chip-place chip-lodging text-3xs py-0.5 px-2 font-bold shrink-0">🏨 Nocleg / Start</span>`
        : `<span class="chip-place text-3xs py-0.5 px-2 shrink-0 bg-slate-800 text-slate-300 border border-slate-700 rounded-lg">📍 Start trasy</span>`);

    // End location determination:
    // NEVER pick a peak as the overnight location!
    // If the last place is a peak or trail, find the last place of category 'lodging' or 'home', or fallback to the day's hotel/start location.
    let endLocation = startLocation;
    if (places.length > 1) {
      const lastPlace = places[places.length - 1];
      const isPeakOrTrail = lastPlace.category === 'peak' || 
                            lastPlace.category === 'attraction' ||
                            /nosal|kasprowy|giewont|rysy|kościelec|świnica|szpiglas|czerwone wierch|pico|arieiro|ruivo|ślęż|szrenic|śnieżk|turnia|wierch|kopa|czub|szczyt|szlak|trail|levada/i.test(lastPlace.name);

      if (isPeakOrTrail) {
        // Look backwards for a lodging or home place
        const lodgingPlaces = places.filter(p => 
          p.category === 'lodging' || 
          (p.semanticType && (p.semanticType.toLowerCase().includes('lodging') || p.semanticType.toLowerCase().includes('home'))) ||
          /hotel|hostel|resort|apartament|apartment|pousada|guest house|villa|bnb|schronisko|nocleg|pensjonat|kwatera/i.test(p.name)
        );
        if (lodgingPlaces.length > 0) {
          endLocation = lodgingPlaces[lodgingPlaces.length - 1].name;
        } else {
          // Fallback to the day's hotel/start location
          endLocation = (!isStartPeak && startLocation) ? startLocation : (trip.destination || 'Baza noclegowa / Hotel');
        }
      } else {
        endLocation = lastPlace.name;
      }
    }

    const peaks = places.filter(p => p.category === 'peak');
    const attractions = places.filter(p => (p.category === 'attraction' || (p.category === 'other' && p !== places[0])) && p.category !== 'peak');
    const food = places.filter(p => p.category === 'food');

    let dayWalkKm = 0;
    const moves = [];
    activities.forEach(a => {
      const distKm = (a.distanceMeters || 0) / 1000;
      const durMin = a.end ? Math.round((a.end - a.start) / 60000) : 0;
      const t = a.activityType || '';

      if (t.includes('WALK') || t.includes('HIKE') || t.includes('FOOT')) {
        dayWalkKm += distKm;
        if (distKm >= 0.8) moves.push({ icon: '🥾', text: `Pieszo (${distKm.toFixed(1)} km, ${durMin} min)` });
      } else if (t.includes('VEHICLE') || t.includes('CAR')) {
        if (distKm >= 1.5) moves.push({ icon: '🚗', text: `Przejazd (${distKm.toFixed(1)} km, ${durMin} min)` });
      } else if (t.includes('TRAIN') || t.includes('SUBWAY')) {
        moves.push({ icon: '🚆', text: `Pociąg / Metro (${distKm.toFixed(1)} km, ${durMin} min)` });
      } else if (t.includes('FLYING')) {
        moves.push({ icon: '✈️', text: `Lot (${distKm.toFixed(0)} km, ${durMin} min)` });
      }
    });

    let cardBody = `
      <div class="space-y-3 text-sm text-slate-300">
        ${bookingBannerHtml}

        <!-- Start of day -->
        <div class="flex items-start gap-2.5">
          ${startChip}
          <div class="pt-0.5">
            <span class="font-medium text-slate-200">${startLocation}</span> 
            <span class="text-xs text-slate-400">(${places[0]?.start ? places[0].start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'}) : ''})</span>
          </div>
        </div>
    `;

    if (moves.length > 0) {
      cardBody += `
        <div class="flex items-start gap-2.5">
          <span class="text-base shrink-0">🛣️</span>
          <div>
            <b>Dojazdy i trasy:</b>
            <div class="flex flex-wrap gap-1.5 mt-1">
              ${moves.map(m => `<span class="bg-[#0f172a] text-cyan-300 text-xs px-2.5 py-0.5 rounded-lg border border-cyan-500/30 shadow-xs">${m.icon} ${m.text}</span>`).join('')}
            </div>
          </div>
        </div>
      `;
    }

    if (dayWalkKm > 0.4) {
      cardBody += `
        <div class="flex items-start gap-2.5">
          <span class="text-base shrink-0">🚶</span>
          <div><b>Pieszo łącznie:</b> <span class="font-bold text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]">${dayWalkKm.toFixed(1)} km</span></div>
        </div>
      `;
    }

    // Mountain Tracks from Intervals.icu / Strava
    if (day.mountainTracks && day.mountainTracks.length > 0) {
      cardBody += `
        <div class="space-y-2 pt-1">
          ${day.mountainTracks.map((tr, trIdx) => {
            const hasPoly = tr.polyline && tr.polyline.length > 0;
            return `
            <div class="mountain-track-card p-3 bg-gradient-to-r from-emerald-950/60 via-slate-900/80 to-cyan-950/50 border border-emerald-500/30 hover:border-cyan-400/60 rounded-xl space-y-2 shadow-[0_0_15px_rgba(16,185,129,0.1)] transition group ${hasPoly ? 'cursor-pointer hover:shadow-[0_0_20px_rgba(6,182,212,0.2)]' : ''}" data-day="${dayNumber}" data-track-index="${trIdx}">
              <div class="flex items-center justify-between text-xs text-emerald-300 flex-wrap gap-2">
                <span class="font-bold flex items-center gap-1.5 text-emerald-200 group-hover:text-cyan-300 transition">
                  <span>🥾</span> <span>${tr.name || 'Wędrówka górska / Trening'}</span>
                </span>
                <div class="flex items-center gap-1.5">
                  ${hasPoly ? `<span class="text-3xs bg-cyan-950/80 text-cyan-300 px-2 py-0.5 rounded-full font-mono font-bold border border-cyan-500/40">⛰️ Ślad GPS</span>` : ''}
                  <span class="text-3xs bg-emerald-900/60 text-emerald-300 px-2 py-0.5 rounded-full font-mono font-bold border border-emerald-500/30">
                    Strava / Intervals
                  </span>
                </div>
              </div>
              <div class="flex flex-wrap items-center justify-between gap-2 text-2xs text-slate-300 font-mono">
                <div class="flex flex-wrap items-center gap-3">
                  <span>📏 Dystans: <b class="text-emerald-400 font-bold">${tr.distanceKm} km</b></span>
                  <span>↗️ Przewyższenie: <b class="text-cyan-400 font-bold">${tr.elevationGainM} m</b></span>
                  ${tr.durationMin ? `<span>⏱️ Czas: <b class="text-slate-100 font-bold">${Math.floor(tr.durationMin / 60)}h ${tr.durationMin % 60}min</b></span>` : ''}
                </div>
                ${hasPoly ? `
                  <button type="button" class="btn-focus-gps-track inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/25 text-cyan-300 hover:text-cyan-100 border border-cyan-500/30 text-3xs font-bold transition shadow-xs" data-day="${dayNumber}" data-track-index="${trIdx}">
                    <span>🗺️</span> <span>Pokaż ślad GPS</span>
                  </button>
                ` : ''}
              </div>
            </div>
            `;
          }).join('')}
        </div>
      `;
    }

    // Peaks & Summits (Zdobyte szczyty i punkty widokowe - autentyczne z bazy i osi czasu)
    const verifiedPeaks = day.peaks || [];
    const hasAnyPeaks = peaks.length > 0 || verifiedPeaks.length > 0;

    if (hasAnyPeaks) {
      const peakCount = Math.max(peaks.length, verifiedPeaks.length);
      cardBody += `
        <div class="flex items-start gap-2.5">
          <span class="text-base shrink-0">⛰️</span>
          <div class="w-full">
            <div class="font-bold text-cyan-300 flex items-center gap-1.5">
              <span>Zdobyte szczyty i punkty widokowe (${peakCount}):</span>
            </div>
            <ul class="space-y-1.5 mt-1 text-xs">
              ${(verifiedPeaks.length > 0 ? verifiedPeaks : peaks).map(pk => {
                const pkName = pk.name || '';
                const baseName = pkName.split('(')[0].trim();
                const matchedPhotos = dayPhotos.filter(p => p.matchedPlace && p.matchedPlace.toLowerCase().includes(baseName.toLowerCase()));
                const photoSnippet = matchedPhotos.length > 0
                  ? `<div class="flex gap-1.5 mt-1">
                      ${matchedPhotos.map(mp => `
                        <img src="${mp.url}" alt="${mp.name}" title="${mp.name} (kliknij aby powiększyć)" class="w-10 h-10 object-cover rounded-md ring-1 ring-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.4)] cursor-pointer hover:scale-105 transition" onclick="window.photoMatcher.openLightbox('${mp.id}')" />
                      `).join('')}
                     </div>`
                  : '';

                const eleBadge = pk.ele ? `<span class="px-2 py-0.5 rounded-md bg-cyan-500/20 text-cyan-300 font-bold font-mono text-xs border border-cyan-500/30">${Math.round(pk.ele)} m n.p.m.</span>` : '';
                const gpsAlt = pk.gpsAltM ? `<span class="text-3xs text-slate-400 font-mono">GPS: ${Math.round(pk.gpsAltM)}m</span>` : '';
                const timeSnippet = pk.timeLabel ? `<span class="text-cyan-400 font-mono text-3xs">Godz. ${pk.timeLabel}</span>` : (pk.start ? `<span class="text-cyan-400 font-mono text-3xs">${pk.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})}</span>` : '');

                return `
                  <li class="p-2.5 rounded-xl bg-cyan-950/40 border border-cyan-500/40 space-y-1 hover:border-cyan-400 transition shadow-[0_0_12px_rgba(6,182,212,0.1)]">
                    <div class="flex items-center justify-between flex-wrap gap-2">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="chip-place chip-viewpoint text-3xs py-0.5 px-2 font-bold shrink-0">⛰️ Szczyt</span>
                        <span class="font-bold text-cyan-100">${pkName}</span>
                        ${eleBadge}
                      </div>
                      <div class="flex items-center gap-2 shrink-0 ml-auto">
                        ${gpsAlt}
                        ${timeSnippet}
                      </div>
                    </div>
                    ${photoSnippet}
                  </li>
                `;
              }).join('')}
            </ul>
          </div>
        </div>
      `;
    }

    // Attractions with matched photos attached
    if (attractions.length > 0) {
      cardBody += `
        <div class="flex items-start gap-2.5">
          <span class="text-base shrink-0">📍</span>
          <div class="w-full">
            <b>Zwiedzanie i punkty:</b>
            <ul class="space-y-1.5 mt-1 text-xs text-slate-300">
              ${attractions.map(a => {
                const lowerName = a.name.toLowerCase();
                const isViewpoint = lowerName.includes('pico') || lowerName.includes('miradouro') || lowerName.includes('widok') || lowerName.includes('szczyt') || lowerName.includes('skał') || lowerName.includes('ponta') || lowerName.includes('cabo');
                const chipHtml = isViewpoint
                  ? `<span class="chip-place chip-viewpoint text-3xs py-0.5 px-2 shrink-0">⛰️ Widok</span>`
                  : `<span class="chip-place chip-attraction text-3xs py-0.5 px-2 shrink-0">🌲 Atrakcja</span>`;

                const matchedPhotos = dayPhotos.filter(p => p.matchedPlace && p.matchedPlace.includes(a.name.split('(')[0].trim()));
                const photoSnippet = matchedPhotos.length > 0
                  ? `<div class="flex gap-1.5 mt-1">
                      ${matchedPhotos.map(mp => `
                        <img src="${mp.url}" alt="${mp.name}" title="${mp.name} (kliknij aby powiększyć)" class="w-10 h-10 object-cover rounded-md ring-1 ring-cyan-500 shadow-[0_0_8px_rgba(0,240,255,0.3)] cursor-pointer hover:scale-105 transition" onclick="window.photoMatcher.openLightbox('${mp.id}')" />
                      `).join('')}
                     </div>`
                  : '';

                return `
                  <li class="p-2.5 rounded-xl bg-[#0f172a]/90 border border-slate-800 space-y-1 hover:border-slate-700 transition">
                    <div class="flex items-center justify-between flex-wrap gap-2">
                      <div class="flex items-center gap-2 flex-wrap">
                        ${chipHtml}
                        <span class="font-semibold text-slate-100">${a.name}</span>
                      </div>
                      <span class="text-slate-400 shrink-0 ml-auto font-mono text-3xs">${a.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})}${a.end ? ' - ' + a.end.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'}) : ''}</span>
                    </div>
                    ${photoSnippet}
                  </li>
                `;
              }).join('')}
            </ul>
          </div>
        </div>
      `;
    }

    // Food
    if (food.length > 0) {
      cardBody += `
        <div class="flex items-start gap-2.5">
          <span class="chip-place chip-food text-3xs py-0.5 px-2 shrink-0">🍽️ Jedzenie</span>
          <div class="w-full">
            <b>Restauracje / Gastronomia:</b>
            <ul class="space-y-1 mt-1 text-xs text-rose-300">
              ${food.map(f => {
                const matchedPhotos = dayPhotos.filter(p => p.matchedPlace && p.matchedPlace.includes(f.name.split('(')[0].trim()));
                const photoSnippet = matchedPhotos.length > 0
                  ? `<div class="flex gap-1.5 mt-1">
                      ${matchedPhotos.map(mp => `
                        <img src="${mp.url}" alt="${mp.name}" class="w-10 h-10 object-cover rounded-md ring-1 ring-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.3)] cursor-pointer hover:scale-105 transition" onclick="window.photoMatcher.openLightbox('${mp.id}')" />
                      `).join('')}
                     </div>`
                  : '';

                return `
                  <li class="p-2.5 rounded-xl bg-[#0f172a]/90 border border-rose-500/30 hover:border-rose-500/50 transition">
                    <div class="flex items-center justify-between flex-wrap gap-2">
                      <div class="flex items-center gap-2">
                        <span class="chip-place chip-food text-3xs py-0.5 px-1.5">🍽️</span>
                        <span class="font-semibold text-rose-200">${f.name}</span>
                      </div>
                      <span class="text-rose-400 shrink-0 ml-auto font-mono text-3xs">${f.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})}</span>
                    </div>
                    ${photoSnippet}
                  </li>
                `;
              }).join('')}
            </ul>
          </div>
        </div>
      `;
    }

    // Day Photos Gallery Preview
    if (dayPhotos.length > 0) {
      cardBody += `
        <div class="p-2.5 bg-amber-950/40 border border-amber-500/30 rounded-xl space-y-1.5">
          <div class="text-3xs font-bold uppercase tracking-wider text-amber-300 flex items-center justify-between">
            <span>📷 Zdjęcia z tego dnia (${dayPhotos.length}):</span>
            <span class="text-3xs text-amber-400/70 font-normal">Kliknij zdjęcie aby powiększyć</span>
          </div>
          <div class="flex gap-2 overflow-x-auto pb-1 custom-scroll">
            ${dayPhotos.map(p => `
              <div class="shrink-0 relative group cursor-pointer" onclick="window.photoMatcher.openLightbox('${p.id}')">
                <img src="${p.url}" alt="${p.name}" class="w-16 h-16 object-cover rounded-lg shadow-xs group-hover:ring-2 ring-amber-400 transition" />
                <span class="absolute bottom-0 inset-x-0 bg-black/75 text-white text-3xs truncate px-1 py-0.5 rounded-b-lg">
                  ${p.matchedPlace ? p.matchedPlace.split('(')[0] : p.name}
                </span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    // End of day
    cardBody += `
        <div class="flex items-start gap-2.5 pt-2 border-t border-slate-800">
          <span class="chip-place chip-lodging text-3xs py-0.5 px-2 shrink-0">🌙 Powrót</span>
          <div><b>Powrót / Nocleg:</b> <span class="font-medium text-purple-300">${endLocation}</span></div>
        </div>
      </div>
    `;

    card.innerHTML = cardHeader + cardBody;

    const btnFocus = card.querySelector('.btn-focus-day');
    if (btnFocus) {
      btnFocus.addEventListener('click', () => {
        lastUserFilterClickTime = Date.now();
        activeElevationTrackIndex = 0;
        filterMapByDay(dayNumber, allMapPoints);
      });
    }

    // Mountain track click & focus
    card.querySelectorAll('.mountain-track-card, .btn-focus-gps-track').forEach(trackEl => {
      trackEl.addEventListener('click', (e) => {
        e.stopPropagation();
        const trDay = parseInt(trackEl.dataset.day, 10);
        const trIdx = parseInt(trackEl.dataset.trackIndex, 10);
        focusMountainTrack(trDay, trIdx, allMapPoints);
      });
    });

    daysContainer.appendChild(card);

    places.forEach(p => {
      if (p.lat && p.lon && (p.lat !== 0 || p.lon !== 0)) {
        allMapPoints.push({
          lat: p.lat,
          lon: p.lon,
          name: p.name,
          category: p.category,
          categoryIcon: p.categoryIcon,
          categoryLabel: p.categoryLabel,
          day: dayNumber,
          time: p.start ? p.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'}) : ''
        });
      }
    });
  });

  setupMapDayFilter(trip, allMapPoints);
  generateMarkdownForTrip(trip);

  currentActiveDayFilter = 'all';
  renderMapPoints(allMapPoints, trip.photos || []);

  // 1. Scrollytelling with IntersectionObserver
  setupScrollytelling(trip, allMapPoints);
}

// Scrollytelling with IntersectionObserver
let tripDetailScrollyObserver = null;
let scrollyDebounceTimer = null;
let lastUserFilterClickTime = 0;
let lastActiveScrollyDay = null;

function setupScrollytelling(trip, allMapPoints) {
  if (tripDetailScrollyObserver) {
    tripDetailScrollyObserver.disconnect();
    tripDetailScrollyObserver = null;
  }
  clearTimeout(scrollyDebounceTimer);
  lastActiveScrollyDay = null;

  if (typeof IntersectionObserver === 'undefined') return;

  const dayCards = document.querySelectorAll('#days-container .day-itinerary-card');
  if (!dayCards || dayCards.length === 0) return;

  // Build points & photos lookup map per day
  const dayDataMap = new Map();
  trip.days.forEach((day, idx) => {
    const dayNum = idx + 1;
    const dayPoints = allMapPoints.filter(p => p.day === dayNum);
    const dayPhotos = (trip.photos || []).filter(p => p.dayNumber === dayNum);
    const focusPoints = [...dayPoints];
    dayPhotos.forEach(p => {
      if (p.lat && p.lon && !focusPoints.some(fp => Math.abs(fp.lat - p.lat) < 0.0001 && Math.abs(fp.lon - p.lon) < 0.0001)) {
        focusPoints.push({ lat: p.lat, lon: p.lon, name: p.name });
      }
    });
    dayDataMap.set(dayNum, focusPoints);
  });

  const observerOptions = {
    root: null, // viewport
    threshold: [0.4] // card is at least 40% visible in the viewport
  };

  tripDetailScrollyObserver = new IntersectionObserver((entries) => {
    const visibleEntries = entries.filter(e => e.isIntersecting && e.intersectionRatio >= 0.4);
    if (visibleEntries.length === 0) return;

    // Pick entry with the largest visible ratio
    visibleEntries.sort((a, b) => b.intersectionRatio - a.intersectionRatio);
    const topEntry = visibleEntries[0];
    const dayNum = parseInt(topEntry.target.dataset.day, 10);
    if (!dayNum || dayNum === lastActiveScrollyDay) return;

    clearTimeout(scrollyDebounceTimer);
    scrollyDebounceTimer = setTimeout(() => {
      // Skip triggering if user manually clicked a day filter recently (1500ms grace period)
      if (Date.now() - lastUserFilterClickTime < 1500) {
        return;
      }

      lastActiveScrollyDay = dayNum;

      // 1. Highlight corresponding button in #trip-day-filter-bar
      const filterBar = document.getElementById('trip-day-filter-bar');
      if (filterBar) {
        filterBar.querySelectorAll('.map-day-btn').forEach(btn => {
          if (btn.dataset.day === String(dayNum)) {
            btn.className = 'map-day-btn px-2.5 py-1 rounded-lg bg-cyan-500 text-slate-950 font-black whitespace-nowrap shadow-[0_0_10px_rgba(0,240,255,0.4)]';
            // Scroll ONLY the inner horizontal container without affecting the webpage window scroll
            filterBar.scrollLeft = btn.offsetLeft - (filterBar.clientWidth / 2) + (btn.clientWidth / 2);
          } else {
            btn.className = 'map-day-btn px-2.5 py-1 rounded-lg bg-[#0f172a] hover:bg-[#1a263e] text-slate-400 hover:text-cyan-300 font-semibold border border-slate-800 whitespace-nowrap';
          }
        });
      }

      // 2. Automatically call smartCenterMap for that day's points/photos without jarring the user
      const pointsToFocus = dayDataMap.get(dayNum);
      if (pointsToFocus && pointsToFocus.length > 0) {
        smartCenterMap(pointsToFocus, {
          padding: [45, 45],
          maxZoom: 15,
          isolateDestination: false
        });
      }
    }, 150);
  }, observerOptions);

  dayCards.forEach(c => tripDetailScrollyObserver.observe(c));
}

function renderBookingsSection(trip) {
  const section = document.getElementById('trip-bookings-section');
  const cardsContainer = document.getElementById('trip-bookings-cards');
  if (!section || !cardsContainer) return;

  if (!trip.bookings || trip.bookings.length === 0) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');
  cardsContainer.innerHTML = '';

  trip.bookings.forEach(b => {
    const card = document.createElement('div');
    card.className = 'glass-panel rounded-xl p-3.5 border border-slate-800 space-y-2 shadow-lg';

    let extraDetails = '';
    if (b.type === 'tour_package') {
      extraDetails = `
        <div class="text-xs text-slate-300 space-y-1">
          <div><b>Organizator:</b> <span class="text-teal-300 font-bold">${b.provider}</span></div>
          <div><b>Hotel:</b> <span class="text-slate-100 font-semibold">${b.hotelName}</span> (${b.boardBasis || 'HB'})</div>
          <div><b>Przelot:</b> ${b.flightInfo || 'Czarter ITAKA'}</div>
          <div><b>Transfer:</b> ${b.transferInfo || 'Autokar lotnisko ↔ hotel'}</div>
          ${b.repContact ? `<div class="text-3xs text-teal-300 bg-teal-500/10 border border-teal-500/30 p-1.5 rounded-lg mt-1">📞 ${b.repContact}</div>` : ''}
        </div>
      `;
    } else if (b.type === 'car_rental') {
      extraDetails = `
        <div class="text-xs text-slate-300 space-y-0.5">
          <div><b>Model:</b> <span class="text-cyan-300">${b.carModel}</span></div>
          <div><b>Odbiór:</b> ${b.pickup} (${b.pickupDate ? b.pickupDate.toLocaleString('pl-PL', {dateStyle:'short', timeStyle:'short'}) : ''})</div>
          <div><b>Zwrot:</b> ${b.returnPlace} (${b.returnDate ? b.returnDate.toLocaleString('pl-PL', {dateStyle:'short', timeStyle:'short'}) : ''})</div>
          ${b.included ? `<div class="text-3xs text-emerald-300 bg-emerald-950/80 border border-emerald-500/30 p-1.5 rounded-lg mt-1">${b.included}</div>` : ''}
        </div>
      `;
    } else if (b.type === 'lodging') {
      extraDetails = `
        <div class="text-xs text-slate-300 space-y-0.5">
          <div><b>Obiekt:</b> <span class="text-indigo-300">${b.hotelName}</span></div>
          <div><b>Adres:</b> ${b.address}</div>
          <div><b>Pobyt:</b> ${b.checkInDate ? b.checkInDate.toLocaleDateString('pl-PL') : ''} – ${b.checkOutDate ? b.checkOutDate.toLocaleDateString('pl-PL') : ''}</div>
          ${b.roomType ? `<div class="text-3xs text-blue-300 bg-blue-950/80 border border-blue-500/30 p-1.5 rounded-lg mt-1">${b.roomType}</div>` : ''}
        </div>
      `;
    } else if (b.type === 'flight') {
      extraDetails = `
        <div class="text-xs text-slate-300 space-y-0.5">
          <div><b>Rejs:</b> <span class="text-sky-300">${b.flightNumber}</span> (${b.airline})</div>
          <div><b>Trasa:</b> ${b.departureAirport} ➔ ${b.arrivalAirport}</div>
          <div><b>Wylot:</b> ${b.departureDate ? b.departureDate.toLocaleString('pl-PL', {dateStyle:'short', timeStyle:'short'}) : ''}</div>
          ${b.seat ? `<div><b>Miejsca:</b> ${b.seat}</div>` : ''}
        </div>
      `;
    } else {
      extraDetails = `
        <div class="text-xs text-slate-300 space-y-0.5">
          <div><b>Atrakcja:</b> <span class="text-emerald-300">${b.attractionName || b.title}</span></div>
          <div><b>Termin:</b> ${b.visitDate ? b.visitDate.toLocaleString('pl-PL', {dateStyle:'short', timeStyle:'short'}) : ''}</div>
          ${b.ticketCount ? `<div><b>Bilety:</b> ${b.ticketCount}</div>` : ''}
        </div>
      `;
    }

    card.innerHTML = `
      <div class="flex items-start justify-between gap-2 border-b border-slate-800 pb-2">
        <div class="flex items-center gap-2">
          <span class="text-2xl">${b.icon || '📌'}</span>
          <div>
            <span class="text-3xs uppercase tracking-wider font-bold text-blue-300 bg-blue-950/80 px-2 py-0.5 rounded-md border border-blue-500/40">${b.categoryLabel || b.provider}</span>
            <h5 class="text-xs font-bold text-slate-100 leading-tight mt-0.5">${b.title}</h5>
          </div>
        </div>
        <div class="text-right shrink-0">
          <span class="text-xs font-black text-cyan-300">${b.price || ''}</span>
        </div>
      </div>
      ${extraDetails}
      <div class="flex items-center justify-between pt-1 border-t border-slate-800 text-3xs text-slate-400">
        <span>Nr: <code class="font-mono font-bold text-cyan-300 bg-[#070b14] px-1.5 py-0.5 rounded border border-cyan-500/30">${b.bookingNumber}</code></span>
        <button class="text-cyan-400 hover:text-cyan-300 font-bold btn-copy-booking" data-booking="${b.bookingNumber}">Kopiuj nr</button>
      </div>
    `;

    const copyBtn = card.querySelector('.btn-copy-booking');
    if (copyBtn) {
      copyBtn.addEventListener('click', (e) => {
        navigator.clipboard.writeText(e.target.dataset.booking);
        copyBtn.textContent = 'Skopiowano!';
        setTimeout(() => copyBtn.textContent = 'Kopiuj nr', 1500);
      });
    }

    cardsContainer.appendChild(card);
  });
}

function renderPhotoGalleryStrip(trip) {
  const container = document.getElementById('trip-photos-thumbnails');
  const gridContainer = document.getElementById('trip-photos-grid');
  const countBadge = document.getElementById('trip-photos-count-badge');
  const gridCount = document.getElementById('grid-photos-count');
  const statPhotos = document.getElementById('detail-stat-photos');
  const searchInput = document.getElementById('gallery-search-input');
  if (!container || !countBadge) return;

  const allPhotos = trip.photos || [];
  countBadge.textContent = `${allPhotos.length} zdjęć`;
  if (statPhotos) statPhotos.textContent = allPhotos.length;

  // Dynamically render Day Filter Buttons based on trip.days
  const filterContainer = document.getElementById('gallery-day-filters');
  if (filterContainer) {
    let filterHtml = `<button data-day="all" class="gallery-filter-btn px-2.5 py-1 rounded-lg text-xs font-bold ${currentGalleryDayFilter === 'all' ? 'bg-cyan-500 text-slate-950 shadow-[0_0_10px_rgba(0,240,255,0.4)]' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'} transition whitespace-nowrap">Wszystkie (${allPhotos.length})</button>`;
    
    (trip.days || []).forEach((day, dIdx) => {
      const dayNum = dIdx + 1;
      const count = allPhotos.filter(p => p.dayNumber === dayNum).length;
      const isSelected = currentGalleryDayFilter === String(dayNum);
      const rawTitle = day.title ? day.title.split(':')[1]?.trim() || day.title : `Dzień ${dayNum}`;
      const label = rawTitle.length > 18 ? rawTitle.slice(0, 16) + '...' : rawTitle;
      
      filterHtml += `
        <button data-day="${dayNum}" class="gallery-filter-btn px-2 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${isSelected ? 'bg-cyan-500 text-slate-950 font-bold shadow-[0_0_10px_rgba(0,240,255,0.4)]' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'} transition">
          D${dayNum}: ${label} ${count > 0 ? `(${count})` : ''}
        </button>
      `;
    });

    filterContainer.innerHTML = filterHtml;

    // Attach listeners
    filterContainer.querySelectorAll('.gallery-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        filterContainer.querySelectorAll('.gallery-filter-btn').forEach(b => {
          b.className = 'gallery-filter-btn px-2 py-1 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 transition whitespace-nowrap';
        });
        btn.className = 'gallery-filter-btn px-2.5 py-1 rounded-lg text-xs font-bold bg-cyan-500 text-slate-950 shadow-[0_0_10px_rgba(0,240,255,0.4)] transition whitespace-nowrap';
        currentGalleryDayFilter = btn.getAttribute('data-day') || 'all';
        renderPhotoGalleryStrip(trip);
        if (window.photoMatcher && window.map) {
          renderMapPoints(window.lastRenderedPoints || [], trip.photos || []);
        }
      });
    });
  }

  if (allPhotos.length === 0) {
    const isMadeira = trip.title && (trip.title.includes('Madera') || trip.title.includes('ITAKA'));
    const loadHint = isMadeira
      ? 'Kliknij <b>„Wczytaj zdjęcia z biblioteki”</b> powyżej, aby dodać zdjęcia z tego wyjazdu.'
      : 'Kliknij <b>„Wybierz folder ze zdjęciami”</b> lub <b>„Dodaj pliki”</b>, aby przypisać zdjęcia do tego wyjazdu.';
    container.innerHTML = `
      <div id="user-photos-empty-hint" class="text-xs text-slate-400 italic py-2 flex items-center gap-2">
        <span>ℹ️</span> <span>Brak przypisanych zdjęć do tego wyjazdu. ${loadHint}</span>
      </div>
    `;
    if (gridContainer) {
      gridContainer.innerHTML = '<div class="col-span-full text-center text-xs text-slate-500 py-6">Brak zdjęć w galerii dla tego wyjazdu.</div>';
    }
    return;
  }

  // Apply Day Filter & Search Filter
  const q = (searchInput ? searchInput.value : '').trim().toLowerCase();
  const filteredPhotos = allPhotos.filter(photo => {
    // Day filter
    if (currentGalleryDayFilter !== 'all') {
      const dayNum = parseInt(currentGalleryDayFilter, 10);
      if (photo.dayNumber !== dayNum) return false;
    }
    // Search filter
    if (q) {
      const placeMatch = (photo.matchedPlace || '').toLowerCase().includes(q);
      const nameMatch = (photo.filename || photo.name || '').toLowerCase().includes(q);
      if (!placeMatch && !nameMatch) return false;
    }
    return true;
  });

  if (gridCount) {
    gridCount.textContent = `${filteredPhotos.length} z ${allPhotos.length} zdjęć`;
  }

  // 1. Render Horizontal Quick-Scroll Strip (up to first 80 for silky-smooth scroll)
  container.innerHTML = '';
  const stripSlice = filteredPhotos.slice(0, 80);
  if (stripSlice.length === 0) {
    container.innerHTML = `
      <div class="text-xs text-slate-500 italic py-2">
        Brak zdjęć spełniających kryteria filtra.
      </div>
    `;
  } else {
    stripSlice.forEach(photo => {
      const item = document.createElement('div');
      item.className = 'shrink-0 relative group cursor-pointer transition transform hover:-translate-y-0.5';
      const thumbSrc = photo.url || photo.thumbnailUrl;
      const displayName = photo.matchedPlace ? photo.matchedPlace.split('(')[0] : (photo.filename || photo.name || 'Zdjęcie');
      item.innerHTML = `
        <div class="w-20 h-20 rounded-xl overflow-hidden shadow-sm border border-slate-700 bg-slate-900 ring-1 ring-cyan-500/20 group-hover:ring-cyan-400 transition">
          <img src="${thumbSrc}" alt="${displayName}" class="w-full h-full object-cover group-hover:scale-105 transition duration-200" loading="lazy" />
        </div>
        <span class="absolute top-1 right-1 bg-slate-950/85 text-cyan-300 border border-cyan-500/40 rounded text-3xs px-1 font-bold shadow">
          D${photo.dayNumber || '-'}
        </span>
        <span class="absolute bottom-1 inset-x-1 bg-slate-950/90 text-slate-200 rounded text-3xs px-1 py-0.5 truncate text-center font-medium shadow">
          ${displayName}
        </span>
      `;

      item.addEventListener('click', () => {
        window.photoMatcher.openLightbox(photo.id);
      });

      container.appendChild(item);
    });

    if (filteredPhotos.length > 80) {
      const moreBadge = document.createElement('div');
      moreBadge.className = 'shrink-0 p-2 text-2xs text-cyan-400 font-bold bg-slate-950 rounded-xl border border-cyan-500/30 cursor-pointer hover:bg-slate-900';
      moreBadge.textContent = `+${filteredPhotos.length - 80} więcej (rozwiń siatkę)`;
      moreBadge.addEventListener('click', () => {
        const toggleBtn = document.getElementById('btn-toggle-gallery-grid');
        if (toggleBtn) toggleBtn.click();
      });
      container.appendChild(moreBadge);
    }
  }

  // 2. Render Full Responsive Grid View
  if (gridContainer) {
    gridContainer.innerHTML = '';
    filteredPhotos.forEach(photo => {
      const cell = document.createElement('div');
      cell.className = 'relative group cursor-pointer rounded-xl overflow-hidden bg-slate-900 border border-slate-800 hover:border-cyan-400/80 transition transform hover:-translate-y-1 shadow-md';
      const thumbSrc = photo.url || photo.thumbnailUrl;
      const displayName = photo.matchedPlace ? photo.matchedPlace.split('(')[0] : (photo.filename || photo.name || 'Zdjęcie');
      const timeStr = photo.timestamp ? new Date(photo.timestamp).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '';

      cell.innerHTML = `
        <div class="aspect-square w-full overflow-hidden bg-slate-950">
          <img src="${thumbSrc}" alt="${displayName}" class="w-full h-full object-cover group-hover:scale-110 transition duration-300" loading="lazy" />
        </div>
        <div class="p-2 bg-slate-900/95 flex flex-col gap-0.5">
          <div class="flex items-center justify-between gap-1 text-3xs">
            <span class="font-bold text-cyan-300 bg-cyan-950/70 border border-cyan-500/30 px-1 rounded">D${photo.dayNumber || '-'}</span>
            <span class="text-slate-400">${timeStr}</span>
          </div>
          <p class="text-2xs font-semibold text-slate-200 truncate" title="${displayName}">${displayName}</p>
        </div>
      `;

      cell.addEventListener('click', () => {
        window.photoMatcher.openLightbox(photo.id);
      });

      gridContainer.appendChild(cell);
    });
  }
}

function renderPhotoMatcherModalList() {
  const listEl = document.getElementById('photo-matcher-list');
  if (!listEl) return;

  const trip = detectedTrips[currentTripIndex];
  const photos = trip ? (trip.photos || []) : [];

  if (photos.length === 0) {
    listEl.innerHTML = '<div class="text-xs text-slate-400 p-2">Nie dodano jeszcze zdjęć do tego wyjazdu.</div>';
    return;
  }

  listEl.innerHTML = photos.slice(0, 50).map(p => `
    <div class="flex items-center justify-between p-2 rounded-xl bg-slate-50 border border-slate-200/80 text-xs gap-3">
      <div class="flex items-center gap-2.5 overflow-hidden">
        <img src="${p.url}" alt="${p.name}" class="w-10 h-10 object-cover rounded-lg shrink-0" />
        <div class="truncate">
          <div class="font-bold text-slate-800 truncate">${p.matchedPlace || p.name}</div>
          <div class="text-2xs text-slate-500">
            Dzień ${p.dayNumber || '-'} &bull; ${p.timestamp ? new Date(p.timestamp).toLocaleString('pl-PL') : 'Brak daty'}
          </div>
        </div>
      </div>
      <span class="shrink-0 text-3xs font-semibold px-2 py-0.5 rounded-full ${p.geotagSource && p.geotagSource.includes('timeline') ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-blue-800'}">
        ${p.hasGps || p.geotagSource === 'exif_camera' ? '🛰️ Aparat GPS' : '🤖 Timeline GPS'}
      </span>
    </div>
  `).join('');
}

function loadUserPhotosFromIndex() {
  const trip = detectedTrips[currentTripIndex];
  if (!trip) return;

  const isMadeira = trip.title && (trip.title.includes('Madera') || trip.title.includes('ITAKA'));

  if (isMadeira) {
    const photoList = (window.USER_PHOTOS_INDEX && Array.isArray(window.USER_PHOTOS_INDEX) && window.USER_PHOTOS_INDEX.length > 0)
      ? window.USER_PHOTOS_INDEX
      : (window.EMBEDDED_SAMPLE_DATA && window.EMBEDDED_SAMPLE_DATA.trips && window.EMBEDDED_SAMPLE_DATA.trips[0] && window.EMBEDDED_SAMPLE_DATA.trips[0].photos)
        ? window.EMBEDDED_SAMPLE_DATA.trips[0].photos
        : null;

    if (photoList && photoList.length > 0) {
      trip.photos = photoList.map(p => ({
        ...p,
        timestamp: p.timestamp instanceof Date ? p.timestamp : new Date(p.timestamp)
      }));

      window.photoMatcher.photos = trip.photos;

      renderTripDetail(trip);
      renderPhotoMatcherModalList();
      alert(`Wczytano pomyślnie ${trip.photos.length} zdjęć z biblioteki!`);
      return;
    }
  } else {
    // If photos are already attached in trip object
    if (trip.photos && trip.photos.length > 0) {
      window.photoMatcher.photos = trip.photos;
      renderTripDetail(trip);
      renderPhotoMatcherModalList();
      alert(`Wczytano ${trip.photos.length} zdjęć przypisanych do wyjazdu „${trip.title}”!`);
      return;
    }

    // Direct user to folder picker for this trip
    const folderInput = document.getElementById('folder-photo-input');
    if (folderInput) {
      alert(`Wskaż katalog ze zdjęciami dla wyjazdu „${trip.title}” (np. z biblioteki zdjęć)`);
      folderInput.click();
      return;
    }
  }

  // Fallback: Attempt fetch from /api/user-photos
  fetch('api/user-photos')
    .then(res => res.json())
    .then(data => {
      if (Array.isArray(data) && data.length > 0) {
        trip.photos = data.map(p => ({
          ...p,
          timestamp: p.timestamp ? new Date(p.timestamp) : new Date(),
          url: p.url || `api/photo?path=${encodeURIComponent(p.filePath)}`
        }));
        window.photoMatcher.photos = trip.photos;
        renderTripDetail(trip);
        renderPhotoMatcherModalList();
        alert(`Wczytano ${trip.photos.length} zdjęć z serwera API!`);
      } else {
        alert('Brak zaindeksowanych zdjęć. Użyj przycisku „Wybierz folder ze zdjęciami”, aby wskazać katalog.');
      }
    })
    .catch(() => {
      alert('Podłącz serwer lokalny lub wskaż pliki za pomocą przycisku „Wybierz folder ze zdjęciami”.');
    });
}

function loadDemoPhotosForCurrentTrip() {
  loadUserPhotosFromIndex();
}

function setupMapDayFilter(trip, allMapPoints) {
  const container = document.getElementById('trip-day-filter-bar');
  if (!container) return;

  let html = `<button data-day="all" class="map-day-btn px-2.5 py-1 rounded-lg bg-cyan-500 text-slate-950 font-black whitespace-nowrap shadow-[0_0_10px_rgba(0,240,255,0.4)]">Cała trasa</button>`;
  trip.days.forEach((day, index) => {
    const dayNum = index + 1;
    html += `<button data-day="${dayNum}" class="map-day-btn px-2.5 py-1 rounded-lg bg-[#0f172a] hover:bg-[#1a263e] text-slate-400 hover:text-cyan-300 font-semibold border border-slate-800 whitespace-nowrap">Dzień ${dayNum}</button>`;
  });

  container.innerHTML = html;

  container.querySelectorAll('.map-day-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      lastUserFilterClickTime = Date.now();
      const day = e.target.dataset.day;
      filterMapByDay(day, allMapPoints);
    });
  });
}

function filterMapByDay(day, allPoints) {
  currentActiveDayFilter = day;

  const container = document.getElementById('trip-day-filter-bar');
  if (container) {
    container.querySelectorAll('.map-day-btn').forEach(b => {
      if (b.dataset.day === day.toString()) {
        b.className = 'map-day-btn px-2.5 py-1 rounded-lg bg-cyan-500 text-slate-950 font-black whitespace-nowrap shadow-[0_0_10px_rgba(0,240,255,0.4)]';
      } else {
        b.className = 'map-day-btn px-2.5 py-1 rounded-lg bg-[#0f172a] hover:bg-[#1a263e] text-slate-400 hover:text-cyan-300 font-semibold border border-slate-800 whitespace-nowrap';
      }
    });
  }

  const filteredPoints = day === 'all' 
    ? allPoints 
    : allPoints.filter(p => p.day === parseInt(day, 10));

  currentActiveDayFilter = day;
  const trip = detectedTrips[currentTripIndex];
  renderMapPoints(filteredPoints, trip ? trip.photos : []);
}

/**
 * Smart Map Centering & Auto-Bounding System
 * Automatically detects whether to focus on a specific day, a single attraction,
 * or the full destination cluster (ignoring faraway departure airport waypoints).
 */
function smartCenterMap(pointsToFocus, options = {}) {
  if (!map) return;

  // Guarantee map knows its actual rendered dimensions
  map.invalidateSize();

  const validPts = (pointsToFocus || []).filter(p => {
    const lat = Array.isArray(p) ? p[0] : p.lat;
    const lon = Array.isArray(p) ? p[1] : p.lon;
    return typeof lat === 'number' && typeof lon === 'number' && !isNaN(lat) && !isNaN(lon) && (lat !== 0 || lon !== 0);
  }).map(p => Array.isArray(p) ? [p[0], p[1]] : [p.lat, p.lon]);

  if (validPts.length === 0) return;

  if (validPts.length === 1) {
    map.setView(validPts[0], options.singleZoom || 14, { animate: true });
    return;
  }

  let targetPoints = validPts;

  // If viewing all days, isolate destination points from home departure points
  if (options.isolateDestination && validPts.length >= 3) {
    const lats = validPts.map(p => p[0]);
    const lons = validPts.map(p => p[1]);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);

    // If points span more than 3.5 degrees (e.g. flight across Europe or Atlantic)
    if ((maxLat - minLat > 3.5) || (maxLon - minLon > 3.5)) {
      // 1. Check for foreign destination points outside Central Poland (lat < 49.0 or lat > 54.8 or lon < 14.0 or lon > 24.0)
      const foreignPts = validPts.filter(p => p[0] < 49.0 || p[0] > 54.8 || p[1] < 14.0 || p[1] > 24.0);
      if (foreignPts.length >= 2) {
        targetPoints = foreignPts;
      } else {
        // 2. Mountain/Regional destination within Poland (e.g. Tatry & Zakopane: lat < 49.45)
        const southPolandPts = validPts.filter(p => p[0] <= 49.45 && p[0] >= 49.10);
        if (southPolandPts.length >= 2) {
          targetPoints = southPolandPts;
        }
      }
    }
  }

  try {
    const bounds = L.latLngBounds(targetPoints);
    map.fitBounds(bounds, {
      padding: options.padding || [45, 45],
      maxZoom: options.maxZoom || 15,
      animate: true
    });
  } catch (err) {
    map.setView(targetPoints[0], 13);
  }

  // Second pass invalidateSize guarantees crisp tiles after zoom transitions
  setTimeout(() => {
    if (map) map.invalidateSize();
  }, 200);
}

function renderMapPoints(points, photos = []) {
  if (!map) return;

  mapMarkers.forEach(m => map.removeLayer(m));
  mapMarkers = [];
  mapPhotoMarkers.forEach(m => map.removeLayer(m));
  mapPhotoMarkers = [];

  if (mapRouteLine) {
    map.removeLayer(mapRouteLine);
    mapRouteLine = null;
  }

  const latlngs = [];

  points.forEach((pt) => {
    latlngs.push([pt.lat, pt.lon]);

    let color = '#38bdf8';
    if (pt.category === 'peak') color = '#06b6d4'; // Cyan for mountain summits & viewpoints
    else if (pt.category === 'food') color = '#f43f5e';
    else if (pt.category === 'lodging') color = '#a855f7';
    else if (pt.category === 'attraction') color = '#10b981';
    else if (pt.category === 'airport') color = '#fbbf24';

    const circleMarker = L.circleMarker([pt.lat, pt.lon], {
      radius: 8,
      fillColor: color,
      color: '#070b14',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.95
    }).addTo(map);

    const catLabel = pt.categoryLabel || (pt.category === 'peak' ? 'Zdobyty szczyt / Punkt widokowy' : pt.category);
    const eleSnippet = pt.elevation ? `<div style="margin-top:3px; color:#38bdf8; font-weight:bold; font-size:11px;">⛰️ Wysokość: ${Math.round(pt.elevation)} m n.p.m.</div>` : '';
    circleMarker.bindPopup(`
      <div style="font-size:12px; font-family:sans-serif; min-width:140px; background:#0c1322; color:#f1f5f9; padding:8px; border-radius:8px; border:1px solid rgba(0,240,255,0.3);">
        <span style="display:inline-block; font-size:10px; font-weight:bold; background:#082f49; color:#38bdf8; padding:2px 6px; border-radius:4px; margin-bottom:4px; border:1px solid rgba(56,189,248,0.3);">
          Dzień ${pt.day} &bull; ${pt.time || ''}
        </span><br>
        <b style="color:#ffffff; font-size:13px;">${pt.name}</b><br>
        <span style="color:#94a3b8; font-size:11px;">Kategoria: ${catLabel}</span>
        ${eleSnippet}
      </div>
    `);

    mapMarkers.push(circleMarker);
  });

  // Render Photo Markers on Map
  if (photos && photos.length > 0 && window.photoMatcher) {
    mapPhotoMarkers = window.photoMatcher.renderMapPhotoPins(map, photos, currentActiveDayFilter);
    photos.forEach(p => {
      if (p.lat && p.lon && (currentActiveDayFilter === 'all' || p.dayNumber === parseInt(currentActiveDayFilter, 10))) {
        latlngs.push([p.lat, p.lon]);
      }
    });
  }

  // Clear previous GPS tracks & hover marker
  clearGpsTrackLayers();

  // Render High-Resolution Mountain GPS Polyline & Elevation Profile
  const trip = detectedTrips[currentTripIndex];
  renderGpsTracksOnMap(trip, latlngs);

  // Detailed GPS polyline from timelinePath if available
  let routeToDraw = latlngs;
  if (trip && trip.routePoints && trip.routePoints.length > 0 && currentActiveDayFilter === 'all') {
    routeToDraw = trip.routePoints;
  }

  // Draw connecting path
  if (routeToDraw.length > 1) {
    mapRouteLine = L.polyline(routeToDraw, {
      color: '#00f0ff',
      weight: 3.5,
      opacity: 0.85,
      lineCap: 'round',
      lineJoin: 'round'
    }).addTo(map);
  }

  // Smart centering: focus on target places, mountain tracks and photos
  const pointsToCenter = latlngs.length > 0 ? latlngs : routeToDraw;
  smartCenterMap(pointsToCenter, {
    isolateDestination: currentActiveDayFilter === 'all',
    padding: [45, 45],
    maxZoom: currentActiveDayFilter === 'all' ? 14 : 15,
    singleZoom: 14
  });
}

// ----------------------------------------------------
// GPS Track Polyline Rendering & Elevation Profile
// ----------------------------------------------------

function clearGpsTrackLayers() {
  mapGpsTrackLayers.forEach(l => {
    if (map) map.removeLayer(l);
  });
  mapGpsTrackLayers = [];
  hidePulsingHoverMarker();
}

function showPulsingHoverMarker(lat, lon) {
  if (!map || typeof lat !== 'number' || typeof lon !== 'number') return;
  if (!mapGpsHoverMarker) {
    const icon = L.divIcon({
      className: 'gps-pulsing-marker',
      html: '<div class="gps-pulsing-circle"></div>',
      iconSize: [14, 14],
      iconAnchor: [7, 7]
    });
    mapGpsHoverMarker = L.marker([lat, lon], { icon, zIndexOffset: 2000 }).addTo(map);
  } else {
    mapGpsHoverMarker.setLatLng([lat, lon]);
  }
}

function hidePulsingHoverMarker() {
  if (mapGpsHoverMarker && map) {
    map.removeLayer(mapGpsHoverMarker);
    mapGpsHoverMarker = null;
  }
}

function getHaversineDistanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function findClosestPointInPolyline(pts, targetLatLng) {
  if (!pts || pts.length === 0) return null;
  const tLat = targetLatLng.lat !== undefined ? targetLatLng.lat : targetLatLng[0];
  const tLon = targetLatLng.lng !== undefined ? targetLatLng.lng : (targetLatLng.lon !== undefined ? targetLatLng.lon : targetLatLng[1]);
  let closest = pts[0];
  let minSqDist = Infinity;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const dLat = p.lat - tLat;
    const dLon = p.lon - tLon;
    const sqDist = dLat * dLat + dLon * dLon;
    if (sqDist < minSqDist) {
      minSqDist = sqDist;
      closest = p;
    }
  }
  return closest;
}

function createGpsFlagMarker(type, pt, trackName) {
  const isStart = type === 'start';
  const label = isStart ? '🚩 START' : '🏁 META';
  const bg = isStart 
    ? 'background:#10b981; color:#022c22; border:1.5px solid #ffffff;' 
    : 'background:#f43f5e; color:#ffffff; border:1.5px solid #ffffff;';
  const eleStr = pt.ele ? `${Math.round(pt.ele)}m` : '';
  const html = `
    <div style="display:inline-flex; align-items:center; gap:4px; ${bg} font-weight:800; font-size:10px; font-family:sans-serif; padding:2px 7px; border-radius:9999px; box-shadow:0 0 12px rgba(0,0,0,0.6); transform:translate(-50%, -100%); white-space:nowrap; cursor:pointer;">
      <span>${label}</span>
      ${eleStr ? `<span style="opacity:0.85; font-size:9px;">${eleStr}</span>` : ''}
    </div>
  `;
  const icon = L.divIcon({
    className: isStart ? 'gps-flag-start' : 'gps-flag-finish',
    html: html,
    iconSize: [0, 0]
  });
  const marker = L.marker([pt.lat, pt.lon], { icon, zIndexOffset: 500 });
  marker.bindPopup(`
    <div style="font-family:sans-serif; font-size:12px; background:#0c1322; color:#f1f5f9; padding:8px; border-radius:8px; border:1px solid rgba(0,240,255,0.3); min-width:140px;">
      <b style="color:${isStart ? '#34d399' : '#f87171'};">${label} &bull; ${trackName || 'Ślad GPS'}</b><br>
      <div style="margin-top:4px; color:#cbd5e1; font-size:11px;">
        ⛰️ Wysokość: <b>${pt.ele ? Math.round(pt.ele) + ' m n.p.m.' : 'Brak danych'}</b><br>
        📍 Koordynaty: ${pt.lat.toFixed(5)}, ${pt.lon.toFixed(5)}
      </div>
    </div>
  `);
  return marker;
}

function renderGpsTracksOnMap(trip, latlngs) {
  if (!map) return;

  const tracks = [];
  if (trip && trip.days) {
    if (currentActiveDayFilter === 'all') {
      trip.days.forEach((d, idx) => {
        (d.mountainTracks || []).forEach((tr, tIdx) => {
          if (tr.polyline && tr.polyline.length > 0) {
            tracks.push({ track: tr, dayNumber: idx + 1, trackIndex: tIdx });
          }
        });
      });
    } else {
      const dayNum = parseInt(currentActiveDayFilter, 10);
      const d = trip.days[dayNum - 1];
      if (d) {
        (d.mountainTracks || []).forEach((tr, tIdx) => {
          if (tr.polyline && tr.polyline.length > 0) {
            tracks.push({ track: tr, dayNumber: dayNum, trackIndex: tIdx });
          }
        });
      }
    }
  }

  currentElevationTracks = tracks;
  if (activeElevationTrackIndex >= tracks.length) {
    activeElevationTrackIndex = 0;
  }

  // Update Map Toggle Button in control bar & Floating On-Map Button
  const toggleBtn = document.getElementById('btn-toggle-gps-tracks');
  const toggleText = document.getElementById('gps-track-toggle-text');
  const floatingBtn = document.getElementById('btn-floating-gps-toggle');
  const floatingText = document.getElementById('floating-gps-toggle-text');
  const floatingPulse = document.getElementById('floating-gps-pulse-dot');

  if (toggleBtn && toggleText) {
    if (tracks.length === 0) {
      toggleBtn.className = 'text-2xs font-bold px-2.5 py-1 rounded-lg border transition flex items-center gap-1.5 bg-slate-900/60 border-slate-800 text-slate-500 cursor-not-allowed';
      toggleText.textContent = 'Ślad GPS: Brak';
      toggleBtn.title = 'Brak śladów GPS dla wybranego dnia';
    } else if (showGpsTracks) {
      toggleBtn.className = 'text-2xs font-bold px-2.5 py-1 rounded-lg border transition flex items-center gap-1.5 bg-emerald-950/80 border-emerald-500/40 text-emerald-300 hover:bg-emerald-900/90 shadow-[0_0_12px_rgba(16,185,129,0.25)]';
      toggleText.textContent = 'Ślad GPS: Włączony';
      toggleBtn.title = 'Ślady GPS ze Strava / Intervals są włączone. Kliknij, aby wyłączyć.';
    } else {
      toggleBtn.className = 'text-2xs font-bold px-2.5 py-1 rounded-lg border transition flex items-center gap-1.5 bg-slate-800/80 border-slate-700 text-slate-400 hover:text-slate-200';
      toggleText.textContent = 'Ślad GPS: Wyłączony';
      toggleBtn.title = 'Ślady GPS są wyłączone. Kliknij, aby włączyć.';
    }
  }

  if (floatingBtn && floatingText) {
    if (tracks.length === 0) {
      floatingBtn.style.display = 'none';
    } else {
      floatingBtn.style.display = 'flex';
      if (showGpsTracks) {
        floatingBtn.className = 'flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-950/90 backdrop-blur-md border border-emerald-500 text-emerald-300 font-bold text-xs shadow-[0_0_20px_rgba(16,185,129,0.4)] hover:bg-slate-900 hover:scale-105 active:scale-95 transition';
        floatingText.textContent = 'Ślad GPS: Włączony';
        if (floatingPulse) {
          floatingPulse.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]';
          floatingPulse.style.display = 'inline-block';
        }
      } else {
        floatingBtn.className = 'flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-950/90 backdrop-blur-md border border-slate-700 text-slate-400 font-bold text-xs shadow-md hover:bg-slate-900 hover:text-slate-200 transition';
        floatingText.textContent = 'Ślad GPS: Wyłączony';
        if (floatingPulse) {
          floatingPulse.style.display = 'none';
        }
      }
    }
  }

  const profileCard = document.getElementById('elevation-profile-card');

  if (!showGpsTracks || tracks.length === 0) {
    if (profileCard) profileCard.classList.add('hidden');
    return;
  }

  if (profileCard) profileCard.classList.remove('hidden');

  // Render Each Track Polyline & Flags
  tracks.forEach((item) => {
    const tr = item.track;
    if (!tr.polyline || tr.polyline.length === 0) return;

    const polyPoints = tr.polyline.map(p => [p.lat, p.lon]);

    // 1. High-contrast outer glow line (cyan #06b6d4)
    const glowLine = L.polyline(polyPoints, {
      color: '#06b6d4',
      weight: 8,
      opacity: 0.38,
      lineCap: 'round',
      lineJoin: 'round',
      className: 'gps-track-glow'
    }).addTo(map);
    mapGpsTrackLayers.push(glowLine);

    // 2. High-contrast core mountain polyline (emerald #10b981)
    const coreLine = L.polyline(polyPoints, {
      color: '#10b981',
      weight: 4,
      opacity: 0.95,
      lineCap: 'round',
      lineJoin: 'round',
      className: 'gps-track-core'
    }).addTo(map);
    mapGpsTrackLayers.push(coreLine);

    // 3. Start & Finish Flag Markers
    const startMarker = createGpsFlagMarker('start', tr.polyline[0], tr.name);
    startMarker.addTo(map);
    mapGpsTrackLayers.push(startMarker);

    const finishMarker = createGpsFlagMarker('finish', tr.polyline[tr.polyline.length - 1], tr.name);
    finishMarker.addTo(map);
    mapGpsTrackLayers.push(finishMarker);

    // 4. Interactive hover & click along polyline
    coreLine.bindTooltip('', {
      sticky: true,
      className: 'gps-trail-tooltip',
      direction: 'top',
      offset: [0, -10]
    });

    coreLine.on('mousemove', (e) => {
      const closest = findClosestPointInPolyline(tr.polyline, e.latlng);
      if (closest) {
        const tipHtml = `
          <div style="font-size:11px; font-family:sans-serif; min-width:130px;">
            <div style="font-weight:800; color:#00f0ff; margin-bottom:3px; display:flex; align-items:center; gap:4px;">
              <span>🥾</span> <span>${tr.name || 'Ślad górski GPS'}</span>
            </div>
            <div style="color:#cbd5e1; font-size:10.5px;">📏 Dystans: <b style="color:#ffffff;">${((closest.dist || 0) / 1000).toFixed(2)} km</b></div>
            <div style="color:#cbd5e1; font-size:10.5px;">⛰️ Wysokość: <b style="color:#34d399;">${Math.round(closest.ele || 0)} m n.p.m.</b></div>
          </div>
        `;
        coreLine.setTooltipContent(tipHtml);
        showPulsingHoverMarker(closest.lat, closest.lon);
        updateElevationChartCursorFromMap(closest);
      }
    });

    coreLine.on('mouseout', () => {
      hidePulsingHoverMarker();
      clearElevationChartCursor();
    });

    coreLine.on('click', () => {
      activeElevationTrackIndex = item.trackIndex;
      renderElevationProfile();
      map.fitBounds(L.latLngBounds(polyPoints), { padding: [45, 45], maxZoom: 15 });
    });

    // Sample coordinates into latlngs so smartCenterMap automatically includes the mountain trail
    const sampleStep = Math.max(1, Math.floor(tr.polyline.length / 30));
    for (let s = 0; s < tr.polyline.length; s += sampleStep) {
      latlngs.push([tr.polyline[s].lat, tr.polyline[s].lon]);
    }
  });

  // Render Elevation Profile Widget
  renderElevationProfile();
}

function updateElevationChartCursorFromMap(closest) {
  currentChartHoverPt = closest;
  renderElevationProfile();
  const tooltip = document.getElementById('elevation-tooltip');
  if (tooltip) {
    tooltip.classList.remove('hidden');
    const eleEl = document.getElementById('ele-tooltip-ele');
    const distEl = document.getElementById('ele-tooltip-dist');
    if (eleEl) eleEl.textContent = `⛰️ ${Math.round(closest.ele || 0)} m`;
    if (distEl) distEl.textContent = `📏 ${((closest.dist || 0) / 1000).toFixed(2)} km`;
    tooltip.style.left = '12px';
    tooltip.style.top = '12px';
  }
}

function clearElevationChartCursor() {
  currentChartHoverPt = null;
  renderElevationProfile();
  const tooltip = document.getElementById('elevation-tooltip');
  if (tooltip) tooltip.classList.add('hidden');
}

function toggleGpsTracks() {
  showGpsTracks = !showGpsTracks;
  const trip = detectedTrips[currentTripIndex];
  if (trip) {
    const allMapPoints = [];
    (trip.days || []).forEach((d, idx) => {
      (d.events || []).filter(e => e.type === 'place').forEach(p => {
        if (p.lat && p.lon) allMapPoints.push({ lat: p.lat, lon: p.lon, name: p.name, category: p.category, day: idx + 1 });
      });
    });
    filterMapByDay(currentActiveDayFilter, allMapPoints);
  }
}

function toggleElevationChartCollapse() {
  isElevationChartCollapsed = !isElevationChartCollapsed;
  const wrapper = document.getElementById('elevation-chart-wrapper');
  const text = document.getElementById('elevation-collapse-text');
  const icon = document.getElementById('elevation-collapse-icon');

  if (wrapper) wrapper.classList.toggle('hidden', isElevationChartCollapsed);
  if (text) text.textContent = isElevationChartCollapsed ? 'Rozwiń' : 'Zwiń';
  if (icon) icon.style.transform = isElevationChartCollapsed ? 'rotate(180deg)' : 'rotate(0deg)';

  if (!isElevationChartCollapsed) {
    setTimeout(() => renderElevationProfile(), 60);
  }
}

function focusMountainTrack(dayNumber, trackIndex, allMapPoints) {
  lastUserFilterClickTime = Date.now();
  activeElevationTrackIndex = trackIndex;

  if (currentActiveDayFilter !== dayNumber.toString() && currentActiveDayFilter !== dayNumber) {
    filterMapByDay(dayNumber, allMapPoints || []);
  }

  const trip = detectedTrips[currentTripIndex];
  const day = trip?.days?.[dayNumber - 1];
  const track = day?.mountainTracks?.[trackIndex];
  if (track && track.polyline && track.polyline.length > 0 && map) {
    const trackBounds = L.latLngBounds(track.polyline.map(p => [p.lat, p.lon]));
    map.fitBounds(trackBounds, { padding: [50, 50], maxZoom: 15, animate: true });
    renderElevationProfile();
  }

  const mapContainer = document.getElementById('map-container');
  if (mapContainer && window.innerWidth < 1024) {
    mapContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function renderElevationProfile() {
  const card = document.getElementById('elevation-profile-card');
  const canvas = document.getElementById('elevation-canvas');
  if (!card || !canvas) return;

  if (!showGpsTracks || currentElevationTracks.length === 0) {
    card.classList.add('hidden');
    return;
  }
  card.classList.remove('hidden');

  // Track Selector Pills (if multiple tracks)
  const selector = document.getElementById('elevation-track-selector');
  if (selector) {
    if (currentElevationTracks.length > 1) {
      selector.classList.remove('hidden');
      selector.innerHTML = currentElevationTracks.map((item, idx) => {
        const tr = item.track || item;
        const isActive = idx === activeElevationTrackIndex;
        const activeClass = isActive
          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/60 shadow-[0_0_8px_rgba(6,182,212,0.3)] font-bold'
          : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200';
        const distStr = tr.distanceKm ? `${tr.distanceKm} km` : (tr.polyline ? `${((tr.polyline[tr.polyline.length - 1].dist || 0) / 1000).toFixed(1)} km` : '');
        return `
          <button type="button" class="btn-ele-track-pill px-2.5 py-1 rounded-lg border text-3xs whitespace-nowrap transition ${activeClass}" data-index="${idx}">
            🥾 ${tr.name || `Trasa ${idx + 1}`} ${distStr ? `(${distStr})` : ''}
          </button>
        `;
      }).join('');

      selector.querySelectorAll('.btn-ele-track-pill').forEach(btn => {
        btn.addEventListener('click', () => {
          const idx = parseInt(btn.dataset.index, 10);
          activeElevationTrackIndex = idx;
          const target = currentElevationTracks[idx];
          const tr = target.track || target;
          if (tr && tr.polyline && tr.polyline.length > 0 && map) {
            map.fitBounds(L.latLngBounds(tr.polyline.map(p => [p.lat, p.lon])), { padding: [50, 50], maxZoom: 15 });
          }
          renderElevationProfile();
        });
      });
    } else {
      selector.classList.add('hidden');
    }
  }

  const activeItem = currentElevationTracks[activeElevationTrackIndex] || currentElevationTracks[0];
  const track = activeItem.track || activeItem;
  if (!track || !track.polyline || track.polyline.length < 2) {
    return;
  }

  // Update track title badge
  const trackNameEl = document.getElementById('elevation-track-name');
  if (trackNameEl) {
    trackNameEl.textContent = track.name || 'Wędrówka górska';
    trackNameEl.title = track.name || 'Wędrówka górska';
  }

  // Prepare and normalize points
  const rawPts = track.polyline;
  let cumDist = 0;
  const pts = [];
  let minEle = Infinity;
  let maxEle = -Infinity;
  let maxEleIdx = 0;
  let totalGain = 0;

  for (let i = 0; i < rawPts.length; i++) {
    const rp = rawPts[i];
    let d = rp.dist;
    if (d === undefined || d === null || (i > 0 && d === 0 && pts[i - 1].dist === 0)) {
      if (i > 0) cumDist += getHaversineDistanceMeters(rawPts[i - 1].lat, rawPts[i - 1].lon, rp.lat, rp.lon);
      d = cumDist;
    } else {
      cumDist = d;
    }
    const ele = (rp.ele !== undefined && rp.ele !== null && !isNaN(rp.ele)) ? rp.ele : (i > 0 ? pts[i - 1].ele : 0);
    if (ele < minEle) minEle = ele;
    if (ele > maxEle) {
      maxEle = ele;
      maxEleIdx = i;
    }
    if (i > 0 && ele > pts[i - 1].ele) {
      totalGain += (ele - pts[i - 1].ele);
    }
    pts.push({ lat: rp.lat, lon: rp.lon, ele, dist: d });
  }

  const totalDist = pts[pts.length - 1].dist || 1;
  const startEle = pts[0].ele;

  // Update Quick Stats Bar
  const startEl = document.getElementById('ele-stat-start');
  if (startEl) startEl.innerHTML = `🚩 Start: <b class="text-emerald-400 font-bold">${Math.round(startEle)} m</b>`;
  const maxEl = document.getElementById('ele-stat-max');
  if (maxEl) maxEl.innerHTML = `⛰️ Szczyt: <b class="text-white font-bold">${Math.round(maxEle)} m</b>`;
  const gainEl = document.getElementById('ele-stat-gain');
  if (gainEl) gainEl.innerHTML = `↗️ W górę: <b class="text-cyan-300 font-bold">+${Math.round(track.elevationGainM || totalGain)} m</b>`;
  const distEl = document.getElementById('ele-stat-dist');
  if (distEl) distEl.innerHTML = `📏 Dystans: <b class="text-slate-100 font-bold">${(totalDist / 1000).toFixed(1)} km</b>`;

  if (isElevationChartCollapsed) return;

  // Setup Canvas Dimensions & DPR
  const wrapper = document.getElementById('elevation-chart-wrapper');
  if (!wrapper) return;
  const rect = wrapper.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = rect.width;
  const h = rect.height;
  if (w <= 0 || h <= 0) return;

  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  const ctx = canvas.getContext('2d');
  ctx.resetTransform ? ctx.resetTransform() : ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);

  // Layout Margins
  const ml = 38;
  const mr = 16;
  const mt = 18;
  const mb = 20;
  const chartW = Math.max(10, w - ml - mr);
  const chartH = Math.max(10, h - mt - mb);

  // Y Scale
  const eleSpan = maxEle - minEle;
  const yPad = Math.max(25, eleSpan * 0.12);
  const yMin = Math.max(0, Math.floor((minEle - yPad) / 50) * 50);
  const yMax = Math.ceil((maxEle + yPad) / 50) * 50;

  function getX(distM) {
    return ml + (distM / totalDist) * chartW;
  }
  function getY(eleM) {
    return mt + chartH - ((eleM - yMin) / (yMax - yMin)) * chartH;
  }

  // Draw Horizontal Gridlines & Y Labels
  const ySteps = 3;
  ctx.font = '10px monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let s = 0; s <= ySteps; s++) {
    const val = yMin + ((yMax - yMin) / ySteps) * s;
    const yPos = getY(val);
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 1;
    ctx.moveTo(ml, yPos);
    ctx.lineTo(ml + chartW, yPos);
    ctx.stroke();

    ctx.fillStyle = '#64748b';
    ctx.fillText(`${Math.round(val)}m`, ml - 6, yPos);
  }

  // Draw Vertical Gridlines & X Labels (km)
  const totalKm = totalDist / 1000;
  const kmStep = totalKm > 25 ? 5 : (totalKm > 10 ? 2 : (totalKm > 4 ? 1 : 0.5));
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let k = 0; k <= totalKm; k += kmStep) {
    const xPos = getX(k * 1000);
    if (xPos > ml + chartW) break;
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.moveTo(xPos, mt);
    ctx.lineTo(xPos, mt + chartH);
    ctx.stroke();

    ctx.fillStyle = '#64748b';
    ctx.fillText(`${k % 1 === 0 ? k : k.toFixed(1)}k`, xPos, mt + chartH + 5);
  }

  // Area Fill with Smooth Cyan-Emerald Gradient
  const grad = ctx.createLinearGradient(0, mt, 0, mt + chartH);
  grad.addColorStop(0, 'rgba(6, 182, 212, 0.45)');
  grad.addColorStop(0.5, 'rgba(16, 185, 129, 0.22)');
  grad.addColorStop(1, 'rgba(15, 23, 42, 0.04)');

  ctx.beginPath();
  ctx.moveTo(ml, mt + chartH);
  for (let i = 0; i < pts.length; i++) {
    ctx.lineTo(getX(pts[i].dist), getY(pts[i].ele));
  }
  ctx.lineTo(ml + chartW, mt + chartH);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Top Stroke Line with Subtle Glow
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) {
    const px = getX(pts[i].dist);
    const py = getY(pts[i].ele);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 2.4;
  ctx.stroke();

  // Peak Point Badge
  const peakPt = pts[maxEleIdx];
  const peakX = getX(peakPt.dist);
  const peakY = getY(peakPt.ele);
  ctx.beginPath();
  ctx.arc(peakX, peakY, 4, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.font = 'bold 9px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillStyle = '#38bdf8';
  ctx.fillText(`⛰️ ${Math.round(maxEle)}m`, peakX, Math.max(10, peakY - 8));

  // If hovering: draw guide line and glowing dot
  if (currentChartHoverPt) {
    const hx = getX(currentChartHoverPt.dist);
    const hy = getY(currentChartHoverPt.ele);

    ctx.save();
    ctx.setLineDash([3, 3]);
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.85)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(hx, mt);
    ctx.lineTo(hx, mt + chartH);
    ctx.stroke();
    ctx.restore();

    ctx.beginPath();
    ctx.arc(hx, hy, 5, 0, Math.PI * 2);
    ctx.fillStyle = '#00f0ff';
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // Attach hover events once
  if (!canvas._hasHoverEvents) {
    canvas._hasHoverEvents = true;

    function handlePointerMove(e) {
      if (currentElevationTracks.length === 0) return;
      const cRect = canvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      const relX = clientX - cRect.left;

      const aItem = currentElevationTracks[activeElevationTrackIndex] || currentElevationTracks[0];
      const curTrack = aItem.track || aItem;
      if (!curTrack || !curTrack.polyline || curTrack.polyline.length < 2) return;

      const trackPts = curTrack.polyline;
      const tDist = trackPts[trackPts.length - 1].dist || 1;
      const clampedX = Math.max(ml, Math.min(ml + chartW, relX));
      const targetDist = ((clampedX - ml) / chartW) * tDist;

      let closest = trackPts[0];
      let minDiff = Infinity;
      for (let i = 0; i < trackPts.length; i++) {
        const diff = Math.abs((trackPts[i].dist || 0) - targetDist);
        if (diff < minDiff) {
          minDiff = diff;
          closest = trackPts[i];
        }
      }

      currentChartHoverPt = closest;
      renderElevationProfile();
      showPulsingHoverMarker(closest.lat, closest.lon);

      const tooltip = document.getElementById('elevation-tooltip');
      if (tooltip) {
        tooltip.classList.remove('hidden');
        const eleEl = document.getElementById('ele-tooltip-ele');
        const distEl = document.getElementById('ele-tooltip-dist');
        if (eleEl) eleEl.textContent = `⛰️ ${Math.round(closest.ele || 0)} m`;
        if (distEl) distEl.textContent = `📏 ${((closest.dist || 0) / 1000).toFixed(2)} km`;

        const tipX = Math.max(10, Math.min(w - 140, relX - 60));
        const tipY = Math.max(5, (clientY - cRect.top) - 35);
        tooltip.style.left = `${tipX}px`;
        tooltip.style.top = `${tipY}px`;
      }
    }

    function handlePointerLeave() {
      currentChartHoverPt = null;
      renderElevationProfile();
      hidePulsingHoverMarker();
      const tooltip = document.getElementById('elevation-tooltip');
      if (tooltip) tooltip.classList.add('hidden');
    }

    canvas.addEventListener('mousemove', handlePointerMove);
    canvas.addEventListener('touchmove', handlePointerMove, { passive: true });
    canvas.addEventListener('mouseleave', handlePointerLeave);
    canvas.addEventListener('touchend', handlePointerLeave);
  }
}

// Generate Markdown for Export
function generateMarkdownForTrip(trip) {
  const lines = [];
  lines.push(`# 🌴 ${trip.title}\n`);
  lines.push(`**Termin**: ${trip.startDate.toLocaleDateString('pl-PL')} – ${trip.endDate.toLocaleDateString('pl-PL')} (${trip.stats.days} dni)`);
  lines.push(`**Podsumowanie**: 🥾 ${trip.stats.walkKm.toFixed(1)} km pieszo | 🚗 ${trip.stats.driveKm.toFixed(0)} km transport | 📍 ${trip.stats.placesCount} miejsc | 📷 ${(trip.photos || []).length} zdjęć\n`);

  // Bookings Section in Markdown
  if (trip.bookings && trip.bookings.length > 0) {
    lines.push(`### 📬 Rezerwacje & Vouchery`);
    trip.bookings.forEach(b => {
      lines.push(`- **${b.icon || '📌'} ${b.title}** (Nr rezerwacji: \`${b.bookingNumber}\`, Koszt: ${b.price || 'Opłacono'})`);
      if (b.pickup) lines.push(`  - Odbiór / Zameldowanie: ${b.pickup || b.address}`);
      if (b.included) lines.push(`  - W cenie: ${b.included}`);
    });
    lines.push('');
  }

  const flights = trip.events.filter(e => e.activityType === 'FLYING');
  if (flights.length > 0) {
    lines.push(`### ✈️ Podróż & Transfer lotniczy`);
    flights.forEach(f => {
      const durMin = f.end ? Math.round((f.end - f.start) / 60000) : 0;
      lines.push(`- **Lot**: ${f.start.toLocaleDateString('pl-PL')} ${f.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})} (czas lotu: ok. ${Math.floor(durMin/60)}h ${durMin%60}m)`);
    });
    lines.push('');
  }

  trip.days.forEach((day, index) => {
    const dayNumber = index + 1;
    const dateObj = new Date(day.date);
    const dateStr = dateObj.toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    const places = day.events.filter(e => e.type === 'place');
    const activities = day.events.filter(e => e.type === 'activity');
    const dayPhotos = (trip.photos || []).filter(p => p.dayNumber === dayNumber);
    const dayBookings = (trip.bookings || []).filter(b => {
      const bDate = b.pickupDate || b.checkInDate || b.departureDate || b.visitDate;
      return bDate && bDate.toISOString().split('T')[0] === day.date;
    });

    let startLocation = places[0] ? places[0].name : 'Początek trasy';
    const firstPlace = places[0];
    const isStartPeak = firstPlace && firstPlace.category === 'peak';

    // End location determination:
    // NEVER pick a peak as the overnight location!
    let endLocation = startLocation;
    if (places.length > 1) {
      const lastPlace = places[places.length - 1];
      const isPeakOrTrail = lastPlace.category === 'peak' || 
                            lastPlace.category === 'attraction' ||
                            /nosal|kasprowy|giewont|rysy|kościelec|świnica|szpiglas|czerwone wierch|pico|arieiro|ruivo|ślęż|szrenic|śnieżk|turnia|wierch|kopa|czub|szczyt|szlak|trail|levada/i.test(lastPlace.name);

      if (isPeakOrTrail) {
        const lodgingPlaces = places.filter(p => 
          p.category === 'lodging' || 
          (p.semanticType && (p.semanticType.toLowerCase().includes('lodging') || p.semanticType.toLowerCase().includes('home'))) ||
          /hotel|hostel|resort|apartament|apartment|pousada|guest house|villa|bnb|schronisko|nocleg|pensjonat|kwatera/i.test(p.name)
        );
        if (lodgingPlaces.length > 0) {
          endLocation = lodgingPlaces[lodgingPlaces.length - 1].name;
        } else {
          endLocation = (!isStartPeak && startLocation) ? startLocation : (trip.destination || 'Baza noclegowa / Hotel');
        }
      } else {
        endLocation = lastPlace.name;
      }
    }

    const peaks = places.filter(p => p.category === 'peak');
    const attractions = places.filter(p => (p.category === 'attraction' || (p.category === 'other' && p !== places[0])) && p.category !== 'peak');
    const food = places.filter(p => p.category === 'food');

    let dayWalkKm = 0;
    const moves = [];
    activities.forEach(a => {
      const distKm = (a.distanceMeters || 0) / 1000;
      const durMin = a.end ? Math.round((a.end - a.start) / 60000) : 0;
      const t = a.activityType || '';

      if (t.includes('WALK') || t.includes('HIKE') || t.includes('FOOT')) {
        dayWalkKm += distKm;
        if (distKm >= 0.8) moves.push(`🥾 Pieszo (${distKm.toFixed(1)} km, ${durMin} min)`);
      } else if (t.includes('VEHICLE') || t.includes('CAR')) {
        if (distKm >= 1.5) moves.push(`🚗 Samochód (${distKm.toFixed(1)} km, ${durMin} min)`);
      } else if (t.includes('TRAIN') || t.includes('SUBWAY')) {
        moves.push(`🚆 Pociąg/Metro (${distKm.toFixed(1)} km, ${durMin} min)`);
      } else if (t.includes('FLYING')) {
        moves.push(`✈️ Lot (${distKm.toFixed(0)} km, ${durMin} min)`);
      }
    });

    lines.push(`## 📅 Dzień ${dayNumber}: ${dateStr}`);
    if (dayBookings.length > 0) {
      dayBookings.forEach(db => {
        lines.push(`- **Rezerwacja dnia**: ${db.icon} ${db.title} (Nr: \`${db.bookingNumber}\`)`);
      });
    }
    lines.push(`- **Start**: ${startLocation}`);
    if (moves.length > 0) {
      lines.push(`- **Dojazdy i trasy**: ${moves.join(', ')}`);
    }
    if (dayWalkKm > 0.4) {
      lines.push(`- **Pieszo łącznie**: ok. ${dayWalkKm.toFixed(1)} km na nogach`);
    }
    if (peaks.length > 0) {
      lines.push(`- **Zdobyte szczyty i punkty widokowe**:`);
      peaks.forEach(pk => lines.push(`  - ⛰️ ${pk.name} (${pk.start ? pk.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'}) : ''})`));
    }
    if (attractions.length > 0) {
      lines.push(`- **Zwiedzanie i punkty**:`);
      attractions.forEach(a => lines.push(`  - 📍 ${a.name} (${a.start ? a.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'}) : ''})`));
    }
    if (food.length > 0) {
      lines.push(`- **Restauracje i gastronomia**:`);
      food.forEach(f => lines.push(`  - 🍴 ${f.name} (${f.start.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})})`));
    }
    if (dayPhotos.length > 0) {
      lines.push(`- **Zdjęcia (${dayPhotos.length})**: ${dayPhotos.map(p => p.matchedPlace || p.name).join(', ')}`);
    }
    lines.push(`- **Powrót do bazy**: ${endLocation}`);
    lines.push('');
  });

  const textarea = document.getElementById('raw-markdown-output');
  if (textarea) textarea.value = lines.join('\n');
}

function loadPreparsedTrips(tripsArray) {
  detectedTrips = tripsArray.map(t => {
    const trip = { ...t };
    trip.startDate = new Date(trip.startDate);
    trip.endDate = new Date(trip.endDate);
    trip.year = trip.startDate.getFullYear();
    trip.stats = trip.stats || {
      days: trip.durationDays || (trip.days ? trip.days.length : 1),
      placesCount: trip.placesCount || 0,
      walkKm: trip.totalKmWalk || 0,
      driveKm: trip.totalKmDrive || 0,
      flightCount: trip.totalKmFlight > 0 ? 1 : 0
    };
    trip.highlights = trip.highlights || [];
    trip.bookings = trip.bookings || [];
    trip.photos = trip.photos || [];

    trip.events = [];
    if (Array.isArray(trip.days)) {
      trip.days.forEach((day, dIdx) => {
        day.events = day.events || [];
        day.events.forEach(ev => {
          ev.start = parseTimestamp(ev.startTime || ev.start);
          ev.end = parseTimestamp(ev.endTime || ev.end);
          trip.events.push(ev);
        });
      });
    }
    return trip;
  });

  attachPreloadedSampleData();
  updateGlobalStats();
  renderYearFilters();
  renderCatalogGrid();
  showCatalogView();

  setTimeout(() => {
    if (catalogMap) {
      catalogMap.invalidateSize();
      renderCatalogMap();
    }
  }, 250);
}

// Load Demo Dataset
async function loadDemoData() {
  if (window.sampleTripsData && Array.isArray(window.sampleTripsData) && window.sampleTripsData.length > 0) {
    loadPreparsedTrips(window.sampleTripsData);
    return;
  }

  try {
    const res = await fetch('sample-trips.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data && data.trips && Array.isArray(data.trips)) {
      loadPreparsedTrips(data.trips);
      return;
    }
    allParsedEvents = [];
    ingestTimelineData(data);
    clusterAndDisplayTrips();
  } catch (err) {
    console.warn('Błąd pobierania sample-trips.json przez fetch, aktywacja wbudowanych danych demo:', err);
    if (window.sampleTripsData) {
      loadPreparsedTrips(window.sampleTripsData);
      return;
    }
    try {
      const res2 = await fetch('sample-madera.json');
      if (res2.ok) {
        const data2 = await res2.json();
        allParsedEvents = [];
        ingestTimelineData(data2);
        clusterAndDisplayTrips();
      }
    } catch (e2) {
      console.warn('Wszystkie metody ładowania danych demo zawiodły:', e2);
    }
  }
}
