---
name: set
description: Use whenever the person says what they're working toward - in the conversation beside their Hydra-OS pages, or in answer to "What are you working toward?" - such as "Swim twice a week", "Read 12 books by December" or "save $5,000 for a trip by June". Also use it when they say where a goal they keep by hand stands now ("I'm on my fifth book"), and when they want any change to a goal - its target, its date, the page that counts it, its words, why it matters, setting it aside, marking it done, bringing it back, removing it, or undoing a change. It saves what they say at once, says which installed app counts it, and every save has its Undo.
---

# Goals, through the conversation

A new goal starts here, with you. The person says what they're working toward here, in the conversation beside their pages, often in answer to "What are you working toward?". Each page's goal line points them to you. You save it as they say it, tell them who counts it, and connect what counts it. Their pages keep the quick edits on a goal already saved: its target and date, its words, why it matters, set aside, done, back, removing it, and Undo.

What they tell you is their choice, so you save it at once. You never save a goal they didn't ask for, and you never add a target or an amount they didn't give. A date they didn't give, Goals gives itself, and the saved line says so.

Everything goes through one command, `hydra goals`, which runs Goals' own save path. Every save is one step: run the command with `--yes`. It prints what was saved, then `undo fields: --change=<id>`. Say that line in your own words, and that they can undo it. Run the command without `--yes` only when you want to see the line first: that saves nothing.

## A new goal

### 1. Take it as they say it

A goal Goals can count has what's counted, how many, a date and, for a habit, how often ("3 a week"). Take every part their words already give.
- **Ask only for a number, and only when their words have none:** "How many?", or "How many a week?". One short question, once. If they'd rather not say, save it as they said it: Goals shows it as not counted yet.
- **Never ask by when.** With no date in their words, Goals gives it one: 12 weeks for a habit said as a rate, a year for any other target. The saved line says so, and the date changes on the goal any time.
- **Never ask where it stands today.** It starts at nothing today unless they've said where it stands. They can tell you later.

### 2. Who counts it

The pages installed say whether they count a goal, and as what: each page names the units it counts, and a page with its own check answers for itself. Goals asks them when you save, and the saved line says so: "Wellbeing counts it: any swim in your iPhone's Health data." Never say a page counts a goal before the saved line does.
- **Leave `--app` out,** and Goals asks the pages installed. What one counts is saved in the unit it gives. Anything no page counts is kept by hand, at once, and the line says so, with a page's reason when it has one: "Wellbeing doesn't read steps yet. You keep it by hand: tell Claude where it stands." When a page on sale counts it, the line ends "The Finance page can count this for you.": say it as the line has it, and no more.
- **Sleep and lights out** are counted in nights. The hours or the time stay in their words, and it's every night until they say otherwise: "Sleep 7 hours a night" saves as 7 nights a week. When they say how many nights, it's `--target=5 --per=week --unit=nights`.
- **When a page arrives that counts a goal kept by hand,** Goals moves the goal to it at once, and its page says so. If they'd rather keep it by hand, it's `hydra goals measure --goal=<id> --app=goals --yes`, or the change's Undo.

### 3. Save it

One `hydra goals add` carries every part:

```
hydra goals add --words='<the goal in their words>' --unit=<word> --target=<number> --by=YYYY-MM-DD --yes
```

- **`--words`:** the goal as they said it, one line of up to 120 characters. Keep their words. Put it in single quotes, so a `$` stays as typed, and write a single quote inside it as `'\''`.
- **How often:** `--target=<how many> --per=day|week|month`, so `--target=3 --per=week` is three a week. Goals works out the count to its date.
- **Where it starts,** when they've said it isn't at nothing today: `--from=<number>`, with `--on=YYYY-MM-DD` when it began another day.
- **What Goals reads from the line itself:** a date ("by Aug 1", "this year", "in 6 weeks"), a count or a sum ("12 books", "$20,000") and a rate ("twice a week"). You don't need to repeat those. A date they give that the line doesn't read goes in `--by`.
- **Several goals at once:** save each one in turn, and say each saved line.

The saved line ends with who counts it, and what Wellbeing still needs: "Wellbeing counts it: any swim in your iPhone's Health data. Wellbeing counts it once your health export is in." Say that, and no more than that.

