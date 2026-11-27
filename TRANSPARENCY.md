# What Hydra-OS installs

Everything Hydra-OS puts on your Mac, everything it runs, every address it reaches, and how to remove it. This is Hydra-OS 1.0.0.

## The folder

Everything Hydra-OS keeps is in one folder, `~/Hydra-OS`, readable only by you (mode 0700):

- `hydra/`: Hydra-OS's own files: its settings (`config.json`), the list of your pages (`registry.json`), how each read went (`health.json`), its own store of pages (`hydra/store/`, the copies Claude Code loads), the `hydra` command and a few small tools (`hydra/bin/`), its log (`hydra/logs/hydra.log`), Home's page, and the backup it makes before an update.
- `yours/`: what you chose: your goals, your sources, your settings, and any notes you leave for Claude.
- A folder for each page, such as `health/` and `goals/`: what that page reads and keeps.
- `.claude/`: `settings.json` lets Claude run Hydra-OS's own `hydra` command, and lets the morning review write its answers in `hydra/think/answers/`; `settings.local.json` is Claude Code's own list of the plugins turned on in this folder; `launch.json` lets the Claude app's Browser pane open Home.

## The plugins

Hydra-OS itself (`hydra`), Goals and Wellbeing are Claude Code plugins, installed at local scope in `~/Hydra-OS`, so they're on only in chats in that folder and off in every other chat. Setup installs them from Hydra-OS's own store, `~/Hydra-OS/hydra/store/`, copied from this repo, then removes this repo's plugin list (`hydra-os-get`) from Claude Code. From then on, every update comes only through `hydra update`, and only once its signature checks out (The signing key, below). A page you add later from Home's Shop is installed the same way.

## The two background helpers

They run only if you said yes to them at setup.

- **Home's server** starts each time you log in to this Mac, as the launch agent `os.hydra.home`, in `~/Library/LaunchAgents/os.hydra.home.plist`. It serves your pages on this Mac's own loopback address only, `127.0.0.1`, on port 8792 or the next free one, and takes writes only from its own pages.
- **The tick** runs every 15 minutes, as the launch agent `os.hydra.tick`, in `~/Library/LaunchAgents/os.hydra.tick.plist`. It starts each page's daily read once it's due, in Python on this Mac, reading only files on your Mac. It never starts Claude Code or a model.
- Both show as Hydra-OS in System Settings, General, Login Items.

**To turn them off,** say "turn the helpers off" in a Hydra-OS chat: Claude runs `hydra helpers off`, which stops both and removes their launch agents. "Turn the helpers on" starts them at login again.

**With the helpers off,** nothing of Hydra-OS runs while no Hydra-OS chat is open. Home's server starts with a chat in `~/Hydra-OS` and stops when the last one ends, and each chat's start runs the tick once, so the day's reads catch up then.

## The hooks

Every hook's first step returns at once unless the chat's folder is `~/Hydra-OS`, before it reads anything or starts anything.

Hydra-OS itself:

