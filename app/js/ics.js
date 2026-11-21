// iCalendar (.ics) generation for reminders.
//
// One all-day VEVENT per predicted cycle, each with a display alarm one day
// before. UIDs are stable per index (cycle-pred-1, cycle-pred-2, ...) and
// SEQUENCE increases on every export, so calendars that honour UIDs update the
// existing events instead of adding duplicates.

const MS_PER_DAY = 86400000;

function escapeText(text) {
  return String(text)
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n');
}

// RFC 5545: lines longer than 75 octets are folded with CRLF + space.
function fold(line) {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return line;
  let out = '', cur = '', len = 0;
  for (const ch of line) {
    const n = enc.encode(ch).length;
    if (len + n > 75) { out += cur + '\r\n '; cur = ''; len = 1; }
    cur += ch; len += n;
  }
  return out + cur;
}

const compact = (iso) => iso.replace(/-/g, '');

function nextDayIso(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d) + MS_PER_DAY).toISOString().slice(0, 10);
}

export function uidFor(k) {
  return `cycle-pred-${k}@cycle-app`;
}

export function buildICS(isoDates, { summary = 'Personal reminder', sequence = 0, now = new Date() } = {}) {
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//cycle-app//on-device prediction//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ];
  isoDates.forEach((iso, i) => {
    lines.push(
      'BEGIN:VEVENT',
      `UID:${uidFor(i + 1)}`,
      `SEQUENCE:${sequence}`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${compact(iso)}`,
      `DTEND;VALUE=DATE:${compact(nextDayIso(iso))}`,
      `SUMMARY:${escapeText(summary)}`,
      'TRANSP:TRANSPARENT',
      'BEGIN:VALARM',
      'ACTION:DISPLAY',
      `DESCRIPTION:${escapeText(summary)}`,
      'TRIGGER:-P1D',
      'END:VALARM',
      'END:VEVENT',
    );
  });
  lines.push('END:VCALENDAR');
  return lines.map(fold).join('\r\n') + '\r\n';
}
