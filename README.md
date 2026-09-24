# Cat Stats

Configurable pet stats, one or more fountains, Granary camera feeder and LR5. Six 192×32 pages: pet summary, feeding, hydration, fountain maintenance, litter status and separate cleaning-cycle and hopper screens, plus a dedicated priority-alert page. Alerts never replace normal device pages. Demo data is visibly marked. Live data is never silently replaced by demo values.

**Status:** functional local initial implementation with standalone and Home Assistant adapters, durable history and an optional Cloudflare relay. Tested against fixtures and the real Glance renderer. Live device readings and relay publishing were verified on one installation; physical Scroll output remains unverified. See [verified capabilities and limitations](research/CAPABILITIES.md).

## Standalone setup (no Home Assistant)

Requires Python 3.12 or newer and Git. Run commands from the cloned `cat-stats` folder. The LR5 library is pinned to inspected source because the published package tested was too old.

```powershell
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements-standalone.txt
Copy-Item config.standalone.example.json config.json
```

Use environment variables for credentials; never put them in the Glance app or commit them. For a temporary interactive session, avoid typing passwords into command history:

```powershell
$env:CAT_STATS_PETLIBRO_EMAIL = Read-Host 'PETLIBRO email'
$env:CAT_STATS_PETLIBRO_PASSWORD = Read-Host 'PETLIBRO password' -MaskInput
$env:CAT_STATS_WHISKER_EMAIL = Read-Host 'Whisker email'
$env:CAT_STATS_WHISKER_PASSWORD = Read-Host 'Whisker password' -MaskInput
.venv/Scripts/python -m cat_stats --discover
```

Discovery prints only device identifiers and pet IDs. Enter matching `serial` values in `config.json`; enter the Whisker pet ID in `whisker_pet_id`. Set `pets[].name` to any display name. Confirm fountain labels: PLWF106 is plug-in, PLWF116 cordless. Both are supported; do not assume the label from appearance alone.

PETLIBRO's community integration advises a separate shared-device account to avoid signing the phone app out. The standalone adapter uses the same cloud protocol, so follow that advice if sharing is supported for your devices. Only the inspected US region is implemented. Authentication failures require local troubleshooting; never share your passwords or raw API dumps in a public issue.

Run a single check, then the continuous Cat Stats:

```powershell
.venv/Scripts/python -m cat_stats --once
.venv/Scripts/python -m cat_stats
```

The Cat Stats polls every five minutes in standalone mode. It writes `status.json` and `cat-stats.sqlite` locally. Keep the database across restarts. Configure your service manager or Windows Task Scheduler with this folder as its working directory, the venv Python executable and `-m cat_stats`; supply credentials through the account's protected environment/secret manager. Close the terminal or stop the service to stop polling. No feeding, cleaning or device-setting commands are issued.

## Connect Glance through a separate Cloudflare Worker

Install Cloudflare's Wrangler tool and sign in using your normal local development setup. From `cloudflare/`:

```text
wrangler kv namespace create CAT_STATS
```

Put the returned namespace ID in `wrangler.toml`. Create a NEW namespace and worker, never reuse Bambu's. Generate two independent random keys (for example `python -c "import secrets; print(secrets.token_urlsafe(32))"` twice), then store them through Wrangler's prompts:

```text
wrangler secret put READ_KEY
wrangler secret put WRITE_KEY
wrangler deploy
```

Set Cat Stats environment variables `CAT_STATS_PUSH_URL` to your HTTPS Worker `/ingest` URL and `CAT_STATS_WRITE_KEY` to its write key. Restart the Cat Stats. In Glance, set `endpoint` to the Worker's `/status` URL and `readkey` to the separate read key. Leave demo set to `Live`. The relay rejects unauthorized reads/writes, limits payloads and marks snapshots older than 15 minutes stale. Glance independently checks timestamps. Cloudflare KV is eventually consistent, and the app cache/refresh is five minutes; this is an ambient dashboard, not an instant alert service.

