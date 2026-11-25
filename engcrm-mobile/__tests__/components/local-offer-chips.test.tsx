import { render } from "@testing-library/react-native";

import { LocalOfferChips } from "../../components/LocalOfferChips";
import { useLocalOffers } from "../../hooks/useLocalOffers";

jest.mock("../../hooks/useLocalOffers", () => ({ useLocalOffers: jest.fn() }));

it("shows a cached offer even when it has no deals", () => {
  jest.mocked(useLocalOffers).mockReturnValue([{ id: 7, slug: "training", name: "Training", website: null, revenue_kind: "one_off" }]);
  expect(render(<LocalOfferChips offer="all" onChange={jest.fn()} />).getByText("Training")).toBeTruthy();
});
