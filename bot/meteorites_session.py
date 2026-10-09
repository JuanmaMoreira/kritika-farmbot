"""Transient character lifecycle for the existing B1 support procedure."""
from dataclasses import asdict
from enum import Enum
from time import perf_counter
from contextlib import contextmanager
from contextvars import ContextVar

from bot.character_identity import CHARACTER_IDS
from bot.event_log import record_best_effort

METEORITES_EXCEPTIONS = frozenset({'berserker', 'demon_blade', 'kaiserin'})
_active_scope = ContextVar('shared_meteorites_character_scope', default=None)

@contextmanager
def meteorites_character_scope():
    token = _active_scope.set(None)
    try:
        yield
    finally:
        _active_scope.reset(token)

def current_meteorites_scope():
    return _active_scope.get()

def bind_meteorites_scope(scope):
    _active_scope.set(scope)


class MeteoritesState(str, Enum):
    NOT_REQUESTED = 'NOT_REQUESTED'
    SETUP_IN_PROGRESS = 'SETUP_IN_PROGRESS'
    READY = 'READY'
    CLEANUP_IN_PROGRESS = 'CLEANUP_IN_PROGRESS'
    RELEASED = 'RELEASED'
    INTERRUPTED = 'INTERRUPTED'


class MeteoritesCharacterScope:
    def __init__(self, procedure, *, setup, cleanup, events, clock=perf_counter):
        self.procedure = procedure
        self.setup = setup
        self.cleanup = cleanup
        self.events = events
        self.clock = clock
        self.state = MeteoritesState.NOT_REQUESTED
        self.character_id = None
        self.skipped_exception = False
        self.reason = ''
        self.setup_outcome = None
        self.cleanup_outcome = None
        self.setup_seconds = 0.
        self.cleanup_seconds = 0.
        self.coordinator_seconds = 0.
        self.navigation_seconds = 0.

    def _emit(self):
        record_best_effort(self.events, 'session.meteorites', **self.report())

    def begin(self, context):
        if self.skipped_exception or self.state is MeteoritesState.READY: return True
        if self.state is not MeteoritesState.NOT_REQUESTED: return False
        started = self.clock(); delegated = 0.
        try:
            cid = context.character_id
            if cid not in CHARACTER_IDS.values():
                self.interrupt('stable_character_id_unknown')
                return False
            self.character_id = cid
            if cid in METEORITES_EXCEPTIONS:
                self.skipped_exception = True
                self._emit()
                return True
            self.state = MeteoritesState.SETUP_IN_PROGRESS
            self._emit()
            action_started = self.clock()
            try: progress = self.setup()
            finally:
                delegated = self.clock()-action_started
                self.setup_seconds = delegated
            self.setup_outcome = progress.phase
            if progress.phase != 'equipped':
                self.interrupt('setup:' + progress.reason)
                return False
            self.state = MeteoritesState.READY
            self._emit()
            return True
        except Exception as error:
            self.setup_outcome = 'exception'
            self.interrupt('setup_exception:' + str(error))
            return False
        finally:
            self.coordinator_seconds += max(0., self.clock()-started-delegated)

    def finish(self, *, safe_stop=False):
        if self.skipped_exception or self.state is MeteoritesState.RELEASED: return True
        if self.state is not MeteoritesState.READY: return False
        started = self.clock(); delegated = 0.
        try:
            self.state = MeteoritesState.CLEANUP_IN_PROGRESS
            self._emit()
            action_started = self.clock()
            try: progress = self.cleanup(safe_stop=safe_stop)
            finally:
                delegated = self.clock()-action_started
                self.cleanup_seconds = delegated
            self.cleanup_outcome = progress.phase
            if progress.phase != 'complete':
                self.interrupt('cleanup:' + progress.reason)
                return False
            self.state = MeteoritesState.RELEASED
            self._emit()
            return True
        except Exception as error:
            self.cleanup_outcome = 'exception'
            self.interrupt('cleanup_exception:' + str(error))
            return False
        finally:
            self.coordinator_seconds += max(0., self.clock()-started-delegated)

    def interrupt(self, reason):
        if self.skipped_exception or self.state in {MeteoritesState.RELEASED, MeteoritesState.INTERRUPTED}: return
        self.state = MeteoritesState.INTERRUPTED
        self.reason = reason
        self._emit()

    def report(self):
        progress = self.procedure.progress
        operations = progress.operations
        return dict(status='SKIPPED_EXCEPTION' if self.skipped_exception else self.state.value,
            character_id=self.character_id, reason=self.reason,
            setup_outcome=self.setup_outcome, cleanup_outcome=self.cleanup_outcome,
            equip_effects=list(progress.equipped), unequip_effects=list(progress.released),
            operation_count=len(operations),
            action_inputs=sum(op['result'].action_inputs for op in operations),
            retries=sum(op['result'].metrics.get('retries', 0) for op in operations),
            setup_seconds=self.setup_seconds, cleanup_seconds=self.cleanup_seconds,
            coordinator_seconds=self.coordinator_seconds, navigation_seconds=self.navigation_seconds,
            operation_seconds=sum(op['result'].metrics.get('wall_seconds', 0.) for op in operations),
            manual_preparation_required=self.state is MeteoritesState.INTERRUPTED,
            set_may_remain_equipped=(self.state is MeteoritesState.INTERRUPTED
                and (bool(set(progress.equipped)-set(progress.released)) or bool(progress.pending)
                    or self.setup_outcome == 'exception' or self.cleanup_outcome == 'exception')),
            progress=asdict(progress))

    def full_set_equipped_verified(self, character_id):
        """Consume B1's eleven credited effects only inside the READY lifecycle."""
        p = self.procedure.progress
        return (character_id is not None and character_id == self.character_id
            and self.state is MeteoritesState.READY and not self.skipped_exception
            and p.phase == 'equipped' and p.equipped == list(range(11))
            and not p.released and p.pending is None)
