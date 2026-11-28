# Setting Wellbeing up

Wellbeing is set up by Hydra-OS, not by itself. Setup installs it with the main app and makes its folder, `<root>/health/`, empty. Wellbeing loads no job of its own: Hydra-OS starts its read once a day.

## Its source

Wellbeing reads Apple Health's own export, with no Terminal step. Claude leads the three steps in the chat, one at a time, and the page shows them beside the place to drop the export, with the one the person is on marked:

1. On the iPhone, open the Health app, tap your picture or initials, then Export All Health Data.
2. AirDrop the export to the Mac.
3. Drop it on Wellbeing's page, beside the chat, or choose it there. Hydra-OS's own server puts it in `<root>/health/inbox/` and starts Wellbeing's read once.

As each step begins, Claude marks it on the page with `hydra act health export-step --step=<1 to 3> --yes`. Its Undo puts the step before back.

The export never goes into Claude's chat, since a file dropped into Claude's panel is uploaded off the Mac. When the person asks how to add it, Claude points them to Wellbeing's page, and asks them not to drop it into the chat.

From the export, `scripts/apple.py` reads only sleep, resting heart rate and workouts, streamed at any size, and never opens a workout route, a location or a clinical record. An export is a snapshot, so new days need another export, and the page says so.

A file of days comes in the same way: a spreadsheet saved as `.csv`, or a `.json`, with a row for each day, dropped on the page. `scripts/upload.py` lists the columns it reads. Another tracker's own export is read only when its columns carry those names.

## No iPhone

A person with no iPhone tells Claude about a workout, and Claude saves it: `hydra act health log-workout --kind=<walk, run, ride, swim, lift, yoga or row> --day=<YYYY-MM-DD> [--minutes=<1 to 600>]`, read back first, then with `--yes` after their yes. Its Undo is `unlog-workout`. Wellbeing counts each one toward their goals and the week's workouts, with no spreadsheet and no file. They're kept in `<root>/health/store/workouts.jsonl`.

Any other source the person records is kept, and Wellbeing's page says it can't read it yet.

## Remove it

- The person chooses Remove Wellbeing… at the foot of its page. It asks first, then Hydra-OS takes Wellbeing out and stops starting its read.
- Wellbeing's folder, `<root>/health/`, goes to the Trash under its title, so they can take it back. It holds their days, the exports they dropped, their meal log, the workouts they logged and their answers.
