# Initial validation

Tested locally with Python 3.14, Node 24 and the user's installed Glance Developer Network renderer.

- 16 Cat Stats tests: multiple fountains, persistence/restart, seven local calendar dates, missing days, event deduplication, invalid/future events, unavailable readings, midnight handling, DST, unit conversion, priority, configurable names, feeder schedules and latest successful feeding.
- Relay tests: separate read/write credentials, missing snapshot, schema/timestamp validation, ingest/read, stale detection and payload size limit.
- 96 real Starlark page renders: eight pages × six scenarios × two rotation times; all 192×32 with blank 10-pixel outer margins.
- Live render path mocked at HTTP boundary: normal empty snapshot, invalid payload, stale snapshot and priority selection on the dedicated alerts page. No vendor credentials involved.
- Instantiated the actual pinned `pylitterbot.LitterRobot5` and checked the mapper preserves absent telemetry.
- Glance manifest/app validator run before delivery.

Live PETLIBRO and Whisker readings and the separate Cloudflare relay were verified during local setup. Still unverified: physical Scroll output, all vendor response variations, Dockstream 2 individual drinking events. The feeder illustration shows the standard bowl; exact slow-feed bowl artwork is not available yet.
