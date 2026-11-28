# Hydra-OS

Your day, your goals and your wellbeing, on pages that live inside Claude. Hydra-OS is a set of Claude Code plugins for the Claude app on a Mac: Home, Goals and Wellbeing come with it, and they fill in from your own data, kept as files on your Mac in one folder, `~/Hydra-OS`.

**[TRANSPARENCY.md](TRANSPARENCY.md)** says everything Hydra-OS installs, runs and reaches, and how to remove it. Read it first.

## Install it through Claude

Hydra-OS puts your pages in a Hydra-OS folder on your Mac, with its own copy of Python. Two helpers start when you log in, to show your pages and keep them fresh, and a short morning review uses a little of your Claude plan each day. Nothing about you is sent anywhere. Turn any of it off, or remove Hydra-OS, in Help.

Open the Claude app on your Mac, start a new chat in the Code tab, and paste this line:

```text
Install Hydra-OS from https://github.com/mynamejoi/hydra-os, with its helpers and morning review on.
```

It takes a few minutes. You need a Mac with macOS 13 or later, the Claude app and a Claude plan (Pro or higher), and nothing else: no Apple developer tools, no Terminal.

## For Claude: the steps

1. **Their message asks for Hydra-OS with its helpers and morning review on.** Check what you'd like to check. Then, in the reply that runs the command, first tell them in a few plain sentences what it sets up: their pages in a Hydra-OS folder on this Mac with its own copy of Python; two helpers that start at login to show their pages and keep them fresh; a short morning review that uses a little of their Claude plan each day; nothing about them sent anywhere; and that Help turns any of it off or removes Hydra-OS. If their message didn't say yes to the helpers, ask once, and add `--helpers no` if they say no.
2. **Run this one command, whole, as it is.** Keep it one command: a change of folder and a shell variable don't carry from one command to the next. To try again, run the same command again; it picks up where it was left.

```sh
claude_code="$(ps -o comm= -p $PPID)"
if [ "${claude_code##*/}" != claude ]; then
  echo "This chat's Claude Code isn't this shell's parent, so nothing was changed. Start a new chat in the Claude app's Code tab and paste the install line again."
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

What it does, in order:

- **The Claude Code running this chat** is your shell's parent process, so `ps -o comm= -p $PPID` gives its full path, ending in `/claude`. The command uses it, not a `claude` command: a Mac with the Claude app alone has none, and this chat's own copy is already signed in.
- **Hydra-OS's signed catalog, checked first.** It fetches this repo's `catalog.json` and its signature, `catalog.json.sig`, into a folder of its own, and the Mac's own `/usr/bin/openssl` checks the signature against Hydra-OS's public key, written out in the command. Its fingerprint, the sha256 of that key, is `da0ff2dedb55bbcc449d6ffc5e8e881b89f3b7186a680a0a3e2f11183d07193d`, as on the download page.
- **Hydra-OS itself,** the zip that catalog names for the core, checked against the sha256 the catalog gives, then unpacked with the Mac's own `ditto`. If any of it doesn't check out, it says so in one line and changes nothing.
- **Hydra-OS's own setup,** `hydra-setup`, from that zip, with this chat's Claude Code. It fetches Hydra-OS's own Python, the build of Astral's python-build-standalone for this Mac's chip, and checks it against the sha256 Astral publishes before it's unpacked. Then it makes `~/Hydra-OS`, readable only by them, installs the plugins there at local scope, so Hydra-OS's hooks and skills are on only in chats in `~/Hydra-OS`, and starts the helpers. It prints its steps, and at its end what comes next: moving this chat into `~/Hydra-OS` with the Claude app's own folder change, opening Home beside it, and a short walkthrough. If a step stops it, it says why in one line and changes nothing.

Nothing in it uses `git`, Apple's developer tools or the Mac's own `python3`.

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
