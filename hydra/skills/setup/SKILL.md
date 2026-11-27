---
name: setup
description: Set up Hydra-OS on this Mac, in this chat, or pick its setup up again. Use when the person asks to set up Hydra-OS, or says "try again" after its setup stopped. Says in plain words what installs, asks once (with whether Hydra-OS's two helpers may start at login), then runs one self-contained command, and moves the chat into their Hydra-OS folder with Home beside it.
---

# Set up Hydra-OS

1. **Tell them what installs,** in a few plain sentences: one folder, `~/Hydra-OS`, with their pages and their own files; Hydra-OS itself, Goals and Wellbeing, as Claude Code plugins that are on only in chats in that folder; and, only with their yes, two helpers that start at login: Home's server, which shows their pages, and the tick, which starts each page's daily read every 15 minutes. With a no, nothing of Hydra-OS runs while no Hydra-OS chat is open, and the day's reads catch up when one opens. TRANSPARENCY.md, at the top of Hydra-OS's repo, says everything Hydra-OS installs and does.
2. **Ask once:** may you set it up, and may the two helpers start at login? Their answer to the helpers is `yes` or `no`, and they can change it later with `hydra helpers on` or `hydra helpers off`. Show them anything they ask to see, and answer any question.
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

   The Claude Code running this chat is your shell's parent process, so the command uses it rather than a `claude` command, which a Mac with the Claude app alone doesn't have. When Apple's free developer tools aren't there, it opens Apple's own installer and changes nothing else; once it's done, run the same command again. Otherwise it makes `~/Hydra-OS`, installs Hydra-OS there at local scope, and runs Hydra-OS's own setup, which prints "Adding your pages…" and "Starting them…" as it goes, then "Hydra-OS is set up." and what to do next. If a step stops it, it prints why in one line and changes nothing; tell them in your own words.

   If the command doesn't take, the official way is theirs to type in a new chat in the Code tab with `~/Hydra-OS` as its folder: `/plugin marketplace add mynamejoi/hydra-os`, then `/plugin install hydra@hydra-os-get`, choosing local scope when asked, then "Set up Hydra-OS".
4. **The chat into their folder, and Home.** Move this chat into `~/Hydra-OS` with the Claude app's own folder change, which asks them first. Then open Home in the Browser pane, from the Hydra-OS entry in `~/Hydra-OS/.claude/launch.json`, in one tab.

Home's welcome sheet asks their name, so don't ask it here. The rest of the first run follows from Home and from what they tell you next.
