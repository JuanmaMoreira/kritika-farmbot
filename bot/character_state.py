"""Durable character facts. Informational balances never authorize gameplay."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import time

from bot.character_identity import CHARACTER_IDS, PERSONAL_NAME_CLASSES

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / 'runtime/character_state.sqlite3'
SCHEMA_VERSION = 1
DAY = 86400
WB_PERIOD = 3 * DAY  # projection between countdown observations, not a wall hour

def utc_now():
    return time.time()

def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()

_scope = ContextVar('persistent_character_scope', default=None)

def current_character_state():
    return _scope.get()

@contextmanager
def character_state_scope():
    token = _scope.set(None)
    try:
        yield
    finally:
        _scope.reset(token)

def establish_character_state(store, character_id):
    # Caller must be inside a character scope; never fall back to a position.
    _scope.set((store, character_id) if store is not None and character_id in CHARACTER_IDS.values() else None)

class CharacterStateStore:
    def __init__(self, path=DEFAULT_DB_PATH, *, now=utc_now, events=None):
        self.path, self.now, self.events = Path(path), now, events
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
        except BaseException:
            self.db.close()
            raise
        if version not in (0, SCHEMA_VERSION):
            self.db.close()
            raise ValueError(f'Unsupported character DB schema {version}; file preserved')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        try:
            with self.transaction():
                self.db.execute('''CREATE TABLE IF NOT EXISTS characters (
                    character_id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, identity_source TEXT NOT NULL)''')
                self.db.execute('''CREATE TABLE IF NOT EXISTS operational (
                    character_id TEXT PRIMARY KEY REFERENCES characters(character_id),
                    stage_ads_remaining INTEGER CHECK(stage_ads_remaining BETWEEN 0 AND 2),
                    stage_ads_epoch TEXT, ads_status TEXT, ads_updated_at REAL, ads_source TEXT,
                    ads_last_attempt_at REAL, ads_last_attempt_status TEXT,
                    wb_cycle_id INTEGER, wb_participated INTEGER CHECK(wb_participated IN (0,1)),
                    wb_previous_reward_available INTEGER CHECK(wb_previous_reward_available IN (0,1)),
                    wb_daily_quest_state TEXT, wb_updated_at REAL, wb_source TEXT)''')
                self.db.execute('''CREATE TABLE IF NOT EXISTS resource_snapshots (
                    id INTEGER PRIMARY KEY, character_id TEXT NOT NULL REFERENCES characters(character_id),
                    lapiz INTEGER NOT NULL CHECK(lapiz>=0), dark_essence INTEGER NOT NULL CHECK(dark_essence>=0),
                    light_essence INTEGER NOT NULL CHECK(light_essence>=0), nature_essence INTEGER NOT NULL CHECK(nature_essence>=0),
                    k_coins INTEGER NOT NULL CHECK(k_coins>=0), observed_at REAL NOT NULL, source TEXT NOT NULL)''')
                self.db.execute('CREATE INDEX IF NOT EXISTS resources_latest ON resource_snapshots(character_id,observed_at DESC,id DESC)')
                self.db.execute('''CREATE TABLE IF NOT EXISTS fact_history (
                    id INTEGER PRIMARY KEY, character_id TEXT REFERENCES characters(character_id),
                    kind TEXT NOT NULL, value TEXT NOT NULL, observed_at REAL NOT NULL,
                    effective_at REAL NOT NULL, source TEXT NOT NULL, epoch TEXT, cycle INTEGER)''')
                self.db.execute('''CREATE TABLE IF NOT EXISTS reset_clock (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), anchor REAL NOT NULL,
                    observed_at REAL NOT NULL, raw_remaining TEXT NOT NULL, source TEXT NOT NULL,
                    next_daily REAL NOT NULL, next_wb REAL NOT NULL, wb_cycle_id INTEGER NOT NULL,
                    wb_open INTEGER NOT NULL, precision_seconds INTEGER NOT NULL)''')
                for canonical, cid in CHARACTER_IDS.items():
                    self.db.execute('INSERT OR IGNORE INTO characters VALUES (?,?,?,?)', (cid, canonical, PERSONAL_NAME_CLASSES[canonical], 'USER_GT'))
                    # A renamed display must never rename its primary key.
                    self.db.execute('INSERT OR IGNORE INTO operational(character_id) VALUES (?)', (cid,))
                self.db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        except BaseException:
            self.db.close()
            raise
        self.clock = ResetClock(self)
        self.clock.catch_up()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def emit(self, event, **fields):
        if self.events is not None:
            self.events.record(event, **fields)

    def history(self, cid, kind, value, at, source, epoch=None, cycle=None, effective=None):
        self.db.execute('INSERT INTO fact_history(character_id,kind,value,observed_at,effective_at,source,epoch,cycle) VALUES (?,?,?,?,?,?,?,?)',
                        (cid, kind, str(value), at, at if effective is None else effective, source, epoch, cycle))

    def _valid_id(self, cid):
        if cid not in CHARACTER_IDS.values():
            raise ValueError('Unknown character identity; no write permitted')

    def operational(self, cid):
        self._valid_id(cid)
        self.clock.catch_up()
        with self.lock:
            return dict(self.db.execute('SELECT * FROM operational WHERE character_id=?', (cid,)).fetchone())

    def ads(self, cid, status, *, observed_count=None, at=None, source=None):
        self._valid_id(cid)
        at = self.now() if at is None else at
        with self.transaction():
            self.clock._catch_up(self.now())
            old = self.db.execute('SELECT * FROM operational WHERE character_id=?', (cid,)).fetchone()
            clock=self.clock._read()
            if clock and at < clock['next_daily']-DAY or old['ads_updated_at'] is not None and at < old['ads_updated_at']:
                return False
            count = old['stage_ads_remaining']
            if observed_count is not None:
                if type(observed_count) is not int or not 0 <= observed_count <= 2:
                    raise ValueError('Invalid observed Ads count')
                count = observed_count
            elif status == 'REWARDED':
                count = max(0, count-1) if count is not None else None
            elif status == 'DAILY_EXHAUSTED':
                count = 0
            elif status not in ('TEMPORARILY_UNAVAILABLE', 'ABORTED_RECOVERED'):
                raise ValueError('Unknown Ads event')
            changed = status not in ('TEMPORARILY_UNAVAILABLE', 'ABORTED_RECOVERED')
            self.db.execute('''UPDATE operational SET stage_ads_remaining=?,
                ads_status=CASE WHEN ? THEN ? ELSE ads_status END,
                ads_updated_at=CASE WHEN ? THEN ? ELSE ads_updated_at END,
                ads_source=CASE WHEN ? THEN ? ELSE ads_source END,
                ads_last_attempt_at=?, ads_last_attempt_status=? WHERE character_id=?''',
                (count, changed, status, changed, at, changed, source or status, at, status, cid))
            self.history(cid, 'ads', count, at, source or status, old['stage_ads_epoch'])
        self.emit('character_state.ads_updated', character_id=cid, remaining=count, status=status)
        return True

    def wb(self, cid, participated, *, source, previous_reward=None, at=None, cycle=None):
        self._valid_id(cid)
        if type(participated) is not bool or previous_reward is not None and type(previous_reward) is not bool:
            raise ValueError('Invalid WB observation')
        at = self.now() if at is None else at
        with self.transaction():
            self.clock._catch_up(at)
            old = self.db.execute('SELECT * FROM operational WHERE character_id=?', (cid,)).fetchone()
            clock = self.clock._read()
            current_cycle = clock['wb_cycle_id'] if clock else None
            if cycle is not None and cycle != current_cycle:
                return False
            # Any accredited YES is monotonic in a cycle, especially Raid Complete.
            value = bool(participated or old['wb_participated'] == 1)
            effective_source = old['wb_source'] if old['wb_participated'] == 1 and not participated else source
            self.db.execute('''UPDATE operational SET wb_cycle_id=?,wb_participated=?,
                wb_previous_reward_available=COALESCE(?,wb_previous_reward_available),
                wb_updated_at=?,wb_source=? WHERE character_id=?''',
                (current_cycle, value, previous_reward, at, effective_source, cid))
            self.history(cid, 'wb_participated', value, at, source, cycle=current_cycle)
        self.emit('character_state.wb_updated', character_id=cid, participated=value, source=effective_source, cycle=current_cycle)
        return True

    def resources(self, cid, values, *, observed_at=None, source='QUICK_MENU'):
        self._valid_id(cid)
        fields = ('lapiz','dark_essence','light_essence','nature_essence','k_coins')
        # Atomic five-field snapshot: partial/unreadable keeps last reliable one.
        if set(values) != set(fields) or any(type(values[k]) is not int or values[k] < 0 for k in fields):
            return False
        at = self.now() if observed_at is None else observed_at
        with self.transaction():
            self.db.execute('INSERT INTO resource_snapshots(character_id,lapiz,dark_essence,light_essence,nature_essence,k_coins,observed_at,source) VALUES (?,?,?,?,?,?,?,?)',
                (cid, *(values[k] for k in fields), at, source))
        self.emit('character_state.resources_updated', character_id=cid, observed_at=stamp(at), **values)
        return True

    def wb_daily_quest(self, cid, active):
        self._valid_id(cid)
        at=self.now()
        with self.transaction():
            self.clock._catch_up(at)
            value='ACTIVE' if active else 'ABSENT'
            self.db.execute('UPDATE operational SET wb_daily_quest_state=? WHERE character_id=?',(value,cid))
            self.history(cid,'wb_daily_quest',value,at,'DAILY_QUEST_MARKER')

    def rows(self):
        self.clock.catch_up()
        with self.lock:
            return [dict(r) for r in self.db.execute('''SELECT c.*,o.*,r.lapiz,r.dark_essence,r.light_essence,
                r.nature_essence,r.k_coins,r.observed_at AS resource_observed_at
                FROM characters c JOIN operational o USING(character_id)
                LEFT JOIN resource_snapshots r ON r.id=(SELECT id FROM resource_snapshots
                    WHERE character_id=c.character_id ORDER BY observed_at DESC,id DESC LIMIT 1)
                ORDER BY c.display_name''')]

    def close(self):
        with self.lock:
            self.db.close()

class ResetClock:
    def __init__(self, store):
        self.store = store

    def _read(self):
        row = self.store.db.execute('SELECT * FROM reset_clock WHERE singleton=1').fetchone()
        return dict(row) if row else None

    def state(self):
        self.catch_up()
        with self.store.lock:
            return self._read()

    def calibrate(self, remaining_seconds, *, observed_at=None, raw_remaining='', precision_seconds=1, source='WB_COUNTDOWN'):
        if remaining_seconds < 0 or remaining_seconds > WB_PERIOD:
            raise ValueError('Invalid WB countdown')
        s = self.store
        at = s.now() if observed_at is None else observed_at
        anchor = at + remaining_seconds + 1800
        next_daily = anchor
        while next_daily-DAY > at:
            next_daily -= DAY
        with s.transaction():
            previous = self._read()
            if previous is not None:
                shift = anchor-previous['next_wb']
                if abs(shift) < DAY/2:
                    # A countdown phase correction belongs to this same cycle.
                    # Catch up against its new boundary, not the stale forecast.
                    s.db.execute('UPDATE reset_clock SET next_daily=next_daily+?,next_wb=? WHERE singleton=1',
                                 (shift,anchor))
                    if next_daily-DAY < previous['next_daily']-DAY:
                        # A projected reset occurred before the revised boundary.
                        # Its assigned 2 is not a fresh physical observation.
                        s.db.execute('''UPDATE operational SET stage_ads_remaining=NULL,
                            ads_status='UNKNOWN',ads_source='CLOCK_RECALIBRATION'
                            WHERE ads_source='SYNCHRONIZED_RESET' AND ads_updated_at>=?''',
                                     (previous['next_daily']-DAY,))
            self._catch_up(at)
            old = self._read()
            cycle = old['wb_cycle_id'] if old else 1
            # Recalibration within the same observed cycle never erases YES.
            s.db.execute('INSERT OR REPLACE INTO reset_clock VALUES (1,?,?,?,?,?,?,?,?,?)',
                (anchor, at, raw_remaining, source, next_daily, anchor, cycle, remaining_seconds > 0, precision_seconds))
            epoch = stamp(next_daily-DAY)
            if old is None:
                s.db.execute('UPDATE operational SET stage_ads_epoch=?,wb_cycle_id=?', (epoch, cycle))
                s.db.execute('UPDATE operational SET stage_ads_remaining=NULL WHERE ads_updated_at<?',(next_daily-DAY,))
                s.db.execute('UPDATE operational SET wb_participated=NULL WHERE wb_updated_at<?',(anchor-WB_PERIOD,))
            else:
                # Align epoch labels to a seasonal anchor without asserting reset.
                s.db.execute('UPDATE operational SET stage_ads_epoch=?', (epoch,))
            s.history(None,'reset_anchor',anchor,at,source,cycle=cycle)
        s.emit('reset_clock.calibrated', raw_remaining=raw_remaining, observed_at=stamp(at), close_at=stamp(anchor-1800), synchronized_reset_at=stamp(anchor), source=source, precision_seconds=precision_seconds)
        return self.state()

    def _catch_up(self, now):
        s = self.store
        c = self._read()
        if c is None:
            return
        daily = c['next_daily']
        if now >= daily:
            missed = int((now-daily)//DAY)+1
            latest = daily+(missed-1)*DAY
            epoch = stamp(latest)
            s.db.execute('''UPDATE operational SET stage_ads_remaining=2,stage_ads_epoch=?,
                ads_status='RESET',ads_updated_at=?,ads_source='SYNCHRONIZED_RESET',
                ads_last_attempt_at=NULL,ads_last_attempt_status=NULL,wb_daily_quest_state=NULL''', (epoch, latest))
            s.db.execute('UPDATE reset_clock SET next_daily=? WHERE singleton=1', (daily+missed*DAY,))
            s.history(None,'daily_reset',2,now,'SYNCHRONIZED_RESET',epoch=epoch,effective=latest)
            s.emit('reset_clock.daily_transition', epoch=epoch, missed_resets=missed)
        wb = c['next_wb']
        if now >= wb:
            missed = int((now-wb)//WB_PERIOD)+1
            cycle = c['wb_cycle_id']+missed
            latest = wb+(missed-1)*WB_PERIOD
            wb += missed*WB_PERIOD
            s.db.execute('''UPDATE operational SET wb_cycle_id=?,wb_participated=0,
                wb_previous_reward_available=NULL,wb_updated_at=?,wb_source='WB_CYCLE_RESET' ''',(cycle,latest))
            s.db.execute('UPDATE reset_clock SET wb_cycle_id=?,next_wb=? WHERE singleton=1',(cycle,wb))
            s.history(None,'wb_cycle_reset',cycle,now,'WB_CYCLE_RESET',cycle=cycle,effective=latest)
            s.emit('reset_clock.wb_cycle_transition', cycle=cycle, projected=True)
        opened=now < wb-1800
        s.db.execute('UPDATE reset_clock SET wb_open=? WHERE singleton=1 AND wb_open<>?', (opened,opened))

    def catch_up(self, now=None):
        with self.store.transaction():
            self._catch_up(self.store.now() if now is None else now)

    def next_transition(self):
        state = self.state()
        if state is None:
            return None
        return min(state['next_daily'], state['next_wb']-1800 if state['wb_open'] else state['next_wb'])

class ResetScheduler:
    """Runtime owner; GUI has its own Tk timer and both transitions are atomic."""
    def __init__(self, store):
        self.store, self.stop = store, threading.Event()
        self.thread = threading.Thread(target=self._run, name='character-reset-clock', daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            boundary = self.store.clock.next_transition()
            delay = 60 if boundary is None else max(.05,min(60,boundary-self.store.now()))
            if self.stop.wait(delay):
                break
            self.store.clock.catch_up()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)

class CharacterStateEvents:
    """Consume causal existing observations once, before later cleanup can fail."""
    def __call__(self, event):
        scope = current_character_state()
        if scope is None:
            return
        store, cid = scope
        at = event.timestamp.timestamp()
        fields = event.fields
        if event.event == 'stages.ad_selection':
            count = fields.get('video_count')
            if type(count) is int:
                store.ads(cid, 'DAILY_EXHAUSTED' if count == 0 else 'OBSERVED', observed_count=count, at=at,
                          source='VIDEO0' if count==0 else 'VIDEO_COUNT')
        elif event.event == 'stages.sapphire_effect' and fields.get('after',0) > fields.get('before',0):
            store.ads(cid, 'REWARDED', at=at)
        elif event.event == 'stages.daily_exhausted':
            store.ads(cid, 'DAILY_EXHAUSTED', at=at)
        elif event.event == 'stages.temporarily_unavailable':
            store.ads(cid, 'TEMPORARILY_UNAVAILABLE', at=at)
        elif event.event == 'stages.ad_aborted_recovered':
            store.ads(cid, 'ABORTED_RECOVERED', at=at)
        elif event.event == 'world_boss.raid_complete_verified':
            store.wb(cid, True, source='RAID_COMPLETE', at=at)
