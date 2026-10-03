import { act, renderHook, waitFor } from "@testing-library/react-native";

import { usePagedList } from "../../services/usePagedList";

const rows = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => ({ id: from + i }));

type Row = { id: number };
type Fetch = (page: number) => Promise<Row[]>;

function setup(fetchPage: Fetch, pageSize = 3) {
  return renderHook(({ fetch }: { fetch: Fetch }) => usePagedList<Row>(fetch, pageSize), {
    initialProps: { fetch: fetchPage },
  });
}

describe("usePagedList", () => {
  it("loads the first page, then the next ones as asked, and stops at a short page", async () => {
    const fetchPage = jest.fn(async (page: number) => (page === 1 ? rows(1, 3) : page === 2 ? rows(4, 5) : []));
    const { result } = setup(fetchPage);
    await act(async () => { await result.current.reload(); });
    expect(result.current.items.map((r) => r.id)).toEqual([1, 2, 3]);
    await act(async () => { await result.current.loadMore(); });
    expect(result.current.items.map((r) => r.id)).toEqual([1, 2, 3, 4, 5]);
    await act(async () => { await result.current.loadMore(); });
    expect(fetchPage).toHaveBeenCalledTimes(2); // page 2 was short: there is no page 3 to ask for
  });

  it("shows a row once even if it turns up on two pages", async () => {
    const fetchPage = jest.fn(async (page: number) => (page === 1 ? rows(1, 3) : [{ id: 3 }, { id: 4 }, { id: 5 }]));
    const { result } = setup(fetchPage);
    await act(async () => { await result.current.reload(); });
    await act(async () => { await result.current.loadMore(); });
    expect(result.current.items.map((r) => r.id)).toEqual([1, 2, 3, 4, 5]);
  });

  it("does nothing before the first page has loaded, or while a page is on its way", async () => {
    let release: (value: { id: number }[]) => void = () => {};
    const fetchPage = jest.fn((page: number) =>
      page === 1 ? Promise.resolve(rows(1, 3)) : new Promise<{ id: number }[]>((resolve) => { release = resolve; }),
    );
    const { result } = setup(fetchPage);
    await act(async () => { await result.current.loadMore(); });
    expect(fetchPage).not.toHaveBeenCalled();
    await act(async () => { await result.current.reload(); });
    act(() => { result.current.loadMore(); result.current.loadMore(); });
    expect(fetchPage).toHaveBeenCalledTimes(2); // page 1 and one page 2 — not two
    await act(async () => { release(rows(4, 4)); });
    await waitFor(() => expect(result.current.items).toHaveLength(4));
  });

  it("drops a slow answer that belongs to an older filter", async () => {
    let answerOld: (value: { id: number }[]) => void = () => {};
    const oldFetch = jest.fn(() => new Promise<{ id: number }[]>((resolve) => { answerOld = resolve; }));
    const newFetch = jest.fn(async () => rows(10, 11));
    const { result, rerender } = setup(oldFetch);
    act(() => { result.current.reload(); });
    rerender({ fetch: newFetch });
    await act(async () => { await result.current.reload(); });
    await act(async () => { answerOld(rows(1, 2)); });
    expect(result.current.items.map((r) => r.id)).toEqual([10, 11]);
    expect(result.current.loading).toBe(false);
  });

  it("reports a failed load, and keeps what is shown when a later page fails", async () => {
    const failing = jest.fn(async () => { throw new Error("offline"); });
    const first = setup(failing);
    await act(async () => { await first.result.current.reload(); });
    expect(first.result.current.error).toBe(true);
    expect(first.result.current.items).toEqual([]);

    const fetchPage = jest.fn(async (page: number) => {
      if (page === 1) return rows(1, 3);
      throw new Error("offline");
    });
    const { result } = setup(fetchPage);
    await act(async () => { await result.current.reload(); });
    await act(async () => { await result.current.loadMore(); });
    expect(result.current.items).toHaveLength(3);
    expect(result.current.error).toBe(false);
    expect(result.current.loadingMore).toBe(false);
    await act(async () => { await result.current.loadMore(); }); // the next scroll tries again
    expect(fetchPage).toHaveBeenCalledTimes(3);
  });

  it("starts again from page 1 on reload", async () => {
    const fetchPage = jest.fn(async (page: number) => (page === 1 ? rows(1, 3) : rows(4, 6)));
    const { result } = setup(fetchPage);
    await act(async () => { await result.current.reload(); });
    await act(async () => { await result.current.loadMore(); });
    await act(async () => { await result.current.reload(); });
    expect(result.current.items.map((r) => r.id)).toEqual([1, 2, 3]);
    await act(async () => { await result.current.loadMore(); });
    expect(fetchPage).toHaveBeenLastCalledWith(2);
  });
});
