---
name: setup
description: Set up Hydra-OS on this Mac, in this chat, or pick its setup up again. Use when the person asks to set up Hydra-OS, or says "try again" after its setup stopped. Says in one sentence what installs, then runs one self-contained command, and moves the chat into their Hydra-OS folder with Home beside it.
---

# Set up Hydra-OS

1. **Say in one sentence what installs, then start.** Hydra-OS puts their pages in one folder, `~/Hydra-OS`, with its own copy of Python; it starts two helpers at login, Home's server, which shows their pages, and the tick, which starts each page's daily read; and a short morning review uses a little of their Claude plan each morning. They can turn the helpers or the review off in Help, any time. Their asking is their yes. TRANSPARENCY.md, at the top of Hydra-OS's repo, says everything Hydra-OS installs and does: show them anything they ask to see.
2. **Run this one command, whole, as it is.** Keep it one command: a change of folder and a shell variable don't carry from one command to the next. To try again, run the same command again; it picks up where it was left. If they said no to the helpers, add `--helpers no` to its hydra-setup line.

```sh
claude_code="$(ps -o comm= -p $PPID)"
if [ "${claude_code##*/}" != claude ]; then
  echo "This chat's Claude Code isn't this shell's parent, so nothing was changed. Use the official way below."
else
  get="$(mktemp -d -t hydra-os)" && cd "$get" && from=https://raw.githubusercontent.com/mynamejoi/hydra-os/main &&
  { curl -fsSL --proto '=https' -O "$from/catalog.json" -O "$from/catalog.json.sig" &&
    printf '%s\n' '-----BEGIN PUBLIC KEY-----' 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEDftLcdylOmR9zkw9faD4TsIB1nvQsT64WnVvsiY32R0TN/VDaS1pZegQumClEySA08LDiEiN1hqBZnp65slBmQ==' '-----END PUBLIC KEY-----' > key.pem &&
    /usr/bin/openssl base64 -d -A -in catalog.json.sig -out catalog.der &&
    /usr/bin/openssl dgst -sha256 -verify key.pem -signature catalog.der catalog.json &&
    zip="$(/usr/bin/plutil -extract core.zip raw -o - catalog.json)" &&
    sum="$(/usr/bin/plutil -extract core.sha256 raw -o - catalog.json)" &&
    curl -fsSL --proto '=https' -o core.zip "$from/$zip" &&
    got="$(/usr/bin/openssl dgst -sha256 core.zip)" && [ "${got##* }" = "$sum" ] &&
    /usr/bin/ditto -x -k core.zip core ||
    { echo "Hydra-OS's download didn't check out against its signed catalog, so nothing was changed."; false; }; } &&
  /bin/sh core/bin/hydra-setup --claude "$claude_code"
fi
```

   The Claude Code running this chat is your shell's parent process, so the command uses it rather than a `claude` command, which a Mac with the Claude app alone doesn't have. It checks Hydra-OS's signed catalog with the Mac's own openssl, then the core's zip against it, then runs Hydra-OS's own setup, which fetches its own Python, checked by its sha256, and prints "Adding your pages…" and "Starting them…" as it goes, then "Hydra-OS is set up." and what to do next. If a step stops it, it prints why in one line and changes nothing; tell them in your own words, and offer to try again. Never ask them to open Terminal or to type a command.

   If the command doesn't take, the official way is theirs to type, on a Mac with Apple's developer tools, in a new chat in the Code tab with `~/Hydra-OS` as its folder: `/plugin marketplace add mynamejoi/hydra-os`, then `/plugin install hydra@hydra-os-get`, choosing local scope when asked, then "Set up Hydra-OS".
4. **The chat into their folder, Home, and a short walkthrough.** Move this chat into `~/Hydra-OS` with the Claude app's own folder change, which asks them first. Then open Home in the Browser pane, from the Hydra-OS entry in `~/Hydra-OS/.claude/launch.json`, in one tab. Then, in a few short sentences, walk them through it: Home, beside the chat, shows their day and their goals, with each of their pages a tap away; they talk to you here, in their own words, to ask about or change anything; and it grows with them, as they ask you for new plots and new data and add pages from the Shop. Then ask: "What's one thing you're working toward?" Their answer is their first goal.

Home greets them by name, so never ask it. The rest of the first run follows from what they tell you next.
