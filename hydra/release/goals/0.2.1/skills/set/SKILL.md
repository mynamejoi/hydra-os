---
name: set
description: Use whenever the person says what they're working toward - in the conversation beside their Hydra-OS pages, or in answer to "What are you working toward?" - such as "Swim twice a week", "Read 12 books by December" or "save $5,000 for a trip by June". Also use it when they say where a goal they keep by hand stands now ("I'm on my fifth book"), and when they want any change to a goal - its target, its date, the page that counts it, its words, why it matters, setting it aside, marking it done, bringing it back, removing it, or undoing a change. It shapes a new goal with them, says which installed app measures it, and saves each step only after their yes to the exact line Goals reads back.
---

# Goals, through the conversation

A new goal starts here, with you. The person says what they're working toward here, in the conversation beside their pages, often in answer to "What are you working toward?". Each page's goal line points them to you. You shape it with them, say which app measures it, save it with their yes, and connect what measures it. Their pages keep the quick edits on a goal already saved: its target and date, its words, why it matters, set aside, done, back, removing it, and Undo.

A goal is saved only by the person's own yes to the exact line Goals reads back. You never save one they didn't ask for, and you never add a target, a date or an amount they didn't give.

Everything goes through one command, `hydra goals`, which runs Goals' own save path. Every save is two steps:

1. **The check.** Run the command without `--yes`. It saves nothing. It prints the goal as it would be saved, in one line, then `token: <t>`.
2. **The save.** Show the person that line, word for word, and ask if that's right. Only after a clear yes, run **the same command, with the same fields**, plus `--yes --token=<t>`. It prints what was saved, then `undo fields: --change=<id>`.

A token is good only until the goals change, so a save that's refused for its token needs its check run again.

## A new goal

### 1. Shape it

A goal Goals can count has four parts: what's counted, how many, by when, and, for a habit, how often ("3 a week"). Take every part their words already give. Ask only for what's missing, in one short question at a time: "By when?", "How many a week?", "How many do you have now?". Read it back after two questions at most.

If they'd rather not say, save it as they said it. Goals shows what's missing, and you can come back to it once.

### 2. Who counts it

The pages installed say whether they count a goal, and as what: each page names the units it counts, and a page with its own check answers for itself. Goals asks them when you run the check in step 3, and the check's line says so: "Wellbeing counts it: any swim in your iPhone's Health data." Never say a page counts a goal before that line does.
- **Leave `--app` out,** and Goals asks the pages installed. What one counts is saved in the unit it gives. Anything no page counts is kept by hand, and the line says so, with a page's reason when it has one: "Wellbeing doesn't read steps yet. You keep it by hand: tell Claude where it stands." When a page on sale counts it, the line ends "The Finance page can count this for you.": say it as the line has it, and no more.
- **Sleep and lights out** are counted in nights. The hours or the time stay in their words, and how many nights is the target: "Sleep 7 hours a night" is `--target=7 --per=week --unit=nights` once they say how many nights a week.
- **Kept by hand:** "I can keep it by hand. Tell me the number when it moves, and its plot follows what you tell me." Ask where it stands today, which is where its plot starts: `--from=<that number>`. When they'd rather keep it by hand anyway, it's `--app=goals`.
- **A new page, later:** "Or keep it as it is until a page for it comes to Hydra-OS." With their yes it's `--app=none`. They can move it to by hand at any time.
- **When a page arrives that fits a goal kept by hand,** Goals asks once, on its page and on Home: "Finance can count 'House deposit' now.", with "Count it" and "Not this one". In the chat, with their word, it's `hydra goals answer --question=<its id> --pick=count`, or `--pick=pass`, read back first as every save is.

### 3. Read it back, and save it

One `hydra goals add` carries every part, then its check, their yes and the save:

```
hydra goals add --words='<the goal in their words>' --unit=<word> --target=<number> --by=YYYY-MM-DD
```

- **`--words`:** the goal as they said it, one line of up to 120 characters. Keep their words. Put it in single quotes, so a `$` stays as typed, and write a single quote inside it as `'\''`.
- **How often:** `--target=<how many> --per=day|week|month`, so `--target=3 --per=week` is three a week. Goals works out the count to its date.
- **Where it starts,** when it isn't at nothing today: `--from=<number>`, with `--on=YYYY-MM-DD` when it began another day.
- **What Goals reads from the line itself:** a date ("by Aug 1", "this year", "in 6 weeks"), a count or a sum ("12 books", "$20,000") and a rate ("twice a week"). You don't need to repeat those.
- **Several goals at once:** run each one's check and show every line together. After their yes, save them one by one, running each check again right before its own save.

