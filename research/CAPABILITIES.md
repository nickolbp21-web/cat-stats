# Integration evidence — checked September 23, 2026

## Existing Bambu conventions

Inspected `apps/bambu-print-status` without changing it. Reused the architecture: independent `manifest.yaml` + `app.star`, HTTPS status JSON with `x-api-key`, encrypted Glance API-key input, 300-second refresh/cache, uppercase bitmap fonts, 192×32 canvas and x=10..181 safe area. Cat Stats has separate SQLite history, Cloudflare namespace and secrets. No Bambu endpoints or credentials were read or copied.

## PETLIBRO (community protocol, not a public supported vendor API)

Sources: [supported models](https://github.com/jjjonesjr33/petlibro), [API protocol](https://github.com/jjjonesjr33/petlibro/blob/dev/custom_components/petlibro/api.py), [Dockstream 2 fields](https://github.com/jjjonesjr33/petlibro/blob/dev/custom_components/petlibro/devices/fountains/dockstream_2_smart_fountain.py), [Granary fields](https://github.com/jjjonesjr33/petlibro/blob/dev/custom_components/petlibro/devices/feeders/granary_smart_camera_feeder.py), [HA sensors](https://github.com/jjjonesjr33/petlibro/blob/dev/custom_components/petlibro/sensor.py).

PLAF203, PLWF106 and PLWF116 are listed. Fountain drinking totals use `todayTotalMl` / `yesterdayTotalMl` from `todayDrinkData`. Water percentage is separate (`weightPercent`); filter life is days. No verified per-drink volume/timestamp mapping was found for these models. Do not derive drinking from reservoir changes or counter increments. Missing fields stay null instead of adopting upstream zero defaults. Fountain totals do not identify a pet.

Feeding history uses successful `GRAIN_OUTPUT_SUCCESS` records and millisecond `recordTime`; scheduled times use enabled plans, timezone and ISO weekday repeat lists. Food low is based on explicit boolean `surplusGrain`. Bowl attachment/color do not alter these telemetry mappings. Standalone currently supports the inspected US API host only. These interfaces can change; the code is fixture-tested, not account-tested.

## Whisker

Sources: [Home Assistant documentation](https://www.home-assistant.io/integrations/litterrobot/), [pinned LR5 implementation](https://github.com/natekspencer/pylitterbot/blob/ba90c7c317d2873fcf6f5266f9d97b0f309fba58/pylitterbot/robot/litterrobot5.py), [pet profiles](https://github.com/natekspencer/pylitterbot/blob/ba90c7c317d2873fcf6f5266f9d97b0f309fba58/pylitterbot/pet.py).

LR5 provides status, drawer/litter percentages, connectivity, cycles, hopper installation and maintenance flags. The pinned library contains LR5; the PyPI version obtained during development (2025.6.5) did not. Raw keys preserve missing fields rather than defaulting to zero. Pet measured weight is pounds upstream, converted to kg internally; visits follow timestamped pet weight history, matching the integration convention. A capped history cannot claim a complete visit count unless it reaches before local midnight. Robot weight is not assigned to a pet automatically. Hopper connection does not imply hopper fill percentage. `odometerCleanCycles` is shown simply as cycles, without promising lifetime totals.

## Device artwork

The display app documents its manufacturer source URLs and asset transformations in `ASSETS.md`.
