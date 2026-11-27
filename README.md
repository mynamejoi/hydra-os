# Hydra-OS

Your day, your goals and your wellbeing, on pages that live inside Claude. Hydra-OS is a set of Claude Code plugins for the Claude app on a Mac: Home, Goals and Wellbeing come with it, and they fill in from your own data, kept as files on your Mac in one folder, `~/Hydra-OS`.

**[TRANSPARENCY.md](TRANSPARENCY.md)** says everything Hydra-OS installs, runs and reaches, and how to remove it. Read it first.

## Install it through Claude

Open the Claude app on your Mac, start a new chat in the Code tab, and paste this line:

```text
Install Hydra-OS from https://github.com/mynamejoi/hydra-os. Read its README and TRANSPARENCY.md first, tell me plainly what it will install, and ask me before each step.
```

It takes a few minutes. Claude asks before each step. You need a Mac with macOS 13 or later and a Claude plan (Pro or higher).

## For Claude: the steps

Tell the person what each step does, in your own words, before you take it, and ask before each one. Show them what a step runs when they ask, and answer any question.

1. **Apple's developer tools.** Hydra-OS runs on Apple's own `python3`, and Claude Code adds this repo's plugin list with `git`; both come with Apple's free developer tools. Check with `xcode-select -p`. If that fails, `xcode-select --install` opens Apple's own installer; go on once it's done.
2. **The folder.** `mkdir -m 700 ~/Hydra-OS`. Everything Hydra-OS keeps lives there.
3. **The plugin, at local scope inside that folder.** Use the Claude Code that runs this chat, not a `claude` command: a Mac with the Claude app alone has none, and this chat's own copy is the one already signed in. Its full path is your shell's parent process, a path ending in `/claude`:

   ```sh
   cd ~/Hydra-OS
   claude_code="$(ps -o comm= -p $PPID)"
   "$claude_code" plugin marketplace add mynamejoi/hydra-os --scope local
   "$claude_code" plugin install hydra@hydra-os-get --scope local
   ```

   Local scope means Hydra-OS's hooks and skills are on only in chats in `~/Hydra-OS`, and off in every other chat.
4. **The helpers.** Ask whether Hydra-OS's two helpers may start each time they log in to this Mac: Home's server, which shows their pages, and the tick, which starts each page's daily read every 15 minutes. With a no, nothing of Hydra-OS runs while no Hydra-OS chat is open: Home's server starts with a Hydra-OS chat, and the day's reads catch up then. They can change it later.
5. **Setup.** From `~/Hydra-OS`, `"$claude_code" plugin list --json` gives `hydra@hydra-os-get`'s `installPath`. Run its `bin/hydra-setup` with the same Claude Code and their answer:

   ```sh
   "<installPath>/bin/hydra-setup" --claude "$claude_code" --helpers yes   # or --helpers no
   ```

   It prints its steps as it goes, and at its end what comes next: moving this chat into `~/Hydra-OS` with the Claude app's own folder change, and opening Home beside it. If a step stops it, it says why in one line and changes nothing; running it again picks up from there.

### If a step doesn't take

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
