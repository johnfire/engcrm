import { render, fireEvent } from "@testing-library/react-native";

import { OrganizationRow } from "../../components/OrganizationRow";
import type { Organization } from "../../services/api";

const ORG = {
  id: 9,
  name: "Galerie Nord",
  city: "Ulm",
  country: "DE",
  type: "gallery",
  pipeline_stage: "suspect",
  status: "ready",
  do_not_contact: false,
  email_bounced: false,
  research_exhausted: false,
  email: null,
  website: null,
  fit_score: null,
  flagged: false,
  starred: false,
  personal_priority: null,
  last_contact: null,
  created_at: "2026-07-01T00:00:00",
} as Organization;

describe("OrganizationRow — LinkedIn badge", () => {
  it("shows how many LinkedIn connections you have there", () => {
    const screen = render(
      <OrganizationRow item={{ ...ORG, linkedin_connection_count: 3 }} onPress={() => {}} />,
    );
    expect(screen.getByText("in 3")).toBeTruthy();
  });

  it("shows nothing when there are none, or the server predates the field", () => {
    const zero = render(
      <OrganizationRow item={{ ...ORG, linkedin_connection_count: 0 }} onPress={() => {}} />,
    );
    expect(zero.queryByText(/^in /)).toBeNull();
    zero.unmount();

    const legacy = render(<OrganizationRow item={ORG} onPress={() => {}} />);
    expect(legacy.queryByText(/^in /)).toBeNull();
  });

  it("still opens the organization when pressed", () => {
    const onPress = jest.fn();
    const screen = render(
      <OrganizationRow item={{ ...ORG, linkedin_connection_count: 1 }} onPress={onPress} />,
    );
    fireEvent.press(screen.getByText("Galerie Nord"));
    expect(onPress).toHaveBeenCalledWith(9);
  });
});
