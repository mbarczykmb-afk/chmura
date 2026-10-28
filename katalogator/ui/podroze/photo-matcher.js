/**
 * Photo Matcher Module for Google Timeline Travel Summarizer
 * Handles client-side EXIF reading, photo geotagging, time/place matching with Google Timeline,
 * and Leaflet photo marker rendering.
 */

class PhotoMatcher {
  constructor() {
    this.photos = []; // Array of loaded photo objects
    this.initLightbox();
  }

  /**
   * Parse EXIF metadata from ArrayBuffer of JPEG image
   * Extracts DateTimeOriginal, DateTime, GPS Latitude, and GPS Longitude
   */
  parseExif(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    const result = {
      timestamp: null,
      lat: null,
      lon: null,
      hasExif: false,
      hasGps: false
    };

    // Check JPEG SOI (Start of Image) marker: 0xFFD8
    if (view.byteLength < 4 || view.getUint16(0) !== 0xFFD8) {
      return result;
    }

    let offset = 2;
    const length = view.byteLength;

    while (offset < length - 4) {
      const marker = view.getUint16(offset);
      offset += 2;

      // APP1 marker (0xFFE1) contains EXIF
      if (marker === 0xFFE1) {
        const segmentLength = view.getUint16(offset);
        const exifHeaderOffset = offset + 2;

        // Verify "Exif\0\0" header (0x45786966 0x0000)
        if (view.getUint32(exifHeaderOffset) === 0x45786966 && view.getUint16(exifHeaderOffset + 4) === 0x0000) {
          result.hasExif = true;
          this.parseTiffHeader(view, exifHeaderOffset + 6, result);
        }
        break;
      } else if ((marker & 0xFF00) !== 0xFF00) {
        break; // Not a valid marker
      } else {
        // Skip other markers
        const segmentLength = view.getUint16(offset);
        offset += segmentLength;
      }
    }

    return result;
  }

  parseTiffHeader(view, tiffOffset, result) {
    if (tiffOffset + 8 > view.byteLength) return;

    // Byte order: 0x4949 ('II' Little-Endian), 0x4D4D ('MM' Big-Endian)
    const byteOrder = view.getUint16(tiffOffset);
    const littleEndian = byteOrder === 0x4949;

    // 0x002A (42) verification
    if (view.getUint16(tiffOffset + 2, littleEndian) !== 42) return;

    const firstIfdOffset = view.getUint32(tiffOffset + 4, littleEndian);
    if (firstIfdOffset < 8) return;

    const ifdOffset = tiffOffset + firstIfdOffset;
    this.parseIfd(view, tiffOffset, ifdOffset, littleEndian, result);
  }

  parseIfd(view, tiffOffset, ifdOffset, littleEndian, result) {
    if (ifdOffset + 2 > view.byteLength) return;
    const entriesCount = view.getUint16(ifdOffset, littleEndian);
    let exifSubIfdOffset = null;
    let gpsSubIfdOffset = null;

    let offset = ifdOffset + 2;
    for (let i = 0; i < entriesCount; i++) {
      if (offset + 12 > view.byteLength) break;
      const tag = view.getUint16(offset, littleEndian);

      if (tag === 0x0132 && !result.timestamp) { // DateTime
        const valOffset = view.getUint32(offset + 8, littleEndian);
        result.timestamp = this.readExifDateString(view, tiffOffset + valOffset);
      } else if (tag === 0x8769) { // Exif SubIFD Pointer
        exifSubIfdOffset = tiffOffset + view.getUint32(offset + 8, littleEndian);
      } else if (tag === 0x8825) { // GPS SubIFD Pointer
        gpsSubIfdOffset = tiffOffset + view.getUint32(offset + 8, littleEndian);
      }
      offset += 12;
    }

    // Read Exif SubIFD for DateTimeOriginal (Tag 0x9003)
    if (exifSubIfdOffset && exifSubIfdOffset + 2 <= view.byteLength) {
      const subEntriesCount = view.getUint16(exifSubIfdOffset, littleEndian);
      let subOffset = exifSubIfdOffset + 2;
      for (let j = 0; j < subEntriesCount; j++) {
        if (subOffset + 12 > view.byteLength) break;
        const subTag = view.getUint16(subOffset, littleEndian);
        if (subTag === 0x9003 || (subTag === 0x9004 && !result.timestamp)) { // DateTimeOriginal / DateTimeDigitized
          const valOffset = view.getUint32(subOffset + 8, littleEndian);
          const date = this.readExifDateString(view, tiffOffset + valOffset);
          if (date) result.timestamp = date;
        }
        subOffset += 12;
      }
    }

    // Read GPS SubIFD
    if (gpsSubIfdOffset && gpsSubIfdOffset + 2 <= view.byteLength) {
      this.parseGpsIfd(view, tiffOffset, gpsSubIfdOffset, littleEndian, result);
    }
  }

