# Automatic calendar updates with an iOS Shortcut

A web app can't write to the iPhone Calendar by itself, but Apple's Shortcuts
app can. With the **Cycle Sync** Shortcut installed, every time you save, edit
or delete a date (or import a CSV), the app opens the Shortcut and passes it
the new predictions. The Shortcut then:

1. deletes the predictions it added last time, and nothing else;
2. adds the new predictions as **all-day events** in your default calendar;
3. adds the alerts (by default a week before, three days before and on the
   day, at 09:00) as **reminders** with an alert, in your default Reminders list.

Alerts go to Reminders because Reminders accept an exact date and time.

Everything happens on the device; nothing is sent online. (If your default
calendar and Reminders list are in iCloud, iCloud syncs them like any other
event.)

## Install

1. On your iPhone, open **[Cycle Sync.shortcut](https://github.com/gaiabertolino/period-app/raw/main/shortcut/Cycle%20Sync.shortcut)**
   in Safari, then tap **Add Shortcut**. (On a Mac, download it and
   double-click it. Shortcuts added on a Mac also sync to your iPhone through iCloud.)
2. In the app: **Settings** → tick **Update my calendar automatically with an
   iOS Shortcut** → **Save**.
3. **Data → Sync calendar now** to fill the calendar the first time. iOS may
   ask "Open in Shortcuts?" (tap Open). The first time, it also asks for
   access to Calendar and Reminders, and asks you to confirm removing items.

## How it only touches its own items (safety)

- Everything the Shortcut creates has the note
  `Added by cycle-app. Updated automatically.` It only ever deletes events
  and reminders whose notes contain `cycle-app`.
- Calendar searches are limited to the last 180 and the next 1400 days, as
  Shortcuts requires.
- It deletes only when the input starts with a prediction line
  (`event|…`). An empty or unexpected input deletes nothing.
- Before removing events, iOS shows a confirmation with the number of items.
  It should be about the number of predicted cycles (12 by default). **If it
  shows a number that doesn't make sense, tap Don't Allow.**

These rules were checked on macOS with read-only test Shortcuts before the
delete steps were added (see `tools/make_shortcut.py`).

`shortcut/Cycle Sync Dry Run.shortcut` runs the same searches but only
**counts** what would be deleted, without deleting or adding anything.
Useful if you change something.

## What the app sends

Plain text, one item per line:

```
event|2026-12-01|Personal reminder
alert|2026-11-24 09:00|Personal reminder (in 7 days)
alert|2026-11-28 09:00|Personal reminder (in 3 days)
alert|2026-12-01 09:00|Personal reminder
event|2026-12-31|Personal reminder
...
```

Alerts already in the past are left out.

## Rebuilding the Shortcut

```bash
python3 tools/make_shortcut.py
shortcuts sign --mode anyone -i "shortcut/Cycle Sync.unsigned.shortcut" -o "shortcut/Cycle Sync.shortcut"
shortcuts sign --mode anyone -i "shortcut/Cycle Sync Dry Run.unsigned.shortcut" -o "shortcut/Cycle Sync Dry Run.shortcut"
```

Signing needs a Mac signed in to iCloud. Signing with `--mode anyone` embeds
only Apple's certificates and an anonymous ID, not your name or Apple ID.
