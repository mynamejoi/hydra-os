# What each page reads, and the way in

Each page reads only the sources its own column.json declares, and `hydra setup <page>` prints its own steps. This list was checked in November 2026 against each service's own pages. Services change: before you tell the person a way, check it's still there.

## What each page reads
- **Wellbeing:** sleep, resting heart and workouts, from the Health app's own export on their iPhone, as a file, or a spreadsheet they keep, as a CSV file.
- **Goals:** nothing of its own: it counts their goals from what the other pages read, or by hand.
- **Finance:** account balances and transactions, and holdings if they invest, read only: Monarch or Robinhood through Claude's own connector, or a file from their bank.
- **People:** who they write to and meet, and when: Gmail and Google Calendar through Claude's own connectors, read only, or a contacts or calendar file they export.
- **Inbox:** their mail and calendar invites: Gmail and Google Calendar through Claude's own connectors, read only, or a calendar file.
- **Research:** their own notes dropped on its page, and the public release notes and plugin list it checks.
- **Content:** each video's views, watch time, clicks and subscribers, from YouTube Studio's own export, as a file.
- **Home and Dreams:** nothing of their own; they read the other pages.

## The services

| Service | Page | Way in | Cost and catch |
|---|---|---|---|
| Apple Health | Wellbeing | On the iPhone: Health, their picture, Export All Health Data, then AirDrop it to this Mac and drop it on Wellbeing's page | Free. It's a snapshot, so they add a fresh one when they want it current. |
| A spreadsheet of their days | Wellbeing | Two columns, Date and what they track, one row a day, saved as a CSV file and dropped on the page | Free. |
| Monarch | Finance | Claude connector, by Monarch | Needs a Monarch plan. Finance's own hook lets only its listed reads through. |
| Robinhood | Finance | Claude connector, by Robinhood | Free. Finance's own hook refuses every order, trade and transfer tool. |
| A bank or card | Finance | The bank's own download (CSV), dropped on Finance's page | Free, and repeated when they want it current. |
| Gmail | People, Inbox | Claude connector, by Google | Free. The pages' own hooks let only reading tools through. |
| Google Calendar | People, Inbox | Claude connector, by Google | Free. |
| A contacts or calendar file | People, Inbox | Exported from their contacts or calendar app as .vcf, .csv or .ics, and dropped on the page | Free. |
| YouTube Studio | Content | Studio's own export of their videos' numbers, as a file dropped on Content's page | Free. |
| Anything else | none yet | Say which page could use it, or keep it for later | Don't connect what no page reads. |
