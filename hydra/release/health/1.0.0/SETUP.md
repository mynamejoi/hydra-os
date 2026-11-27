# Setting Wellbeing up

Wellbeing is set up by Hydra-OS, not by itself. Setup installs it with the main app and makes its folder, `<root>/health/`, empty. Wellbeing loads no job of its own: Hydra-OS starts its read once a day.

## Its source

Wellbeing reads Apple Health's own export, with no Terminal step. Claude gives the three steps in the chat, and the page holds the place to drop the export:

1. On the iPhone, open the Health app, tap your picture, then Export All Health Data.
2. AirDrop the export to the Mac.
3. Drop it on Wellbeing's page in the Hydra-OS app, or choose it there. Hydra-OS's own server puts it in `<root>/health/inbox/` and starts Wellbeing's read once.

The export never goes into Claude's chat, since a file dropped into Claude's panel is uploaded off the Mac. When the person asks how to add it, Claude points them to Wellbeing's page, and asks them not to drop it into the chat.

From the export, `scripts/apple.py` reads only sleep, resting heart rate and workouts, streamed at any size, and never opens a workout route, a location or a clinical record. An export is a snapshot, so new days need another export, and the page says so.

A file of days comes in the same way: a spreadsheet saved as `.csv`, or a `.json`, with a row for each day, dropped on the page. `scripts/upload.py` lists the columns it reads. Another tracker's own export is read only when its columns carry those names.

Any other source the person records is kept, and Wellbeing's page says it can't read it yet.

## Remove it

- Tell Claude to remove Wellbeing. Hydra-OS stops starting its read.
- Wellbeing's folder, `<root>/health/`, stays until the person deletes it. It holds their days, the exports they dropped, their meal log and their answers.
