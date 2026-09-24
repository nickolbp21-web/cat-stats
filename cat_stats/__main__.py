import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .ha import collect, read_states, request_json
from .store import Store


async def run():
    parser = argparse.ArgumentParser(description='Cat Stats read-only standalone or Home Assistant collector')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--database', default='cat-stats.sqlite')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--import-events', help='Import normalized JSON event array; never vendor guesses')
    parser.add_argument('--discover', action='store_true', help='List vendor device identifiers for local setup')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    tz = ZoneInfo(config['timezone'])
    if args.discover:
        from .standalone import discover
        await discover(config)
        return
    ids = [d['id'] for d in config['devices']]
    pet_ids = [p['id'] for p in config.get('pets', [])]
    if len(ids) != len(set(ids)) or len(pet_ids) != len(set(pet_ids)):
        raise ValueError('Device and pet IDs must be unique')
    if any(d.get('assigned_pet') and d['assigned_pet'] not in pet_ids for d in config['devices']):
        raise ValueError('assigned_pet must refer to a configured pet')
    store = Store(args.database)
    if args.import_events:
        with store.db:
            for event in json.loads(Path(args.import_events).read_text()):
                if event.get('device') not in ids or (event.get('pet_id') and event['pet_id'] not in pet_ids):
                    raise ValueError('Unknown event device or pet')
                store.event(event, datetime.now(timezone.utc))
        print('Events imported; replaying identical event IDs is safe.')
        store.db.close()
        return
    source = config.get('source', 'home_assistant')
    if source not in ('standalone', 'home_assistant'):
        raise ValueError('source must be standalone or home_assistant')
    token = os.environ.get('CAT_STATS_HA_TOKEN')
    adapter = None
    if source == 'standalone':
        from .standalone import Standalone
        adapter = Standalone(config)
    elif not token:
        raise ValueError('CAT_STATS_HA_TOKEN is required for Home Assistant mode')
    endpoint = os.environ.get('CAT_STATS_PUSH_URL')
    if endpoint and not endpoint.startswith('https://'):
        raise ValueError('Push endpoint must use HTTPS')
    while True:
        try:
            now = datetime.now(timezone.utc)
            if adapter:
                mapped, states = await adapter.read(now)
            else:
                mapped = config
                states = await asyncio.to_thread(read_states, config['home_assistant_url'], token)
            data = collect(mapped, states, store, now, tz)
            target = Path('status.json')
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
            temporary.replace(target)
            if endpoint:
                request_json(endpoint, os.environ['CAT_STATS_WRITE_KEY'], data, 'x-api-key')
            print('Cat Stats updated', now.isoformat(), flush=True)
        except Exception as exc:
            # Never print exception bodies/URLs, credentials, or raw vendor responses.
            print('Update failed (' + type(exc).__name__ + '); previous data will expire.', flush=True)
            store.db.rollback()
            if adapter:
                await adapter.close()
                adapter = Standalone(config)
            if args.once:
                store.db.close()
                raise SystemExit(1)
        if args.once:
            if adapter:
                await adapter.close()
            store.db.close()
            break
        await asyncio.sleep(max(300 if adapter else 60, int(config.get('poll_seconds', 60))))


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
