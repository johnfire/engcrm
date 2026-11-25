import type { Server } from "./reviewer-routing";

export const API_BASE = "https://engcrm.christopherrehm.de";

export function baseForServer(server: Server): string {
  return server === "reviewer" ? `${API_BASE}/reviewer` : API_BASE;
}
