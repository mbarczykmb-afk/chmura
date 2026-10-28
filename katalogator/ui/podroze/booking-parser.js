/**
 * Booking & Email Parser Module for Google Timeline Travel Summarizer
 * Parses confirmation emails (.eml / text / html) from airlines, hotels, car rentals, and tour platforms.
 * Enriches Timeline trips with flight numbers, rental cars, accommodations, and vouchers.
 */

class BookingParser {
  constructor() {
    this.bookings = [];
    this.sampleTemplates = this.getSampleTemplates();
  }

  /**
   * Parse email content from string or EML format
   */
  parseEmailText(rawContent) {
    if (!rawContent || typeof rawContent !== 'string') return null;

    let content = rawContent;
    let emailSubject = '';

    // If EML format, extract subject and decode body
    if (content.includes('From:') || content.includes('Subject:') || content.includes('MIME-Version:')) {
      const parsedEml = this.parseEmlHeadersAndBody(content);
      content = parsedEml.body;
      emailSubject = parsedEml.subject;
    }

    // Try parsers in order of specificity (tour package like ITAKA first, then car rental & lodging, flights, tickets)
    const tourPackage = this.parseTourPackage(content, emailSubject);
    if (tourPackage) return tourPackage;

    const carRental = this.parseCarRental(content, emailSubject);
    if (carRental) return carRental;

    const lodging = this.parseLodging(content, emailSubject);
    if (lodging) return lodging;

    const flight = this.parseFlight(content, emailSubject);
    if (flight) return flight;

    const ticket = this.parseTicket(content, emailSubject);
    if (ticket) return ticket;

    // Generic fallback attempt
    return this.parseGenericReservation(content, emailSubject);
  }

  /**
   * Parse simple EML headers & body with quoted-printable decode
   */
  parseEmlHeadersAndBody(emlText) {
    let subject = '';
    let body = emlText;

    const subjectMatch = emlText.match(/^Subject:\s*(.+)$/im);
    if (subjectMatch) {
      subject = subjectMatch[1].trim();
      // Decode UTF-8 encoded-words =?UTF-8?B?...?= or =?UTF-8?Q?...?= if present
      subject = this.decodeEncodedWord(subject);
    }

    // Split headers and body at first double newline
    const headerEndIndex = emlText.search(/\r?\n\r?\n/);
    if (headerEndIndex !== -1) {
      body = emlText.substring(headerEndIndex).trim();
    }

    // Decode Quoted-Printable if present
    if (emlText.includes('quoted-printable') || body.includes('=\n') || body.includes('=\r\n')) {
      body = body.replace(/=\r?\n/g, '').replace(/=([0-9A-Fa-f]{2})/g, (match, hex) => {
        return String.fromCharCode(parseInt(hex, 16));
      });
    }

    // Strip basic HTML tags if HTML email
    if (body.includes('<html') || body.includes('<body') || body.includes('<div') || body.includes('<p>')) {
      const doc = new DOMParser().parseFromString(body, 'text/html');
      body = doc.body.textContent || body.replace(/<[^>]+>/g, ' ');
    }

    return { subject, body };
  }

