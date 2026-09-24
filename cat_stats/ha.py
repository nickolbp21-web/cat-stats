"""Explicit Home Assistant entity mappings, with unit and availability checks."""
import json
import urllib.request
from datetime import timedelta
from .store import number, timestamp
from .profile import pet_age


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, token, payload=None, header='Authorization'):
    headers = {header: ('Bearer ' if header == 'Authorization' else '') + token,
               'User-Agent': 'CatStats/0.1'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, headers=headers,
        data=None if payload is None else json.dumps(payload, allow_nan=False).encode())
    with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
        return json.load(response)


def read_states(url, token):
    if not url.startswith(('https://', 'http://')):
        raise ValueError('Home Assistant URL must use HTTP or HTTPS')
    data = request_json(url.rstrip('/') + '/api/states', token)
    if not isinstance(data, list):
        raise ValueError('Invalid Home Assistant response')
    return {e['entity_id']: e for e in data if isinstance(e, dict) and 'entity_id' in e}


UNITS = {
    'today_ml': {'ml': 1, 'mL': 1, 'L': 1000, 'l': 1000, 'fl oz': 29.5735295625},
    'yesterday_ml': {'ml': 1, 'mL': 1, 'L': 1000, 'l': 1000, 'fl oz': 29.5735295625},
    'weight_kg': {'kg': 1, 'g': .001, 'lb': .45359237, 'lbs': .45359237},
    'water_pct': {'%': 1}, 'waste_pct': {'%': 1}, 'litter_pct': {'%': 1},
    'filter_days': {'d': 1, 'days': 1},
}
BOOLS = {'online', 'hopper_connected', 'food_low', 'laser_dirty', 'drawer_removed', 'bonnet_removed'}
COUNTS = {'visits_today', 'cycles', 'feedings_today'}
TIMES = {'last_feed_at', 'next_feed_at'}
TEXT = {'status', 'hopper_status'}


def value(states, entity_id, metric):
    entity = states.get(entity_id, {})
    state = entity.get('state')
    if state is None or state in ('unavailable', 'unknown', ''):
        return None
    if metric in BOOLS:
        return {'on': True, 'off': False}.get(state)
    if metric in TIMES:
        try:
            return timestamp(state).isoformat()
        except (ValueError, TypeError):
            return None
    if metric in TEXT:
        return str(state)[:80]
    if metric in UNITS:
        scale = UNITS[metric].get(entity.get('attributes', {}).get('unit_of_measurement'))
        n = number(state)
        if scale is None or n is None or (metric.endswith('_pct') and n > 100):
            return None
        return n * scale
    if metric in COUNTS:
        n = number(state)
        return int(n) if n is not None and n.is_integer() else None
    raise ValueError('Unsupported metric: ' + metric)


def collect(config, states, store, now, tz):
    today = now.astimezone(tz).date()
    devices = []
    for spec in config['devices']:
        device = {k: spec[k] for k in ('id', 'kind', 'name', 'model') if k in spec}
        for metric, entity_id in spec.get('entities', {}).items():
            device[metric] = value(states, entity_id, metric) if entity_id else None
        for metric in TIMES:
            if device.get(metric):
                device[metric + '_local'] = timestamp(device[metric]).astimezone(tz).strftime('%m/%d %H:%M')
        if spec['kind'] == 'fountain':
            # Do not turn an unavailable counter or an old pre-midnight value into zero/today.
            for metric, offset in [('today_ml', 0), ('yesterday_ml', 1)]:
                entity = states.get(spec.get('entities', {}).get(metric), {})
                try:
                    reported_day = timestamp(entity.get('last_updated', '')).astimezone(tz).date()
                except (ValueError, TypeError):
                    reported_day = None
                if reported_day == today:
                    store.daily(spec['id'], today - timedelta(days=offset), device.get(metric), offset == 1, now.isoformat())
                else:
                    device[metric] = None
        devices.append(device)
    pets = []
    for spec in config.get('pets', []):
        pet = {'id': spec['id'], 'name': spec['name']}
        pet.update(pet_age(spec.get('birth_date'), today))
        pet.update({m: value(states, e, m) if e else None for m, e in spec.get('entities', {}).items()})
        pets.append(pet)
    fountains = [d for d in config['devices'] if d['kind'] == 'fountain']
    hydration = store.hydration(fountains, now, tz)
    # Current totals require a valid current reading from EVERY configured fountain.
    if any(d.get('today_ml') is None for d in devices if d['kind'] == 'fountain'):
        hydration['today_ml'] = None
        hydration['seven_days_ml'] = None
    for pet in pets:
        assigned = [d for d in fountains if d.get('assigned_pet') == pet['id']]
        pet['hydration'] = store.hydration(assigned, now, tz, pet['id'])
        if any(d.get('today_ml') is None for d in devices if d['id'] in [x['id'] for x in assigned]):
            pet['hydration']['today_ml'] = None
            pet['hydration']['seven_days_ml'] = None
    alerts = []
    for d in devices:
        def alert(priority, message):
            alerts.append({'priority': priority, 'title': message, 'device': d['name'], 'kind': d['kind']})
        if d.get('online') is False:
            alert(0, 'DEVICE OFFLINE')
            continue
        if d.get('waste_pct') is not None and d['waste_pct'] >= config.get('waste_alert_pct', 90):
            alert(1, 'DRAWER FULL')
        if d.get('water_pct') is not None and d['water_pct'] <= config.get('water_alert_pct', 15):
            alert(1, 'WATER LOW')
        if d.get('litter_pct') is not None and d['litter_pct'] <= config.get('litter_alert_pct', 20):
            alert(2, 'LITTER LOW')
        for field, title in [('food_low', 'FOOD LOW'), ('laser_dirty', 'CLEAN LASER'), ('drawer_removed', 'DRAWER REMOVED'), ('bonnet_removed', 'BONNET REMOVED')]:
            if d.get(field) is True:
                alert(1, title)
        if d.get('filter_days') is not None and d['filter_days'] <= 0:
            alert(3, 'REPLACE FILTER')
    result = {'schema_version': 1, 'generated_at': int(now.timestamp()), 'demo': False,
              'pets': pets, 'devices': devices, 'hydration': hydration,
              'alerts': sorted(alerts, key=lambda a: (a['priority'], a['device']))}
    # Only mapped readings are persisted, never HA's full states (which can contain secrets).
    store.snapshot(now, result)
    return result
