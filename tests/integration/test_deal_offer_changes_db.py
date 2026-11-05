"""Switch an existing pitched offer without creating another deal or losing its state."""
from datetime import date

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_offers import list_offers
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, start_subscription
from gcrm.tools.deal_offer_changes import DealOfferConflict, change_deal_offer
from gcrm.tools.deal_records import (
    DealNotFound,
    add_deal,
    get_deals,
    set_deal_next_step,
    update_deal,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def pitched_company(clean_database, monkeypatch):
    monkeypatch.setattr('gcrm.tools.db_organizations.geocode', lambda *args: None)
    offers = {offer['slug']: offer['id'] for offer in list_offers(None)}
    company = save_organization('BIB example', '', source='test_fixture', pipeline_stage='opportunity', status='proposal')
    person = save_person('Course coordinator', source='test_fixture', contact_id=company)
    [deal] = get_deals('organization', company)
    update_deal(deal['id'], contact_person_id=person)
    set_deal_next_step(deal['id'], 'Check the proposal', date(2026, 11, 20))
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE deals SET notes='Keep these notes' WHERE id=%s", (deal['id'],))
        cursor.execute('SELECT workspace_id FROM deals WHERE id=%s', (deal['id'],))
        workspace = cursor.fetchone()['workspace_id']
    return company, person, deal['id'], offers, workspace


def test_switch_preserves_the_same_deal_and_its_history(pitched_company):
    company, person, deal_id, offers, workspace = pitched_company
    changed = change_deal_offer(deal_id, offers['training'], workspace)
    assert changed['id'] == deal_id and changed['offer_slug'] == 'training'
    assert (changed['pipeline_stage'], changed['status']) == ('opportunity', 'proposal')
    assert changed['contact_person_id'] == person and changed['notes'] == 'Keep these notes'
    assert changed['next_step'] == 'Check the proposal' and changed['next_step_date'] == '2026-11-20'
    [stored] = get_deals('organization', company)
    assert stored['id'] == deal_id and stored['offer_id'] == offers['training']
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT offer_id,summary FROM interactions WHERE contact_id=%s', (company,))
        history = cursor.fetchall()
    assert len(history) == 1 and history[0]['offer_id'] == offers['consulting']
    assert 'Check the proposal' in history[0]['summary']


def test_financial_records_stay_attached_to_the_same_deal(pitched_company):
    _, _, deal_id, offers, workspace = pitched_company
    sale_id = add_deal_sale(deal_id, '250', date(2026, 11, 1), workspace_id=workspace)
    subscription_id = start_subscription(deal_id, '39', date(2026, 11, 1), workspace_id=workspace)
    change_deal_offer(deal_id, offers['training'], workspace)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT deal_id,amount_eur FROM sales WHERE id=%s', (sale_id,))
        sale = cursor.fetchone()
        assert sale['deal_id'] == deal_id and str(sale['amount_eur']) == '250.00'
        cursor.execute('SELECT deal_id,amount_eur_month,ended_on FROM subscriptions WHERE id=%s', (subscription_id,))
        subscription = cursor.fetchone()
        assert subscription['deal_id'] == deal_id and str(subscription['amount_eur_month']) == '39.00'
        assert subscription['ended_on'] is None


def test_duplicate_target_is_refused_without_merging_or_changing_either_deal(pitched_company):
    company, _, deal_id, offers, workspace = pitched_company
    other = add_deal('organization', company, offers['training'], workspace, stage='customer', status='customer')
    with pytest.raises(DealOfferConflict):
        change_deal_offer(deal_id, offers['training'], workspace)
    deals = {deal['id']: deal for deal in get_deals('organization', company)}
    assert deals[deal_id]['offer_slug'] == 'consulting' and deals[deal_id]['status'] == 'proposal'
    assert deals[other]['offer_slug'] == 'training' and deals[other]['pipeline_stage'] == 'customer'


def test_switch_to_the_current_offer_is_a_noop(pitched_company):
    company, _, deal_id, offers, workspace = pitched_company
    [before] = get_deals('organization', company)
    changed = change_deal_offer(deal_id, offers['consulting'], workspace)
    assert changed == before
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) AS n FROM audit_log WHERE action='deal.offer_changed'")
        assert cursor.fetchone()['n'] == 0


def test_person_deal_can_switch_offers_without_changing_owner(pitched_company):
    _, person, _, offers, workspace = pitched_company
    deal_id = add_deal('person', person, offers['consulting'], workspace, stage='nibble', status='contacted')
    changed = change_deal_offer(deal_id, offers['training'], workspace)
    assert changed['person_id'] == person and changed['contact_id'] is None
    assert changed['pipeline_stage'] == 'nibble' and changed['offer_slug'] == 'training'


def test_missing_archived_or_foreign_targets_cannot_change_the_deal(pitched_company):
    company, _, deal_id, offers, workspace = pitched_company
    with pytest.raises(DealNotFound):
        change_deal_offer(deal_id, offers['training'], workspace + 100000)
    with pytest.raises(DealNotFound):
        change_deal_offer(deal_id, 999999, workspace)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (name,slug) VALUES ('Foreign offer workspace','switch-foreign') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        foreign_workspace = cursor.fetchone()['id']
        cursor.execute("INSERT INTO offers (workspace_id,slug,name,revenue_kind) VALUES (%s,'foreign','Foreign','one_off') "
                       "ON CONFLICT(workspace_id,slug) DO UPDATE SET name=EXCLUDED.name RETURNING id", (foreign_workspace,))
        foreign_offer = cursor.fetchone()['id']
    with pytest.raises(DealNotFound):
        change_deal_offer(deal_id, foreign_offer, workspace)
    with db() as connection:
        connection.cursor().execute('UPDATE offers SET archived_at=NOW() WHERE id=%s', (offers['training'],))
    try:
        with pytest.raises(DealNotFound):
            change_deal_offer(deal_id, offers['training'], workspace)
    finally:
        with db() as connection:
            connection.cursor().execute('UPDATE offers SET archived_at=NULL WHERE id=%s', (offers['training'],))
    assert get_deals('organization', company)[0]['offer_slug'] == 'consulting'