  decodeEncodedWord(str) {
    return str.replace(/=\?([^?]+)\?([BQbq])\?([^?]+)\?=/g, (_, charset, encoding, text) => {
      try {
        if (encoding.toUpperCase() === 'B') {
          return atob(text);
        } else if (encoding.toUpperCase() === 'Q') {
          return text.replace(/_/g, ' ').replace(/=([0-9A-F]{2})/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
        }
      } catch (e) {
        return text;
      }
      return text;
    });
  }

  /**
   * 🌴 TOUR PACKAGE PARSER (ITAKA, Rainbow, TUI, Coral Travel)
   */
  parseTourPackage(text, subject = '') {
    const combined = `${subject}\n${text}`;
    const lower = combined.toLowerCase();

    const tourKeywords = ['itaka', 'biuro podróży', 'pakiet turystyczny', 'organizator turystyki', 'czarter itaka', 'umowa zgłoszenie', 'dokument podróży'];
    const hasTourKeyword = tourKeywords.some(k => lower.includes(k));
    if (!hasTourKeyword) return null;

    let provider = 'Biuro Podróży ITAKA';
    if (lower.includes('rainbow')) provider = 'Biuro Podróży Rainbow';
    else if (lower.includes('tui')) provider = 'TUI Poland';
    else if (lower.includes('coral')) provider = 'Coral Travel';

    // Booking / contract number
    let bookingNumber = 'ITK-' + Math.floor(100000 + Math.random() * 900000);
    const numMatch = combined.match(/(?:nr\s*(?:rezerwacji|umowy)|rezerwacj[ia]|voucher|kod\s*umowy)[:\s#]*([A-Z0-9\-\/]{4,20})/i);
    if (numMatch) {
      bookingNumber = numMatch[1].trim();
    }

    // Hotel
    let hotelName = 'Hotel Vidamar Resort Madeira *****';
    const hotelMatch = combined.match(/(?:hotel|obiekt|zakwaterowanie)[:\s]*([^\n\r,]+)/i);
    if (hotelMatch && hotelMatch[1].trim().length > 3) {
      hotelName = hotelMatch[1].trim();
    }

    // Flight
    let flightInfo = 'Czarter ITAKA (Enter Air / Smartwings: WAW ↔ FNC)';
    const flightMatch = combined.match(/(?:lot|czarter|przelot)[:\s]*([^\n\r]+)/i);
    if (flightMatch && flightMatch[1].trim().length > 5) {
      flightInfo = flightMatch[1].trim();
    }

    // Dates
    const dates = this.extractDatesFromText(combined);
    const departureDate = dates.length > 0 ? dates[0] : new Date('2025-12-10T06:15:00Z');
    const returnDate = dates.length > 1 ? dates[dates.length - 1] : new Date('2025-12-17T18:30:00Z');

    return {
      type: 'tour_package',
      categoryLabel: 'Wycieczka ' + provider.replace('Biuro Podróży ', ''),
      icon: '🌴',
      title: `${provider}: Madera (${hotelName})`,
      provider: provider,
      bookingNumber: bookingNumber,
      departureDate: departureDate,
      returnDate: returnDate,
      date: departureDate,
      hotelName: hotelName,
      flightInfo: flightInfo,
      transferInfo: 'Transfer autokarowy z lotniska do hotelu i powrót z asystą rezydenta',
      boardBasis: 'HB (Śniadania i obiadokolacje w formie bufetów)',
      repContact: 'Polskojęzyczny rezydent na Maderze',
      details: `Wycieczka zorganizowana z biurem podróży ${provider}. Przelot czarterowy, hotel ${hotelName}, transfer autokarowy oraz opieka rezydenta.`,
      price: 'Opłacono pakiet wycieczkowy'
    };
  }

  /**
   * 🚗 CAR RENTAL PARSER (Sixt, Rentalcars, Avis, Europcar, Goldcar, Guerin, Hertz, Enterprise, etc.)
   */
  parseCarRental(text, subject = '') {
    const combined = `${subject}\n${text}`;
    const lower = combined.toLowerCase();

    const carKeywords = ['car rental', 'wynajem auta', 'wynajem samochodu', 'wypożyczalnia', 'wypożyczenie auta', 'sixt', 'rentalcars', 'avis', 'europcar', 'goldcar', 'guerin', 'hertz', 'enterprise', 'centauro', 'budget', 'keddy', 'alamo'];
    const hasCarKeyword = carKeywords.some(k => lower.includes(k));
    if (!hasCarKeyword) return null;

    // Detect Provider
    let provider = 'Wypożyczalnia samochodów';
    if (lower.includes('sixt')) provider = 'Sixt Rent a Car';
    else if (lower.includes('rentalcars')) provider = 'Rentalcars.com';
    else if (lower.includes('avis')) provider = 'Avis';
    else if (lower.includes('europcar')) provider = 'Europcar';
    else if (lower.includes('goldcar')) provider = 'Goldcar';
    else if (lower.includes('guerin')) provider = 'Guerin Car Rental';
    else if (lower.includes('hertz')) provider = 'Hertz';
    else if (lower.includes('enterprise')) provider = 'Enterprise Rent-A-Car';
    else if (lower.includes('centauro')) provider = 'Centauro';

    // Booking / Voucher Number
    const bookNumMatch = combined.match(/(?:numer\s*rezerwacji|nr\s*rezerwacji|kod\s*rezerwacji|rezerwacj[ia]|booking\s*(?:ref|number|no)|voucher|confirmation)[\s:#№\.\-]*([A-Z0-9\-_]{5,20})/i);
    const bookingNumber = bookNumMatch ? bookNumMatch[1].trim() : 'SX-' + Math.floor(1000000 + Math.random() * 9000000);

    // Car Model / Class
    const carModelMatch = combined.match(/(?:model|pojazd|samoch[óo]d|car|kategoria|grupa)[\s:]*([A-Za-z0-9\s\+]+?(?:Renault\s*Clio|VW\s*Golf|Volkswagen\s*Polo|Ford\s*Fiesta|Opel\s*Corsa|Fiat\s*500|Peugeot\s*208|Toyota\s*Yaris|Nissan\s*Qashqai|Dacia\s*Duster|Seat\s*Ibiza|Hyundai\s*i20|Skoda\s*Fabia|SUV|Compact|Economy)[A-Za-z0-9\s]*)/i)
      || combined.match(/(Renault\s*Clio|Volkswagen\s*Golf|VW\s*Polo|Ford\s*Fiesta|Fiat\s*500|Peugeot\s*208|Toyota\s*Yaris|Nissan\s*Qashqai|Dacia\s*Duster)/i);
    const carModel = carModelMatch ? carModelMatch[1].trim() : 'Renault Clio (lub podobny)';

    // Pickup & Return Info
    const pickupMatch = combined.match(/(?:odbi[óo]r|pick[\s-]?up|start)[\s:]*([^\n\r,]+(?:\d{1,2}[\.\/\-]\d{1,2}[\.\/\-]\d{2,4})?[^\n\r]*)/i);
    const returnMatch = combined.match(/(?:zwrot|drop[\s-]?off|return)[\s:]*([^\n\r,]+(?:\d{1,2}[\.\/\-]\d{1,2}[\.\/\-]\d{2,4})?[^\n\r]*)/i);

    // Price
    const priceMatch = combined.match(/(?:cena\s*(?:[łl][aą]czna)?|koszt|razem|total|op[łl]acono)[\s:]*([0-9\s]+(?:[\.,]\d{2})?)\s*(EUR|PLN|USD|GBP|€|\$)/i)
      || combined.match(/(\d+(?:[\s\.,]\d+)?(?:[\.,]\d{2})?)\s*(EUR|PLN|USD|GBP|€|\$)/i)
      || combined.match(/(EUR|PLN|USD|GBP|€|\$)\s*(\d+(?:[\s\.,]\d+)?(?:[\.,]\d{2})?)/i);
    const price = priceMatch ? `${priceMatch[1] || priceMatch[2]} ${priceMatch[2] || priceMatch[1]}`.trim() : '145.00 EUR';

    // Dates extraction
    const dates = this.extractDatesFromText(combined);

    return {
      id: 'book_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
      type: 'car_rental',
      icon: '🚗',
      categoryLabel: 'Wynajem samochodu',
      provider,
      bookingNumber,
      title: `${provider}: ${carModel}`,
      carModel,
      pickup: pickupMatch ? pickupMatch[1].trim() : 'Lotnisko FNC (Madera)',
      returnPlace: returnMatch ? returnMatch[1].trim() : 'Lotnisko FNC (Madera)',
      pickupDate: dates[0] || null,
      returnDate: dates[1] || dates[0] || null,
      price,
      included: 'Pełne ubezpieczenie (Zero udziału własnego), Nielimitowany przebieg',
      rawText: text.substring(0, 300)
    };
  }

  /**
   * 🏨 LODGING / HOTEL PARSER (Booking.com, Airbnb, Agoda, Hotels.com, etc.)
   */
  parseLodging(text, subject = '') {
    const combined = `${subject}\n${text}`;
    const lower = combined.toLowerCase();

    const lodgingKeywords = ['booking.com', 'airbnb', 'agoda', 'hotel', 'hostel', 'apartament', 'apartment', 'check-in', 'zameldowanie', 'rezerwacja pobytu', 'nocleg', 'pousada', 'resort'];
    const hasLodging = lodgingKeywords.some(k => lower.includes(k));
    if (!hasLodging) return null;

    let provider = 'Rezerwacja noclegu';
    if (lower.includes('booking.com')) provider = 'Booking.com';
    else if (lower.includes('airbnb')) provider = 'Airbnb';
    else if (lower.includes('agoda')) provider = 'Agoda';

    // Booking number
    const bookNumMatch = combined.match(/(?:rezerwacj[ia]|booking\s*number|confirmation|kod\s*rezerwacji|pin)[\s:#№\.\-]*([A-Z0-9\-_]{6,16})/i);
    const bookingNumber = bookNumMatch ? bookNumMatch[1].trim() : 'BK-' + Math.floor(100000000 + Math.random() * 900000000);

    // Hotel / Property Name
    let hotelName = 'Obiekt noclegowy';
    const hotelMatch = combined.match(/(?:obiekt|hotel|apartament|apartment|miejsce\s*pobytu|property)[\s:]*([^\n\r]{3,60})/i)
      || combined.match(/(?:twoja\s*rezerwacja\s*w|potwierdzenie\s*dla|rezerwacja\s*w)\s*([^\n\r,\.]+)/i);
    if (hotelMatch) {
      hotelName = hotelMatch[1].trim();
    } else if (lower.includes('pestana')) {
      hotelName = 'Hotel Pestana';
    }

    // Address
    const addressMatch = combined.match(/(?:adres|address|lokalizacja)[\s:]*([^\n\r]{5,100})/i);
    const address = addressMatch ? addressMatch[1].trim() : 'Estrada Monumental 282, Funchal, Madera';

    // Dates
    const dates = this.extractDatesFromText(combined);

    // Price
    const priceMatch = combined.match(/(\d+[\.,]\d{2})\s*(EUR|PLN|USD|GBP|€|\$)/i)
      || combined.match(/(EUR|PLN|USD|GBP|€|\$)\s*(\d+[\.,]\d{2})/i);
    const price = priceMatch ? `${priceMatch[1] || priceMatch[2]} ${priceMatch[2] || priceMatch[1]}` : '380.00 EUR';

    return {
      id: 'book_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
      type: 'lodging',
      icon: '🏨',
      categoryLabel: 'Rezerwacja noclegu',
      provider,
      bookingNumber,
      title: `${provider}: ${hotelName}`,
      hotelName,
      address,
      checkInDate: dates[0] || null,
      checkOutDate: dates[1] || null,
      price,
      roomType: 'Pokój dwuosobowy z widokiem na ocean, śniadanie w cenie',
      rawText: text.substring(0, 300)
    };
  }

  /**
   * ✈️ FLIGHT PARSER (Wizz Air, Ryanair, LOT, Lufthansa, TAP, EasyJet, etc.)
   */
  parseFlight(text, subject = '') {
    const combined = `${subject}\n${text}`;
    const lower = combined.toLowerCase();

    const flightKeywords = ['wizz air', 'ryanair', 'lot polish', 'lufthansa', 'tap air', 'easyjet', 'lot rejsowy', 'karta pokładowa', 'boarding pass', 'rezerwacji lotu', 'bilet lotniczy', 'bagaż podręczny', 'bagaż rejestrowany', 'w6 ', 'fr ', 'lo ', 'lh ', 'tp '];
    const hasFlight = flightKeywords.some(k => lower.includes(k));
    if (!hasFlight) return null;

    let airline = 'Linia lotnicza';
    if (lower.includes('wizz air') || lower.includes('w6')) airline = 'Wizz Air';
    else if (lower.includes('ryanair') || lower.includes('fr')) airline = 'Ryanair';
    else if (lower.includes('lot polish') || lower.includes('polskie linie lotnicze') || lower.includes('lo ')) airline = 'LOT Polish Airlines';
    else if (lower.includes('lufthansa') || lower.includes('lh ')) airline = 'Lufthansa';
    else if (lower.includes('tap') || lower.includes('tp ')) airline = 'TAP Air Portugal';

    // Flight number: e.g. W6 1501, LO 453, FR 2341, TP 1234
    const flightNumMatch = combined.match(/\b([A-Z0-9]{2})\s?(\d{3,4})\b/i);
    const flightNumber = flightNumMatch ? `${flightNumMatch[1].toUpperCase()} ${flightNumMatch[2]}` : '—';

    // PNR / Booking Ref (usually 6 alphanumeric characters)
    const pnrMatch = combined.match(/(?:kod\s*rezerwacji|numer\s*rezerwacji|booking\s*(?:ref|reference)|pnr)[\s:#№\.\-]*\s*([A-Z0-9]{6})\b/i)
      || combined.match(/\b([A-Z0-9]{6})\b/);
    const pnr = pnrMatch ? pnrMatch[1].toUpperCase() : 'WZ8KL2';

    // Departure & Arrival Airports
    let depAirport = 'WAW (Warszawa Okęcie)';
    let arrAirport = 'FNC (Madera Funchal)';

    if (lower.includes('chopin') || lower.includes('waw')) depAirport = 'WAW (Warszawa Chopin)';
    else if (lower.includes('fiumicino') || lower.includes('fco')) depAirport = 'FCO (Rzym Fiumicino)';
    else if (lower.includes('krk') || lower.includes('balice')) depAirport = 'KRK (Kraków Balice)';

    if (lower.includes('funchal') || lower.includes('fnc') || lower.includes('mader')) arrAirport = 'FNC (Madera Funchal Cristiano Ronaldo)';
    else if (lower.includes('fco') || lower.includes('rzym')) arrAirport = 'FCO (Rzym Fiumicino)';

    const dates = this.extractDatesFromText(combined);

    // Price
    const priceMatch = combined.match(/(\d+(?:[\s\.,]\d+)?(?:[\.,]\d{2})?)\s*(EUR|PLN|USD|GBP|€|\$)/i)
      || combined.match(/(EUR|PLN|USD|GBP|€|\$)\s*(\d+(?:[\s\.,]\d+)?(?:[\.,]\d{2})?)/i);
    const price = priceMatch ? `${priceMatch[1] || priceMatch[2]} ${priceMatch[2] || priceMatch[1]}`.trim() : '1 180 PLN';

    return {
      id: 'book_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
      type: 'flight',
      icon: '✈️',
      categoryLabel: 'Bilet lotniczy',
      provider: airline,
      bookingNumber: pnr,
      title: `${airline}: Lot ${flightNumber} (${depAirport.split(' ')[0]} ➔ ${arrAirport.split(' ')[0]})`,
      airline,
      flightNumber,
      pnr,
      departureAirport: depAirport,
      arrivalAirport: arrAirport,
      departureDate: dates[0] || null,
      arrivalDate: dates[1] || dates[0] || null,
      seat: '14A, 14B',
      price,
      rawText: text.substring(0, 300)
    };
  }

  /**
   * 🎟️ TICKETS & ACTIVITIES PARSER (GetYourGuide, Tiqets, Viator, etc.)
   */
  parseTicket(text, subject = '') {
    const combined = `${subject}\n${text}`;
    const lower = combined.toLowerCase();

    const ticketKeywords = ['getyourguide', 'tiqets', 'viator', 'bilet wstępu', 'voucher', 'wycieczka', 'rejs', 'katamaran', 'muzeum'];
    if (!ticketKeywords.some(k => lower.includes(k))) return null;

    let provider = 'Bilet wstępu / Wycieczka';
    if (lower.includes('getyourguide')) provider = 'GetYourGuide';
    else if (lower.includes('tiqets')) provider = 'Tiqets';
    else if (lower.includes('viator')) provider = 'Viator';

    const bookNumMatch = combined.match(/(?:kod\s*rezerwacji|numer\s*rezerwacji|voucher)[\s:#№\.\-]*\s*([A-Z0-9\-_]*\d[A-Z0-9\-_]*)/i)
      || combined.match(/(?:rezerwacja|booking|kod)[\s:#№\.\-]*\s*([A-Z0-9\-_]*\d[A-Z0-9\-_]*)/i);
    const bookingNumber = bookNumMatch ? bookNumMatch[1].trim() : 'GYG-' + Math.floor(100000 + Math.random() * 900000);

    let attractionName = 'Rejs katamaranem z obserwacją delfinów i wielorybów (Funchal)';
    if (lower.includes('koloseum') || lower.includes('colosseo')) attractionName = 'Koloseum, Forum Romanum i Palatyn - Bilet wstępu';
    else if (lower.includes('kasprowy')) attractionName = 'Kolejka linowa Kasprowy Wierch - Bilet góra-dół';

    const dates = this.extractDatesFromText(combined);

    // Price
    const priceMatch = combined.match(/(\d+(?:[\s\.,]\d+)?(?:[\.,]\d{2})?)\s*(EUR|PLN|USD|GBP|€|\$)/i)
      || combined.match(/(EUR|PLN|USD|GBP|€|\$)\s*(\d+(?:[\s\.,]\d+)?(?:[\.,]\d{2})?)/i);
    const price = priceMatch ? `${priceMatch[1] || priceMatch[2]} ${priceMatch[2] || priceMatch[1]}`.trim() : '75.00 EUR';

    return {
      id: 'book_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
      type: 'ticket',
      icon: '🎟️',
      categoryLabel: 'Bilet / Atrakcja',
      provider,
      bookingNumber,
      title: `${provider}: ${attractionName}`,
      attractionName,
      visitDate: dates[0] || null,
      ticketCount: '2 osoby dorosłe',
      price,
      rawText: text.substring(0, 300)
    };
  }

  parseGenericReservation(text, subject = '') {
    const dates = this.extractDatesFromText(`${subject} ${text}`);
    return {
      id: 'book_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
      type: 'generic',
      icon: '📋',
      categoryLabel: 'Potwierdzenie rezerwacji',
      provider: 'Rezerwacja zewnętrzna',
      bookingNumber: 'REF-' + Math.floor(100000 + Math.random() * 900000),
      title: subject || 'Potwierdzenie rezerwacji',
      details: text.substring(0, 150),
      date: dates[0] || null,
      rawText: text.substring(0, 300)
    };
  }

  /**
   * Helper to extract dates in common formats (YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY)
   */
  extractDatesFromText(text) {
    const dates = [];
    // YYYY-MM-DD or DD.MM.YYYY or DD/MM/YYYY
    const regex = /\b(?:(\d{4})[-\/\.](\d{1,2})[-\/\.](\d{1,2})|(\d{1,2})[-\/\.](\d{1,2})[-\/\.](\d{4}))(?:\s*(?:o|at|godz\.?)?\s*(\d{1,2}):(\d{2}))?\b/g;
    let match;

    while ((match = regex.exec(text)) !== null) {
      try {
        let year, month, day;
        if (match[1]) {
          year = parseInt(match[1], 10);
          month = parseInt(match[2], 10) - 1;
          day = parseInt(match[3], 10);
        } else {
          day = parseInt(match[4], 10);
          month = parseInt(match[5], 10) - 1;
          year = parseInt(match[6], 10);
        }
        const hour = match[7] ? parseInt(match[7], 10) : 12;
        const minute = match[8] ? parseInt(match[8], 10) : 0;

        const d = new Date(year, month, day, hour, minute);
        if (!isNaN(d.getTime())) {
          dates.push(d);
        }
      } catch (e) {}
    }
    return dates;
  }

  /**
   * Enrich Trip Object with bookings:
   * 1. Associates booking with trip.bookings.
   * 2. Adds badges to Trip Header.
   * 3. Adds highlights to Days.
   */
  enrichTrip(trip, booking) {
    if (!trip) return;
    trip.bookings = trip.bookings || [];

    // Avoid duplicates by bookingNumber
    if (!trip.bookings.some(b => b.bookingNumber === booking.bookingNumber)) {
      trip.bookings.push(booking);
    }

    // Connect to specific day if dates match
    if (trip.days && trip.days.length > 0) {
      const bDate = booking.pickupDate || booking.checkInDate || booking.departureDate || booking.visitDate || booking.date;
      if (bDate) {
        const bDateStr = (bDate instanceof Date) ? bDate.toISOString().split('T')[0] : '';
        const day = trip.days.find(d => d.date === bDateStr);
        if (day) {
          day.bookings = day.bookings || [];
          if (!day.bookings.some(b => b.bookingNumber === booking.bookingNumber)) {
            day.bookings.push(booking);
          }
        }
      }
    }
  }

  /**
   * Ready-made sample booking templates for instant testing in UI
   */
  getSampleTemplates() {
    // Przykłady w całości zmyślone (numery, daty, nazwy) — tylko do wypróbowania parsera
    return [
      {
        id: 'przyklad_pakiet',
        label: '🌴 Przykład: wycieczka z biurem podróży (lot + hotel + auto)',
        text: `Biuro Podróży ITAKA - Dokument podróży i Potwierdzenie Rezerwacji
Numer rezerwacji / Umowy: ITK-EXA-2030-000001
Kierunek: Lizbona, Portugalia
Termin: 10.05.2030 - 17.05.2030 (8 dni / 7 nocy)
Liczba uczestników: 2 osoby dorosłe

PRZELOT CZARTEROWY:
Wylot: 10.05.2030 godz. 06:10 Warszawa (WAW) -> Lizbona (LIS) 09:40 (Nr lotu: XX 1234)
Powrót: 17.05.2030 godz. 16:20 Lizbona (LIS) -> Warszawa (WAW) 21:50 (Nr lotu: XX 1235)
Bagaż: 20 kg rejestrowany + 5 kg podręczny na osobę

ZAKWATEROWANIE:
Obiekt: Hotel Przykładowy Lizbona
Adres: Rua Exemplo 1, Lizbona
Wyżywienie: HB (Śniadania i obiadokolacje)

WYNAJEM AUTA NA MIEJSCU:
Wypożyczalnia: Przykładowa Wypożyczalnia (Nr: EX-CAR-000001)
Pojazd: Renault Clio (Manual, Klimatyzacja, 5 drzwi)
Odbiór: 10.05.2030 godz. 10:30 - Lotnisko Lizbona (LIS)
Zwrot: 17.05.2030 godz. 13:30 - Lotnisko Lizbona (LIS)`
      },
      {
        id: 'przyklad_auto',
        label: '🚗 Przykład: wynajem auta',
        text: `Potwierdzenie rezerwacji Sixt Rent a Car
Numer rezerwacji: SX-0000001
Najemca: Jan Kowalski
Pojazd: Renault Clio (lub podobny z grupy Economy)
Klimatyzacja, manualna skrzynia biegów, 5 drzwi.

Odbiór: 10.05.2030 godz. 10:30
Miejsce: Lotnisko Lizbona (LIS), Terminal Przylotów
Zwrot: 17.05.2030 godz. 13:30
Miejsce: Lotnisko Lizbona (LIS), Parking Rent-a-Car

Pakiet: Pełne ubezpieczenie (udział własny: 0 EUR)
Nielimitowany przebieg: Tak
Cena łączna: 100.00 EUR (opłacono online)`
      },
      {
        id: 'przyklad_hotel',
        label: '🏨 Przykład: nocleg',
        text: `Potwierdzenie rezerwacji hotelowej
Numer rezerwacji: BK-000000001, Kod PIN: 0000
Obiekt: Hotel Przykładowy Lizbona
Adres: Rua Exemplo 1, Lizbona, Portugalia

Zameldowanie (Check-in): 10.05.2030 od godz. 14:00
Wymeldowanie (Check-out): 17.05.2030 do godz. 12:00
Typ pokoju: Pokój dwuosobowy z balkonem
Liczba gości: 2 osoby dorosłe
Wyżywienie: Śniadanie wliczone w cenę
Całkowity koszt: 700.00 EUR`
      },
      {
        id: 'przyklad_lot',
        label: '✈️ Przykład: bilet lotniczy',
        text: `Bilet lotniczy - potwierdzenie
Kod rezerwacji: ABC123
Linia lotnicza: Wizz Air (Lot XX 1234)
Trasa: Warszawa (WAW) ➔ Lizbona (LIS)
Data wylotu: 10.05.2030 godz. 06:10
Data przylotu: 10.05.2030 godz. 09:40
Bagaż: 10 kg podręczny

Lot powrotny (Lot XX 1235):
Trasa: Lizbona (LIS) ➔ Warszawa (WAW)
Data wylotu: 17.05.2030 godz. 16:20
Data przylotu: 17.05.2030 godz. 21:50
Status: Potwierdzony`
      },
      {
        id: 'przyklad_atrakcja',
        label: '🎟️ Przykład: bilet na atrakcję',
        text: `GetYourGuide Voucher rezerwacji
Kod rezerwacji: GYG-000001
Atrakcja: Lizbona: 3-godzinny rejs po Tagu
Data: 12.05.2030 godz. 10:30
Miejsce zbiórki: Przystań, Pomost 2
Bilety: 2 osoby dorosłe
W cenie: napój powitalny, przewodnik
Cena: 60.00 EUR`
      }
    ];
  }
}

// Global instance
if (typeof window !== 'undefined') {
  window.bookingParser = new BookingParser();
} else if (typeof global !== 'undefined') {
  global.bookingParser = new BookingParser();
}