  parseGpsIfd(view, tiffOffset, gpsOffset, littleEndian, result) {
    if (gpsOffset + 2 > view.byteLength) return;
    const entries = view.getUint16(gpsOffset, littleEndian);
    let offset = gpsOffset + 2;

    let latRef = 'N';
    let lonRef = 'E';
    let latCoords = null;
    let lonCoords = null;

    for (let i = 0; i < entries; i++) {
      if (offset + 12 > view.byteLength) break;
      const tag = view.getUint16(offset, littleEndian);

      if (tag === 1) { // GPSLatitudeRef
        latRef = String.fromCharCode(view.getUint8(offset + 8));
      } else if (tag === 2) { // GPSLatitude (3 rationals)
        const valOffset = tiffOffset + view.getUint32(offset + 8, littleEndian);
        latCoords = this.readRationalArray(view, valOffset, 3, littleEndian);
      } else if (tag === 3) { // GPSLongitudeRef
        lonRef = String.fromCharCode(view.getUint8(offset + 8));
      } else if (tag === 4) { // GPSLongitude (3 rationals)
        const valOffset = tiffOffset + view.getUint32(offset + 8, littleEndian);
        lonCoords = this.readRationalArray(view, valOffset, 3, littleEndian);
      }
      offset += 12;
    }

    if (latCoords && lonCoords) {
      let lat = latCoords[0] + latCoords[1] / 60 + latCoords[2] / 3600;
      let lon = lonCoords[0] + lonCoords[1] / 60 + lonCoords[2] / 3600;
      if (latRef === 'S') lat = -lat;
      if (lonRef === 'W') lon = -lon;

      result.lat = lat;
      result.lon = lon;
      result.hasGps = true;
    }
  }

  readRationalArray(view, offset, count, littleEndian) {
    const rationals = [];
    for (let i = 0; i < count; i++) {
      const pos = offset + (i * 8);
      if (pos + 8 > view.byteLength) return null;
      const num = view.getUint32(pos, littleEndian);
      const den = view.getUint32(pos + 4, littleEndian);
      rationals.push(den === 0 ? 0 : num / den);
    }
    return rationals;
  }

