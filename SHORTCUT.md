# Automatic calendar updates with an iOS Shortcut

A web app can't write to the iPhone Calendar by itself, but Apple's Shortcuts
app can. You build one Shortcut, once. After that, every time you save, edit
or delete a date (or import a CSV), the app opens the Shortcut and passes it
the new predictions. The Shortcut then:

1. deletes the old predictions from a calendar called **Cycle**;
2. adds the new predictions there as all-day events;
3. replaces the alerts in a Reminders list called **Cycle**: by default one
   week before, three days before and on the day, at 09:00.

Alerts go to Reminders because Reminders accept an exact date and time.
The Shortcuts "Add New Event" action only offers fixed alert presets.

Everything happens on the phone; nothing is sent online. (If the Cycle
calendar or list is stored in iCloud, iCloud syncs it like any other calendar.
Pick **On My iPhone** if you don't want that.)

## 1. Create the calendar and the list

- **Calendar** app → Calendars → Add Calendar → name it `Cycle`.
- **Reminders** app → Add List → name it `Cycle`.

Use these only for the app. The Shortcut deletes whatever is in them.

## 2. Build the Shortcut

Open **Shortcuts** → **+** → name it exactly `Cycle Sync`. (Another name works
if you also change it in the app's Settings.) Add these actions in order.
Search for each one by name.

1. **Receive input**: tap the input placeholder at the top and set
   *Receive **Text** input*. Set *If there's no input* → **Stop**.
2. **Find Calendar Events**: Add Filter → *Calendar* is **Cycle**.
3. **Remove Events**: input: *Calendar Events* from step 2.
4. **Find Reminders**: Add Filter → *List* is **Cycle**.
5. **Remove Reminders**: input: *Reminders* from step 4.
6. **Split Text**: text: *Shortcut Input*; separator: **New Lines**.
7. **Repeat with Each**: item in *Split Text*. Inside the loop:
   1. **Split Text**: text: *Repeat Item*; separator: **Custom** → `|`
   2. **Get Item from List**: **First Item** of *Split Text* →
      **Set Variable** `Kind`
   3. **Get Item from List**: **Item At Index** `2` of the same *Split Text* →
      **Get Dates from Input** → **Set Variable** `When`
   4. **Get Item from List**: **Last Item** of the same *Split Text* →
      **Set Variable** `Title`
   5. **If** `Kind` *is* `event`
      - **Add New Event**: title `Title`, calendar **Cycle**, turn on
        **All Day**, Start Date `When`, End Date `When`, alert **None**.
   6. **Otherwise**
      - **Add New Reminder**: title `Title`, list **Cycle**, turn on the
        alert / *Remind Me* option and set it to **At Time** → `When`.
   7. **End If**
8. **End Repeat** (added automatically).
9. Optional: **Show Notification** → `Calendar updated`.

The first time it runs, iOS asks for permission to delete events and
reminders. Choose **Always Allow**, otherwise it asks every time.

## 3. Turn it on in the app

App → **Settings** → tick **Update my calendar automatically with an iOS
Shortcut**. Check the Shortcut name, then tap **Save**. Then go to **Data →
Sync calendar now** to try it. iOS may first ask "Open in Shortcuts?"; tap
Open. When the Shortcut has finished, switch back to the app.

From then on, saving, editing or deleting a date opens the Shortcut
automatically. Changing the alert settings shows a banner with a
**Sync calendar** button.

If you used the `.ics` export before, delete those older events by hand
once. They aren't in the Cycle calendar, so the Shortcut doesn't touch them.

## What the app sends

The Shortcut input is plain text, one item per line:

```
event|2026-12-01|Personal reminder
alert|2026-11-24 09:00|Personal reminder (in 7 days)
alert|2026-11-28 09:00|Personal reminder (in 3 days)
alert|2026-12-01 09:00|Personal reminder
event|2026-12-31|Personal reminder
...
```

Alerts that are already in the past are left out. To see exactly what your
Shortcut receives, add a **Quick Look** action on *Shortcut Input* at the top
while testing.
