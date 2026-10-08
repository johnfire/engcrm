import { client } from "./api";

export interface ProfileCandidate {
  url: string;
  title: string;
  snippet: string;
}

export interface ProfileSuggestions {
  status: "found" | "no_match" | "needs_name" | "unavailable";
  candidates: ProfileCandidate[];
}

export async function searchCaptureProfiles(
  captureId: number, name: string, company: string, city: string,
): Promise<ProfileSuggestions> {
  const response = await client.post(`/api/cards/${captureId}/linkedin-search`,
    { name, company, city }, { timeout: 30000 });
  return response.data;
}
