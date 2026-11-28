# Setting up Goals

Goals comes with Hydra-OS. Its setup installs it with the rest and draws its page, so there's nothing to set up by hand.

## Your first goal

Tell Claude, in the conversation beside your pages, what you're working toward: "I want to swim twice a week again", or "save $5,000 for a trip by June". Claude saves it as you say it, and asks only for a number when you gave none. With no date, a habit runs 12 weeks and anything else a year: you can change the date on the goal any time. Every save has an Undo.

Each goal names the page that counts it. Until that page has what it reads, the goal says what it's waiting for, such as "Wellbeing counts it once your health export is in."

When no page here counts it, it's kept by hand: you tell Claude the number when it moves, and its plot follows what you tell it. When a page that can count it arrives later, the goal moves to that page by itself. If that page is removed, its goals are kept by hand again, and they move back when it returns.

## Every day

- Goals checks each goal's pace after every page's run, so its page and Home show where each goal stands and where this pace lands.
- When a goal passes its date, give it a new date or set it aside, on the goal or by telling Claude. A new date moves it at once.
- To change a target or a date, use "Change target or date" on the goal, or tell Claude.

## If something's wrong

Home says it in one line, with what fixes it. Saying "repair Hydra-OS" to Claude puts Hydra-OS's own files back, and never touches your goals.

## Remove it

1. Tell Claude "remove Goals from Hydra-OS". It runs `claude plugin uninstall goals@hydra-os`.
2. Goals' own folder, `~/Hydra-OS/goals/`, stays until you ask Claude to delete it.
3. **Your goals stay yours.** They're in `~/Hydra-OS/yours/goals.json`, and nothing removes them unless you ask. Home's goals band still shows them, with their pace from the pages that count them. Adding or changing a goal waits until Goals is back.
