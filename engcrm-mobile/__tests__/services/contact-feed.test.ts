const mockGet = jest.fn();
jest.mock("../../services/api", () => ({ client: { get: (...args: unknown[]) => mockGet(...args) } }));
import { contactKey, fetchContactFeed } from "../../services/contact-feed";

it("keeps person and organization identities separate", () => {
  expect(contactKey({ id: 1, kind: "person" })).toBe("person-1");
  expect(contactKey({ id: 1, kind: "organization" })).toBe("organization-1");
});

it("uses the combined endpoint with every filter and the requested page", async () => {
  const contacts = [{ id: 1, kind: "person" }];
  mockGet.mockResolvedValue({ data: contacts });
  const filters = { search: "Ann", kind: "person" as const, stage: "candidate", sort: "newest" as const, page: 2 };
  expect(await fetchContactFeed(filters)).toEqual(contacts);
  expect(mockGet).toHaveBeenCalledWith("/api/contact-feed", { params: filters });
});
