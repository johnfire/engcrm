export function isExpiredBootstrap(error: unknown): boolean {
  if (!error || typeof error !== "object" || !("response" in error)) return false;
  const response = error.response;
  if (!response || typeof response !== "object" || !("status" in response) || !("data" in response)) return false;
  const body = response.data;
  if (!body || typeof body !== "object" || !("detail" in body)) return false;
  return response.status === 400 && ["Invalid or expired bootstrap token", "Bootstrap token has expired"].includes(String(body.detail));
}

export function isSingleMutationConflict(error: unknown, mutations: Record<string, unknown>[]): boolean {
  return mutations.length === 1 && !!error && typeof error === "object" && "response" in error &&
    !!error.response && typeof error.response === "object" && "status" in error.response &&
    error.response.status === 409 && typeof mutations[0].mutation_id === "string";
}
