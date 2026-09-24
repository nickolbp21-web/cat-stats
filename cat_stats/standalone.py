"""Read-only vendor adapters. Protocol evidence is recorded in research/CAPABILITIES.md."""
import asyncio
import copy
import hashlib
import json
import os
import urllib.request
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from .ha import NoRedirect, UNITS, BOOLS
from .store import number


class VendorError(Exception):
    pass


class Petlibro:
    def __init__(self, tz):
        self.tz = tz
        self.token = None

    def call(self, path, body, retry=True):
        headers = {'Content-Type':'application/json','source':'ANDROID','language':'EN',
                   'timezone':self.tz,'version':'1.3.45'}
        if self.token:
            headers['token'] = self.token
        req = urllib.request.Request('https://api.us.petlibro.com' + path,
                                     data=json.dumps(body).encode(), headers=headers)
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise VendorError('Invalid PETLIBRO response')
        if data.get('code') == 1009 and retry and path != '/member/auth/login':
            self.login()
            return self.call(path, body, False)
        if data.get('code') != 0:
            raise VendorError('PETLIBRO rejected request')
        return data.get('data')

    def login(self):
        data = self.call('/member/auth/login', {
            'appId':1,'appSn':'c35772530d1041699c87fe62348507a8','country':'US',
            'email':os.environ['CAT_STATS_PETLIBRO_EMAIL'],
            # Required vendor protocol; never persist this password hash.
            'password':hashlib.md5(os.environ['CAT_STATS_PETLIBRO_PASSWORD'].encode()).hexdigest(),
            'phoneBrand':'','phoneSystemVersion':'','timezone':self.tz,'thirdId':None,'type':None
        }, False)
        if not isinstance(data, dict) or not isinstance(data.get('token'), str):
            raise VendorError('PETLIBRO login did not return a token')
        self.token = data['token']

    def device(self, spec, now):
        if not self.token:
            self.login()
        serial = spec['serial']
        args = {'id':serial,'deviceSn':serial}
        info = self.call('/device/device/realInfo', args)
        if not isinstance(info, dict):
            raise VendorError('Missing device information')
        result = {'online': info.get('online') if type(info.get('online')) is bool else None}
        if spec['kind'] == 'fountain':
            if spec['model'] not in ('PLWF106','PLWF116'):
                raise ValueError('Standalone fountain requires PLWF106 or PLWF116')
            drink = self.call('/data/deviceDrinkWater/todayDrinkData', args)
            if not isinstance(drink, dict):
                drink = {}
            result.update(today_ml=number(drink.get('todayTotalMl')),
                          yesterday_ml=number(drink.get('yesterdayTotalMl')),
                          water_pct=number(info.get('weightPercent')),
                          filter_days=number(info.get('remainingReplacementDays')))
        elif spec['kind'] == 'feeder':
            if spec['model'] != 'PLAF203':
                raise ValueError('Standalone feeder requires PLAF203')
            grain = self.call('/device/data/grainStatus', args)
            result['feedings_today'] = number(grain.get('todayFeedingTimes')) if isinstance(grain,dict) else None
            surplus = info.get('surplusGrain')
            result['food_low'] = not surplus if type(surplus) is bool else None
            records = self.call('/device/workRecord/list', {
                'deviceSn':serial,'startTime':int((now-timedelta(days=30)).timestamp()*1000),
                'endTime':int(now.timestamp()*1000),'size':25,'type':['GRAIN_OUTPUT_SUCCESS']})
            times = []
            for day in records if isinstance(records,list) else []:
                for record in day.get('workRecords', []) if isinstance(day,dict) else []:
                    ms = number(record.get('recordTime')) if isinstance(record,dict) else None
                    if ms and record.get('type') == 'GRAIN_OUTPUT_SUCCESS' and ms <= now.timestamp()*1000:
                        times.append(ms)
            result['last_feed_at'] = datetime.fromtimestamp(max(times)/1000,timezone.utc).isoformat() if times else None
            base = self.call('/device/device/baseInfo', args)
            if isinstance(base,dict) and base.get('enableFeedingPlan') is True:
                plans = self.call('/device/feedingPlan/list', args)
                result['next_feed_at'] = next_feed(plans, now)
        return result


def next_feed(plans, now):
    candidates = []
    for plan in plans if isinstance(plans,list) else []:
        if not isinstance(plan,dict) or not plan.get('enable'):
            continue
        try:
            tz = ZoneInfo(plan['timezone'])
            hour, minute = map(int, plan['executionTime'].split(':'))
            days = plan.get('repeatDay', '[]')
            days = json.loads(days) if isinstance(days,str) else days
            if not isinstance(days,list) or any(type(d) is not int or d not in range(1,8) for d in days):
                continue
            for offset in range(8):
                date = now.astimezone(tz).date()+timedelta(days=offset)
                if days and date.isoweekday() not in days:
                    continue
                candidate = datetime.combine(date,time(hour,minute),tz).astimezone(timezone.utc)
                if candidate > now:
                    candidates.append(candidate)
                    break
        except (KeyError, ValueError, TypeError):
            continue
    return min(candidates).isoformat() if candidates else None


