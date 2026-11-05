"""Reclassify an existing deal's offer without replacing the deal or its history."""
from psycopg2.errors import UniqueViolation

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit
from gcrm.tools.deal_records import DealNotFound, get_deal


class DealOfferConflict(ValueError):
    """The owner already has a live deal for the target offer."""


def _validate_offer_change(cursor, deal: dict, offer_id: int) -> None:
    cursor.execute("SELECT id FROM offers WHERE id=%s AND archived_at IS NULL "
                   "AND workspace_id=(SELECT workspace_id FROM deals WHERE id=%s)", (offer_id, deal['id']))
    if cursor.fetchone() is None:
        raise DealNotFound('Offer not found')


def change_deal_offer(deal_id: int, offer_id: int, workspace_id: int | None = None) -> dict:
    """Change the same deal in place; a repeated selection is a no-op."""
    try:
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT id FROM deals WHERE id=%s AND deleted_at IS NULL '
                           'AND (%s IS NULL OR workspace_id=%s) FOR UPDATE', (deal_id, workspace_id, workspace_id))
            if cursor.fetchone() is None:
                raise DealNotFound('Deal not found')
            before = get_deal(cursor, deal_id, workspace_id)
            if before['offer_id'] == offer_id:
                return serialize_row(before)
            _validate_offer_change(cursor, before, offer_id)
            cursor.execute('UPDATE deals SET offer_id=%s WHERE id=%s', (offer_id, deal_id))
            after = get_deal(cursor, deal_id, workspace_id)
    except UniqueViolation as conflict:
        raise DealOfferConflict('This offer is already pitched here. Use its existing card instead.') from conflict
    log_audit(None, None, 'deal.offer_changed', f'deal:{deal_id}',
              f"{before['offer_id']}:{before['offer_name']} -> {after['offer_id']}:{after['offer_name']}")
    return serialize_row(after)
