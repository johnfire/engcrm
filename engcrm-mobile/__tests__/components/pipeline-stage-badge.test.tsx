import { render } from "@testing-library/react-native";

import { DealChips } from "../../components/DealChips";
import { PipelineStageBadge } from "../../components/pipeline-stage-badge";

describe("PipelineStageBadge", () => {
  it.each([
    ["candidate", "Candidate", "#d1d5db20", "#9ca3af", "#d1d5db"],
    ["suspect", "Suspect", "#7c6fff26", "#7c6fff", "#aaa3ff"],
    ["nibble", "Nibble", "#2dd4bf20", "#2dd4bf", "#5eead4"],
    ["prospect", "Prospect", "#2a2600", "#ffeb3b", "#ffeb3b"],
    ["opportunity", "Opportunity", "#f59e0b20", "#f59e0b", "#fbbf24"],
    ["customer", "Customer", "#22c55e20", "#22c55e", "#4ade80"],
    ["not_now", "Not now", "#94a3b812", "#94a3b8", "#cbd5e1"],
    ["not_in_pipeline", "Not in pipeline", "#6b728018", "#6b7280", "#cbd5e1"],
  ])("shows %s as a labeled colored badge", (stage, label, backgroundColor, borderColor, color) => {
    const screen = render(<PipelineStageBadge stage={stage} />);

    expect(screen.getByLabelText(`Pipeline stage: ${label}`)).toHaveStyle({ backgroundColor, borderColor });
    expect(screen.getByText(label)).toHaveStyle({ color });
  });

  it("keeps an unknown server stage visible with a neutral treatment", () => {
    const screen = render(<PipelineStageBadge stage="future_stage" />);

    expect(screen.getByLabelText("Pipeline stage: [stage.future_stage]")).toBeTruthy();
    expect(screen.getByText("[stage.future_stage]")).toHaveStyle({ color: "#cbd5e1" });
  });
});

describe("DealChips", () => {
  it("shows every offer and stage as a separate accessible badge", () => {
    const screen = render(
      <DealChips
        showOffer
        deals={[
          { id: 1, offer: "Consulting", slug: "consulting", stage: "prospect", status: "contacted" },
          { id: 2, offer: "LearnWohl", slug: "learnwohl", stage: "customer", status: "customer" },
        ]}
      />,
    );

    expect(screen.getByLabelText("Pipeline stage: Consulting, Prospect")).toBeTruthy();
    expect(screen.getByLabelText("Pipeline stage: LearnWohl, Customer")).toBeTruthy();
  });

  it("omits the offer name when the list is filtered to one offer", () => {
    const screen = render(
      <DealChips
        showOffer={false}
        deals={[
          { id: 1, offer: "Consulting", slug: "consulting", stage: "opportunity", status: "meeting" },
        ]}
      />,
    );

    expect(screen.getByLabelText("Pipeline stage: Opportunity")).toBeTruthy();
    expect(screen.queryByText(/Consulting/)).toBeNull();
  });
});