The display app lives in [the Cat Stats submission branch](https://github.com/nickolbp21-web/glance-dev-network/tree/cat-stats/apps/cat-stats). Clone that branch separately and run `gdn studio apps/cat-stats`. Choose Demo to preview without credentials. Run `gdn validate apps/cat-stats` before submitting. The display app is submitted separately to the Glance Developer Network. This Cat Stats never issues device-control commands.

For guided Windows device selection, run `Connect Cat Stats.cmd` after copying the example configuration and installing dependencies. It prompts for credentials locally and starts collection. Set push environment variables before launching it to enable relay publishing.

## Hydration semantics

- Today means the configured local calendar day. Seven days means today plus six previous local dates, not a rolling 168-hour window.
- Both fountains contribute once. Daily totals are upserted, not summed on every poll. Yesterday's API value finalizes yesterday and repairs overnight missed polls.
- The 7-day number stays `--` until all seven days have coverage for every configured fountain. Outages lasting more than a day can leave gaps; restarting cannot reconstruct unavailable vendor history.
- Default scope is household. Set each fountain's `assigned_pet` to a pet ID only when that fountain is exclusively used by that pet. Select that ID in Glance's `petid` input for pet hydration. Leaving `petid` blank rotates summary pets and shows household hydration.
- PETLIBRO per-drink volume/time remains unverified. The live app shows unavailable, even though Demo illustrates how a supported event would look. Drinking totals never come from reservoir loss.
- Raw normalized drinking events can be imported with `python -m cat_stats --import-events events.json`. Each event needs `source`, configured `device`, stable `event_id`, zoned ISO `at`, and `amount_ml`; optional `pet_id` and `duration_seconds`. Replayed IDs are ignored. Raw input is stored locally. Individual events supply last-drink information; daily provider counters supply totals, so they are never added together. There is no automatic vendor drink-event adapter yet.

## Optional Home Assistant setup

Install `requirements.txt`, copy `config.example.json` to `config.json`, and set `source` to `home_assistant` (also the default if omitted). Install the PETLIBRO community integration and built-in Whisker integration. Use Developer Tools → States to copy actual entity IDs into the blank mappings; IDs vary per installation. Set `CAT_STATS_HA_TOKEN` to a long-lived access token and `home_assistant_url` to your trusted instance. HTTPS is preferred; local HTTP sends the token unencrypted on that network.

Map fountain today/yesterday consumption (mL, L or US fl oz), water percentage (%) and filter days. Map feeder successful last feeding and next feeding timestamps, feeding count and food-low/online binary sensors where available. Map LR5 status, drawer/litter percentages, cycles, online, hopper connected and maintenance flags. Map pet measured weight and visits to that pet's entities. Never map the robot's unassigned last weight to every pet. Missing/unavailable entities and unrecognized units produce unknown values.

## Validation and maintenance

```text
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_worker.mjs
```

Display validation is performed in the separate Glance app repository with `gdn validate apps/cat-stats`.

Database tables: `daily` (per-device calendar totals and finalization), `events` (deduplicated normalized raw events), `snapshots` (mapped telemetry only). Snapshots do not contain HA's full entity state or vendor auth/camera payloads. History currently has no automatic retention limit; back up the database and manage disk space for long-running installations. Changing timezone or repurposing a device ID changes historical meaning: use a new database/device ID rather than mixing records. Public config is generic; `config.json`, credentials, database files and downloaded research source are excluded from version control.

Brand names identify compatible devices. Cat Stats is not affiliated with PETLIBRO or Whisker.

Pet birthdays: set `birth_date` to `YYYY-MM-DD` in each pet configuration. Summary shows completed years and days since the last birthday in the configured timezone. February 29 birthdays use February 28 in non-leap years. No birthday means unavailable age.

LR5 hopper: the adapter maps the verified `hopperStatusIndicator.title` status (for example Litter Low). No numeric hopper-fullness field is assumed. Missing status displays LEVEL NOT REPORTED. The cycle counter is explicitly the LR5 lifetime cleaning-cycle counter. Restart the collector after updating adapter code to receive this new status field.

