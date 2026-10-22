import { useCallback, useState } from 'react';

/** In-memory saved words. Persist (AsyncStorage / backend) once that exists. */
export function useSavedWords() {
  const [saved, setSaved] = useState<ReadonlySet<string>>(new Set());
  const toggle = useCallback((id: string) => {
    setSaved((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);
  return { saved, toggle };
}
