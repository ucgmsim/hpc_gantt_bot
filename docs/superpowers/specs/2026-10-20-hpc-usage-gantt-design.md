# HPC usage Gantt chart: design

2026-10-20 · Approved by the user. This replaces the Slack-bot design of 2026-10-19 (`2026-10-19-hpc-usage-reminder-bot-design.md`).

**Tags:**
- *(decided)*: the user decided it.
- *(approved)*: Claude proposed it and the user approved it.
- *(Claude's call)*: decided by Claude; the user may still change it.

## Why

The team runs earthquake simulations on several HPCs with time-limited allocations. Allocations sitting idle and forgotten slots are still the problems to solve.

For simplicity, the team dropped the Slack bot *(decided)*. Instead, an always-current Gantt chart of the plan sits at a fixed place in the team Dropbox, and a recurring Slack message posts its link.

## What it does

A small script runs every hour on mantle *(approved)*. Each run:

1. Downloads the "HPC usage plan" Google Sheet as `.xlsx`. No login is needed because the sheet is link-shared. This is the existing code.
2. Checks the rows with the existing rules, minus everything that was only there for Slack.
3. Draws a Gantt chart as a PNG.
4. Uploads it with rclone to **`dropbox:/QuakeCoRE/hpc_usage_gantt.png`**, replacing the previous chart *(decided: the team Dropbox through rclone; the name is Claude's call from the user's two suggestions)*.

**Outside the code** *(decided)*: after the first upload, the user creates a Dropbox share link to that file and sets up a recurring Slack message with it, e.g. `/remind #channel "HPC usage plan: <link>" every Monday at 9am`. The file is replaced in place, so the link keeps showing the latest chart. This is checked during the laptop trial.

**Order of work** *(decided)*: get the chart drawn and uploaded from the laptop first, and only then set it up as a service on mantle.

## Goals

- **Always current:** the chart is up to date (at most an hour old) and always at the same link.
- **Readable at a glance:**
  - one lane per HPC;
  - one bar per run, labelled with who and what;
  - a "today" line;
  - empty lanes, which show idle machines.
- **No silent drops:** rows that can't be drawn are listed on the chart itself.
- **Simple to run:** one uv script, with no Slack token and no state file.

## Non-goals

- Any Slack integration in the code: no tokens, no posting, no reminders, @mentions or alerts *(decided)*.
- An interactive or web chart.
- Keeping old charts. Dropbox's own version history covers that if it's ever needed.

## Anti-goals

- **A chart that silently leaves runs out.** Every row the bot can't draw is listed on the chart.
- **Misread dates.** The existing typed-date reading stays.
- **A broken chart replacing a good one.** If the sheet can't be read, nothing is uploaded. The old chart stays, and its "updated" time shows that it's stale.
- **Secrets in the repo or the sheet.** The Dropbox token lives only in rclone's config.

## The sheet

The sheet keeps its three tabs. They get tidied *(approved)*:
- **People** keeps only `Name`. Remove the `Slack member ID` and `Admin` columns, and the how-to note on the member ID header.
- **HPCs** keeps only `HPC`. Remove `Alert if idle`.
- **Runs** is unchanged: `Person | Description | HPC | Start date | End date`. Person and HPC stay dropdowns fed by the People and HPCs tabs.

The user does the tidy-up in the sheet *(decided)*. The bot finds columns by name and ignores any extras, so the code works whether or not the tidy-up has been done yet.

**Row checks** are the existing rules, with the Slack-only checks removed (member IDs, admins). A Runs row is drawn when:
- its Person is on People;
- its HPC is on HPCs;
- both dates are real dates;
- the start date is on or before the end date.

Two rules about which rows get checked *(Claude's call)*:
- Rows that end before the chart's first day aren't checked, because they aren't drawn.
- Rows with unreadable or reversed dates are always reported.

## The chart

The chart follows the dataviz skill's rules, and the layout descends from `gantt.py` *(approved)*, which is in the desktop Trash and serves as the reference.

- **Time span:** from the Monday two weeks before this week to 13 weeks after this week's Monday, which is about three months ahead *(approved)*. There's a hairline at each Monday, labelled like `19 Oct`.
- **Lanes:** one per HPC, top to bottom in HPCs-tab order. Every HPC on the tab gets a lane, even with nothing planned *(approved)*. An empty lane says "nothing planned" in muted text.
- **Runs:**
  - Each run has its own row in its HPC's lane, sorted by start date.
  - The bar is thin, starts on the run's start date, and ends after its end date, because end dates are inclusive.
  - A run that extends past either edge of the chart is cut at that edge, and the cut end is square.
- **Labels:** each bar has a caption in dark text, `Person · Description`. Captions sit next to the bar rather than inside it, are never coloured, and are shortened if they're too long.
- **Colour** *(decided 2026-10-20; replaces the earlier "coloured by person")*:
  - Runs that are underway or upcoming are blue (`#2a78d6`, the palette's first colour). Runs that have already finished are light grey.
  - A small legend explains the two colours.
  - **Why not one colour per person:** in a Gantt chart any two people's bars can sit next to each other. The dataviz rules allow that for at most three colours; past that, some pairs are hard to tell apart even with full colour vision, and much harder for colour-blind readers. The caption already names the person, so colour is better spent highlighting what's current.
- **Today:** a thin dark vertical line, labelled "today".
- **Title:** "HPC usage plan", with a subtitle such as "Updated Tue 20 Oct 2026, 14:00 NZDT" *(approved)*.
- **Footer:** the rows that couldn't be drawn, in small print *(approved)*, e.g. `Row 6 (Casey, Frontera): start date "early Nov" isn't a date`. If there are many, show the first few, then "and N more". The footer also names the source, "HPC usage plan" in Google Sheets.
- **Format:** PNG, wide enough to read on a laptop screen. Its height grows with the number of rows. It has its own light background, so it looks the same in Dropbox's light and dark modes.

## Uploading

- **Command:** `rclone copyto <local png> dropbox:/QuakeCoRE/hpc_usage_gantt.png`. rclone uses the running account's own config, where the remote is called `dropbox` *(decided)*.
- **Destination:** this is a command-line option, so trials can upload elsewhere.
- **Failure:** if rclone fails, the script exits with an error, which goes to the systemd journal.
- **Share link:** create it once, after the first upload. Either run `rclone link dropbox:/QuakeCoRE/hpc_usage_gantt.png`, which creates an "anyone with the link can view" link, or use Dropbox's Share button. This publishes the file, so it's done only with the user's go-ahead.

## Running it

*(Claude's call)*

- **Script:** rename `hpc_reminder.py` to `hpc_gantt.py`. It's one uv script with its dependencies listed inline (`openpyxl`, `requests`, `matplotlib`, `cyclopts`), on Python 3.14, like `gantt.py`.
- **Command:** a single command, `hpc_gantt.py [--no-upload] [--output PATH] [--upload-to REMOTE:PATH] [--pretend-today-is YYYY-MM-DD]`. `SHEET_ID` is still read from the environment.
  - `--no-upload` draws the chart into `--output` (default `./hpc_usage_gantt.png`) and stops there.
  - Without it, the script draws the chart and uploads it to `--upload-to` (default `dropbox:/QuakeCoRE/hpc_usage_gantt.png`).
- **Code that goes:** everything specific to Slack. That's the message text, posting, retry-on-post, state file, idle alerts, weekly and heads-up commands, their tests, and the current systemd units.
- **Code that stays:** the date helpers, the sheet download with retries, and the sheet parsing (simplified as above), with their tests.

## Laptop trial

These steps run before anything is set up on mantle *(decided)*:

1. **Look at it locally.**
   - Draw the chart from the example data and look at it. This is the visual check.
   - Also draw it from the real sheet with `--no-upload`, to check the download end to end. Until the team lists HPCs on the sheet, that chart has no lanes at all *(Claude's call)*.
2. **Upload to a test file.** Use the user's own folder, e.g. `dropbox:/QuakeCoRE/<you>/hpc_usage_gantt_test.png`. Create a share link, upload again, and check that the same link now shows the new chart.
3. **Upload to the real path** and create the real share link, when the user says so. Ideally that's once the HPCs tab is filled in, because the link goes to the whole team *(Claude's call)*.

## On mantle (later, with the user)

- **Schedule:** a systemd service plus a timer that fires every hour.
- **Account:** the service runs either as an existing account that already has rclone set up, or as a new account. A new account needs rclone installed and the Dropbox token in its rclone config *(decided; which one is still open)*.
- **rclone config:**
  - rclone refreshes the Dropbox token and writes it back, so the config must be writable by that account.
  - The token gives full access to the team's Dropbox, so the config file is mode 600.
  - Authorising a separate token for the bot (`rclone authorize "dropbox"`) would let it be revoked without affecting anything else. This is optional.
- **Environment:** `SHEET_ID` can go straight into the unit file, since it's no longer next to any secret.

## Left to the builder

- **Chart styling within the rules above:** exact sizes, fonts, how captions are shortened, legend placement, and how many problem lines to show before "and N more".
- **Tests:**
  - unit tests for laying out the chart's data (lanes, rows, cutting at the edges, captions, colour by finished or not);
  - a smoke test that a PNG is produced;
  - tests of the rclone call using a fake runner;
  - CLI tests.
- **A visual check:** render the chart and look at it before calling any step done.

## Open items

- Which mantle account runs the service.
- The channel and wording of the Slack reminder. The user sets this up.
- Whether the share link survives a re-upload. The laptop trial checks this.
