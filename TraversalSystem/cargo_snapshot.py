"""Conservative comparison of ship Cargo.json snapshots around a transfer."""
import datetime
import json
import os


def read_snapshot(directory):
    try:
        path = os.path.join(directory, 'Cargo.json')
        with open(path, encoding='utf-8-sig') as stream:
            before = os.fstat(stream.fileno())
            data = json.load(stream)
            after = os.fstat(stream.fileno())
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            return None
        timestamp = datetime.datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None or data.get('event') != 'Cargo' or data.get('Vessel') != 'Ship':
            return None
        items = data['Inventory']
        if not isinstance(items, list):
            return None
        quantities = {}
        for item in items:
            name, count = item['Name'], item['Count']
            if not isinstance(name, str) or not name.strip() or type(count) is not int or count < 0:
                return None
            key = name.casefold()
            quantities[key] = quantities.get(key, 0) + count
        if type(data.get('Count')) is not int or data['Count'] != sum(quantities.values()):
            return None
        return timestamp, before.st_mtime_ns, quantities
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def classify_change(before, after):
    if before is None or after is None:
        return 'unknown'
    # Both the event time and file modification must move forward; never trust stale files.
    if after[0] < before[0] or after[1] <= before[1]:
        return 'unknown'
    old, new = before[2], after[2]
    increases = {name for name, count in new.items() if count > old.get(name, 0)}
    if increases - {'tritium'}:
        return 'wrong'
    if increases == {'tritium'}:
        return 'tritium'
    return 'unknown'
