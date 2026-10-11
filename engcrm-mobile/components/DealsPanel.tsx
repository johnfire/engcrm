// What is being pitched to this organization or person: one card per offer, with
// its stage and status (saved the moment a chip is tapped), the contact person
// (organizations), the next step, and what it earns — plus pitching another
// offer and stopping one. The same as the web's Deals panel.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import {
  changeDeal,
  createDeal,
  Deal,
  endSubscription,
  fetchDeals,
  fetchOffers,
  Offer,
  Owner,
  removeDeal,
  setDealNextStep,
  startSubscription,
} from "../services/deals";
import { dateInDays } from "../services/followUps";
import { stageLabelKey, statusLabelKey } from "../services/organizationState";
import { onChanged, organizationKey, personKey } from "../services/refreshBus";
import { PersonNextStep } from "./PersonNextStep";
import { Chip, StageStatusChange, StageStatusPicker } from "./StageStatusPicker";

type Props = {
  owner: Owner;
  ownerId: number;
  canEdit: boolean;
  /** An organization's people, who can be named its deals' contact person. */
  contactPeople?: { id: number; name: string }[];
};

export function DealsPanel({ owner, ownerId, canEdit, contactPeople = [] }: Props) {
  const { t } = useTranslation();
  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      Promise.all([fetchDeals(owner, ownerId), fetchOffers()])
        .then(([loaded, available]) => {
          setDeals(loaded);
          setOffers(available);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [owner, ownerId],
  );

  // Load now, and again whenever the meeting log saved something that can move a deal.
  useEffect(() => {
    load();
    return onChanged(owner === "organization" ? organizationKey(ownerId) : personKey(ownerId), () => {
      load();
    });
  }, [load, owner, ownerId]);

  async function pitch(offer: Offer) {
    try {
      await createDeal(owner, ownerId, offer.id);
      await load();
    } catch {
      setFailed(true);
    }
  }

  if (deals === null) {
    return (
      <View style={styles.box}>
        {failed ? <Text style={styles.error}>{t("deals.loadFailed")}</Text> : <ActivityIndicator color="#7c6fff" />}
      </View>
    );
  }

  const pitched = new Set(deals.map((deal) => deal.offer_id));
  const addable = offers.filter((offer) => !pitched.has(offer.id));

  return (
    <View style={styles.panel}>
      <Text style={styles.heading}>{t("deals.title")}</Text>
      {deals.length === 0 && <Text style={styles.muted}>{t("deals.none")}</Text>}
      {deals.map((deal) => (
        <DealCard
          key={`${deal.id}-${deal.pipeline_stage}-${deal.status}`}
          deal={deal}
          owner={owner}
          ownerId={ownerId}
          canEdit={canEdit}
          contactPeople={contactPeople}
          onChanged={load}
        />
      ))}
      {canEdit && addable.length > 0 && (
        <View style={styles.block}>
          <Text style={styles.label}>{t("deals.add")}</Text>
          <View style={styles.choices}>
            {addable.map((offer) => (
              <Chip key={offer.id} label={`+ ${offer.name}`} selected={false} onPress={() => void pitch(offer)} />
            ))}
          </View>
        </View>
      )}
      {failed && <Text style={styles.error}>{t("deals.saveFailed")}</Text>}
    </View>
  );
}

function DealCard({
  deal,
  owner,
  ownerId,
  canEdit,
  contactPeople,
  onChanged: reload,
}: {
  deal: Deal;
  owner: Owner;
  ownerId: number;
  canEdit: boolean;
  contactPeople: { id: number; name: string }[];
  onChanged: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [contactPerson, setContactPerson] = useState(deal.contact_person_id);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const running = deal.money?.running ?? null;

  async function saveState(change: StageStatusChange) {
    await changeDeal(deal.id, { stage: change.pipeline_stage, status: change.status });
  }

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setFailed(false);
    try {
      await action();
      await reload();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function pickContactPerson(id: number | null) {
    const previous = contactPerson;
    setContactPerson(id);
    changeDeal(deal.id, { contact_person_id: id }).catch(() => {
      setContactPerson(previous);
      setFailed(true);
    });
  }

  function confirmRemove() {
    Alert.alert(t("deals.removeTitle"), t("deals.removeConfirm", { offer: deal.offer_name }), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("deals.remove"), style: "destructive", onPress: () => void act(() => removeDeal(deal.id)) },
    ]);
  }

  return (
    <View style={styles.card} accessibilityLabel={deal.offer_name}>
      {canEdit ? (
        <StageStatusPicker
          title={deal.offer_name}
          stage={deal.pipeline_stage}
          status={deal.status}
          onSave={saveState}
        />
      ) : (
        <View>
          <Text style={styles.offer}>{deal.offer_name}</Text>
          <Text style={styles.muted}>
            {t(stageLabelKey(deal.pipeline_stage))} · {t(statusLabelKey(deal.status))}
          </Text>
        </View>
      )}

      {owner === "organization" && canEdit && contactPeople.length > 0 && (
        <View style={styles.block}>
          <Text style={styles.label}>{t("deals.contactPerson")}</Text>
          <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("deals.contactPerson")}>
            <Chip label="—" selected={contactPerson === null} onPress={() => pickContactPerson(null)} />
            {contactPeople.map((person) => (
              <Chip
                key={person.id}
                label={person.name}
                selected={contactPerson === person.id}
                onPress={() => pickContactPerson(person.id)}
              />
            ))}
          </View>
        </View>
      )}

      <PersonNextStep
        personId={ownerId}
        step={deal.next_step}
        date={deal.next_step_date}
        canEdit={canEdit}
        onSaved={() => void reload()}
        save={(step, date) => setDealNextStep(deal.id, step, date)}
      />

      <View style={styles.block}>
        {running && (
          <Text style={styles.money}>
            {t("subscription.running", { amount: running.amount_eur_month, date: running.started_on })}
          </Text>
        )}
        {!!deal.money && Number(deal.money.sales_total) > 0 && (
          <Text style={styles.muted}>
            {t("deals.oneOffTotal", { amount: deal.money.sales_total, count: deal.money.sales.length })}
          </Text>
        )}
        {canEdit && (
          <View style={styles.row}>
            <TextInput
              style={styles.input}
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              placeholder={t("subscription.amount")}
              placeholderTextColor="#666"
              editable={!busy}
              accessibilityLabel={t("subscription.amount")}
            />
            <TouchableOpacity
              accessibilityRole="button"
              disabled={busy || !amount.trim()}
              onPress={() =>
                void act(async () => {
                  await startSubscription(deal.id, amount.replace(",", ".").trim(), dateInDays(0));
                  setAmount("");
                })
              }
            >
              <Text style={[styles.action, (busy || !amount.trim()) && styles.disabled]}>
                {running ? t("subscription.changeToday") : t("subscription.startToday")}
              </Text>
            </TouchableOpacity>
          </View>
        )}
        {canEdit && running && (
          <TouchableOpacity
            accessibilityRole="button"
            disabled={busy}
            onPress={() => void act(() => endSubscription(deal.id, dateInDays(0)))}
          >
            <Text style={styles.action}>{t("subscription.endToday")}</Text>
          </TouchableOpacity>
        )}
      </View>

      {canEdit && (
        <TouchableOpacity accessibilityRole="button" onPress={confirmRemove} disabled={busy}>
          <Text style={styles.remove}>{t("deals.remove")}</Text>
        </TouchableOpacity>
      )}
      {failed && <Text style={styles.error}>{t("deals.saveFailed")}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { marginTop: 16 },
  heading: { color: "#888", fontSize: 11, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  box: { backgroundColor: "#1a1a2e", borderRadius: 10, marginTop: 16, padding: 14 },
  card: { backgroundColor: "#15152a", borderColor: "#ffffff15", borderRadius: 12, borderWidth: 1, marginTop: 10, padding: 10 },
  offer: { color: "#fff", fontSize: 15, fontWeight: "700" },
  block: { marginTop: 10 },
  label: { color: "#888", fontSize: 11, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 8 },
  row: { alignItems: "center", flexDirection: "row", gap: 10, marginTop: 6 },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#333",
    borderRadius: 8,
    borderWidth: 1,
    color: "#fff",
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  money: { color: "#aaa3ff", fontSize: 15, fontWeight: "700" },
  action: { color: "#7c6fff", fontSize: 14, fontWeight: "600", paddingVertical: 6 },
  disabled: { opacity: 0.4 },
  remove: { color: "#ef8a8a", fontSize: 13, marginTop: 10 },
  muted: { color: "#888", fontSize: 13, marginTop: 4 },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
});
