# HPC usage reminder bot

Reads the team's "HPC usage plan" Google Sheet and posts reminders to a Slack channel.
- **Mondays at 9am** (New Zealand time): the week's planned HPC runs, with an @mention for each person. The admin also gets an @mention about watched HPCs that have nothing planned this week or next.
- **Fridays at 9am:** a heads-up about runs that start the following week.

The full design is in [docs/superpowers/specs/2026-10-19-hpc-usage-reminder-bot-design.md](docs/superpowers/specs/2026-10-19-hpc-usage-reminder-bot-design.md).

## The sheet

The sheet has three tabs, **Runs**, **People** and **HPCs**, described in the design's "The Google Sheet" section.

To join, add a row to **People** with your name and your Slack member ID. To find your ID in Slack:
1. Click your profile picture, then **Profile**.
2. Click the three-dot (**More**) button.
3. Choose **Copy member ID**.

Your name then appears in the Person dropdown on **Runs**.

## Try it

Print what the posts would say, without sending anything:

```bash
SHEET_ID=<id from the sheet's URL> uv run --script hpc_reminder.py weekly --dry-run
SHEET_ID=<id from the sheet's URL> uv run --script hpc_reminder.py heads-up --dry-run --pretend-today-is 2026-10-23
```

`--pretend-today-is YYYY-MM-DD` runs as if it were another day. Runs that actually post also need `SLACK_BOT_TOKEN` and `SLACK_CHANNEL`.

## Tests

```bash
uv run --no-project --python 3.14 --with pytest --with-requirements hpc_reminder.py python -m pytest -q
```

## Deploy on mantle

```bash
# 1. A service account with its own uv
sudo useradd --system --create-home --home-dir /opt/hpc-reminder --shell /usr/sbin/nologin hpc-reminder
sudo -u hpc-reminder -H sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
# 2. Code and units (run from a copy of this repo on mantle)
sudo install -o root -g root -m 644 hpc_reminder.py /opt/hpc-reminder/hpc_reminder.py
sudo install -o root -g root -m 644 deploy/hpc-reminder@.service deploy/hpc-reminder-weekly.timer deploy/hpc-reminder-heads-up.timer /etc/systemd/system/
# 3. Settings and secrets: root-only, systemd reads the file before dropping privileges
sudo install -o root -g root -m 600 deploy/hpc-reminder.env.example /etc/hpc-reminder.env
sudoedit /etc/hpc-reminder.env
sudo systemctl daemon-reload
# 4. Dry run as the service user: prints the Monday post and sends nothing
#    (the first run also downloads Python 3.14 for uv)
sudo systemd-run --pipe --wait --uid=hpc-reminder -p EnvironmentFile=/etc/hpc-reminder.env \
  /opt/hpc-reminder/.local/bin/uv run --script /opt/hpc-reminder/hpc_reminder.py weekly --dry-run
# 5. Go live
sudo systemctl enable --now hpc-reminder-weekly.timer hpc-reminder-heads-up.timer
systemctl list-timers 'hpc-reminder*'
```

## Operating

- **Next scheduled posts:** `systemctl list-timers 'hpc-reminder*'`
- **Logs:** `journalctl -u 'hpc-reminder@*'`
- **Post now:** `sudo systemctl start hpc-reminder@weekly.service`. This does nothing if this week's post has already gone out.
- **Send a post again anyway:** use the step-4 `systemd-run` line, with `weekly --force` (or `heads-up --force`) instead of `weekly --dry-run`.
- **Change the channel:** invite AI boss to the new channel, then put its ID in `/etc/hpc-reminder.env` using `sudoedit`. The next run picks it up.
- **Update the code:** copy the new `hpc_reminder.py` into place with the step-2 `install` line.
