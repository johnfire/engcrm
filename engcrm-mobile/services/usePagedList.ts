import { useCallback, useRef, useState } from "react";

/** One page at a time, for lists that can be longer than a screen (a LinkedIn import
 *  alone is hundreds of people). `fetchPage(page)` answers 1, 2, 3 … ; a page shorter
 *  than `pageSize` is the last. `reload` starts again from page 1 and is the hook's
 *  trigger: it changes whenever `fetchPage` does, which is when a filter changed.
 *
 *  An answer that arrives after a newer request was made is dropped, and a row that
 *  turns up on two pages (the list changed between them) is shown once. */
export function usePagedList<T extends { id: number }>(
  fetchPage: (page: number) => Promise<T[]>,
  pageSize: number,
) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const ticket = useRef(0);
  const page = useRef(1);
  const more = useRef(false);
  const busy = useRef(false);

  const reload = useCallback(async () => {
    const mine = ++ticket.current;
    busy.current = true;
    setLoading(true);
    setLoadingMore(false); // a page still on its way belongs to the old filters
    try {
      const first = await fetchPage(1);
      if (mine !== ticket.current) return;
      page.current = 1;
      more.current = first.length >= pageSize;
      setItems(first);
      setError(false);
    } catch {
      if (mine !== ticket.current) return;
      more.current = false;
      setError(true);
    } finally {
      if (mine === ticket.current) {
        busy.current = false;
        setLoading(false);
      }
    }
  }, [fetchPage, pageSize]);

  const loadMore = useCallback(async () => {
    if (busy.current || !more.current) return;
    const mine = ticket.current;
    busy.current = true;
    setLoadingMore(true);
    try {
      const next = await fetchPage(page.current + 1);
      if (mine !== ticket.current) return;
      page.current += 1;
      more.current = next.length >= pageSize;
      setItems((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...next.filter((item) => !seen.has(item.id))];
      });
    } catch {
      // Keep what is shown. The next scroll to the end tries this page again.
    } finally {
      if (mine === ticket.current) {
        busy.current = false;
        setLoadingMore(false);
      }
    }
  }, [fetchPage, pageSize]);

  return { items, loading, loadingMore, error, reload, loadMore };
}
