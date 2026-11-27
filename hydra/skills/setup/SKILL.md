---
name: setup
description: Set up Hydra-OS on this Mac, in this chat, or pick its setup up again. Use when the person asks to set up Hydra-OS, or says "try again" after its setup stopped. Explains each step in plain words and asks before each one, asks whether Hydra-OS's two helpers may start at login, runs hydra-setup, then moves the chat into their Hydra-OS folder and opens Home beside it.
---

# Set up Hydra-OS

Explain each step in your own words before you take it, and ask before each one. When they ask what a step runs or changes, show them, and answer any question they have. TRANSPARENCY.md, at the top of Hydra-OS's repo, says everything Hydra-OS installs and does.

## 1. Apple's developer tools

Hydra-OS runs on Apple's own `python3`, which comes with Apple's free developer tools. `hydra-setup` checks they're there. When they aren't, it opens Apple's own installer and stops; once it's done, run `hydra-setup` again.

## 2. The helpers

Ask whether Hydra-OS's two helpers may start each time they log in to this Mac: Home's server, which shows their pages, and the tick, which starts each page's daily read every 15 minutes. With a no, nothing of Hydra-OS runs while no Hydra-OS chat is open: Home's server starts with a Hydra-OS chat and stops after the last one, and the day's reads catch up then. Either way, they can change it later: `hydra helpers on` or `hydra helpers off`.

## 3. hydra-setup

Run it by its full path in this plugin's own folder, with the Claude Code running this chat and their answer:

```
<this plugin's folder>/bin/hydra-setup --claude <the Claude Code running this chat> --helpers yes|no
```

The Claude Code running this chat is your shell's parent process: `ps -o comm= -p $PPID` prints its full path, ending in `/claude`. Setup uses it for Claude Code's own plugin commands, since a Mac with the Claude app alone has no `claude` command.

As it works it prints "Adding your pages…" and "Starting them…". At its end it prints "Hydra-OS is set up." and what to do next. If a step stops it, it prints why in one line and changes nothing; tell them in your own words, and run it again when they say "try again". It picks up where it was left.

## 4. The chat into their folder, and Home

Move this chat into `~/Hydra-OS` with the Claude app's own folder change, which asks them first. Then open Home in the Browser pane, from the Hydra-OS entry in `~/Hydra-OS/.claude/launch.json`, in one tab.

Home's welcome sheet asks their name, so don't ask it here. The rest of the first run follows from Home and from what they tell you next.
