export type CoordinatorState = "syncing" | "idle" | "error" | "needs_auth";

function isAuthenticationFailure(error: unknown): boolean {
  return !!error && typeof error === "object" && "response" in error && !!error.response &&
    typeof error.response === "object" && "status" in error.response && error.response.status === 401;
}

export function createSyncCoordinator(sync: () => Promise<void>, report: (state: CoordinatorState) => void,
                                      random: () => number = Math.random) {
  let running = false;
  let rerun = false;
  let stopped = false;
  let authBlocked = false;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function trigger(): void {
    if (stopped || authBlocked) return;
    if (timer !== null) { clearTimeout(timer); timer = null; }
    if (running) { rerun = true; return; }
    void run();
  }

  async function run(): Promise<void> {
    running = true;
    report("syncing");
    let succeeded = false;
    try {
      await sync();
      succeeded = true;
      failures = 0;
      if (!stopped) report("idle");
    } catch (error) {
      if (stopped) return;
      if (isAuthenticationFailure(error)) {
        authBlocked = true;
        rerun = false;
        report("needs_auth");
      } else {
        report("error");
        const base = Math.min(60_000, 1_000 * (2 ** Math.min(failures, 6)));
        failures += 1;
        timer = setTimeout(trigger, base + Math.floor(base * 0.25 * random()));
      }
    } finally {
      running = false;
      if (succeeded && rerun && !stopped) { rerun = false; trigger(); }
    }
  }

  function stop(): void {
    stopped = true;
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  return { trigger, stop };
}