  readExifDateString(view, offset) {
    try {
      let str = '';
      for (let i = 0; i < 19; i++) {
        if (offset + i >= view.byteLength) break;
        const char = String.fromCharCode(view.getUint8(offset + i));
        str += char;
      }
      // EXIF date format: "YYYY:MM:DD HH:MM:SS"
      const match = str.match(/^(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/);
      if (match) {
        return new Date(
          parseInt(match[1], 10),
          parseInt(match[2], 10) - 1,
          parseInt(match[3], 10),
          parseInt(match[4], 10),
          parseInt(match[5], 10),
          parseInt(match[6], 10)
        );
      }
    } catch (e) {
      console.warn('Error reading EXIF date:', e);
    }
    return null;
  }

  /**
   * Process uploaded/dropped file(s)
   */
  async processFiles(files, trip) {
    const newPhotos = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file.type.startsWith('image/')) continue;

      const arrayBuffer = await file.arrayBuffer();
      const exif = this.parseExif(arrayBuffer);

      // Fallback timestamp: file modification date
      const timestamp = exif.timestamp || new Date(file.lastModified);

      // Create data URL for preview
      const previewUrl = await this.readFileAsDataURL(file);

      const photoObj = {
        id: 'photo_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
        name: file.name,
        size: file.size,
        timestamp,
        hasOriginalGps: exif.hasGps,
        lat: exif.lat,
        lon: exif.lon,
        url: previewUrl,
        matchedPlace: null,
        matchedCategory: null,
        matchConfidence: 'none',
        geotagSource: exif.hasGps ? 'exif_camera' : 'none',
        dayNumber: null
      };

      if (trip) {
        this.matchPhotoToTrip(photoObj, trip);
      }

      newPhotos.push(photoObj);
      this.photos.push(photoObj);
    }