### 4. Connect what counts it

- **When the page takes a file,** as Wellbeing takes their Apple Health export, say where it goes in one line: "On the Wellbeing page, drop your Apple Health export or choose it."
- **When it needs something connected,** follow the connect skill for that page, starting from this goal.
- **When its data is already in,** as when Wellbeing has read their Apple Health export, the save has it counted at once: say it's counted from the data read so far, and shows on their Goals page now.
- **When it's already connected** but nothing is read yet, say it starts counting at its next run.

After the save, tell them it's on their Goals page and on Home, in a line.

### Three examples, made up

- "Swim twice a week": `hydra goals add --words='Swim twice a week' --unit=swims --target=2 --per=week --yes`. Its line says Wellbeing counts it, and that it runs 12 weeks.
- "Run a 10k by spring": a distance, never 10 runs: `hydra goals add --words='Run a 10k by spring' --unit=km --target=10 --yes`. Its line says it's kept by hand. Each longer run they tell you is its new number.
- "Read 12 books by December": `hydra goals add --words='Read 12 books by December' --unit=books --target=12 --yes`. Its line says it's kept by hand.

## A goal kept by hand

When they tell you where it stands, save that number:

```
hydra goals progress --goal=<id> --value=<number> --yes
```

- Add `--on=YYYY-MM-DD` when the number is from another day than today.
- It saves at once: "Saved: 5 books, as of today.", with its Undo.
- Don't ask for numbers on your own schedule: the day's check-in, below, is Goals' one question. When they bring the goal up, take the number they give.

## The day's check-in

Once a day Goals has one question, "How's '{goal}' going?", about one goal. It's in `goals/home.json` in this folder (`questions`: its `id`, and the goal's `id`, whose words are in `yours/goals.json`), and Home shows it too. It's open until it has an `answer`.

- When it's open at a Hydra-OS chat's first turn, ask it once, in a few words, with the goal's words. Ask nothing more.
- Save their answer at once, in their own words, at most 120 characters: `hydra goals answer --question=<its-id> --words='<their-words>' --yes`.
- For a goal kept by hand, keep the number with its unit as they said it ("7 books", "$2,400"), so its pace moves. "2 more books" adds to the last number.
- Once it's answered, here or on Home, it carries an `answer`: don't ask it again that day. To take it back: `hydra goals unanswer --question=<its-id> --yes`.

## Changing a goal

Find the goal's `id` (`g-` and six characters) in `yours/goals.json` in this folder, by its words. Each change below saves at once, once they've said what they want.

| They want | The command |
|---|---|
| A new target or date | `hydra goals set --goal=<id> --words='12 swims by Sep 1' --yes` (or `--target`, `--by`, `--per`, `--unit`) |
| Wellbeing to count it, or by hand | `hydra goals measure --goal=<id> --app=health --yes`, which Wellbeing answers, or `--app=goals` for by hand |
| Where a goal kept by hand stands | `hydra goals progress --goal=<id> --value=<number> --yes` |
| Its words changed | `hydra goals reword --goal=<id> --words='<the new words>' --yes` |
| Why it matters, kept with it | `hydra goals because --goal=<id> --words='<their reason>' --yes` |
| Set aside, done, or back in hand | `hydra goals aside --goal=<id> --yes`, `done`, or `back` |
| Taken out for good | `hydra goals drop --goal=<id> --yes` |
| A change put back | `hydra goals undo --change=<id from undo fields> --yes` |

A goal past its date shows as missed until they give it a new date or set it aside. Its page offers both, and nothing waits on it. When they give you a date, it moves at once: `hydra goals set --goal=<id> --by=<YYYY-MM-DD> --yes`.

Goals never asks why a goal matters, or what got in its way. When they tell you why anyway, keep it with `hydra goals because`.

## When it says no

When `hydra goals` refuses, it says why in one plain line, and nothing is saved. Tell them that line as it is, and do what it says. Never work around it.
- Goals keeps no goal about a diagnosis, a medicine, a supplement or a dose, and none to buy, sell or hold an investment. Offer what the refusal offers: the habit behind it, or a sum to save.
- No goal holds an email address, a link, a phone number, a folder's path, a password or a key.

Speak to them in plain words about their goals and their pages, never about files, commands or how Hydra-OS is built.
