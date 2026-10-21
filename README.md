# HPC usage Gantt chart

Draws the team's **HPC usage plan** (a Google Sheet) as a Gantt chart and uploads it to Dropbox. Each upload replaces the previous chart.
- **Layout:** one lane per HPC, and one bar per run, labelled "Person · description".
- **Colours:** blue bars are underway or upcoming; grey bars have finished.
- **Span:** from two weeks back to about three months ahead.
- **Problems:** any rows in the sheet it couldn't draw are listed under the chart.

It runs once a week on GitHub Actions (see [How it runs](#how-it-runs)) and uploads to `dropbox:/QuakeCoRE/hpc_usage_gantt.png`. A recurring Slack reminder, set up in Slack itself, posts the file's share link. The design is in [docs/superpowers/specs/2026-10-20-hpc-usage-gantt-design.md](docs/superpowers/specs/2026-10-20-hpc-usage-gantt-design.md).

## The sheet

Three tabs, each with its header in row 1:

| Tab | Columns |
|---|---|
| Runs | Person, Description, HPC, Start date, End date |
| People | Name |
| HPCs | HPC |

- **Dropdowns:** Person and HPC on the Runs tab are dropdowns fed by the other two tabs.
- **End dates** count as part of the run.
- **Sharing:** the sheet must stay shared as "Anyone with the link can view".

## Try it on your laptop

Draw the chart without uploading it. This writes `hpc_usage_gantt.png`:

```bash
SHEET_ID=<id from the sheet's URL> uv run --script hpc_gantt.py --no-upload
```

Try an upload to your own Dropbox folder. This needs an rclone remote called `dropbox`:

```bash
SHEET_ID=<id> uv run --script hpc_gantt.py --upload-to dropbox:/QuakeCoRE/<you>/hpc_usage_gantt_test.png
```

`--pretend-today-is YYYY-MM-DD` draws the chart as if it were another day.

## Tests

```bash
uv run --no-project --python 3.14 --with pytest --with-requirements hpc_gantt.py python -m pytest -q
```

## The share link and the Slack reminder

After the first upload, create a share link, which lets anyone with the link view the chart:

```bash
rclone link dropbox:/QuakeCoRE/hpc_usage_gantt.png
```

Then, in the Slack channel, type `/remind #channel "HPC usage plan: <link>" every Monday at 9am`. Each upload replaces the file in place, so the link always shows the latest chart.

## How it runs

A GitHub Actions workflow, [`.github/workflows/update-chart.yml`](.github/workflows/update-chart.yml), runs the script once a week, early on Monday morning NZ time. It can also be run by hand.

- **Secrets:** both live in the repo's `dropbox` environment, which only `main` can use.
  - `SHEET_ID` is the ID from the sheet's URL. It's a secret so that the sheet's link stays private.
  - `DROPBOX_REFRESH_TOKEN` is the refresh token of an rclone `dropbox` remote. It gives full access to the team Dropbox.
- **Public log:** this repo is public, and so is the log of every run. That's why the script logs only how many problems it found in the sheet; the chart lists them.
- **Keep-alive:** GitHub switches off a public repo's schedules after 60 days without a commit, so each scheduled run also switches the workflow back on.

## Operating

- **Refresh the chart now:** on GitHub, go to Actions → "Update the HPC usage chart" → "Run workflow". Or run `gh workflow run update-chart.yml --repo ucgmsim/hpc_gantt_bot`. Either way needs write access to the repo.
- **Runs and their logs:** the Actions tab, or `gh run list --workflow update-chart.yml --repo ucgmsim/hpc_gantt_bot`.
- **When a run fails:** GitHub emails whoever last edited the `cron` line.
- **Replace the Dropbox token** (for example, after it was revoked): run this on a machine with a working `dropbox` remote. The token is never shown:

  ```bash
  rclone config dump | jq -j '.dropbox.token | fromjson | .refresh_token' | gh secret set DROPBOX_REFRESH_TOKEN --env dropbox --repo ucgmsim/hpc_gantt_bot
  ```
- **Point it at another sheet:** `gh secret set SHEET_ID --env dropbox --repo ucgmsim/hpc_gantt_bot`. It prompts for the ID.
- **After changing the script's dependencies:** run `uv lock --script hpc_gantt.py` to re-lock, and commit both files.
