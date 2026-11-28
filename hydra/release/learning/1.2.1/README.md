# Research

A weekly scout for what you're working on: what's new, what you're missing, and how it could sell.

Research is a page in Hydra-OS. It runs on your Mac, inside your own Claude, and keeps everything it learns in a folder on your Mac.

## What it does

- **Each Monday,** your morning review runs a few web searches for three of your projects, the ones scouted longest ago, so each gets its turn, and Claude writes up to six finds from what comes back: for each project, one thing worth doing next, with the page it came from.
- **Your projects** are your goals and what you tell Claude you're working on, or type on Research's page. Each one gets a row: what to learn, how it could sell, what's new, its openings, its gaps, and Claude skills for it. Don't scout on a goal's row takes it off.
- **How to sell it** shows the project closest to selling in five parts: who buys, what they pay, where they are, who else sells it, and your proof.
- **Every morning,** Research reads the public release notes for Claude Code, the Claude app, the Claude API and the plugin marketplace, so you can see what changed in Claude's tools.
- **Your own notes,** dropped on the page as .md or .txt files, back what the scout finds.

## What leaves your Mac

- **The Monday searches,** run with Claude's own web search during your morning review. Research writes each one in code from a fixed list of general topics and the month, such as "handmade ceramics news November 2026". Each project's topic is matched from its own words on your Mac, or picked by Claude in your chat when none matches. A search never holds your name, your city, a project's name or anything you typed, and Hydra-OS checks each one again before it runs. The morning review sees only each project's topics.
- **Plain requests for the public release-note pages** listed in `allow.json`, with no sign-in and nothing of yours in them.

Nothing else is sent anywhere. Your notes, your projects and the finds stay on your Mac.

## What it never does

- It never reads your mail, messages, calendar, contacts or any file you didn't drop on its page.
- It never sends a message or posts anything.
- It never gives advice about money, health or the law.
- Its daily run never starts Claude. Only the Monday step of your morning review uses Claude, under your own account.

## How much of your Claude plan it uses

Its Monday review uses some of your Claude plan, and so does its first scout, at the first morning review after it has one of your goals or projects. Other mornings use none, unless Monday's searches couldn't run; then the next morning tries once more.

## Where its files live

In `~/Hydra-OS/learning/` on your Mac: your projects, the finds of the last twelve weeks, your notes and the release notes it has read. Nothing is kept on a server.

## Setting it up

Research comes with Hydra-OS, free, beside Home and Goals. There's nothing to buy or set up: it scouts your goals from the next morning review, and anything you tell Claude you're working on. [SETUP.md](SETUP.md) says what it uses.

## Removing it

Tell Claude to remove Research from Hydra-OS. Its folder stays until you delete it.

## What's changed

See [CHANGELOG.md](CHANGELOG.md).
