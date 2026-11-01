# socialartzy

A free, fully cloud-hosted posting bot for an art account: it publishes one
queued artwork per day to **Instagram** and **Pinterest** from GitHub Actions.
Your laptop stays off — GitHub's servers do the work at 10:00 UTC.

- Runs 100% on GitHub Actions (free minutes for public repos)
- No paid APIs: unofficial [instagrapi](https://github.com/subzeroid/instagrapi)
  and [py3-pinterest](https://github.com/bstoilov/py3-pinterest)
- Human-like pacing (15–45 s on Instagram, 20–60 s on Pinterest) plus a
  persisted daily counter so the bot can never over-post
- Alt text support (`custom_accessibility_caption` on Instagram, `alt_text` on
  Pinterest)
- Every run commits the updated queue, the counters and `logs/posting.log` back
  to the repo, so nothing is ever posted twice

## Layout

| Path | Purpose |
| --- | --- |
| `.github/workflows/post.yml` | Cron job: daily at 10:00 UTC + manual runs |
| `content/queue.csv` | The content queue (one row per artwork) |
| `art/` | The image files referenced by the queue |
| `post_instagram.py` | Instagram poster (`instagrapi`) |
| `post_pinterest.py` | Pinterest poster (`py3-pinterest`, or API v5 if a token is set) |
| `run_bot.py` | Entry point the workflow runs; posts to both platforms |
| `artbot/` | Shared config, logging, queue, rate-limit and runner code |
| `logs/posting.log` | Append-only log, committed by the workflow |
| `state/daily_count.json` | Posts used today, per platform (committed) |
| `tests/` | Standard-library unit tests + the placeholder image generator |

## The queue

`content/queue.csv` columns:

| Column | Meaning |
| --- | --- |
| `id` | Unique id, e.g. `1` |
| `platform` | `both`, `instagram` or `pinterest` (aliases `ig`, `pins` also work) |
| `image_filename` | File name inside `art/` |
| `caption` | Post text without hashtags |
| `alt_text` | Accessibility description (≤ 1,000 chars on Instagram) |
| `hashtags` | Space or comma separated, `#` optional |
| `pinterest_board` | Board name (e.g. `Abstract Art`) or numeric board id |
| `posted_instagram` | Maintained by the bot |
| `posted_pinterest` | Maintained by the bot |
| `posted` | `true` once every platform for that row is done (you can also set it by hand to skip a row) |
| `posted_at` | UTC timestamp of the last successful post |

The bot always picks the **first row that is still pending** for the platform it
is about to post to. A `platform=both` row is marked per platform, so Instagram
can publish it today and Pinterest tomorrow without a duplicate. Rows are never
deleted, so the CSV doubles as a posting history.

To add artwork:

1. Drop the image into `art/` (JPG or PNG, ideally 1080×1350).
2. Append a row to `content/queue.csv`.
3. Commit and push (or edit the file straight in the GitHub web UI).
## Setup

### 1. Repository secrets

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Required | Notes |
| --- | --- | --- |
| `IG_USERNAME` | yes | Instagram username |
| `IG_PASSWORD` | yes | Instagram password |
| `IG_SESSIONID` | optional | Session id from a browser cookie; when set it is used instead of a password login and avoids most challenge/captcha prompts |
| `PINTEREST_EMAIL` | yes | Pinterest account email |
| `PINTEREST_PASSWORD` | yes | Pinterest password |
| `PINTEREST_USERNAME` | recommended | Your handle (the part after `pinterest.com/`) so boards are found by name |
| `PINTEREST_ACCESS_TOKEN` | optional | Official API v5 token; when present it is used instead of the unofficial client |

### 2. Optional tuning variables

`Settings → Secrets and variables → Actions → Variables`

| Variable | Default | Notes |
| --- | --- | --- |
| `IG_DAILY_LIMIT` | `2` | Instagram posts per UTC day (Instagram allows ~100/24h, but 1–3 is the human range) |
| `PINTEREST_DAILY_LIMIT` | `3` | Pinterest pins per UTC day (1–5 keeps new accounts safe) |
| `IG_DELAY_RANGE` | `15,45` | Seconds of random pause between every Instagram request |
| `PINTEREST_DELAY_RANGE` | `20,60` | Seconds of random pause before/after each pin |

### 3. First run

`Actions → Daily art posting → Run workflow`. Choose `dry_run` the first time to
preview the caption and alt text without touching either account. Then run it for
real.

### 4. Schedule

`.github/workflows/post.yml` runs `0 10 * * *` (10:00 UTC every day). Edit that
line to change the time; GitHub cron is always UTC and scheduled runs can start a
few minutes late under load.

## Local usage

```bash
pip install -r requirements.txt
python run_bot.py --check          # validate the queue and the images
python run_bot.py --dry-run        # print what would be posted, no network
python run_bot.py                  # real run (needs the env vars / secrets)
python -m unittest discover -s tests -v
```

Environment variables mirror the secrets (`IG_USERNAME`, `PINTEREST_EMAIL`, ...).
`DRY_RUN=1` forces preview mode.
## Safety rails

- **Daily quota** – `state/daily_count.json` is read before every post and reset
  on each new UTC day. Re-running the workflow cannot exceed the limit.
- **Pacing** – every request is wrapped in a randomised delay; the bot never
  sends a burst of API calls.
- **Idempotency** – a row is only flagged as posted after the platform confirms
  success, and the flag is stored per platform.
- **Fail loudly, stop early** – a failed post logs the reason (challenge, 2FA,
  rate limit, missing board, ...) and stops that platform for the day instead of
  retrying in a loop.
- **Concurrency** – `concurrency: socialartzy-posting` stops two runs from
  overlapping.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ChallengeRequired` / checkpoint in the log | Open Instagram, approve the login attempt, or add `IG_SESSIONID` |
| `Pinterest login did not return any cookies` | Pinterest showed a captcha; log in once from a stable IP, or switch to `PINTEREST_ACCESS_TOKEN` |
| `Pinterest board 'X' was not found` | Set `PINTEREST_USERNAME`, check the board name, or use the numeric board id |
| `daily ... limit reached` | Expected: the bot is protecting the account. It resumes tomorrow (UTC) |
| `Artwork not found` | The image is missing from `art/` or `image_filename` is wrong |
| Log shows the post but the queue did not change | The commit step failed; check that workflow permissions include `contents: write` |

## Notes and limits

- Both Instagram and Pinterest clients are unofficial. They work well at 1-3
  posts/day, but no automation of this kind can be guaranteed against a platform
  policy change. Keep the volume low and the account verified.
- Instagram may challenge a brand-new login coming from a GitHub runner IP. The
  optional `IG_SESSIONID` path exists for exactly that case.
- Pinterest's official API v5 requires an approved developer app; the free route
  (py3-pinterest) needs no key, which is why it is the default.# socialartzy
