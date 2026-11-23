import datetime
import json
import os
import threading

UTC = datetime.timezone.utc


def event_time(event):
    return datetime.datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))


class JournalWatcher:
    # A conservative five-minute cooldown after the actual arrival event.
    COOLDOWN_SECONDS = 300
    STALE_REQUEST_SECONDS = 30 * 60

    def __init__(self):
        self.lock = threading.RLock()
        self.reset_all()

    def reset_all(self):
        with self.lock:
            self.lastCarrierRequest = ''
            self.hasJumped = False
            self.departureTime = ''
            self.lastFuel = 1000
            self.lastUsedFileName = None
            self.positions = {}
            self.carrier_id = None
            self.pending = None
            self.last_jump_at = None
            self.cancelled_at = None
            self.expected_system = None
            self.request_started = None
            self.last_system = None
            self.unknown_until = None
            self.cargo_transfer_serial = 0
            self.cargo_transfer_events = []

    def initialize(self, directory):
        """Recover state across recent sessions without reporting historical jumps as new."""
        with self.lock:
            self.reset_all()
            files = sorted(os.path.join(directory, name) for name in os.listdir(directory)
                           if name.startswith('Journal') and name.endswith('.log'))
            # Establish ownership before replaying arrival events from other carriers.
            for filename in files[-10:]:
                with open(filename, encoding='utf-8-sig') as journal:
                    for line in journal:
                        if not line.endswith('\n'):
                            continue
                        event = json.loads(line)
                        if event.get('event') == 'CarrierStats':
                            self.carrier_id = event.get('CarrierID')
            for filename in files[-10:]:
                self.process_journal(filename, historical=True)
            self.hasJumped = False
            self.lastCarrierRequest = ''
            self.departureTime = ''
            if self.last_jump_at is None and self.pending is None:
                self.unknown_until = datetime.datetime.now(UTC) + datetime.timedelta(seconds=self.COOLDOWN_SECONDS)

    def begin_navigation(self, system):
        with self.lock:
            self.expected_system = system.casefold()
            self.request_started = datetime.datetime.now(UTC)
            self.lastCarrierRequest = ''
            self.departureTime = ''
            self.hasJumped = False
            self.cancelled_at = None

    def _apply(self, event, historical):
        kind = event.get('event')
        if kind == 'CarrierStats':
            self.carrier_id = event.get('CarrierID', self.carrier_id)
            fuel = event['FuelLevel']
            if not historical:
                print('Fuel: %s' % fuel)
                if fuel < self.lastFuel and fuel < 100:
                    print('alert:Your Tritium is running low.')
            self.lastFuel = fuel
        elif kind == 'CargoTransfer' and not historical:
            self.cargo_transfer_serial += 1
            self.cargo_transfer_events.append((self.cargo_transfer_serial, event.get('Transfers')))
            self.cargo_transfer_events = self.cargo_transfer_events[-100:]
        elif kind == 'CarrierJumpRequest':
            if self.carrier_id is not None and event.get('CarrierID') != self.carrier_id:
                return
            self.carrier_id = event.get('CarrierID', self.carrier_id)
            self.pending = event
            self.cancelled_at = None
            fresh = self.request_started is not None and event_time(event) >= self.request_started - datetime.timedelta(seconds=1)
            if not historical and fresh and event['SystemName'].casefold() == self.expected_system:
                self.lastCarrierRequest = event['SystemName']
                self.departureTime = event['DepartureTime']
                print('Carrier destination: ' + self.lastCarrierRequest)
                print('Departure time: ' + self.departureTime)
        elif kind == 'CarrierJumpCancelled':
            if self.carrier_id is not None and event.get('CarrierID', self.carrier_id) != self.carrier_id:
                return
            self.pending = None
            self.cancelled_at = event_time(event)
        elif kind in ('CarrierJump', 'Location'):
            if self.carrier_id is not None and event.get('MarketID') != self.carrier_id:
                return
            if event.get('StationType') != 'FleetCarrier' or not event.get('Docked'):
                return
            if kind == 'Location':
                if (not self.pending or event.get('StarSystem') != self.pending['SystemName']
                        or event_time(event) < datetime.datetime.fromisoformat(self.pending['DepartureTime'].replace('Z', '+00:00'))):
                    return
            self.last_system = event.get('StarSystem')
            self.last_jump_at = event_time(event)
            self.unknown_until = None
            self.pending = None
            if (not historical and self.request_started is not None
                    and self.last_jump_at >= self.request_started
                    and event.get('StarSystem', '').casefold() == self.expected_system):
                self.hasJumped = True

    def process_journal(self, file_name, historical=False):
        file_name = os.fspath(file_name)
        with self.lock:
            self.lastUsedFileName = file_name
            position = self.positions.get(file_name, 0)
            if os.path.getsize(file_name) < position:
                position = 0
            with open(file_name, 'rb') as journal:
                journal.seek(position)
                while True:
                    start = journal.tell()
                    line = journal.readline()
                    if not line or not line.endswith(b'\n'):
                        self.positions[file_name] = start
                        break  # writer may still be appending this event
                    self._apply(json.loads(line.decode('utf-8-sig')), historical)
            return True

    def readiness(self, now=None):
        with self.lock:
            now = now or datetime.datetime.now(UTC)
            if self.pending is not None:
                try:
                    departure = datetime.datetime.fromisoformat(self.pending['DepartureTime'].replace('Z', '+00:00'))
                    if departure.tzinfo is None:
                        raise ValueError('departure time has no timezone')
                except (KeyError, ValueError, TypeError, AttributeError):
                    return 'jump in progress; departure time unknown; waiting for arrival confirmation', None
                if now <= departure + datetime.timedelta(seconds=self.STALE_REQUEST_SECONDS):
                    return 'jump in progress; waiting for arrival confirmation', None
                print('WARNING: Ignoring stale carrier jump request; departure was over 30 minutes ago.', flush=True)
                self.pending = None
            until = self.last_jump_at + datetime.timedelta(seconds=self.COOLDOWN_SECONDS) if self.last_jump_at else None
            if self.unknown_until and (until is None or self.unknown_until > until):
                until = self.unknown_until
            if self.cancelled_at:
                cancelled_until = self.cancelled_at + datetime.timedelta(seconds=60)
                until = max(until, cancelled_until) if until else cancelled_until
            remaining = max(0, (until - now).total_seconds()) if until else 0
            return ('cooldown', remaining) if remaining else ('ready', 0)

    def cargo_transfer_marker(self):
        with self.lock:
            return self.cargo_transfer_serial

    def pending_jump_countdown(self, now=None):
        """Return destination and seconds until scheduled departure, if known."""
        with self.lock:
            if self.pending is None:
                return None
            try:
                departure = datetime.datetime.fromisoformat(self.pending['DepartureTime'].replace('Z', '+00:00'))
                if departure.tzinfo is None:
                    return None
                now = now or datetime.datetime.now(UTC)
                return self.pending.get('SystemName', 'unknown'), max(0, int((departure - now).total_seconds()))
            except (KeyError, ValueError, TypeError, AttributeError):
                return None

    def pending_jump_identity(self):
        with self.lock:
            if self.pending is None:
                return None
            try:
                destination = self.pending['SystemName']
                requested = event_time(self.pending)
                if not isinstance(destination, str) or not destination or requested.tzinfo is None:
                    return None
                return destination, requested
            except (KeyError, ValueError, TypeError, AttributeError):
                return None

    def arrival_matches(self, identity):
        with self.lock:
            return (identity is not None and self.pending is None and self.last_jump_at is not None
                    and isinstance(self.last_system, str)
                    and self.last_system.casefold() == identity[0].casefold()
                    and self.last_jump_at >= identity[1]
                    and (self.cancelled_at is None or self.cancelled_at < identity[1]))

    def cargo_transfers_since(self, marker):
        with self.lock:
            return [(serial, transfers) for serial, transfers in self.cargo_transfer_events if serial > marker]

    def raise_if_cancelled(self):
        if self.cancelled_at and self.request_started and self.cancelled_at >= self.request_started:
            raise RuntimeError('Carrier jump was cancelled in game. Traversal aborted.')

    def last_carrier_request(self):
        if self.lastUsedFileName:
            self.process_journal(self.lastUsedFileName)
        self.raise_if_cancelled()
        return self.lastCarrierRequest

    def reset_jump(self):
        with self.lock:
            self.hasJumped = False

    def get_jumped(self):
        if self.lastUsedFileName:
            self.process_journal(self.lastUsedFileName)
        self.raise_if_cancelled()
        return self.hasJumped
