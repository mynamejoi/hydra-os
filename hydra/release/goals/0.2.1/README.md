# Goals

Everything you're working toward, on one plot: each goal with its pace, counted by the page that reads its data. Goals
comes free with Hydra-OS.

## Setting a goal

Tell Claude, in the chat beside your pages, what you're working toward: "swim twice a week again", or "save $5,000 for
a trip by June". Claude asks only what's missing, reads the goal back as Goals would save it, and saves it only when
you say yes. Every save has an Undo.

Goals doesn't keep a goal about a diagnosis, a medicine, a supplement or a dose, or one to buy, sell or hold a
security.

## Who counts it

Each page says for itself which goals it can count, such as Wellbeing for your workouts or Inbox for your replies.
A goal shows its pace once its page has read the data it needs. When no page counts it, Goals keeps it by hand: you
tell Claude the number when it moves.

## What it reads and keeps

- **Your goals,** in `yours/goals.json` in your Hydra-OS folder. Their words stay in that one file: the page, Home and
  Claude read them from there.
- **Each page's progress** for the goals it counts, from that page's own folder.

Goals works out each goal's pace on your Mac, in code, after each page's run and once a day. It starts no model, makes
no network call, sends nothing anywhere and adds no hook.

## Removing it

Tell Claude to remove Goals from Hydra-OS. Goals' own folder stays until you ask Claude to delete it, and your goals
stay in `yours/goals.json`: Home still shows them, with their pace from the pages that count them.