def robot_metrics(robot):
    # Use inspected raw keys to preserve missing values; some library properties default to 0/False.
    raw = robot.to_dict()
    state = raw.get('state', {}) if isinstance(raw,dict) else {}
    if not isinstance(state,dict):
        state = {}
    result = {name: state.get(key) for name,key in {
        'online':'isOnline','hopper_connected':'isHopperInstalled','laser_dirty':'isLaserDirty',
        'drawer_removed':'isDrawerRemoved','bonnet_removed':'isBonnetRemoved',
        'waste_pct':'dfiLevelPercent','litter_pct':'litterLevelPercent','cycles':'odometerCleanCycles'}.items()}
    indicator = state.get('hopperStatusIndicator')
    title = indicator.get('title') if isinstance(indicator, dict) else None
    result['hopper_status'] = title if isinstance(title, str) and title else None
    status = robot.status if state and type(state.get('isOnline')) is bool else None
    result['status'] = getattr(status, 'name', str(status)).replace('_', ' ') if status is not None else None
    return result


def synthetic_states(config, readings, now):
    """Feed both adapters into one normalization/history path without guessing HA entity names."""
    mapped = copy.deepcopy(config)
    states = {}
    for spec in mapped['devices'] + mapped.get('pets', []):
        spec['entities'] = {}
        for metric, reading in readings.get(spec['id'], {}).items():
            key = spec['id'] + '.' + metric
            spec['entities'][metric] = key
            unit = next(iter(UNITS[metric])) if metric in UNITS else None
            state = 'unknown' if reading is None else ('on' if reading else 'off') if metric in BOOLS and type(reading) is bool else str(reading)
            states[key] = {'state':state,'last_updated':now.isoformat(),'attributes':{'unit_of_measurement':unit}}
    return mapped, states


class Standalone:
    def __init__(self, config):
        self.config = config
        self.petlibro = Petlibro(config['timezone'])
        self.account = None

    async def read(self, now):
        readings = {}
        for spec in self.config['devices']:
            if spec['kind'] in ('feeder','fountain'):
                readings[spec['id']] = await asyncio.to_thread(self.petlibro.device,spec,now)
        if any(d['kind'] == 'litter' for d in self.config['devices']):
            from pylitterbot import Account, LitterRobot5
            if self.account is None:
                self.account = Account(robot_types=[LitterRobot5])
                await self.account.connect(username=os.environ['CAT_STATS_WHISKER_EMAIL'],
                    password=os.environ['CAT_STATS_WHISKER_PASSWORD'],load_robots=True,load_pets=True)
            else:
                # Call refresh directly; account.refresh_robots catches failures internally.
                for robot in self.account.robots:
                    await robot.refresh()
                await self.account.load_pets()
            for spec in self.config['devices']:
                if spec['kind'] != 'litter':
                    continue
                matches = [r for r in self.account.robots if r.serial == spec['serial']]
                if len(matches) != 1:
                    raise VendorError('Configured LR5 not found')
                readings[spec['id']] = robot_metrics(matches[0])
            for spec in self.config.get('pets', []):
                match = next((p for p in self.account.pets if p.id == spec.get('whisker_pet_id')), None)
                if match:
                    raw = match.to_dict()
                    pounds = number(raw.get('lastWeightReading'))
                    start = datetime.combine(now.astimezone(ZoneInfo(self.config['timezone'])).date(),time.min,ZoneInfo(self.config['timezone']))
                    history = await match.fetch_weight_history(limit=100)
                    # A full result may be truncated; do not label an incomplete count as today's total.
                    complete = len(history) < 100 or any(x.timestamp < start for x in history)
                    readings[spec['id']] = {'weight_kg':pounds*.45359237 if pounds is not None else None,
                        'visits_today':sum(start <= x.timestamp <= now for x in history) if complete else None}
        return synthetic_states(self.config, readings, now)

    async def close(self):
        if self.account:
            await self.account.disconnect()


async def discover(config):
    """Print only setup identifiers, never tokens or raw responses."""
    from pylitterbot import Account, LitterRobot5
    if os.environ.get('CAT_STATS_PETLIBRO_EMAIL'):
        client = Petlibro(config['timezone'])
        await asyncio.to_thread(client.login)
        devices = await asyncio.to_thread(client.call, '/device/device/list', {})
        if not isinstance(devices,list):
            raise VendorError('Unexpected PETLIBRO device list format')
        for d in devices:
            if isinstance(d,dict):
                print(json.dumps({k:d[k] for k in ('name','deviceSn','productIdentifier') if k in d}))
    if os.environ.get('CAT_STATS_WHISKER_EMAIL'):
        account = Account(robot_types=[LitterRobot5])
        try:
            await account.connect(username=os.environ['CAT_STATS_WHISKER_EMAIL'],
                password=os.environ['CAT_STATS_WHISKER_PASSWORD'],load_robots=True,load_pets=True)
            for robot in account.robots:
                print(json.dumps({'name':robot.name,'serial':robot.serial,'model':robot.model}))
            for pet in account.pets:
                print(json.dumps({'name':pet.name,'whisker_pet_id':pet.id}))
        finally:
            await account.disconnect()
