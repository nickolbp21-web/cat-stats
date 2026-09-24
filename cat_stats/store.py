"""Durable history. Daily provider totals and individual events are never added together."""
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return dt.astimezone(timezone.utc)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS daily (
              device TEXT, day TEXT, ml REAL, final INTEGER, observed TEXT,
              PRIMARY KEY(device, day));
            CREATE TABLE IF NOT EXISTS events (
              source TEXT, device TEXT, event_id TEXT, pet TEXT,
              at TEXT, ml REAL, duration REAL, raw TEXT,
              PRIMARY KEY(source, device, event_id));
            CREATE TABLE IF NOT EXISTS snapshots (
              observed TEXT PRIMARY KEY, payload TEXT);
        ''')

    def daily(self, device, day, ml, final, observed):
        ml = number(ml)
        if ml is None:
            return
        # A yesterday reading finalizes yesterday. Later provisional readings cannot undo it.
        self.db.execute('''INSERT INTO daily VALUES (?,?,?,?,?)
          ON CONFLICT(device,day) DO UPDATE SET ml=excluded.ml, final=excluded.final,
          observed=excluded.observed WHERE excluded.final >= daily.final
          AND excluded.observed >= daily.observed''',
          (device, day.isoformat(), ml, int(final), observed))

    def event(self, event, now):
        required = ('source', 'device', 'event_id', 'at')
        if any(not isinstance(event.get(k), str) or not event[k] for k in required):
            raise ValueError('Event requires source, device, event_id and zoned at timestamp')
        at = timestamp(event['at'])
        ml = number(event.get('amount_ml'))
        if ml is None or at > now:
            raise ValueError('Event amount must be finite, nonnegative and not in the future')
        duration = number(event.get('duration_seconds'))
        self.db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)',
            (event['source'], event['device'], event['event_id'], event.get('pet_id'),
             at.isoformat(), ml, duration, json.dumps(event, allow_nan=False)))

    def hydration(self, devices, now, tz, pet_id=None):
        today = now.astimezone(tz).date()
        ids = [d['id'] for d in devices]
        result = {'today_ml': None, 'seven_days_ml': None, 'covered_days': 0,
                  'last_ml': None, 'last_at_local': None, 'scope': pet_id or 'household'}
        if not ids:
            return result
        placeholders = ','.join('?' for _ in ids)
        rows = self.db.execute(f'SELECT device,day,ml,final FROM daily WHERE device IN ({placeholders})', ids)
        totals = {(d, day): (ml, final) for d, day, ml, final in rows}
        sums = []
        for offset in range(7):
            day = (today - timedelta(days=offset)).isoformat()
            values = [totals.get((d, day)) for d in ids]
            complete = all(v is not None and (offset == 0 or v[1]) for v in values)
            if complete:
                sums.append(sum(v[0] for v in values))
                result['covered_days'] += 1
                if offset == 0:
                    result['today_ml'] = sums[-1]
        if len(sums) == 7:
            result['seven_days_ml'] = sum(sums)
        events = self.db.execute(f'SELECT device,pet,at,ml FROM events WHERE device IN ({placeholders}) AND at<=? ORDER BY at DESC',
                                 ids + [now.isoformat()])
        for device, pet, at, ml in events:
            if pet_id is None or pet == pet_id or (pet is None and any(d['id'] == device and d.get('assigned_pet') == pet_id for d in devices)):
                result['last_ml'] = ml
                result['last_at_local'] = timestamp(at).astimezone(tz).strftime('%m/%d %H:%M')
                break
        return result

    def snapshot(self, now, data):
        self.db.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?)',
                        (now.isoformat(), json.dumps(data, allow_nan=False)))
        self.db.commit()
