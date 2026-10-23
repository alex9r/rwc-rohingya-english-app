import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { api } from '@/api/client';
import type { ProgressSummary } from '@/api/types';

interface AppState {
  saved: ReadonlySet<string>;
  toggleSaved: (wordId: string) => void;
  progress: ProgressSummary | null;
  recordWordPractice: (wordId: string, score: number) => Promise<void>;
  recordScenarioComplete: (scenarioId: string) => Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

/** Shared saved-words + learning progress; the API client is the source of truth. */
export function AppStateProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState<ReadonlySet<string>>(new Set());
  const [progress, setProgress] = useState<ProgressSummary | null>(null);

  useEffect(() => {
    api.getSavedWordIds().then((ids) => setSaved(new Set(ids)));
    api.getProgress().then(setProgress);
  }, []);

  // Ref keeps toggleSaved stable (memoized word rows) without side effects in a state updater.
  const savedRef = useRef(saved);
  useEffect(() => {
    savedRef.current = saved;
  }, [saved]);

  const toggleSaved = useCallback((wordId: string) => {
    const next = new Set(savedRef.current);
    const nowSaved = !next.delete(wordId);
    if (nowSaved) next.add(wordId);
    savedRef.current = next;
    setSaved(next);
    void api.setWordSaved(wordId, nowSaved);
  }, []);

  const recordWordPractice = useCallback(async (wordId: string, score: number) => {
    setProgress(await api.saveProgress({ type: 'word', wordId, score }));
  }, []);

  const recordScenarioComplete = useCallback(async (scenarioId: string) => {
    setProgress(await api.saveProgress({ type: 'scenario', scenarioId }));
  }, []);

  const value = useMemo(
    () => ({ saved, toggleSaved, progress, recordWordPractice, recordScenarioComplete }),
    [saved, toggleSaved, progress, recordWordPractice, recordScenarioComplete],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAppState must be used inside AppStateProvider');
  return v;
}
