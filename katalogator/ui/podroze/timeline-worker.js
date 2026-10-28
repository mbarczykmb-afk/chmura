/**
 * Google Timeline Travels - High-Performance Web Worker
 * Parses 50-100+ MB JSON exports (65,000+ semanticSegments) in milliseconds without freezing UI.
 */

// Haversine distance in km
function haversine(c1, c2) {
  const R = 6371;
  const dLat = (c2[0] - c1[0]) * Math.PI / 180;
  const dLon = (c2[1] - c1[1]) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(c1[0] * Math.PI / 180) * Math.cos(c2[0] * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// Coordinate parsing helper (handles °, geo:, latLng, objects)
function parseCoords(val) {
  if (!val) return null;
  if (typeof val === 'object') {
    if (val.latLng) return parseCoords(val.latLng);
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

// Rich Geographic Gazetteer for naming regions
const REGION_RULES = [
  { name: 'Madera (Portugalia)', test: (lat, lon) => lat >= 32.5 && lat <= 33.2 && lon >= -17.5 && lon <= -16.2, icon: '🌴' },
  { name: 'Maroko', test: (lat, lon) => lat >= 28.0 && lat <= 36.0 && lon >= -10.5 && lon <= -1.0, icon: '🐪' },
  { name: 'Paryż i Francja', test: (lat, lon) => lat >= 48.0 && lat <= 49.5 && lon >= 1.8 && lon <= 3.2, icon: '🗼' },
  { name: 'Alpy i Jezioro Genewskie', test: (lat, lon) => lat >= 45.5 && lat <= 47.0 && lon >= 5.5 && lon <= 7.2, icon: '🏔️' },
  { name: 'Amsterdam (Holandia)', test: (lat, lon) => lat >= 52.0 && lat <= 53.0 && lon >= 4.5 && lon <= 5.5, icon: '🚲' },
  { name: 'Bułgaria (Morze Czarne)', test: (lat, lon) => lat >= 41.5 && lat <= 44.5 && lon >= 26.5 && lon <= 29.0, icon: '🏖️' },
  { name: 'Rzym i Watykan', test: (lat, lon) => lat >= 41.5 && lat <= 42.2 && lon >= 12.0 && lon <= 13.0, icon: '🏛️' },
  { name: 'Wyspy Kanaryjskie', test: (lat, lon) => lat >= 27.5 && lat <= 29.5 && lon >= -18.5 && lon <= -13.0, icon: '🌋' },
  { name: 'Grecja', test: (lat, lon) => lat >= 35.0 && lat <= 41.5 && lon >= 19.0 && lon <= 28.0, icon: '🏛️' },
  { name: 'Tatry i Zakopane', test: (lat, lon) => lat >= 49.1 && lat <= 49.4 && lon >= 19.8 && lon <= 20.3, icon: '⛰️' },
  { name: 'Bieszczady', test: (lat, lon) => lat >= 49.0 && lat <= 49.5 && lon >= 22.0 && lon <= 23.0, icon: '🌲' },
  { name: 'Bałtyk i Trójmiasto', test: (lat, lon) => lat >= 54.2 && lat <= 54.8 && lon >= 18.3 && lon <= 19.0, icon: '🌊' }
];

// Offline POI Gazetteer for resolving friendly names from coordinates
const POI_GAZETTEER = [
  // Madera
  { name: 'Lotnisko Madera Cristiano Ronaldo (FNC)', category: 'airport', lat: 32.6975, lon: -16.7741, radiusKm: 2.0 },
  { name: 'Ponta do Sol (Baza noclegowa & Plaża)', category: 'lodging', lat: 32.7524, lon: -17.2165, radiusKm: 1.5 },
  { name: 'Cascata dos Anjos (Wodospad na drodze)', category: 'attraction', lat: 32.7545, lon: -17.2100, radiusKm: 1.0 },
  { name: 'Plaża i Baseny Seixal (Czarne Piaski)', category: 'attraction', lat: 32.8662, lon: -17.1669, radiusKm: 1.5 },
  { name: 'Miradouro do Véu da Noiva', category: 'attraction', lat: 32.8512, lon: -17.1666, radiusKm: 1.0 },
  { name: 'Naturalne baseny wulkaniczne Porto Moniz', category: 'attraction', lat: 32.8675, lon: -17.1676, radiusKm: 1.5 },
  { name: 'Ribeira da Janela (Skalne Iglice)', category: 'attraction', lat: 32.8554, lon: -17.1530, radiusKm: 1.2 },
  { name: 'Las Fanal (Laurissilva & Prastare Drzewa Til)', category: 'attraction', lat: 32.8135, lon: -17.2463, radiusKm: 2.0 },
  { name: 'Przełęcz Encumeada & Płaskowyż Paul da Serra', category: 'attraction', lat: 32.8083, lon: -17.0494, radiusKm: 2.5 },
  { name: 'Bica da Cana (Punkt Widokowy 1560m)', category: 'attraction', lat: 32.7792, lon: -17.0496, radiusKm: 2.0 },
  { name: 'Miradouro Lombo do Mouro', category: 'attraction', lat: 32.7902, lon: -17.0358, radiusKm: 1.5 },
  { name: 'São Vicente & Jaskinie Wulkaniczne', category: 'attraction', lat: 32.8273, lon: -17.1110, radiusKm: 1.5 },
  { name: 'Arco da Calheta', category: 'lodging', lat: 32.7574, lon: -17.2301, radiusKm: 1.5 },
  { name: 'Calheta Marina & Piaszczysta Plaża', category: 'attraction', lat: 32.7200, lon: -17.1750, radiusKm: 1.5 },
  { name: 'Funchal Marina & Promenada Nadmorska', category: 'attraction', lat: 32.6477, lon: -16.8242, radiusKm: 2.0 },
  { name: 'Mercado dos Lavradores & Stare Miasto Funchal', category: 'attraction', lat: 32.6467, lon: -16.8255, radiusKm: 1.5 },
  { name: 'Pico do Arieiro (1818 m)', category: 'attraction', lat: 32.7355, lon: -16.9288, radiusKm: 2.0 },
  { name: 'Pico Ruivo (1862 m)', category: 'attraction', lat: 32.7592, lon: -16.9431, radiusKm: 2.0 },
  { name: 'Cabo Girão Skywalk (Klif 580 m)', category: 'attraction', lat: 32.6508, lon: -17.0042, radiusKm: 1.5 },
  { name: 'Ponta de São Lourenço (Półwysep św. Wawrzyńca)', category: 'attraction', lat: 32.7431, lon: -16.7011, radiusKm: 2.5 },

  // Polska / Lotniska
  { name: 'Międzynarodowy Port Lotniczy Katowice-Pyrzowice (KTW)', category: 'airport', lat: 50.4753, lon: 19.0812, radiusKm: 3.0 },
  { name: 'Kraków Airport im. Jana Pawła II (KRK)', category: 'airport', lat: 50.0777, lon: 19.7848, radiusKm: 3.0 },
  { name: 'Lotnisko Chopina w Warszawie (WAW)', category: 'airport', lat: 52.1657, lon: 20.9671, radiusKm: 3.0 },

  // Tatry
  { name: 'Zakopane Krupówki (Centrum)', category: 'attraction', lat: 49.2950, lon: 19.9520, radiusKm: 2.0 },
  { name: 'Kolej Linowa Kasprowy Wierch (Kuźnice)', category: 'attraction', lat: 49.2694, lon: 19.9810, radiusKm: 1.5 },
  { name: 'Morskie Oko (Schronisko)', category: 'attraction', lat: 49.2014, lon: 20.0712, radiusKm: 1.5 },
  { name: 'Dolina Kościeliska', category: 'attraction', lat: 49.2570, lon: 19.8680, radiusKm: 2.0 },

  // Maroko
  { name: 'Marrakesz: Plac Dżamaa al-Fna & Suk', category: 'attraction', lat: 31.6258, lon: -7.9891, radiusKm: 2.5 },
  { name: 'Agadir Marina & Plaża', category: 'attraction', lat: 30.4278, lon: -9.6108, radiusKm: 3.0 },
  { name: 'Taghazout (Wioska Surferska)', category: 'attraction', lat: 30.5433, lon: -9.7083, radiusKm: 2.5 }
];

function resolvePoiName(lat, lon, fallbackName) {
  for (const poi of POI_GAZETTEER) {
    if (haversine([lat, lon], [poi.lat, poi.lon]) <= poi.radiusKm) {
      return { name: poi.name, category: poi.category };
    }
  }
  return {
    name: fallbackName && fallbackName !== 'UNKNOWN' ? fallbackName : `Punkt trasy (${lat.toFixed(3)}, ${lon.toFixed(3)})`,
    category: 'other'
  };
}

self.onmessage = function(e) {
  const { data, rawText } = e.data;

  try {
    self.postMessage({ type: 'progress', percent: 10, message: 'Parsowanie JSON...' });

    let parsed = data;
    if (!parsed && rawText) {
      parsed = JSON.parse(rawText);
    }

    self.postMessage({ type: 'progress', percent: 30, message: 'Analiza struktury segmentów...' });

    let rawSegments = [];
    if (Array.isArray(parsed)) {
      rawSegments = parsed;
    } else if (parsed && typeof parsed === 'object') {
      if (Array.isArray(parsed.semanticSegments)) rawSegments = parsed.semanticSegments;
      else if (Array.isArray(parsed.timelineObjects)) rawSegments = parsed.timelineObjects;
    }

    const totalSegs = rawSegments.length;
    self.postMessage({ type: 'progress', percent: 45, message: `Wykrywanie bazy domowej z ${totalSegs.toLocaleString('pl-PL')} zdarzeń...` });

    // 1. Detect Home Base from frequent grid buckets
    const gridBuckets = {};
    const sampleLimit = Math.min(totalSegs, 15000);
    const step = Math.max(1, Math.floor(totalSegs / sampleLimit));

    for (let i = 0; i < totalSegs; i += step) {
      const seg = rawSegments[i];
      let coords = null;
      if (seg.visit?.topCandidate?.placeLocation) coords = parseCoords(seg.visit.topCandidate.placeLocation);
      else if (seg.placeVisit?.location) coords = parseCoords(seg.placeVisit.location);
      else if (seg.activity?.start) coords = parseCoords(seg.activity.start);

      if (coords) {
        const key = `${Math.round(coords[0] * 20) / 20},${Math.round(coords[1] * 20) / 20}`;
        gridBuckets[key] = (gridBuckets[key] || 0) + 1;
      }
    }

    let homeCoords = [50.28, 19.56]; // fallback Olkusz/Katowice
    let maxBucketCount = 0;
    for (const [k, count] of Object.entries(gridBuckets)) {
      if (count > maxBucketCount) {
        maxBucketCount = count;
        homeCoords = k.split(',').map(Number);
      }
    }

    function checkRegion(lat, lon) {
      for (const r of REGION_RULES) {
        if (r.test(lat, lon)) return r;
      }
      const dist = haversine(homeCoords, [lat, lon]);
      if (dist > 120) {
        return { name: `Wyjazd (${Math.round(dist)} km od domu)`, icon: '🚗' };
      }
      return null;
    }

    self.postMessage({ type: 'progress', percent: 60, message: 'Ekstrakcja podróży i ścieżek GPS...' });

    // 2. Extract and filter travel events
    const travelEvents = [];

    rawSegments.forEach((seg, idx) => {
      let coords = null;
      let type = 'UNKNOWN';
      let actType = 'UNKNOWN';
      let distanceMeters = 0;
      let start = null;
      let end = null;
      let rawName = '';

      // Android visit
      if (seg.visit) {
        const cand = seg.visit.topCandidate || {};
        coords = parseCoords(cand.placeLocation || cand.location);
        type = 'place';
        rawName = cand.placeId || cand.name || '';
        start = seg.startTime;
        end = seg.endTime;
      }
      // Classic Takeout placeVisit
      else if (seg.placeVisit) {
        const loc = seg.placeVisit.location || {};
        coords = parseCoords(loc);
        type = 'place';
        rawName = loc.name || loc.address || '';
        start = seg.placeVisit.duration?.startTimestamp;
        end = seg.placeVisit.duration?.endTimestamp;
      }
      // Android activity
      else if (seg.activity) {
        const a = seg.activity;
        coords = parseCoords(a.start) || parseCoords(a.end);
        type = 'activity';
        actType = a.topCandidate?.type || 'UNKNOWN';
        distanceMeters = a.distanceMeters || a.distance || 0;
        start = seg.startTime;
        end = seg.endTime;
      }
      // Classic Takeout activitySegment
      else if (seg.activitySegment) {
        const a = seg.activitySegment;
        coords = parseCoords(a.startLocation) || parseCoords(a.endLocation);
        type = 'activity';
        actType = a.activityType || 'UNKNOWN';
        distanceMeters = a.distance || 0;
        start = a.duration?.startTimestamp;
        end = a.duration?.endTimestamp;
      }

      // Extract GPS timelinePath
      const path = [];
      if (seg.timelinePath && seg.timelinePath.length > 0) {
        seg.timelinePath.forEach(tp => {
          const pt = parseCoords(tp.point);
          if (pt) path.push(pt);
        });
      }

      // If standalone timelinePath segment, use first GPS point as coords
      if (!coords && path.length > 0) {
        coords = path[0];
        type = 'path_segment';
        start = seg.startTime;
        end = seg.endTime;
      }

      if (coords && start) {
        const region = checkRegion(coords[0], coords[1]);
        const isFlight = actType === 'FLYING';

        if (region || isFlight) {
          const poi = resolvePoiName(coords[0], coords[1], rawName);
          travelEvents.push({
            lat: coords[0],
            lon: coords[1],
            type,
            activityType: actType,
            distanceMeters,
            start: new Date(start),
            end: end ? new Date(end) : new Date(start),
            name: poi.name,
            category: poi.category,
            region: region ? region.name : 'Przelot lotniczy',
            icon: region ? region.icon : '✈️',
            path
          });
        }
      }
    });

    self.postMessage({ type: 'progress', percent: 80, message: 'Klastrowanie i budowanie osi czasu wypraw...' });

    travelEvents.sort((a, b) => a.start - b.start);

    // 3. Cluster travel events into trips
    const trips = [];
    let currentTrip = null;

    travelEvents.forEach(e => {
      if (!currentTrip) {
        currentTrip = {
          region: e.region,
          icon: e.icon,
          events: [e],
          start: e.start,
          end: e.end,
          routePoints: [...e.path]
        };
      } else {
        const gapDays = (e.start - currentTrip.end) / (1000 * 60 * 60 * 24);
        if (gapDays <= 2.5) {
          currentTrip.events.push(e);
          if (e.end > currentTrip.end) currentTrip.end = e.end;
          if (e.path && e.path.length > 0) {
            currentTrip.routePoints.push(...e.path);
          }
          if (currentTrip.region === 'Przelot lotniczy' && e.region !== 'Przelot lotniczy') {
            currentTrip.region = e.region;
            currentTrip.icon = e.icon;
          }
        } else {
          if (currentTrip.events.length >= 3) {
            trips.push(currentTrip);
          }
          currentTrip = {
            region: e.region,
            icon: e.icon,
            events: [e],
            start: e.start,
            end: e.end,
            routePoints: [...e.path]
          };
        }
      }
    });

    if (currentTrip && currentTrip.events.length >= 3) {
      trips.push(currentTrip);
    }

    self.postMessage({ type: 'progress', percent: 95, message: 'Finalizowanie statystyk i kart wypraw...' });

    // Format trips for app.js UI
    const formattedTrips = trips.map((t, idx) => {
      const days = Math.max(1, Math.round((t.end - t.start) / (1000 * 60 * 60 * 24)) + 1);
      const startStr = t.start.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
      const endStr = t.end.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
      const monthStr = t.start.toLocaleDateString('pl-PL', { month: 'long', year: 'numeric' });
      const capitalizedMonth = monthStr.charAt(0).toUpperCase() + monthStr.slice(1);
      const title = `${t.region} - ${capitalizedMonth}`;

      let walkM = 0;
      let driveM = 0;
      let placesCount = 0;
      const highlights = [];
      const seen = new Set();

      t.events.forEach(ev => {
        if (ev.type === 'place') {
          placesCount++;
          if (ev.name && !seen.has(ev.name) && !ev.name.includes('Punkt trasy')) {
            seen.add(ev.name);
            highlights.push(ev.name);
          }
        } else if (ev.type === 'activity') {
          const act = ev.activityType || '';
          if (act.includes('WALK') || act.includes('HIKE') || act.includes('FOOT')) {
            walkM += ev.distanceMeters || 0;
          } else if (act.includes('VEHICLE') || act.includes('CAR') || act.includes('BUS')) {
            driveM += ev.distanceMeters || 0;
          }
        }
      });

      // Decimate routePoints if too dense
      let simplifiedRoute = t.routePoints;
      if (t.routePoints.length > 2500) {
        const factor = Math.ceil(t.routePoints.length / 2000);
        simplifiedRoute = t.routePoints.filter((_, i) => i % factor === 0);
      }

      return {
        id: `trip_${idx}_${t.start.getTime()}`,
        title,
        icon: t.icon,
        startDate: t.start,
        endDate: t.end,
        region: t.region,
        stats: {
          days,
          placesCount: placesCount || t.events.length,
          walkKm: walkM / 1000,
          driveKm: driveM / 1000
        },
        highlights: highlights.slice(0, 7),
        events: t.events,
        routePoints: simplifiedRoute
      };
    });

    self.postMessage({
      type: 'done',
      trips: formattedTrips,
      totalEvents: totalSegs,
      homeCoords
    });

  } catch (err) {
    self.postMessage({ type: 'error', error: err.message });
  }
};
