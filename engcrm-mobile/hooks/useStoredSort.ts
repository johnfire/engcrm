// The sort of one list, remembered between sessions. `ready` turns true once the saved
// choice has been read, so a list can wait for it instead of flashing the default order.
import { useCallback, useEffect, useState } from "react";

import {
  defaultSort,
  loadSort,
  nextSort,
  saveSort,
  SortChoice,
  SortOption,
} from "../services/listSort";

export function useStoredSort<Key extends string>(listName: string, options: readonly SortOption<Key>[]) {
  const [sort, setSort] = useState<SortChoice<Key>>(() => defaultSort(options));
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadSort(listName, options).then((saved) => {
      if (cancelled) return;
      if (saved) setSort(saved);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [listName, options]);

  const choose = useCallback(
    (option: SortOption<Key>) => {
      const chosen = nextSort(sort, option);
      setSort(chosen);
      void saveSort(listName, chosen);
    },
    [listName, sort],
  );

  return { sort, ready, choose };
}
