// iCalendar (.ics) generation for reminders.
//
// One all-day VEVENT per predicted cycle, each with one display alarm per entry
// of `alertDays` (default 7, 3 and 0 days before, at 09:00). UIDs are stable per index (cycle-pred-1, cycle-pred-2, ...) and
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

export const DEFAULT_ALERT_DAYS = Object.freeze([7, 3, 0]);
export const DEFAULT_ALERT_TIME = '09:00';

// Alarm trigger relative to the start of an all-day event (local midnight):
// `days` before, at `time` (HH:MM). (7, '09:00') -> '-P6DT15H', (0, '09:00') -> 'PT9H'.
export function alertTrigger(days, time = DEFAULT_ALERT_TIME) {
  const [h, m] = time.split(':').map(Number);
  const total = -days * 1440 + h * 60 + m;
  const abs = Math.abs(total);
  const D = Math.floor(abs / 1440), H = Math.floor((abs % 1440) / 60), M = abs % 60;
  if (abs === 0) return 'PT0S';
  const timePart = H || M ? `T${H ? `${H}H` : ''}${M ? `${M}M` : ''}` : '';
  return `${total < 0 ? '-' : ''}P${D ? `${D}D` : ''}${timePart}`;
}

function alertText(summary, days) {
  if (days === 0) return summary;
  if (days === 1) return `${summary} (tomorrow)`;
  return `${summary} (in ${days} days)`;
}

// Text handed to the iOS Shortcut ("Cycle Sync", see SHORTCUT.md), one item per line:
//   event|2026-12-01|Personal reminder
//   alert|2026-11-24 09:00|Personal reminder (in 7 days)
// Alerts already in the past are left out.
export function buildShortcutPayload(isoDates, {
  summary = 'Personal reminder',
  alertDays = DEFAULT_ALERT_DAYS,
  alertTime = DEFAULT_ALERT_TIME,
  now = new Date(),
} = {}) {
  const clean = (t) => String(t).replace(/[|\s]+/g, ' ').trim();
  const pad = (n) => String(n).padStart(2, '0');
  const nowLocal = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const days = [...new Set(alertDays)].sort((a, b) => b - a);
  const lines = [];
  for (const iso of isoDates) {
    lines.push(`event|${iso}|${clean(summary)}`);
    const [y, m, d] = iso.split('-').map(Number);
    for (const n of days) {
      const when = `${new Date(Date.UTC(y, m - 1, d) - n * MS_PER_DAY).toISOString().slice(0, 10)} ${alertTime}`;
      if (when > nowLocal) lines.push(`alert|${when}|${clean(alertText(summary, n))}`);
    }
  }
  return lines.join('\n');
}

export function shortcutURL(name, payload) {
  return `shortcuts://run-shortcut?name=${encodeURIComponent(name)}&input=text&text=${encodeURIComponent(payload)}`;
}

export function buildICS(isoDates, {
  summary = 'Personal reminder',
  sequence = 0,
  now = new Date(),
  alertDays = DEFAULT_ALERT_DAYS,
  alertTime = DEFAULT_ALERT_TIME,
} = {}) {
  const days = [...new Set(alertDays)].sort((a, b) => b - a);
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
    );
    for (const d of days) {
      lines.push(
        'BEGIN:VALARM',
        'ACTION:DISPLAY',
        `DESCRIPTION:${escapeText(alertText(summary, d))}`,
        `TRIGGER:${alertTrigger(d, alertTime)}`,
        'END:VALARM',
      );
    }
    lines.push('END:VEVENT');
  });
  lines.push('END:VCALENDAR');
  return lines.map(fold).join('\r\n') + '\r\n';
}