The check's line ends with who counts it, and what Wellbeing still needs: "Wellbeing counts it: any swim in your iPhone's Health data. Wellbeing counts it once your health export is in." Say that, and no more than that.

### 4. Connect what counts it

- **When the page takes a file,** as Wellbeing takes their Apple Health export, say where it goes in one line: "On the Wellbeing page, drop your Apple Health export or choose it." Don't try to open the page for them: they open the Wellbeing page themselves.
- **When it needs something connected,** follow the connect skill for that page, starting from this goal.
- **When its data is already in,** as when Wellbeing has read their Apple Health export, the save has it counted at once: say it's counted from the data read so far, and shows on their Goals page now.
- **When it's already connected** but nothing is read yet, say it starts counting at its next run.

After the save, tell them it's on their Goals page and on Home, in a line.

### Three examples, made up

- "Swim twice a week": ask "Until when?" To "till the end of March", the check is `hydra goals add --words='Swim twice a week' --unit=swims --target=2 --per=week --by=2027-03-31`, and its line says Wellbeing counts it.
- "Run a 10k by spring": a distance, never 10 runs. Ask "How far do you run now?" To "about 4 km", the check is `hydra goals add --words='Run a 10k by spring' --unit=km --from=4 --target=10 --by=2027-03-20`, and its line says it's kept by hand. Each longer run they tell you is its new number.
- "Read 12 books by December": ask "How many have you read so far?" To "3", the check is `hydra goals add --words='Read 12 books by December' --unit=books --from=3 --target=12 --by=2026-12-31`, and its line says it's kept by hand.

## A goal kept by hand

When they tell you where it stands, save that number:

```
hydra goals progress --goal=<id> --value=<number>
```

- Add `--on=YYYY-MM-DD` when the number is from another day than today.
- It's two steps, as every save: "Saved: 5 books, as of today.", with its Undo.
- Don't ask for numbers on your own schedule. When its page says to tell you where it stands, or they bring the goal up, ask once.

## Changing a goal

Find the goal's `id` (`g-` and six characters) in `yours/goals.json` in this folder, by its words. Each change below is two steps too.

| They want | The command |
|---|---|
| A new target or date | `hydra goals set --goal=<id> --words='12 swims by Sep 1'` (or `--target`, `--by`, `--per`, `--unit`) |
| Wellbeing to count it, or by hand | `hydra goals measure --goal=<id> --app=health`, which Wellbeing answers, or `--app=goals` for by hand, or `--app=none` |
| Where a goal kept by hand stands | `hydra goals progress --goal=<id> --value=<number>` |
| Its words changed | `hydra goals reword --goal=<id> --words='<the new words>'` |
| Why it matters, kept with it | `hydra goals because --goal=<id> --words='<their reason>'` |
| Set aside, done, or back in hand | `hydra goals aside --goal=<id>`, `done`, or `back` |
| Taken out for good | `hydra goals drop --goal=<id>` |
| A change put back | `hydra goals undo --change=<id from undo fields>` |

A goal past its date stays missed until they give it a new date or set it aside. A new date moves it at once: `hydra goals set --goal=<id> --by=<YYYY-MM-DD>`, after they've said the date. Setting it aside is `hydra goals aside --goal=<id>`. Goals' page offers both too.

In a new goal's first week, Goals' page and Home ask why it matters, "Why does '<the goal's words>' matter to you?", when it has no why yet. So don't ask it yourself when the goal is saved. If they answer it here instead, keep it with `hydra goals because`, and the question goes.

## When it says no

When `hydra goals` refuses, it says why in one plain line, and nothing is saved. Tell them that line as it is, and do what it says, with their yes. Never work around it.
- Goals keeps no goal about a diagnosis, a medicine, a supplement or a dose, and none to buy, sell or hold an investment. Offer what the refusal offers: the habit behind it, or a sum to save.
- No goal holds an email address, a link, a phone number, a folder's path, a password or a key.

Speak to them in plain words about their goals and their pages, never about files, commands or how Hydra-OS is built.
