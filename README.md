# HPC usage Gantt chart

Draws the team's **HPC usage plan** (a Google Sheet) as a Gantt chart and uploads it to Dropbox. Each upload replaces the previous chart.
- **Layout:** one lane per HPC, and one bar per run, labelled "Person · description".
- **Colours:** blue bars are underway or upcoming; grey bars have finished.
- **Span:** from two weeks back to about three months ahead.
- **Problems:** any rows in the sheet it couldn't draw are listed under the chart.

It runs every hour on mantle and uploads to `dropbox:/QuakeCoRE/hpc_usage_gantt.png`. A recurring Slack reminder, set up in Slack itself, posts the file's share link. The design is in [docs/superpowers/specs/2026-10-20-hpc-usage-gantt-design.md](docs/superpowers/specs/2026-10-20-hpc-usage-gantt-design.md).

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

## Deploy on mantle

1. **Pick the account that will run it.** It needs uv, rclone, and an `rclone.conf` with a working `dropbox` remote.
   - On a new account, install uv and rclone, then copy in the `rclone.conf`. The file must be owned by that account with mode 600, and stay writable, because rclone refreshes the Dropbox token and saves it back.
   - Optionally, give the bot its own token with `rclone authorize "dropbox"`, so it can be revoked without affecting anyone else.
   - Check it works by running `rclone lsf dropbox:/QuakeCoRE --max-depth 1` as that account.
2. **Copy the script and its lock file:** `sudo install -D -m 644 -t /opt/hpc-gantt/ hpc_gantt.py hpc_gantt.py.lock`
3. **Install the units.** In `deploy/hpc-gantt.service`, fill in the three `CHANGE_ME` values: the account, the sheet ID, and the directory that holds that account's `uv`. Then run `sudo install -m 644 deploy/hpc-gantt.service deploy/hpc-gantt.timer /etc/systemd/system/`
4. **Reload systemd:** `sudo systemctl daemon-reload`
5. **Test it:** `sudo systemctl start hpc-gantt.service && journalctl -u hpc-gantt -n 20`. The log should end with `Uploaded to dropbox:/QuakeCoRE/hpc_usage_gantt.png`.
6. **Go live:** `sudo systemctl enable --now hpc-gantt.timer`

## Operating

- **Next run:** `systemctl list-timers hpc-gantt.timer`
- **Log:** `journalctl -u hpc-gantt`
- **Refresh the chart now:** `sudo systemctl start hpc-gantt.service`
- **After changing the script's dependencies:** run `uv lock --script hpc_gantt.py` to re-lock, then copy both files to mantle again.
