export type Server = "production" | "reviewer";

export function serverForEmail(email: string): Server {
  return email.trim().toLowerCase() === "tester367google@example.test" ? "reviewer" : "production";
}

export function serverForSession(server: string | null): Server {
  return server === "reviewer" ? "reviewer" : "production";
}
