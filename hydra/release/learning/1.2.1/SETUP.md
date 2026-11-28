# Setting Research up

Research comes with Hydra-OS, free, and is set up by Hydra-OS, not by itself. Hydra-OS installs it with Home and Goals and makes its folder, `<root>/learning/`. Research loads no job of its own: Hydra-OS starts its run once a day, and its weekly scout is part of the morning review.

There's nothing to buy, connect or answer, and no password or key to give. From the start, it works with what the person already has:

- **Their goals.** Every active goal that no other page counts is scouted, from the next morning review. A goal's row in Your projects has Don't scout, with its Undo.
- **What they tell Claude.** When they say what they're working on, Claude adds it with `hydra act learning add-project --words="<its name>" --yes` and says so in one line with its Undo. They can also type a project's name in Your projects on Research's page.
- **Each project's general topic,** from Research's own fixed list, such as "handmade ceramics" or "indie game marketing". It's matched from the project's own words on this Mac. When none matches, Claude picks the closest when the person talks about it, and they can change it by telling Claude. Research searches only these topics, never a project's name.
- **The morning review,** which Hydra-OS turns on at install. Research's scout runs there, on Monday morning, and its first scout at the first morning review after it has a project with a topic. Its Monday review uses some of your Claude plan. With the review off, Research shows release notes and notes only, and its page says it fills in once the review is back on.
- **Optionally, their own notes,** dropped on Research's page as .md or .txt files. They stay on this Mac and are never sent anywhere.

## What it reads, and what it never does

- **Web search:** Claude's own search, in the morning review only, for queries Research's code writes from its fixed list of general topics and the month. Never the person's name, city, project names or anything they typed.
- **Public release notes:** Claude Code's, the Claude API's and the Claude app's, and the official plugin marketplace, read each morning in code with no sign-in (allow.json).
- **Notes the person drops on the page,** read on this Mac only.
- **Never:** mail, messages, calendar, contacts, social accounts, their Claude conversations, or any file but what they drop. Never advice about money, health or the law.

## Remove it

- Tell Claude to remove Research from Hydra-OS. Hydra-OS stops starting its run.
- Research's folder, `<root>/learning/`, stays until the person deletes it. It holds their projects, their notes and the finds.
