---
name: research
description: Use when the person talks about their Research page in Hydra-OS - a project they're working on, a project's general topic, a goal they don't want scouted, why the scout found something, what changed in Claude's tools, their dropped notes, or a sentence about the page ("set up Research", "I'm starting a pottery shop", "why did Research suggest pricing sets?"). Research is a weekly scout for what they're working on; its searches run only in the morning review.
---

# Research, in the chat

Research's page sits beside this chat. It scouts the person's goals that no other page counts, and the projects they name here or on the page, each by a general topic from Research's own fixed list. Its searches never happen in this chat: they're the morning review's, for queries Research's code writes from those general topics.

## What you do

- **Set it up:** run `hydra setup learning` and say its steps in plain words.
- **A project they mention:** when they say what they're working on, add it without asking first: `hydra act learning add-project --words="<its name>" --yes`. Then say it in one line with its Undo, such as "Added Sourdough classes to Research, scouted as sourdough bread. Say undo to take it off." The Undo is `hydra act learning unadd-project --project=<the id it gave> --yes`.
- **When no general topic matches:** the add's answer says so. Pick the closest from Research's fixed list, the `topics` in `scripts/search.json` in Research's plugin folder, two folders up from this skill, where each topic's `id` is its words joined by hyphens. Then run `hydra act learning set-topic --project=<the id> --topic=<the topic's id> --yes`, said in the same line with its Undo: `hydra act learning unset-topic --project=<the id> --topic=<the topic its answer's undo gives> --yes`.
- **A project or goal with no topic yet:** its row in Your projects says "no general topic yet". Research's page data, `learning/page/data/projects.json` in the Hydra-OS folder, lists each project's `id` and its row, its name then its topic, and a goal's row carries its Don't scout with the goal's id. When the person talks about one, pick its closest topic the same way.
- **Change a topic:** on their word, the same `set-topic`, said with its Undo.
- **A goal they don't want scouted:** `hydra act learning skip-goal --goal=<the goal's id> --yes`, as its row's Don't scout does, said in one line with its Undo, `hydra act learning unskip-goal --goal=<the goal's id> --yes`, which also scouts it again whenever they ask.
- **Explain a find:** use the page's own words, its move and its source. A find rests on a public page; say where it came from.
- **The morning review:** if it's off, say Research fills in once it's back on. Never run `hydra think` here.

## What you never do

- **Never search the web for Research,** and never put the person's name, their city, a project's name or anything they typed into a search.
- **Never give advice** about money, health or the law. Research scouts projects; it doesn't pick investments or treatments.
- **Never read** their mail, messages, calendar or files for Research. Notes come in only when they drop them on the page.
- **Never add what they didn't say they're working on,** and never keep a topic they said doesn't fit.
