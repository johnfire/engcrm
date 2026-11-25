import { createSyncCoordinator } from "../../services/sync-coordinator";

async function flush() { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); }

afterEach(() => jest.useRealTimers());

it("runs again when another trigger arrives during an active sync", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => { finish = resolve; });
  const sync = jest.fn().mockReturnValueOnce(pending).mockResolvedValue(undefined);
  const coordinator = createSyncCoordinator(sync, () => {}, () => 0);
  coordinator.trigger();
  coordinator.trigger();
  expect(sync).toHaveBeenCalledTimes(1);
  finish();
  await flush();
  expect(sync).toHaveBeenCalledTimes(2);
  coordinator.stop();
});

it("backs off after network failures and stops retrying after disposal", async () => {
  jest.useFakeTimers();
  const sync = jest.fn().mockRejectedValue(new Error("offline"));
  const coordinator = createSyncCoordinator(sync, () => {}, () => 0);
  coordinator.trigger();
  await flush();
  jest.advanceTimersByTime(999);
  expect(sync).toHaveBeenCalledTimes(1);
  jest.advanceTimersByTime(1);
  await flush();
  expect(sync).toHaveBeenCalledTimes(2);
  coordinator.stop();
  jest.advanceTimersByTime(60_000);
  await flush();
  expect(sync).toHaveBeenCalledTimes(2);
});

it("does not retry an authentication failure automatically", async () => {
  jest.useFakeTimers();
  const sync = jest.fn().mockRejectedValue({ response: { status: 401 } });
  const report = jest.fn();
  const coordinator = createSyncCoordinator(sync, report, () => 0);
  coordinator.trigger();
  await flush();
  expect(report).toHaveBeenCalledWith("needs_auth");
  coordinator.trigger();
  jest.advanceTimersByTime(60_000);
  await flush();
  expect(sync).toHaveBeenCalledTimes(1);
  coordinator.stop();
});
