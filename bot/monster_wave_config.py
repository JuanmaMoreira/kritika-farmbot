"""The two user decisions supported by one Monster Wave SKIP invocation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MonsterWaveConfig:
    purchase_skip_tickets: bool = False
    continue_when_nonblocking_inventory_full: bool = False

    def __post_init__(self):
        for name in ('purchase_skip_tickets', 'continue_when_nonblocking_inventory_full'):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f'{name} must be bool')

    @classmethod
    def from_env(cls, values):
        def read(name):
            value = values.get(name, 'false').strip().lower()
            if value not in {'true', 'false'}:
                raise ValueError(f'{name} must be true or false')
            return value == 'true'
        return cls(read('MW_PURCHASE_SKIP_TICKETS'),
                   read('MW_CONTINUE_WHEN_NONBLOCKING_INVENTORY_FULL'))
