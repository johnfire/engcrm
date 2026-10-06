const mockGet = jest.fn();
const mockPatch = jest.fn();
jest.mock("../../services/api", () => ({ client: {
  get: (...arguments_: unknown[]) => mockGet(...arguments_), patch: (...arguments_: unknown[]) => mockPatch(...arguments_),
} }));
import { fetchContactDate, saveContactDate } from "../../services/contact-dates";

it("loads the exact contact type and identifier", async () => {
  const record = { id: 7, kind: "person" as const, name: "Ann", interaction_id: 9, contact_date: "2026-10-04" };
  mockGet.mockResolvedValue({ data: record });
  expect(await fetchContactDate("person", 7)).toEqual(record);
  expect(mockGet).toHaveBeenCalledWith("/api/contact-feed/person/7/date");
});

it("sends the reviewed history version with the chosen day", async () => {
  const record = { id: 7, kind: "organization" as const, name: "Academy", interaction_id: 9, contact_date: "2026-10-04" };
  mockPatch.mockResolvedValue({ data: { ...record, contact_date: "2026-10-03" } });
  expect((await saveContactDate(record, "2026-10-03")).contact_date).toBe("2026-10-03");
  expect(mockPatch).toHaveBeenCalledWith("/api/contact-feed/organization/7/date", {
    contact_date: "2026-10-03", interaction_id: 9, previous_date: "2026-10-04",
  });
});
