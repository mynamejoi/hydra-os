# hydra: Hydra-OS itself

The main plugin of Hydra-OS. It sets up your Hydra-OS folder, `~/Hydra-OS`, serves Home and each of your pages on this Mac only, starts each page's daily read, and tells Claude where you are on your pages. Python 3.9 standard library only, on the Mac's own `/usr/bin/python3`.

It never starts a model on its own, never signs you in or reads a sign-in, never installs or updates Claude Code, and never writes Claude Code's settings outside `~/Hydra-OS`, nor anything in `~/.claude`. Claude Code's own plugin commands, run in your chat after your yes, do the installing.

## What's here

| Path | What it is |
|---|---|
| `.claude-plugin/plugin.json` | The plugin's manifest |
| `column.json` | Hydra-OS's own entry among your pages: Home and Dreams |
| `bin/hydra-setup` | Setup, run by Claude in your chat after your yes, with the Claude Code running the chat and your answer on the helpers: `hydra-setup --claude <path> --helpers yes\|no`. It checks Apple's free developer tools are on this Mac, opens Apple's own installer when they aren't, then runs `scripts/install.py` |
| `scripts/install.py` | Setup itself: the folder, its own store of pages, the `hydra` command, Home's server and, with your yes, the helpers |
| `scripts/hydra.py` | The `hydra` command Claude runs in your chat, after your yes. `hydra --help` lists what it does |
| `scripts/server.py` | Home's server, on this Mac's loopback address only: your pages, and the few saves they make |
| `scripts/tick.py` | One tick: what's due today, each page's read in turn, and `health.json`. It never starts Claude Code |
| `scripts/act.py` | Setup's own save check, on a throwaway question it removes after |
| `scripts/migrate.py` | Moves a file Hydra-OS keeps to a newer shape, on an update |
| `scripts/shop_key.json` | The public half of the key that signs Hydra-OS's catalog of pages and updates |
| `hooks/hooks.json` | The hooks below, each for chats in your Hydra-OS folder |
| `hooks/primer.py` | At a chat's start: a short note to Claude about your pages, given as data |
| `hooks/prompt.py` | On each message: a message that holds a password or a key is stopped before Claude sees it; then where you are on your pages, as data |
| `hooks/review_fence.py` | Before each tool call: while the morning review runs, only `hydra think` and the reads it lists |
| `hooks/review_keep.py` | After a web search in the morning review: its answer kept for the page that asked |
| `hooks/session_end.py` | At a chat's end: the morning review's fence lifted |
| `skills/setup/` | How Claude sets Hydra-OS up with you |
| `skills/connect/` | How Claude helps you connect your own sources, recorded through `hydra sources add` |
| `scripts/hydralib/` | The library the parts above share |

## `scripts/hydralib/`

| Module | Does |
|---|---|
| `files.py` | Whole-or-nothing writes, modes, `.jsonl` appends, size-capped reads |
| `config.py` | Finding your Hydra-OS folder, and reading and writing its `config.json` |
| `claude.py` | Claude Code's own commands, in a step you take: its version, its plugin list and its plugin installs |
| `registry.py` | `registry.json`: your pages and what each reads |
| `sources.py`, `you.py`, `settings.py`, `yours.py` | What you chose, kept in `~/Hydra-OS/yours/` |
| `health.py` | `health.json`, and the plain-words statuses Home shows |
| `panel.py`, `context.py` | What Claude knows about your pages: where you are, what you asked, every string quoted as data |
| `act.py`, `upload.py`, `widgets.py`, `browser.py` | The saves your pages make, the files you drop on them, Home's widgets, and links that open in your own browser |
| `pages.py` | Pages built when what they're drawn from is newer |
| `runs.py`, `jobs.py` | Starting a page's read, and the two helpers' launch agents |
| `helpers.py`, `session.py` | The two helpers as you chose them (`hydra helpers on` or `off`), and what each Hydra-OS chat's start and end do: the Claude Code running it noted for its commands, and, with the helpers off, Home's server and the day's reads |
| `think.py`, `review_fence.py`, `search_guard.py` | The morning review: its guidance, its fence and its searches |
| `shop.py`, `catalog.py` | The catalog of pages: signed, checked against `shop_key.json`, then each page added from its key |
| `update.py`, `backup.py`, `release.py` | `hydra update`: a backup first, then the new version, put back whole if a step fails |
| `space.py`, `tools.py` | Room on this Mac, and Hydra-OS's own small tools |
| `applog.py`, `report.py` | Hydra-OS's own log in your folder, and `hydra report`, states and counts only |
| `remove.py` | `hydra remove hydra`: asked first, then your folder moved to the Trash whole |
