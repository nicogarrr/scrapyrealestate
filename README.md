# scrapyrealestate

> Language: **English** | [Español](README.es.md)

Tracks several Spanish real-estate portals and alerts you on Telegram about new listings that match your criteria.

**Problem it solves:** new listings in good areas disappear within hours. Instead of refreshing five portals by hand, you get a Telegram message the moment something new shows up in your price range.

It runs in a loop: every X seconds it runs the spiders, compares against what it has already seen and, if a new listing falls inside your price range, posts it to your channel.

This is a refactored version of the original project. The most important changes: it no longer uses MongoDB (deduplication is local, nothing is sent anywhere), everything is configured from a web page (including the Telegram token), dependencies are pinned and the Fotocasa and Yaencontre spiders were rewritten.

## How it works

```text
Idealista, Pisos.com, Fotocasa, Habitaclia, Yaencontre
        |  spiders (Scrapy + Playwright/Chromium)
        v
local deduplication (data/ids.json, no database, no telemetry)
        |  new listing inside your price range
        v
your Telegram channel (your own bot)
```

## Requirements

- Docker (easiest), or Python 3.9+ with `requirements.txt`.
- A Telegram channel with your bot (see below).

## With Docker

```bash
docker run -d --name scrapyrealestate --restart=always -p 8080:8080 \
  mcrespov/scrapyrealestate:latest
```

The `-p 8080:8080` exposes the first-boot configuration web page. The data
(`config.json`, `ids.json`, `useragent.txt`) is ephemeral: it lives inside the
container. A `docker restart` keeps it, but if you delete or recreate the
container it is lost and you will have to configure it again through the web
page (and the alert history starts from zero). For a second instance, change
the name and port (`-p 8081:8080`).

The image boots under `tini` as PID 1, which reaps the zombie (`defunct`)
processes Chromium leaves behind; without it they pile up over many cycles and
exhaust the system PIDs. If you use an old image (without `tini`), add `--init`
to the `docker run` for the same effect.

Logs:

```bash
docker logs -f scrapyrealestate
```

## With docker-compose

The repository includes a `docker-compose.yml` that uses the published image:

```bash
docker compose up -d
docker compose down
```

## Build from source (optional)

```bash
docker build -t scrapyrealestate .
docker run -d --name scrapyrealestate --restart=always -p 8080:8080 scrapyrealestate
```

## Without Docker

With Python 3.9+ (better inside a [virtualenv](https://docs.python.org/3/tutorial/venv.html)):

```bash
pip3 install -r scrapyrealestate/requirements.txt
playwright install chromium

cd scrapyrealestate
python3 main.py
```

In the background on Linux: `nohup python3 main.py &` (logs in `nohup.out`).

## Configuration

The first time, if there is no `data/config.json`, the program opens a
configuration web page at `http://localhost:8080/`. Fill it in and save:
`data/config.json` is created and the program carries on by itself. As long as
that file exists nothing is asked again (you can edit it by hand).

The portal URLs come pre-filled with Madrid searches; change them for your own
before saving.

Parameters:

- `scrapy_rs_name`: instance name.
- `log_level`: script log level (default `INFO`).
- `log_level_scrapy`: Scrapy log level (default `WARNING`).
- `time_update`: seconds between runs (minimum 300).
- `telegram_chatuserID`: your channel's chat id (see below).
- `telegram_bot_token`: your bot token from @BotFather. Optional (see note below).
- `start_msg`: if `True`, sends a message on startup.
- `min_price` / `max_price`: price range (`max_price = 0` means no limit).
- `url_idealista` / `url_pisoscom` / `url_fotocasa` / `url_habitaclia` /
  `url_yaencontre`: search URLs for each portal (multiple allowed).
- `proxy_idealista`: rotating proxies for Idealista (`on`); off by default.
- `send_first`: if enabled, also alerts about what is already there on the first cycle.

The `telegram_bot_token` is optional: leave it empty and a default public bot
is used.

### Telegram channel and chat id

1. Create a channel (public or private).
2. Add your bot as administrator with posting permission (create it with
   [@BotFather](https://t.me/BotFather) and put its token in the
   `telegram_bot_token` field of the web page). If the bot is not added
   correctly, the program does not start.
3. Get the channel's chat id, for example with [@RawDataBot](https://t.me/RawDataBot).
   That is what goes in `telegram_chatuserID` (like `-1001647968000`).

## Portal status

| Portal     | Status     | Notes |
|------------|------------|-------|
| Pisos.com  | Working    | Stable HTML. |
| Habitaclia | Working    | Stable HTML. |
| Yaencontre | Working    | Loaded with Playwright (returns 403 to plain requests). |
| Fotocasa   | Working    | Playwright + Chromium; the spider reads the page's embedded JSON, not the CSS classes. |
| Idealista  | Unreliable | DataDome blocks the automated browser in headless. Chromium, stealth, headful with Xvfb and patched Playwright (rebrowser) were tried without success; real use would need a paid anti-bot service. |

Crawl responsibly and respect the minimum refresh (300s).

## Test a spider

`test_spider.sh` runs one portal crawl and shows how many listings it finds
plus a couple of examples. Run it where `scrapy.cfg` lives. In Docker:

```bash
docker exec -it scrapyrealestate bash -c \
  "cd /scrapyrealestate/scrapyrealestate && ./test_spider.sh fotocasa"
```

Spiders: `idealista`, `pisoscom`, `habitaclia`, `fotocasa`, `yaencontre`. You
can pass your URL as a second argument.

## Structure

```
Dockerfile
docker-compose.yml
README.md
scrapyrealestate/
├── main.py                  # loop, Telegram and local deduplication
├── requirements.txt
├── scrapy.cfg
├── test_spider.sh
└── scrapyrealestate/
    ├── settings.py          # Scrapy + Playwright (Chromium)
    ├── items.py
    ├── flask_server.py      # first-boot configuration web page
    ├── proxies.py
    ├── templates/
    └── spiders/             # idealista, pisoscom, fotocasa, habitaclia, yaencontre
```

`data/` (git-ignored) holds `config.json`, `ids.json` and `useragent.txt`.

## Credits and license

Based on [mferark/scrapyrealestate](https://github.com/mferark/scrapyrealestate). GPL license.

## Migration

The bot was retired from the VM (2026-10-08). This repo is a public fork: code
only, no data and no credentials.

- The state (`data/`) was not kept. On relaunch, already-seen listings are sent once again.
- The Telegram bot token goes in `config.json` (see README-fork.md) and is not in the repo. Regenerate it with BotFather (`/token`).
- The rest of the portal configuration is in `config.asturias.json`.