    return newPhotos;
  }

  readFileAsDataURL(file) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.readAsDataURL(file);
    });
  }

  /**
   * Core Matching Algorithm:
   * 1. Matches photo to Day by date.
   * 2. Checks if photo was taken during a visited Place (placeVisit duration).
   *    If so, directly attaches to attraction/restaurant with its GPS!
   * 3. Checks if photo was taken during an Activity/Transit (activitySegment duration).
   *    If so, linearly interpolates GPS position between start & end locations!
   * 4. If closest in time to a place on that day, assigns nearest coordinates.
   */
  matchPhotoToTrip(photo, trip) {
    if (!photo.timestamp || !trip || !trip.days) return;

    const photoTime = photo.timestamp.getTime();
    const photoDateStr = photo.timestamp.toISOString().split('T')[0];

    // Find day index
    let matchedDayIndex = trip.days.findIndex(d => d.date === photoDateStr);

    // If day didn't match strictly by UTC date, check local date and closest event
    if (matchedDayIndex === -1) {
      // Find closest event across whole trip
      let minDiff = Infinity;
      trip.days.forEach((day, dIdx) => {
        day.events.forEach(ev => {
          if (ev.start) {
            const diff = Math.abs(photoTime - ev.start.getTime());
            if (diff < minDiff && diff < 24 * 3600 * 1000) {
              minDiff = diff;
              matchedDayIndex = dIdx;
            }
          }
        });
      });
    }

    if (matchedDayIndex === -1) {
      return; // Photo is outside trip bounds
    }

    const day = trip.days[matchedDayIndex];
    photo.dayNumber = matchedDayIndex + 1;

    // Check Place visits
    const places = day.events.filter(e => e.type === 'place');
    for (const p of places) {
      const startT = p.start ? p.start.getTime() : 0;
      const endT = p.end ? p.end.getTime() : startT + 3600000;

      // Add a generous 10-minute padding around place visits
      if (photoTime >= (startT - 10 * 60000) && photoTime <= (endT + 10 * 60000)) {
        photo.matchedPlace = p.name;
        photo.matchedCategory = p.category;
        photo.matchConfidence = 'exact_place';

        if (!photo.hasOriginalGps && p.lat && p.lon) {
          photo.lat = p.lat;
          photo.lon = p.lon;
          photo.geotagSource = 'timeline_place';
        }

        // Attach photo reference to place
        p.photos = p.photos || [];
        if (!p.photos.some(existing => existing.id === photo.id)) {
          p.photos.push(photo);
        }
        return;
      }
    }

    // Check Activity segments
    const activities = day.events.filter(e => e.type === 'activity');
    for (const a of activities) {
      const startT = a.start ? a.start.getTime() : 0;
      const endT = a.end ? a.end.getTime() : startT + 1800000;

      if (photoTime >= startT && photoTime <= endT) {
        const typeName = (a.activityType || 'Trasa').replace('IN_', '').replace('_', ' ');
        photo.matchedPlace = `W trasie (${typeName})`;
        photo.matchedCategory = 'transit';
        photo.matchConfidence = 'in_transit';

        if (!photo.hasOriginalGps && a.startLat && a.endLat) {
          const totalDur = endT - startT;
          const ratio = totalDur > 0 ? (photoTime - startT) / totalDur : 0.5;
          photo.lat = a.startLat + (a.endLat - a.startLat) * ratio;
          photo.lon = a.startLon + (a.endLon - a.startLon) * ratio;
          photo.geotagSource = 'timeline_interpolated';
        } else if (!photo.hasOriginalGps && a.startLat) {
          photo.lat = a.startLat;
          photo.lon = a.startLon;
          photo.geotagSource = 'timeline_transit_start';
        }
        return;
      }
    }

    // Proximity fallback: match to nearest place on this day
    if (places.length > 0) {
      let nearestPlace = places[0];
      let minDiff = Math.abs(photoTime - (places[0].start?.getTime() || 0));

      for (let i = 1; i < places.length; i++) {
        const diff = Math.abs(photoTime - (places[i].start?.getTime() || 0));
        if (diff < minDiff) {
          minDiff = diff;
          nearestPlace = places[i];
        }
      }

      photo.matchedPlace = nearestPlace.name;
      photo.matchedCategory = nearestPlace.category;
      photo.matchConfidence = 'proximity';

      if (!photo.hasOriginalGps && nearestPlace.lat && nearestPlace.lon) {
        photo.lat = nearestPlace.lat;
        photo.lon = nearestPlace.lon;
        photo.geotagSource = 'timeline_nearest';
      }

      nearestPlace.photos = nearestPlace.photos || [];
      if (!nearestPlace.photos.some(existing => existing.id === photo.id)) {
        nearestPlace.photos.push(photo);
      }
    }
  }

  /**
   * Render photo pins on Leaflet map with smart spatial clustering
   */
  renderMapPhotoPins(map, photos, currentDayFilter = 'all') {
    const photoMarkers = [];
    const filteredPhotos = currentDayFilter === 'all'
      ? photos
      : photos.filter(p => p.dayNumber === parseInt(currentDayFilter, 10));

    // Spatial clustering: avoid rendering hundreds of overlapping markers on the same spot (~150m grid)
    const clusterMap = new Map();
    filteredPhotos.forEach(p => {
      if (!p.lat || !p.lon) return;
      const key = `${Math.round(p.lat * 400) / 400},${Math.round(p.lon * 400) / 400}`;
      if (!clusterMap.has(key)) {
        clusterMap.set(key, []);
      }
      clusterMap.get(key).push(p);
    });

    clusterMap.forEach((clusterPhotos) => {
      const rep = clusterPhotos[0];
      const count = clusterPhotos.length;
      const isMulti = count > 1;
      const thumbUrl = rep.thumbnailUrl || rep.url;

      const iconHtml = `
        <div class="relative group cursor-pointer transition transform hover:scale-125" style="width:42px; height:42px;">
          <div class="w-10 h-10 rounded-full border-2 border-white shadow-xl overflow-hidden bg-slate-800 ring-2 ring-emerald-500">
            <img src="${thumbUrl}" alt="${rep.name || rep.filename}" class="w-full h-full object-cover" loading="lazy" />
          </div>
          ${isMulti 
            ? `<span class="absolute -top-1 -right-1 bg-amber-500 text-slate-950 font-bold rounded-full px-1.5 py-0.2 text-3xs shadow-md border border-white">+${count}</span>` 
            : `<span class="absolute -bottom-1 -right-1 bg-emerald-600 text-white rounded-full p-0.5 text-2xs shadow">📷</span>`}
        </div>
      `;

      const customIcon = L.divIcon({
        className: 'photo-leaflet-marker',
        html: iconHtml,
        iconSize: [42, 42],
        iconAnchor: [21, 21],
        popupAnchor: [0, -22]
      });

      const marker = L.marker([rep.lat, rep.lon], { icon: customIcon }).addTo(map);

      const ts = rep.timestamp instanceof Date ? rep.timestamp : new Date(rep.timestamp);
      const timeStr = !isNaN(ts.getTime()) ? ts.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '';
      const dateStr = !isNaN(ts.getTime()) ? ts.toLocaleDateString('pl-PL') : '';

      const badgeText = rep.hasGps ? '🛰️ Oryginalny GPS ze zdjęcia' : '🗺️ Dopasowano z Osi Czasu';

      const popupHtml = `
        <div style="width:230px; font-family:sans-serif;" class="text-slate-800">
          <div style="height:140px; border-radius:8px; overflow:hidden; margin-bottom:8px;" class="bg-slate-100 shadow-inner">
            <img src="${rep.thumbnailUrl || rep.url}" alt="${rep.name || rep.filename}" style="width:100%; height:100%; object-fit:cover; cursor:pointer;" onclick="window.photoMatcher.openLightbox('${rep.id}')" />
          </div>
          <div class="text-xs font-bold text-slate-900 leading-tight mb-1">${rep.matchedPlace || rep.filename}</div>
          <div class="text-2xs text-slate-500 flex items-center justify-between mb-1.5">
            <span>📅 ${dateStr} ${timeStr}</span>
            <span class="font-semibold text-emerald-700">Dzień ${rep.dayNumber || '-'}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-3xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-1.5 py-0.5 inline-block">
              ${badgeText}
            </span>
            ${isMulti ? `<span class="text-2xs font-bold text-amber-700">Łącznie ${count} zdjęć w tym punkcie</span>` : ''}
          </div>
        </div>
      `;

      marker.bindPopup(popupHtml);
      photoMarkers.push(marker);
    });

    return photoMarkers;
  }

  /**
   * Setup world-class image lightbox viewer with keyboard navigation,
   * thumbnail strip, fullscreen mode, GPS map centering, and touch swipe.
   */
  initLightbox() {
    if (typeof document === 'undefined') return;
    this.currentLightboxIndex = -1;

    // Attach listeners if modal already exists in DOM or create it
    if (!document.getElementById('photo-lightbox-modal')) {
      const modalHtml = `
        <div id="photo-lightbox-modal" class="fixed inset-0 z-50 bg-slate-950/95 backdrop-blur-xl hidden flex flex-col items-center justify-between p-3 sm:p-6 select-none transition-all duration-300">
          <!-- Top Action / Status Bar -->
          <div class="w-full max-w-6xl flex items-center justify-between px-2 py-1.5 z-50">
            <div class="flex items-center gap-2.5">
              <span class="text-xl">📸</span>
              <span id="lightbox-counter" class="text-xs font-bold text-slate-200 bg-slate-900/90 backdrop-blur-md px-3 py-1 rounded-full border border-slate-700/80 shadow-md">1 / 1</span>
            </div>
            <div class="flex items-center gap-2">
              <button id="lightbox-btn-locate" class="px-3.5 py-1.5 bg-cyan-600/90 hover:bg-cyan-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-cyan-500/20 transition flex items-center gap-1.5 border border-cyan-400/40 active:scale-95" title="Namierz na mapie i wycentruj">
                <span>📍</span> <span>Namierz na mapie</span>
              </button>
              <button id="btn-lightbox-fullscreen" class="p-2 bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl border border-slate-700 transition" title="Pełny ekran (F)">
                <span class="text-sm">⛶</span>
              </button>
              <button id="btn-close-lightbox" class="p-2 bg-rose-900/70 hover:bg-rose-600 text-white rounded-xl border border-rose-500/40 transition" title="Zamknij (Esc)">
                <span class="text-sm font-bold px-1">&times;</span>
              </button>
            </div>
          </div>
          
          <!-- Main Image Display with Left / Right Floating Navigation Arrows -->
          <div class="relative w-full max-w-6xl flex-1 flex items-center justify-center min-h-[50vh] max-h-[72vh] overflow-hidden my-2">
            <button id="lightbox-prev" class="absolute left-2 sm:left-4 text-white text-2xl hover:text-cyan-300 z-50 transition p-3 bg-slate-950/80 hover:bg-slate-900 rounded-full w-12 h-12 flex items-center justify-center border border-slate-700 shadow-2xl backdrop-blur-md active:scale-95" title="Poprzednie zdjęcie (Strzałka w lewo)">
              <span>&larr;</span>
            </button>
            <button id="lightbox-next" class="absolute right-2 sm:right-4 text-white text-2xl hover:text-cyan-300 z-50 transition p-3 bg-slate-950/80 hover:bg-slate-900 rounded-full w-12 h-12 flex items-center justify-center border border-slate-700 shadow-2xl backdrop-blur-md active:scale-95" title="Następne zdjęcie (Strzałka w prawo)">
              <span>&rarr;</span>
            </button>

            <img id="lightbox-img" src="" alt="Podgląd zdjęcia" class="max-w-full max-h-[70vh] object-contain rounded-2xl shadow-2xl transition-all duration-300 ring-1 ring-slate-700/60" />
          </div>

          <!-- Bottom Meta Overlay & Thumbnail Strip -->
          <div class="w-full max-w-6xl flex flex-col gap-2.5 z-50">
            <div class="w-full px-4 py-3 bg-slate-900/90 backdrop-blur-xl rounded-2xl text-white flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border border-slate-700/80 shadow-2xl">
              <div class="min-w-0 flex-1 space-y-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <h4 id="lightbox-title" class="text-sm sm:text-base font-bold text-cyan-300 truncate">Tytuł zdjęcia</h4>
                  <span id="lightbox-location" class="chip-place chip-viewpoint text-3xs py-0.5 px-2.5">
                    📍 Lokalizacja GPS
                  </span>
                </div>
                <p id="lightbox-meta" class="text-2xs sm:text-xs text-slate-400 truncate">Metadane pliku, data i czas wykonania</p>
              </div>
              <div id="lightbox-badges" class="flex flex-wrap items-center gap-1.5 text-2xs shrink-0">
                <!-- dynamic badges -->
              </div>
            </div>

            <!-- Bottom Thumbnails Strip -->
            <div id="lightbox-thumbs-strip" class="flex gap-2 overflow-x-auto py-1 px-1 custom-scroll items-center max-h-[64px]">
              <!-- dynamic thumbnails -->
            </div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    this.attachLightboxListeners();
  }

  attachLightboxListeners() {
    const modal = document.getElementById('photo-lightbox-modal');
    if (!modal || modal.dataset.listenersBound) return;
    modal.dataset.listenersBound = 'true';

    const closeBtn = document.getElementById('btn-close-lightbox');
    if (closeBtn) closeBtn.addEventListener('click', () => this.closeLightbox());

    const prevBtn = document.getElementById('lightbox-prev') || document.getElementById('btn-prev-lightbox');
    if (prevBtn) prevBtn.addEventListener('click', (e) => { e.stopPropagation(); this.prevLightbox(); });

    const nextBtn = document.getElementById('lightbox-next') || document.getElementById('btn-next-lightbox');
    if (nextBtn) nextBtn.addEventListener('click', (e) => { e.stopPropagation(); this.nextLightbox(); });

    const mapBtn = document.getElementById('lightbox-btn-locate') || document.getElementById('btn-lightbox-map');
    if (mapBtn) {
      mapBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.centerCurrentPhotoOnMap();
      });
    }

    const fsBtn = document.getElementById('btn-lightbox-fullscreen');
    if (fsBtn) {
      fsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleFullscreen();
      });
    }

    modal.addEventListener('click', (e) => {
      if (e.target.id === 'photo-lightbox-modal') {
        this.closeLightbox();
      }
    });

    // Keyboard controls
    document.addEventListener('keydown', (e) => {
      if (!modal || modal.classList.contains('hidden')) return;
      if (e.key === 'Escape') this.closeLightbox();
      else if (e.key === 'ArrowLeft') this.prevLightbox();
      else if (e.key === 'ArrowRight') this.nextLightbox();
      else if (e.key === 'f' || e.key === 'F') this.toggleFullscreen();
      else if (e.key === 'm' || e.key === 'M') this.centerCurrentPhotoOnMap();
    });

    // Mobile touch gestures (Swipe Left / Swipe Right)
    let touchStartX = 0;
    let touchEndX = 0;
    modal.addEventListener('touchstart', (e) => {
      touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    modal.addEventListener('touchend', (e) => {
      touchEndX = e.changedTouches[0].screenX;
      const diffX = touchEndX - touchStartX;
      if (Math.abs(diffX) > 40) {
        if (diffX > 0) this.prevLightbox(); // Swipe right -> prev
        else this.nextLightbox(); // Swipe left -> next
      }
    }, { passive: true });
  }

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    }
  }

  centerCurrentPhotoOnMap() {
    if (this.currentLightboxIndex < 0 || !this.photos[this.currentLightboxIndex]) return;
    const photo = this.photos[this.currentLightboxIndex];
    if (!photo.lat || !photo.lon) {
      alert('To zdjęcie nie ma zapisanych współrzędnych GPS.');
      return;
    }

    this.closeLightbox();

    if (window.map) {
      window.map.flyTo([photo.lat, photo.lon], 16, { duration: 1.2 });
      // If photo has a marker, open its popup
      if (Array.isArray(window.mapPhotoMarkers)) {
        const marker = window.mapPhotoMarkers.find(m => {
          const mLatLng = m.getLatLng();
          return Math.abs(mLatLng.lat - photo.lat) < 0.0001 && Math.abs(mLatLng.lng - photo.lon) < 0.0001;
        });
        if (marker) {
          setTimeout(() => marker.openPopup(), 1200);
        }
      }
      // Scroll smoothly to map element
      const mapEl = document.getElementById('travel-map') || document.getElementById('map');
      if (mapEl) {
        mapEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }

  closeLightbox() {
    const modal = document.getElementById('photo-lightbox-modal');
    if (modal) modal.classList.add('hidden');
  }

  openLightbox(photoId) {
    const idx = this.photos.findIndex(p => p.id === photoId);
    if (idx !== -1) {
      this.openLightboxByIndex(idx);
    }
  }

  openLightboxByIndex(index) {
    if (!this.photos || this.photos.length === 0) return;
    if (index < 0) index = this.photos.length - 1;
    if (index >= this.photos.length) index = 0;

    this.currentLightboxIndex = index;
    const photo = this.photos[index];

    const modal = document.getElementById('photo-lightbox-modal');
    const img = document.getElementById('lightbox-img');
    const title = document.getElementById('lightbox-title');
    const counter = document.getElementById('lightbox-counter');
    const meta = document.getElementById('lightbox-meta');
    const badges = document.getElementById('lightbox-badges');
    const thumbsStrip = document.getElementById('lightbox-thumbs-strip');

    // Load full-res URL, with thumbnail fallback while loading
    img.src = photo.url || photo.thumbnailUrl;
    img.onerror = () => {
      // Fallback SVG indicating drive U status
      img.src = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400" viewBox="0 0 600 400"><rect width="100%" height="100%" fill="%230f172a"/><text x="50%" y="45%" fill="%2300f0ff" font-size="40" text-anchor="middle">📷</text><text x="50%" y="60%" fill="%23f8fafc" font-size="16" font-family="sans-serif" font-weight="bold" text-anchor="middle">${encodeURIComponent(photo.filename || photo.name)}</text><text x="50%" y="70%" fill="%2394a3b8" font-size="13" font-family="sans-serif" text-anchor="middle">Brak pliku (podłącz dysk ze zdjęciami)</text></svg>`;
    };

    title.textContent = photo.matchedPlace || photo.name || photo.filename;
    if (counter) counter.textContent = `${index + 1} z ${this.photos.length}`;

    const ts = photo.timestamp instanceof Date ? photo.timestamp : new Date(photo.timestamp);
    const dateStr = !isNaN(ts.getTime())
      ? ts.toLocaleString('pl-PL', { dateStyle: 'long', timeStyle: 'short' })
      : 'Brak daty';

    const coordsStr = (photo.lat && photo.lon)
      ? `${photo.lat.toFixed(5)}, ${photo.lon.toFixed(5)}`
      : 'Brak GPS';

    const fname = photo.filename || photo.name || '';
    meta.textContent = `${dateStr} • Współrzędne GPS: ${coordsStr} • Plik: ${fname}`;

    const locChip = document.getElementById('lightbox-location');
    if (locChip) {
      if (photo.matchedPlace) {
        locChip.innerHTML = `📍 <span>${photo.matchedPlace}</span>`;
        locChip.style.display = 'inline-flex';
      } else if (photo.lat && photo.lon) {
        locChip.innerHTML = `📍 <span>${photo.lat.toFixed(4)}, ${photo.lon.toFixed(4)}</span>`;
        locChip.style.display = 'inline-flex';
      } else {
        locChip.innerHTML = `📍 <span>Współrzędne GPS</span>`;
        locChip.style.display = 'inline-flex';
      }
    }

    badges.innerHTML = `
      <span class="px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold">
        Dzień ${photo.dayNumber || '?'}
      </span>
      <span class="px-2.5 py-0.5 rounded-full ${photo.hasGps ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-800 text-slate-400 border border-slate-700'}">
        ${photo.hasGps || photo.geotagSource === 'exif_camera' ? '🛰️ Oryginalny GPS aparatu' : '🗺️ Dopasowano z Osi Czasu'}
      </span>
    `;

    // Render thumbnail strip (±8 adjacent photos for smooth navigation)
    if (thumbsStrip) {
      const windowSize = 8;
      const startIdx = Math.max(0, index - windowSize);
      const endIdx = Math.min(this.photos.length, index + windowSize + 1);
      const slice = this.photos.slice(startIdx, endIdx);

      thumbsStrip.innerHTML = slice.map((tp, sOffset) => {
        const actualIdx = startIdx + sOffset;
        const isActive = actualIdx === index;
        return `
          <button data-idx="${actualIdx}" class="lightbox-thumb-btn shrink-0 w-12 h-12 rounded-lg overflow-hidden border-2 transition transform hover:scale-105 ${isActive ? 'border-cyan-400 ring-2 ring-cyan-400 shadow-[0_0_10px_rgba(0,240,255,0.6)]' : 'border-slate-700 opacity-60 hover:opacity-100'} bg-slate-900">
            <img src="${tp.url || tp.thumbnailUrl}" alt="" class="w-full h-full object-cover" loading="lazy" />
          </button>
        `;
      }).join('');

      thumbsStrip.querySelectorAll('.lightbox-thumb-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const targetIdx = parseInt(btn.getAttribute('data-idx'), 10);
          this.openLightboxByIndex(targetIdx);
        });
      });
    }

    modal.classList.remove('hidden');
  }

  prevLightbox() {
    if (this.currentLightboxIndex > -1) {
      this.openLightboxByIndex(this.currentLightboxIndex - 1);
    }
  }

  nextLightbox() {
    if (this.currentLightboxIndex > -1) {
      this.openLightboxByIndex(this.currentLightboxIndex + 1);
    }
  }
}

// Global instance
if (typeof window !== 'undefined') {
  window.photoMatcher = new PhotoMatcher();
} else if (typeof global !== 'undefined') {
  global.photoMatcher = new PhotoMatcher();
}

