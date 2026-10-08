import { client } from "../../services/api";
import { searchCaptureProfiles } from "../../services/capture-linkedin";

jest.mock("../../services/api", () => ({ client: { post: jest.fn() } }));

it("sends only identity fields and the pending capture ID", async () => {
  const response = { status: "no_match", candidates: [] };
  (client.post as jest.Mock).mockResolvedValue({ data: response });
  expect(await searchCaptureProfiles(7, "Anna Roth", "ACME", "Augsburg")).toEqual(response);
  expect(client.post).toHaveBeenCalledWith("/api/cards/7/linkedin-search",
    { name: "Anna Roth", company: "ACME", city: "Augsburg" }, { timeout: 30000 });
});