- **SessionStart** (`hooks/primer.py`): a short note to Claude about your pages, given as data, not as instructions. It puts Hydra-OS's own tools first on the path for the chat's commands, and notes which Claude Code runs the chat (the hook's own parent process), so the chat's `hydra` steps use the same one; with none noted, they use the `claude` command on your path, if you have one, and Hydra-OS never looks anywhere else. With the helpers off, it starts Home's server and the tick once.
- **UserPromptSubmit** (`hooks/prompt.py`): a message that looks like it holds a password or a key is stopped before Claude sees it, and you're told why. Otherwise, where you are on your pages, as data.
- **PreToolUse** (`hooks/review_fence.py`): only while the morning review runs, Claude may use only `hydra think` and the reads it lists.
- **PostToolUse on WebSearch** (`hooks/review_keep.py`): only while the morning review runs, each search a page listed keeps its answer for that page.
- **SessionEnd** (`hooks/session_end.py`): the morning review's fence lifts when its chat ends; with the helpers off, Home's server stops after the last Hydra-OS chat.

Goals and Wellbeing have no hooks. Of the pages you can add later, Research and Content have none. Finance has one: before a connector tool runs, it refuses every brokerage, bank or card tool that isn't one of Finance's listed reads, any tool it doesn't know whose name carries a money word, and every tool it doesn't know on a connector it has seen carry a Robinhood or Monarch tool. It notes those connectors' ids in Finance's own folder, `lock/servers.json`, and nowhere else. People and Inbox each have a lock on connector tools: only Gmail's and Google Calendar's reading tools pass, and each answer is cut down to what the page uses before Claude sees it. Each page's own README says more.

## Every address it reaches

Hydra-OS's own code reaches only these:

- **The catalog of pages and updates,** `https://raw.githubusercontent.com/mynamejoi/hydra-os/main/catalog.json`, or its mirror `https://mynamejoi.github.io/hydra-os/catalog.json` when the first doesn't answer: at most once in 20 hours, from the tick, and when you add or update a page. It's a plain request that sends nothing about you, and nothing in it is used until its signature checks out.
- **An update or a page you add,** from the same places, checked against the sha256 the signed catalog gives.
- **A link on a page that leaves it** opens in your own browser, only when you click it. Home's Privacy page links to Anthropic's own privacy policy, `https://www.anthropic.com/legal/privacy`, in the same way.

Claude Code itself fetches this repo with `git` from `github.com` when it adds the plugin list at install.

**The .pack files.** Each is a paid page, sealed. Hydra-OS opens one only when you add that page from Home's Shop, with the key on your receipt, and only once its sha256 matches the signed catalog. Until then, nothing reads it.

Claude reaches your own services only in your chats and in the morning review: the reads each page lists, through the Claude connectors you connected, and the web searches a page lists, in general words.

## The morning review

Only with your yes, in your first chat: a scheduled task in the Claude app, "Hydra-OS morning review", daily at 07:40, whose whole prompt is "Run hydra think and follow what it prints." It runs on your Claude plan, in `~/Hydra-OS`, under the fence above. You can pause or delete it in the Claude app, any time.

## No telemetry

Hydra-OS sends nothing about you, or about how you use it, to anyone. There's no server of ours. Its log stays in `~/Hydra-OS/hydra/logs/`, with keys, card numbers and your own words left out. `hydra report`, or Copy a report on Home's Help page, shows states and counts only, for you to read whole before you share it with anyone.

## The signing key

Hydra-OS's catalog is signed. The key's public half ships in the plugin, as `scripts/shop_key.json`. Its fingerprint, the sha256 of that key, is:

```text
da0ff2dedb55bbcc449d6ffc5e8e881b89f3b7186a680a0a3e2f11183d07193d
```

The download page prints it too, so you can check one against the other. Nothing is listed, opened or installed unless the Mac's own `/usr/bin/openssl` checks the catalog's signature against that key.

## What Hydra-OS never does

- It never downloads Python or any other program, never re-signs anything, never touches a file's quarantine mark, and never uses `sudo`.
- It never installs, updates or signs in to Claude Code, and never starts a Claude session on its own: Claude runs only in your chats and in the morning review you said yes to. Hydra-OS runs Claude Code's own commands, for its plugins and its list of connectors, only in a step you take in a chat or on Home: setting up, connecting a source, adding, updating or removing a page or Hydra-OS itself. If one of those was cut off part way, Home's server runs them once more when it next starts, to put things back. The tick never runs one.
- It never runs a model unattended.
- It never reads your keychain, a password or a token, and never asks you for one.
- It never writes Claude Code's own settings or `~/.claude`: Claude Code's own plugin commands do the installing.

## Remove it

Say "remove Hydra-OS" in a Hydra-OS chat. Claude asks first, then `hydra remove hydra` stops the helpers and removes their launch agents, takes each page and Hydra-OS's own plugin list out of Claude Code, and moves `~/Hydra-OS` to the Trash whole, so you can take it back. If you have the morning review's scheduled task, Claude deletes it with the Claude app's own tool. Your Claude chats stay in Claude.

By hand, in Terminal:

```sh
launchctl bootout gui/$(id -u)/os.hydra.home; launchctl bootout gui/$(id -u)/os.hydra.tick
rm -f ~/Library/LaunchAgents/os.hydra.home.plist ~/Library/LaunchAgents/os.hydra.tick.plist
```

Then, in a chat in `~/Hydra-OS`, `/plugin` to uninstall `hydra`, `goals`, `health` and any page you added, and move `~/Hydra-OS` to the Trash.
