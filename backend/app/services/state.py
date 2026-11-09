"""Key/value progress markers stored in the sync_state table."""
from ..extensions import db
from ..models import SyncState
from ..utils import utcnow


def get_state(key, default=None):
    row = db.session.get(SyncState, key)
    return row.value if row else default


def set_state(key, value):
    row = db.session.get(SyncState, key)
    if row is None:
        db.session.add(SyncState(key=key, value=value))
    else:
        row.value = value
        row.updated_at = utcnow()


def delete_state(key):
    row = db.session.get(SyncState, key)
    if row is not None:
        db.session.delete(row)
