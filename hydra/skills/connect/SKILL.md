---
name: connect
description: Connect a person's own source to a Hydra-OS page - their mail, calendar, money, Health data, video numbers, or a file they export. Use when they say "connect ...", name a service they use, ask what they can connect, or a page tells them to ask Claude to connect something. Finds the way the page reads, walks them through it one step at a time, checks it reads, and records it with hydra sources add.
---

# Connect a source

The person connects their own accounts. You find the way the page reads, walk them through it, check that it reads, and tell the page.

Keep every message short: one step, its link, and what happens next.

**When a page sent them:** the Hydra-OS page context on their message says when they tapped Connect on a page, which page, what it needs ("Connect your mail") and, when they tapped one service's line, which service. Start from that, and don't ask what they already told the page.

**First, every time:** if their message holds a password, a code, a token or any other secret, your reply's first line says you won't use it, where it goes instead (the service's own sign-in page), and that they may want to change it now that it's in this chat. Then carry on.

## 1. What, and for which page
- Name the service and the page it feeds. The pages are Hydra-OS's own (Wellbeing, Finance, People...), not Apple's Health app or any other. `sources.md`, beside this file, lists what each page reads and the way in for each service.
- Only a source the page reads: a service `sources.md` doesn't list feeds no page yet, so say which page could use it, or keep it for later.
- If they name only a need ("my sleep"), ask in one line what they use.

## 2. Is it already there?
- For a Claude connector, run `session_connectors_status` when you have it. Without it, ask them to look under the + beside the message box, then Connectors.
- Connected and on: go to 4.
- On the account but off in this conversation: turn it on with `set_session_connector_enabled` after their yes. Its tools arrive on your next turn, so end the turn and say so.
- Needs sign-in: say where, in the Claude app's own words: the + beside the message box, then Connectors, or Claude's Settings, then Connectors. Never a command to type.

## 3. Walk them through it
- **A Claude connector,** made by the service itself, as `sources.md` names it. One step at a time, each naming the exact place, with the link written out: claude.ai/settings/connectors works in every window. Ask for read access only, and tell them to block anything that sends, writes, orders, trades or deletes where the connector lets them set each tool. The page's own hook lets only its listed reads through either way.
- **A file they export,** dropped on the page. Say where in their app the export is, and that they drop the file on the page, not into the chat.
- **Free first.** When a way costs money (a paid plan), say so in one line and let them decide. Never sign up, start a trial or pay for anything.
- **Their sign-in, their keys.** Never type, ask for, accept or repeat a password, code, token or secret. The first rule above says what to do when one arrives.
- Then wait for them to say it's done.

## 4. Check that it reads
- Make one small read and report a count, never the contents: "I can see 214 nights of sleep since May."
- A connector they just added reaches this conversation only once it's on here (step 2). If it isn't listed at all yet, a new conversation picks it up: say so, and that nothing is lost, since the page's own files are on this Mac. Never guess that it works.
- A page reads a connector in the morning review, a scheduled task in the Claude app that runs only after their yes, and a dropped file in its daily read on this Mac.

## 5. Tell the page
- Record it, after their yes: `hydra sources add <page> <service> --via <connector|file|typed> --reads "<what it reads>"`.
  - For a file they export (`--via file`), the name is what the file is, such as "Apple Health export". It fills the page's own upload source and says where to drop the file and which kinds it takes.
  - For a connector, add `--server "<its name as Claude lists it>"`, such as `--server "claude.ai Gmail"`. Only that server's read tools reach the page.
  - For a second account of the same service, add `--account <their own word for it>`, such as `personal` or `work`. Never an address.
  - It refuses a secret, a page that isn't installed, and a connector that isn't connected yet, each in plain words. It keeps names only.
- Recording it also closes the Connect request the page sent, so the page stops asking.
- Then one line: what's connected and what it reads. For a file, offer to fill the page in now: on their yes, run `hydra run <page>`. For a connector, say the morning review reads it, and offer to start that review now.
