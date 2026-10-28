/**
 * Export Manager Module for Google Timeline Travel Summarizer
 * Exports rich travel itineraries into:
 * 1. Google My Maps / Google Earth (.kml)
 * 2. Google Sheets (.csv with UTF-8 BOM)
 * 3. Google Calendar (.ics format RFC 5545)
 */

class ExportManager {
  /**
   * Helper: Trigger download of text content as file
   */
  downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  slugify(text) {
    return (text || 'podroz')
      .toString()
      .toLowerCase()
      .replace(/[ąćęłńóśźż]/g, match => {
        const map = { 'ą':'a', 'ć':'c', 'ę':'e', 'ł':'l', 'ń':'n', 'ó':'o', 'ś':'s', 'ź':'z', 'ż':'z' };
        return map[match] || match;
      })
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
  }

  formatIcsDate(date) {
    if (!date) return '';
    const d = new Date(date);
    const pad = n => n < 10 ? '0' + n : n;
    return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
  }

  formatIcsAllDayDate(date) {
    if (!date) return '';
    const d = new Date(date);
    const pad = n => n < 10 ? '0' + n : n;
    return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
  }

  escapeCsv(val) {
    if (val === null || val === undefined) return '""';
    const str = String(val).replace(/"/g, '""');
    return `"${str}"`;
  }

  escapeXml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  /**
   * 🗺️ EXPORT 1: Google My Maps & Google Earth (.kml)
   */
  exportToKml(trip) {
    if (!trip) return;

    const lines = [];
    lines.push(`<?xml version="1.0" encoding="UTF-8"?>`);
    lines.push(`<kml xmlns="http://www.opengis.net/kml/2.2">`);
    lines.push(`  <Document>`);
    lines.push(`    <name>${this.escapeXml(trip.title)}</name>`);
    lines.push(`    <description>${this.escapeXml(`Podsumowanie podróży wygenerowane z Google Timeline. Dni: ${trip.stats.days}, Pieszo: ${trip.stats.walkKm.toFixed(1)} km, Miejsca: ${trip.stats.placesCount}`)}</description>`);

    // Styles for Google Earth / My Maps
    lines.push(`
    <!-- Styles -->
    <Style id="style-attraction">
      <IconStyle>
        <color>ff66cc00</color>
        <scale>1.1</scale>
        <Icon><href>http://maps.google.com/mapfiles/ms/icons/green-dot.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="style-food">
      <IconStyle>
        <color>ff0000ff</color>
        <scale>1.1</scale>
        <Icon><href>http://maps.google.com/mapfiles/ms/icons/red-dot.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="style-lodging">
      <IconStyle>
        <color>ffff00ff</color>
        <scale>1.1</scale>
        <Icon><href>http://maps.google.com/mapfiles/ms/icons/purple-dot.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="style-airport">
      <IconStyle>
        <color>ff00aaff</color>
        <scale>1.2</scale>
        <Icon><href>http://maps.google.com/mapfiles/ms/icons/orange-dot.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="style-photo">
      <IconStyle>
        <color>ffffff00</color>
        <scale>1.3</scale>
        <Icon><href>http://maps.google.com/mapfiles/ms/icons/camera.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="style-route">
      <LineStyle>
        <color>ff059669</color>
        <width>4</width>
      </LineStyle>
    </Style>
    `);

    // Folders for each day
    trip.days.forEach((day, index) => {
      const dayNum = index + 1;
      const dateStr = day.date;
      const places = day.events.filter(e => e.type === 'place');
      const photos = (trip.photos || []).filter(p => p.dayNumber === dayNum);

      lines.push(`    <Folder>`);
      lines.push(`      <name>Dzień ${dayNum}: ${dateStr}</name>`);
      lines.push(`      <description>Liczba odwiedzonych punktów: ${places.length}</description>`);

      const routeCoords = [];

      // Placemarks for Visited Places
      places.forEach(p => {
        if (!p.lat || !p.lon) return;
        routeCoords.push(`${p.lon},${p.lat},0`);

        let style = 'style-attraction';
        if (p.category === 'food') style = 'style-food';
        else if (p.category === 'lodging') style = 'style-lodging';
        else if (p.category === 'airport') style = 'style-airport';

        const timeStr = p.start ? p.start.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '';
        const descHtml = `
          <div style="font-family:sans-serif; line-height:1.4;">
            <h3>${p.name}</h3>
            <p><b>Godzina:</b> ${timeStr}</p>
            <p><b>Adres:</b> ${p.address || 'Brak adresu'}</p>
            <p><b>Kategoria:</b> ${p.category}</p>
          </div>
        `;

        lines.push(`      <Placemark>`);
        lines.push(`        <name>${this.escapeXml(p.name)}</name>`);
        lines.push(`        <description><![CDATA[${descHtml}]]></description>`);
        lines.push(`        <styleUrl>#${style}</styleUrl>`);
        lines.push(`        <Point>`);
        lines.push(`          <coordinates>${p.lon},${p.lat},0</coordinates>`);
        lines.push(`        </Point>`);
        lines.push(`      </Placemark>`);
      });

      // Placemarks for Photos
      photos.forEach(photo => {
        if (!photo.lat || !photo.lon) return;

        const photoDesc = `
          <div style="font-family:sans-serif;">
            <h4>📷 ${photo.matchedPlace || photo.name}</h4>
            <p><b>Data i godzina:</b> ${photo.timestamp ? photo.timestamp.toLocaleString('pl-PL') : ''}</p>
            <p><b>Dopasowanie:</b> ${photo.geotagSource}</p>
            ${photo.url ? `<p><img src="${photo.url}" width="280" style="border-radius:6px; margin-top:4px;" /></p>` : ''}
          </div>
        `;

        lines.push(`      <Placemark>`);
        lines.push(`        <name>📷 ${this.escapeXml(photo.matchedPlace || photo.name)}</name>`);
        lines.push(`        <description><![CDATA[${photoDesc}]]></description>`);
        lines.push(`        <styleUrl>#style-photo</styleUrl>`);
        lines.push(`        <Point>`);
        lines.push(`          <coordinates>${photo.lon},${photo.lat},0</coordinates>`);
        lines.push(`        </Point>`);
        lines.push(`      </Placemark>`);
      });

      // LineString for Day Route
      if (routeCoords.length > 1) {
        lines.push(`      <Placemark>`);
        lines.push(`        <name>Trasa: Dzień ${dayNum} (${dateStr})</name>`);
        lines.push(`        <styleUrl>#style-route</styleUrl>`);
        lines.push(`        <LineString>`);
        lines.push(`          <tessellate>1</tessellate>`);
        lines.push(`          <coordinates>`);
        lines.push(`            ${routeCoords.join(' ')}`);
        lines.push(`          </coordinates>`);
        lines.push(`        </LineString>`);
        lines.push(`      </Placemark>`);
      }

      lines.push(`    </Folder>`);
    });

    lines.push(`  </Document>`);
    lines.push(`</kml>`);

    const kmlContent = lines.join('\n');
    const filename = `${this.slugify(trip.title)}.kml`;
    this.downloadFile(kmlContent, filename, 'application/vnd.google-earth.kml+xml;charset=utf-8;');
  }

  /**
   * 📊 EXPORT 2: Google Sheets / Excel (.csv with UTF-8 BOM)
   */
  exportToCsv(trip) {
    if (!trip) return;

    // UTF-8 BOM ensures Polish letters display correctly in Excel and Google Sheets
    let csv = '\uFEFF';

    // Header columns
    const headers = [
      'Dzień',
      'Data',
      'Godzina',
      'Typ Zdarzenia',
      'Kategoria',
      'Miejsce / Aktywność',
      'Adres',
      'Dystans (km)',
      'Czas trwania (min)',
      'GPS Lat',
      'GPS Lon',
      'Rezerwacja / Voucher',
      'Zdjęcia / Notatki'
    ];

    csv += headers.map(h => this.escapeCsv(h)).join(',') + '\r\n';

    // Trip Header Summary Row
    csv += [
      this.escapeCsv('PODSUMOWANIE'),
      this.escapeCsv(`${trip.startDate.toLocaleDateString('pl-PL')} – ${trip.endDate.toLocaleDateString('pl-PL')}`),
      this.escapeCsv(''),
      this.escapeCsv('Cała podróż'),
      this.escapeCsv(trip.stats.days + ' dni'),
      this.escapeCsv(trip.title),
      this.escapeCsv(''),
      this.escapeCsv((trip.stats.walkKm + trip.stats.driveKm).toFixed(1)),
      this.escapeCsv(''),
      this.escapeCsv(''),
      this.escapeCsv(''),
      this.escapeCsv((trip.bookings || []).map(b => b.title).join('; ')),
      this.escapeCsv(`Pieszo: ${trip.stats.walkKm.toFixed(1)} km, Samochód/Pociąg: ${trip.stats.driveKm.toFixed(0)} km, Miejsca: ${trip.stats.placesCount}`)
    ].join(',') + '\r\n';

    // Bookings summary rows
    if (trip.bookings && trip.bookings.length > 0) {
      trip.bookings.forEach(b => {
        csv += [
          this.escapeCsv('VOUCHER'),
          this.escapeCsv(b.pickupDate ? b.pickupDate.toLocaleDateString('pl-PL') : ''),
          this.escapeCsv(''),
          this.escapeCsv('Rezerwacja'),
          this.escapeCsv(b.categoryLabel || b.type),
          this.escapeCsv(b.title),
          this.escapeCsv(b.address || b.pickup || ''),
          this.escapeCsv(''),
          this.escapeCsv(''),
          this.escapeCsv(''),
          this.escapeCsv(''),
          this.escapeCsv(`Nr: ${b.bookingNumber} | Koszt: ${b.price || 'Opłacono'}`),
          this.escapeCsv(b.included || b.roomType || b.flightNumber || '')
        ].join(',') + '\r\n';
      });
    }

    // Days & Events
    trip.days.forEach((day, index) => {
      const dayNum = `Dzień ${index + 1}`;
      const dateStr = day.date;

      day.events.forEach(ev => {
        if (ev.type === 'place') {
          const timeStr = ev.start ? ev.start.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '';
          const durMin = (ev.start && ev.end) ? Math.round((ev.end - ev.start) / 60000) : '';
          const photosCount = (ev.photos && ev.photos.length > 0) ? `📷 ${ev.photos.length} zdjęć` : '';

          csv += [
            this.escapeCsv(dayNum),
            this.escapeCsv(dateStr),
            this.escapeCsv(timeStr),
            this.escapeCsv('Wizyta w miejscu'),
            this.escapeCsv(ev.category || 'atrakcja'),
            this.escapeCsv(ev.name),
            this.escapeCsv(ev.address || ''),
            this.escapeCsv(''),
            this.escapeCsv(durMin),
            this.escapeCsv(ev.lat ? ev.lat.toFixed(6) : ''),
            this.escapeCsv(ev.lon ? ev.lon.toFixed(6) : ''),
            this.escapeCsv(''),
            this.escapeCsv(photosCount)
          ].join(',') + '\r\n';

        } else if (ev.type === 'activity') {
          const timeStr = ev.start ? ev.start.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '';
          const durMin = (ev.start && ev.end) ? Math.round((ev.end - ev.start) / 60000) : '';
          const distKm = ev.distanceMeters ? (ev.distanceMeters / 1000).toFixed(2) : '0';
          const typeName = (ev.activityType || 'Trasa').replace('IN_', '').replace('_', ' ');

          csv += [
            this.escapeCsv(dayNum),
            this.escapeCsv(dateStr),
            this.escapeCsv(timeStr),
            this.escapeCsv('Przemieszczenie'),
            this.escapeCsv(typeName),
            this.escapeCsv(`Przejazd / Spacer: ${typeName}`),
            this.escapeCsv(''),
            this.escapeCsv(distKm),
            this.escapeCsv(durMin),
            this.escapeCsv(ev.startLat ? ev.startLat.toFixed(6) : ''),
            this.escapeCsv(ev.startLon ? ev.startLon.toFixed(6) : ''),
            this.escapeCsv(''),
            this.escapeCsv('')
          ].join(',') + '\r\n';
        }
      });
    });

    const filename = `${this.slugify(trip.title)}.csv`;
    this.downloadFile(csv, filename, 'text/csv;charset=utf-8;');
  }

  /**
   * 📅 EXPORT 3: Google Calendar (.ics RFC 5545)
   */
  exportToIcs(trip) {
    if (!trip) return;

    const lines = [];
    lines.push('BEGIN:VCALENDAR');
    lines.push('VERSION:2.0');
    lines.push('PRODID:-//Google Timeline Travel Summarizer//PL');
    lines.push('CALSCALE:GREGORIAN');
    lines.push('METHOD:PUBLISH');
    lines.push(`X-WR-CALNAME:${trip.title}`);
    lines.push('X-WR-TIMEZONE:UTC');

    const dtstamp = this.formatIcsDate(new Date());

    // Day summary all-day events
    trip.days.forEach((day, index) => {
      const dayNum = index + 1;
      const places = day.events.filter(e => e.type === 'place');
      const dayDateStr = day.date.replace(/-/g, '');
      const nextDate = new Date(day.date);
      nextDate.setDate(nextDate.getDate() + 1);
      const nextDateStr = nextDate.toISOString().split('T')[0].replace(/-/g, '');

      const topPlaces = places.slice(0, 3).map(p => p.name).join(', ');

      lines.push('BEGIN:VEVENT');
      lines.push(`UID:day_${index}_${Date.now()}@google-timeline-travels`);
      lines.push(`DTSTAMP:${dtstamp}`);
      lines.push(`DTSTART;VALUE=DATE:${dayDateStr}`);
      lines.push(`DTEND;VALUE=DATE:${nextDateStr}`);
      lines.push(`SUMMARY:🌴 Dzień ${dayNum}: ${trip.title.split('-')[0].trim()}`);
      lines.push(`DESCRIPTION:Odwiedzone miejsca: ${topPlaces || 'Eksploracja'}\\nLiczba punktów: ${places.length}`);
      lines.push('STATUS:CONFIRMED');
      lines.push('END:VEVENT');
    });

    // Bookings (Flights, Cars, Hotels)
    if (trip.bookings) {
      trip.bookings.forEach((b, bIdx) => {
        const start = b.departureDate || b.pickupDate || b.checkInDate || b.visitDate;
        const end = b.arrivalDate || b.returnDate || b.checkOutDate || (start ? new Date(start.getTime() + 7200000) : null);

        if (start && end) {
          lines.push('BEGIN:VEVENT');
          lines.push(`UID:book_${bIdx}_${Date.now()}@google-timeline-travels`);
          lines.push(`DTSTAMP:${dtstamp}`);
          lines.push(`DTSTART:${this.formatIcsDate(start)}`);
          lines.push(`DTEND:${this.formatIcsDate(end)}`);
          lines.push(`SUMMARY:${b.icon || '📌'} ${b.title}`);
          lines.push(`LOCATION:${b.address || b.pickup || b.departureAirport || ''}`);
          lines.push(`DESCRIPTION:Numer rezerwacji: ${b.bookingNumber}\\nKoszt: ${b.price || '-'}\\n${b.included || b.roomType || ''}`);
          lines.push('STATUS:CONFIRMED');
          lines.push('END:VEVENT');
        }
      });
    }

    // Visited Places Events
    trip.events.filter(e => e.type === 'place').forEach((p, pIdx) => {
      if (!p.start) return;
      const end = p.end || new Date(p.start.getTime() + 3600000);

      lines.push('BEGIN:VEVENT');
      lines.push(`UID:place_${pIdx}_${Date.now()}@google-timeline-travels`);
      lines.push(`DTSTAMP:${dtstamp}`);
      lines.push(`DTSTART:${this.formatIcsDate(p.start)}`);
      lines.push(`DTEND:${this.formatIcsDate(end)}`);
      lines.push(`SUMMARY:📍 ${p.name}`);
      lines.push(`LOCATION:${p.address || ''}`);
      lines.push(`DESCRIPTION:Kategoria: ${p.category}\\nZarejestrowano w Google Timeline.`);
      lines.push('STATUS:CONFIRMED');
      lines.push('END:VEVENT');
    });

    lines.push('END:VCALENDAR');

    const icsContent = lines.join('\r\n');
    const filename = `${this.slugify(trip.title)}.ics`;
    this.downloadFile(icsContent, filename, 'text/calendar;charset=utf-8;');
  }
}

// Global instance
if (typeof window !== 'undefined') {
  window.exportManager = new ExportManager();
} else if (typeof global !== 'undefined') {
  global.exportManager = new ExportManager();
}

