// An organization's one-off sales, as the web's Sales card shows them: newest first,
// each with its offer and what it was, and (admins) recording a sale on one of the
// organization's deals or deleting one recorded by mistake. Subscriptions are the
// Deals panel's. A sale is booked, contracted, collected or cancelled; only collected
// ones are money won.
import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { deleteOrganizationSale, Sale } from "../services/api";
import { dateInDays } from "../services/followUps";
import { changeSaleStatus, Deal, fetchDeals, recordSale } from "../services/deals";
import { formatDay, parseDay } from "../services/dates";
import { formatEur, typedAmount } from "../services/money";
import { SALE_STATUSES, SaleStatus } from "../services/saleStatus";
import { notifyChanged, onChanged, organizationKey } from "../services/refreshBus";
import { Chip } from "./StageStatusPicker";

type Props = {
  organizationId: number;
  sales: Sale[];
  canEdit: boolean;
};

export function SalesCard({ organizationId, sales, canEdit }: Props) {
  const { t } = useTranslation();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [dealId, setDealId] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [wonOn, setWonOn] = useState(() => formatDay(dateInDays(0)));
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<SaleStatus>("booked");
  const [expectedOn, setExpectedOn] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The deals a sale can belong to; again whenever the organization changed.
  useEffect(() => {
    if (!canEdit) return;
    const load = () =>
      fetchDeals("organization", organizationId)
        .then((loaded) => {
          setDeals(loaded);
          setDealId((current) => (loaded.some((d) => d.id === current) ? current : loaded[0]?.id ?? null));
        })
        .catch(() => undefined);
    load();
    return onChanged(organizationKey(organizationId), () => {
      load();
    });
  }, [canEdit, organizationId]);

  async function save() {
    const typed = typedAmount(amount);
    const day = parseDay(wonOn);
    if (!typed || !day) {
      setError(t("sales.invalid"));
      return;
    }
    if (dealId === null) return;
    const expected = expectedOn.trim() ? parseDay(expectedOn) : null;
    if (expectedOn.trim() && !expected) {
      setError(t("sales.invalid"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await recordSale(dealId, typed, day, description.trim(), status, expected);
      setAmount("");
      setDescription("");
      setExpectedOn("");
      notifyChanged(organizationKey(organizationId)); // the list here and the deal's total
    } catch (err: any) {
      setError(err?.response?.data?.detail || t("sales.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  function moveTo(sale: Sale, next: SaleStatus) {
    changeSaleStatus(sale.deal_id, sale.id, next)
      .catch(() => Alert.alert(t("sales.saveFailed")))
      .finally(() => notifyChanged(organizationKey(organizationId)));
  }

  function confirmDelete(sale: Sale) {
    Alert.alert(t("sales.deleteConfirm"), `${formatEur(sale.amount_eur)} · ${formatDay(sale.won_on)}`, [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("sales.delete"),
        style: "destructive",
        onPress: () => {
          deleteOrganizationSale(organizationId, sale.id)
            .catch(() => undefined)
            .finally(() => notifyChanged(organizationKey(organizationId)));
        },
      },
    ]);
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>{t("sales.title")}</Text>
      {sales.length === 0 ? (
        <Text style={styles.muted}>{t("sales.none")}</Text>
      ) : (
        sales.map((sale) => {
          const current: SaleStatus = sale.status ?? "collected";
          return (
            <View key={sale.id} style={[styles.sale, current === "cancelled" && styles.cancelled]}>
              <View style={styles.saleBody}>
                <Text style={styles.saleText}>
                  <Text style={styles.amount}>{formatEur(sale.amount_eur)}</Text>
                  {` · ${formatDay(sale.won_on)} · ${sale.offer}`}
                  {sale.description ? ` · ${sale.description}` : ""}
                </Text>
                <Text style={styles.statusLine}>
                  {t(`sale.status.${current}`)}
                  {(current === "booked" || current === "contracted") && sale.expected_on
                    ? ` · ${t("sale.expectedOn", { date: formatDay(sale.expected_on) })}`
                    : ""}
                  {current === "collected" && sale.collected_on
                    ? ` · ${t("sale.collectedOn", { date: formatDay(sale.collected_on) })}`
                    : ""}
                </Text>
                {canEdit && (
                  <View style={styles.choices}>
                    {SALE_STATUSES.filter((s) => s !== current).map((next) => (
                      <TouchableOpacity key={next} style={styles.move} onPress={() => moveTo(sale, next)}
                        accessibilityRole="button" accessibilityLabel={`${t("sale.moveTo")} ${t(`sale.status.${next}`)}`}>
                        <Text style={styles.moveText}>{t(`sale.status.${next}`)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
              </View>
              {canEdit && (
                <TouchableOpacity onPress={() => confirmDelete(sale)} accessibilityRole="button"
                  accessibilityLabel={`${t("sales.delete")} ${formatEur(sale.amount_eur)}`}>
                  <Text style={styles.delete}>{t("sales.delete")}</Text>
                </TouchableOpacity>
              )}
            </View>
          );
        })
      )}

      {canEdit && deals.length === 0 && <Text style={styles.hint}>{t("sales.needsDeal")}</Text>}
      {canEdit && deals.length > 0 && (
        <View style={styles.form}>
          {deals.length > 1 && (
            <>
              <Text style={styles.label}>{t("sales.forOffer")}</Text>
              <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("sales.forOffer")}>
                {deals.map((deal) => (
                  <Chip key={deal.id} label={deal.offer_name} selected={dealId === deal.id} disabled={saving}
                    onPress={() => setDealId(deal.id)} />
                ))}
              </View>
            </>
          )}
          <Text style={styles.label}>{t("sale.status.label")}</Text>
          <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("sale.status.label")}>
            {SALE_STATUSES.filter((s) => s !== "cancelled").map((s) => (
              <Chip key={s} label={t(`sale.status.${s}`)} selected={status === s} disabled={saving}
                onPress={() => setStatus(s)} />
            ))}
          </View>
          <Text style={styles.label}>{t("sales.amount")}</Text>
          <TextInput style={styles.input} value={amount} onChangeText={setAmount} keyboardType="decimal-pad"
            placeholder="2400" placeholderTextColor="#555" editable={!saving} accessibilityLabel={t("sales.amount")} />
          <Text style={styles.label}>{t("sales.wonOn")}</Text>
          <TextInput style={styles.input} value={wonOn} onChangeText={setWonOn} keyboardType="numbers-and-punctuation"
            maxLength={10} editable={!saving} accessibilityLabel={t("sales.wonOn")} />
          <Text style={styles.label}>{t("sale.expectedOnLabel")}</Text>
          <TextInput style={styles.input} value={expectedOn} onChangeText={setExpectedOn}
            keyboardType="numbers-and-punctuation" maxLength={10} editable={!saving}
            accessibilityLabel={t("sale.expectedOnLabel")} />
          <Text style={styles.label}>{t("sales.description")}</Text>
          <TextInput style={styles.input} value={description} onChangeText={setDescription} maxLength={500}
            placeholder={t("sales.descriptionPlaceholder")} placeholderTextColor="#555" editable={!saving}
            accessibilityLabel={t("sales.description")} />
          {!!error && <Text style={styles.error} accessibilityLiveRegion="assertive">{error}</Text>}
          <TouchableOpacity
            style={[styles.button, (saving || !amount.trim()) && styles.buttonDisabled]}
            onPress={save}
            disabled={saving || !amount.trim()}
            accessibilityRole="button"
            accessibilityState={{ disabled: saving || !amount.trim(), busy: saving }}
          >
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{t("sales.record")}</Text>}
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { marginTop: 20 },
  title: {
    color: "#888",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    marginBottom: 8,
    textTransform: "uppercase",
  },
  muted: { color: "#666", fontSize: 13 },
  hint: { color: "#888", fontSize: 12, marginTop: 8 },
  sale: { alignItems: "flex-start", flexDirection: "row", gap: 10, marginBottom: 12 },
  saleBody: { flex: 1 },
  saleText: { color: "#ccc", fontSize: 14 },
  statusLine: { color: "#9a9ab8", fontSize: 12, marginTop: 2 },
  cancelled: { opacity: 0.55 },
  move: { borderColor: "#ffffff30", borderRadius: 14, borderWidth: 1, minHeight: 32, justifyContent: "center", paddingHorizontal: 10 },
  moveText: { color: "#bbb", fontSize: 12 },
  amount: { color: "#fff", fontWeight: "700" },
  delete: { color: "#ff6b6b", fontSize: 12 },
  form: { backgroundColor: "#1a1a2e", borderRadius: 10, marginTop: 10, padding: 12 },
  label: { color: "#888", fontSize: 12, marginBottom: 4, marginTop: 8 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  input: {
    backgroundColor: "#0f0f23",
    borderColor: "#ffffff20",
    borderRadius: 8,
    borderWidth: 1,
    color: "#fff",
    fontSize: 15,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
  button: {
    alignItems: "center",
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    justifyContent: "center",
    marginTop: 12,
    minHeight: 46,
  },
  buttonDisabled: { opacity: 0.4 },
  buttonText: { color: "#fff", fontSize: 15, fontWeight: "700" },
});
