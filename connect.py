"""Interactive local setup. Passwords stay in this process and its collector child."""
import asyncio
import copy
import getpass
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from cat_stats.standalone import Petlibro, Standalone
from cat_stats.ha import collect
from cat_stats.store import Store
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
logging.disable(logging.CRITICAL)  # Vendor exceptions/logs may contain response details.


def progress(stage):
    (ROOT/'setup-progress.json').write_text(json.dumps({'stage':stage,'updated_at':datetime.now(timezone.utc).isoformat()}))


def choose(label, candidates, describe):
    if not candidates:
        raise ValueError('No matching devices found')
    print('\n' + label)
    for index, candidate in enumerate(candidates, 1):
        print(f'  {index}. {describe(candidate)}')
    while True:
        answer = input('Choose a number: ').strip()
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer)-1]
        print('Please enter one of the listed numbers.')


def credentials(vendor):
    prefix = 'CAT_STATS_' + vendor.upper()
    os.environ[prefix+'_EMAIL'] = input(vendor + ' email: ').strip()
    os.environ[prefix+'_PASSWORD'] = getpass.getpass(vendor + ' password (hidden): ')


async def setup():
    from pylitterbot import Account, LitterRobot5
    os.chdir(ROOT)
    config = json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    config = copy.deepcopy(config)
    print('CAT STATS - CONNECT YOUR DEVICES\n')
    print('Passwords are hidden, kept in memory, and not saved to disk or chat.')
    print('PETLIBRO may sign its phone app out. A shared-device account is preferred when available.')
    progress('waiting_for_petlibro_sign_in')
    credentials('PETLIBRO')
    client = Petlibro(config['timezone'])
    print('\nConnecting to PETLIBRO...')
    await asyncio.to_thread(client.login)
    devices = await asyncio.to_thread(client.call, '/device/device/list', {})
    if not isinstance(devices,list):
        raise ValueError('Unexpected device list; adapter needs adjustment')
    candidates = [d for d in devices if isinstance(d,dict) and d.get('deviceSn')]
    progress('selecting_petlibro_devices')
    used = set()
    for spec in config['devices']:
        if spec['kind'] not in ('feeder','fountain'):
            continue
        selected = choose('Select ' + spec['name'] + ' (' + spec['kind'] + ')',
                          [d for d in candidates if d['deviceSn'] not in used],
                          lambda d: str(d.get('name','Unnamed')) + ' / ' + str(d.get('productIdentifier','')) + ' / ' + d['deviceSn'])
        spec['serial'] = selected['deviceSn']
        used.add(spec['serial'])
        if spec['kind'] == 'fountain':
            spec['model'] = choose('Fountain model (check its label)', ['PLWF106','PLWF116'],
                                    lambda m: m + (' - plug-in' if m == 'PLWF106' else ' - cordless'))
        else:
            print('Using PLAF203 Granary Smart Camera Feeder.')
        name = input('Display name [' + spec['name'] + ']: ').strip()
        if name:
            spec['name'] = name
    progress('waiting_for_whisker_sign_in')
    credentials('WHISKER')
    account = Account(robot_types=[LitterRobot5])
    try:
        print('\nConnecting to Whisker...')
        await account.connect(username=os.environ['CAT_STATS_WHISKER_EMAIL'],
                              password=os.environ['CAT_STATS_WHISKER_PASSWORD'],load_robots=True,load_pets=True)
        progress('selecting_whisker_devices')
        for spec in config['devices']:
            if spec['kind'] == 'litter':
                robot = choose('Select your Litter-Robot 5', account.robots, lambda r: r.name + ' / ' + r.serial)
                spec['serial'] = robot.serial
        for pet in config['pets']:
            selected = choose('Select the Whisker profile for ' + pet['name'], account.pets, lambda p: p.name)
            pet['whisker_pet_id'] = selected.id
    finally:
        await account.disconnect()
    print('\nChecking the first live readings...')
    progress('checking_live_readings')
    adapter = Standalone(config)
    adapter.petlibro = client
    store = Store(str(ROOT/'cat-stats.sqlite'))
    try:
        now = datetime.now(timezone.utc)
        mapped, states = await adapter.read(now)
        data = collect(mapped,states,store,now,ZoneInfo(config['timezone']))
    finally:
        await adapter.close()
        store.db.close()
    # Commit device selections only after the complete read succeeds.
    temp = ROOT/'config.pending.json'
    temp.write_text(json.dumps(config,indent=2),encoding='utf-8')
    temp.replace(ROOT/'config.json')
    (ROOT/'status.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print('\nConnected. First live readings:')
    for d in data['devices']:
        metrics = {k:v for k,v in d.items() if k not in ('id','name','kind','model') and v is not None}
        print(d['name'] + ': ' + json.dumps(metrics))
    print('Water today (all fountains):', data['hydration']['today_ml'], 'mL')
    progress('connected')
    print('\nStarting collection every five minutes. Keep this window open; Ctrl+C stops it.')
    return True


if __name__ == '__main__':
    try:
        if asyncio.run(setup()):
            subprocess.run([sys.executable,'-m','cat_stats'],cwd=ROOT,check=False)
    except KeyboardInterrupt:
        progress('stopped')
    except Exception as exc:
        progress('setup_failed_' + type(exc).__name__)
        print('\nSetup did not finish (' + type(exc).__name__ + '). Your configuration was not replaced.')
        print('Tell Codex this error type and which step failed. Do not share passwords.')
        input('Press Enter to close...')
    finally:
        for name in list(os.environ):
            if name.startswith('CAT_STATS_') and name.endswith(('_EMAIL','_PASSWORD')):
                os.environ.pop(name,None)
