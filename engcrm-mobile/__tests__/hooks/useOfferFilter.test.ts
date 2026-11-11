// The lists always open on every offer. A chip narrows one visit only: a phone that
// remembered an empty offer's pipeline looked as if it had lost all its data.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, renderHook, waitFor } from "@testing-library/react-native";

jest.mock("../../services/deals", () => ({
  ...jest.requireActual("../../services/deals"),
  fetchOffers: async () => [
    { id: 1, slug: "consulting", name: "Consulting" },
    { id: 2, slug: "leguild", name: "LeGuild.art" },
  ],
}));

import { useOfferFilter } from "../../hooks/useOfferFilter";
import { ALL_OFFERS } from "../../services/deals";

beforeEach(async () => {
  await AsyncStorage.clear();
});

describe("useOfferFilter", () => {
  it("opens on every offer, even where an older app version remembered one", async () => {
    await AsyncStorage.setItem("offerFilter", "leguild");
    const { result } = renderHook(() => useOfferFilter());
    expect(result.current.offer).toBe(ALL_OFFERS);
    await waitFor(() => expect(result.current.offers).toHaveLength(2));
    expect(result.current.offer).toBe(ALL_OFFERS);
  });

  it("narrows to a chosen offer for this visit, and opens on every offer the next time", async () => {
    const first = renderHook(() => useOfferFilter());
    await waitFor(() => expect(first.result.current.offers).toHaveLength(2));
    act(() => first.result.current.choose("leguild"));
    expect(first.result.current.offer).toBe("leguild");
    first.unmount();
    const next = renderHook(() => useOfferFilter());
    expect(next.result.current.offer).toBe(ALL_OFFERS);
    await waitFor(() => expect(next.result.current.offers).toHaveLength(2));
  });
});
