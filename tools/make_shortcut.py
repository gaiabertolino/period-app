#!/usr/bin/env python3
"""Generate the "Cycle Sync" Shortcut used by the app (see SHORTCUT.md).

    python tools/make_shortcut.py
    shortcuts sign --mode anyone -i "shortcut/Cycle Sync.unsigned.shortcut" -o "shortcut/Cycle Sync.shortcut"

Also writes "Cycle Sync Dry Run": the same searches, but it only COUNTS what
the real Shortcut would delete. Run it first after any change.

Input (from the app), one item per line:
    event|YYYY-MM-DD|title
    alert|YYYY-MM-DD HH:MM|title

Safety design (each piece was verified on macOS with read-only probes):
  * Deletion only targets items whose notes contain MARKER. Calendar searches
    must also have a date range (Shortcuts requires one, and the Calendar
    only searches bounded ranges of up to 4 years): the next 1400 days and the
    last 180 days.
  * The deletion block runs only if the input starts with "event|" (an empty
    or unexpected input deletes nothing). No If actions: they could not be
    serialized reliably, so a one-match Repeat is used as the guard.
  * Every Find has a limit, and iOS/macOS ask for confirmation before removing
    events, showing how many.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shortcut_lib import (action, output_of, repeat_item, shortcut_input, text, uid,  # noqa: E402
                          workflow, write)

MARKER = "cycle-app"
NOTES = f"Added by {MARKER}. Updated automatically."
OUT = Path(__file__).resolve().parent.parent / "shortcut"

# Shortcuts filter operators (verified): 99 contains, 1000 "is in the next", 1001 "is in the last", 1003 "is between".
# NSCalendarUnit 16 = days.
NOTES_HAS_MARKER = {"Property": "Notes", "Operator": 99, "Removable": True,
                    "Values": {"String": MARKER, "Unit": 4}}


def event_filter(operator: int, days: int) -> dict:
    return {
        "Value": {
            "WFActionParameterFilterPrefix": 1,  # ALL conditions must match
            "WFContentPredicateBoundedDate": True,
            "WFActionParameterFilterTemplates": [
                {"Property": "Start Date", "Operator": operator, "Removable": False,
                 "Values": {"Number": days, "Unit": 16}},
                NOTES_HAS_MARKER,
            ],
        },
        "WFSerializationType": "WFContentPredicateTableTemplate",
    }


def reminder_filter() -> dict:
    return {
        "Value": {"WFActionParameterFilterPrefix": 1, "WFContentPredicateBoundedDate": False,
                  "WFActionParameterFilterTemplates": [NOTES_HAS_MARKER]},
        "WFSerializationType": "WFContentPredicateTableTemplate",
    }


def build(dry_run: bool) -> dict:
    p = "dry-" if dry_run else ""
    guard, g_guard = uid(p + "guard"), uid(p + "g-guard")
    fut, past, rem = uid(p + "find-future"), uid(p + "find-past"), uid(p + "find-rem")

    acts = [
        # Guard: one match only if the input starts with "event|".
        action("text.match", UUID=guard, text=text(shortcut_input()),
               WFMatchTextPattern=r"\Aevent\|", WFMatchTextCaseSensitive=True),
        action("repeat.each", GroupingIdentifier=g_guard, WFControlFlowMode=0,
               WFInput=output_of(guard, "Matches")),
        action("filter.calendarevents", UUID=fut, WFContentItemFilter=event_filter(1000, 1400),
               WFContentItemLimitEnabled=True, WFContentItemLimitNumber=100.0),
        action("filter.calendarevents", UUID=past, WFContentItemFilter=event_filter(1001, 180),
               WFContentItemLimitEnabled=True, WFContentItemLimitNumber=50.0),
        action("filter.reminders", UUID=rem, WFContentItemFilter=reminder_filter(),
               WFContentItemLimitEnabled=True, WFContentItemLimitNumber=300.0),
    ]
    if dry_run:
        cf, cp, cr = uid("dry-cf"), uid("dry-cp"), uid("dry-cr")
        acts += [
            action("count", UUID=cf, Input=output_of(fut, "Calendar Events"), WFCountType="Items"),
            action("count", UUID=cp, Input=output_of(past, "Calendar Events"), WFCountType="Items"),
            action("count", UUID=cr, Input=output_of(rem, "Reminders"), WFCountType="Items"),
            action("repeat.each", GroupingIdentifier=g_guard, WFControlFlowMode=2),
            action("output", WFOutput=text("would delete: future events=", output_of(cf, "Count"),
                                           " past events=", output_of(cp, "Count"),
                                           " reminders=", output_of(cr, "Count")),
                   WFNoOutputSurfaceBehavior="Respond"),
        ]
        return workflow(acts)

    acts += [
        action("removeevents", WFInputEvents=output_of(fut, "Calendar Events"), WFCalendarIncludeFutureEvents=False),
        action("removeevents", WFInputEvents=output_of(past, "Calendar Events"), WFCalendarIncludeFutureEvents=False),
        action("removereminders", WFInputReminders=output_of(rem, "Reminders")),
        action("repeat.each", GroupingIdentifier=g_guard, WFControlFlowMode=2),
    ]

    # Create events and reminders (no deletion below this point).
    for kind in ("event", "alert"):
        m, g = uid(f"match-{kind}"), uid(f"g-{kind}")
        sp, when_txt, when, title = uid(f"sp-{kind}"), uid(f"i2-{kind}"), uid(f"d-{kind}"), uid(f"t-{kind}")
        acts += [
            action("text.match", UUID=m, text=text(shortcut_input()),
                   WFMatchTextPattern=rf"(?m)^{kind}\|.*$", WFMatchTextCaseSensitive=True),
            action("repeat.each", GroupingIdentifier=g, WFControlFlowMode=0, WFInput=output_of(m, "Matches")),
            action("text.split", UUID=sp, text=text(repeat_item()),
                   WFTextSeparator="Custom", WFTextCustomSeparator="|"),
            action("getitemfromlist", UUID=when_txt, WFInput=output_of(sp, "Split Text"),
                   WFItemSpecifier="Item At Index", WFItemIndex=2.0),
            action("detect.date", UUID=when, WFInput=output_of(when_txt, "Item from List")),
            action("getitemfromlist", UUID=title, WFInput=output_of(sp, "Split Text"), WFItemSpecifier="Last Item"),
        ]
        if kind == "event":
            acts.append(action("addnewevent",
                               WFCalendarItemTitle=text(output_of(title, "Item from List")),
                               WFCalendarItemAllDay=True,
                               WFCalendarItemStartDate=text(output_of(when, "Dates")),
                               WFCalendarItemEndDate=text(output_of(when, "Dates")),
                               WFCalendarItemNotes=text(NOTES),
                               WFAlertTime="None"))
        else:
            acts.append(action("addnewreminder",
                               WFCalendarItemTitle=text(output_of(title, "Item from List")),
                               WFCalendarItemNotes=text(NOTES),
                               WFAlertEnabled="Alert",
                               WFAlertCustomTime=text(output_of(when, "Dates"))))
        acts.append(action("repeat.each", GroupingIdentifier=g, WFControlFlowMode=2))

    acts.append(action("output", WFOutput=text("Calendar updated"), WFNoOutputSurfaceBehavior="Respond"))
    return workflow(acts)


def main() -> None:
    write(build(dry_run=False), OUT / "Cycle Sync.unsigned.shortcut")
    write(build(dry_run=True), OUT / "Cycle Sync Dry Run.unsigned.shortcut")
    print(f"wrote {OUT}/Cycle Sync.unsigned.shortcut and Cycle Sync Dry Run.unsigned.shortcut")


if __name__ == "__main__":
    main()
