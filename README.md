# Hydra-OS

Your day, your goals and your wellbeing, on pages that live inside Claude. Hydra-OS is a set of Claude Code plugins for the Claude app on a Mac: Home, Goals and Wellbeing come with it, and they fill in from your own data, kept as files on your Mac in one folder, `~/Hydra-OS`.

**[TRANSPARENCY.md](TRANSPARENCY.md)** says everything Hydra-OS installs, runs and reaches, and how to remove it. Read it first.

## Install it through Claude

Open the Claude app on your Mac, start a new chat in the Code tab, and paste this line:

```text
Install Hydra-OS from https://github.com/mynamejoi/hydra-os. Read its README and TRANSPARENCY.md first, tell me plainly what it will install, then ask me once before you start.
```

It takes a few minutes, longer the first time if your Mac needs Apple's developer tools. Claude asks you once, then sets it up. You need a Mac with macOS 13 or later and a Claude plan (Pro or higher).

## For Claude: the steps

1. **Tell them what installs,** in a few plain sentences, from TRANSPARENCY.md: one folder, `~/Hydra-OS`, with their pages and their own files; Hydra-OS itself, Goals and Wellbeing, as Claude Code plugins that are on only in chats in that folder; and, only with their yes, two helpers that start at login: Home's server, which shows their pages, and the tick, which starts each page's daily read every 15 minutes. With a no, nothing of Hydra-OS runs while no Hydra-OS chat is open, and the day's reads catch up when one opens.
2. **Ask once:** may you set it up, and may the two helpers start at login? Their answer to the helpers is `yes` or `no`. Show them anything they ask to see, and answer any question.
3. **Run this one command, whole, as it is,** with their answer in its last line. Keep it one command: a change of folder and a shell variable don't carry from one command to the next. To try again, run the same command again; it picks up where it was left.

```sh
claude_code="$(ps -o comm= -p $PPID)"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install
  echo "Apple's installer for its free developer tools is open. Once it's done, run this same command again."
elif [ "${claude_code##*/}" != claude ]; then
  echo "This chat's Claude Code isn't this shell's parent, so nothing was changed. Use the official way below."
else
  mkdir -p -m 700 ~/Hydra-OS && cd ~/Hydra-OS &&
  { "$claude_code" plugin marketplace add mynamejoi/hydra-os --scope local || "$claude_code" plugin marketplace update hydra-os-get; } &&
  "$claude_code" plugin install hydra@hydra-os-get --scope local &&
  plugin="$("$claude_code" plugin list --json | /usr/bin/python3 -c 'import json, sys; print(next(p["installPath"] for p in json.load(sys.stdin) if p.get("id") == "hydra@hydra-os-get"))')" &&
  "$plugin/bin/hydra-setup" --claude "$claude_code" --helpers yes
fi
```

What it does, in order:

- **The Claude Code running this chat** is your shell's parent process, so `ps -o comm= -p $PPID` gives its full path, ending in `/claude`. The command uses it, not a `claude` command: a Mac with the Claude app alone has none, and this chat's own copy is already signed in.
- **Apple's free developer tools first.** Hydra-OS runs on Apple's own `python3`, and Claude Code adds this repo with `git`; both come with them. Without them, Apple's own installer opens, and nothing else happens.
- **The folder,** `~/Hydra-OS`, readable only by them, then this repo's plugin list and Hydra-OS itself, installed at local scope there, so Hydra-OS's hooks and skills are on only in chats in `~/Hydra-OS`, and off in every other chat.
- **Hydra-OS's own setup,** `hydra-setup`, from the plugin just installed, with this chat's Claude Code and their answer. It prints its steps, and at its end what comes next: moving this chat into `~/Hydra-OS` with the Claude app's own folder change, and opening Home beside it. If a step stops it, it says why in one line and changes nothing.

### If the command doesn't take

The official way, typed by the person: start a new chat in the Code tab with `~/Hydra-OS` as its folder, type these two lines one at a time, choose local scope when asked, then say "Set up Hydra-OS".

```text
/plugin marketplace add mynamejoi/hydra-os
/plugin install hydra@hydra-os-get
```

## What's in it

- **Home:** your day and your goals on one page.
- **Goals:** what you're working toward, and how it's going.
- **Wellbeing:** your sleep, resting heart and workouts, from your iPhone's Health data. Wellness only: no diagnosis.

More pages are on Home's Shop page. Nothing is for sale yet.

## Your data

Your records stay as files on your Mac, in `~/Hydra-OS`. There's no server of ours, and Hydra-OS sends nothing about you anywhere. Hydra-OS's catalog of pages and updates is signed; its key's fingerprint is `da0ff2dedb55bbcc449d6ffc5e8e881b89f3b7186a680a0a3e2f11183d07193d`.

## Remove it

Say "remove Hydra-OS" in a Hydra-OS chat. Claude asks first, then stops the helpers, takes the plugins out of Claude Code, and moves your Hydra-OS folder to the Trash whole, so you can take it back. Your Claude chats stay in Claude. TRANSPARENCY.md has the steps by hand.

---

Hydra-OS uses Claude, an AI. Its answers can be wrong. Hydra-OS isn't affiliated with or endorsed by Anthropic.
