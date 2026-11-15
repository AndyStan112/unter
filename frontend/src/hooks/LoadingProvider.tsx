import {
  createContext,
  useCallback,
  useContext,
  useId,
  useLayoutEffect,
  useState,
  type ReactNode,
} from 'react';
import { BrandLoader } from '../components/common/BrandLoader';

type SetPending = (id: string, pending: boolean) => void;
const LoadingContext = createContext<SetPending | null>(null);

export function LoadingProvider({ loading, children }: { loading: boolean; children: ReactNode }) {
  const [pending, setPending] = useState<Set<string>>(() => new Set());
  const signal = useCallback<SetPending>((id, active) => {
    setPending((current) => {
      if (current.has(id) === active) return current;
      const next = new Set(current);
      if (active) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);
  return (
    <LoadingContext.Provider value={signal}>
      <BrandLoader loading={loading || pending.size > 0}>{children}</BrandLoader>
    </LoadingContext.Provider>
  );
}

/** Only initial loading belongs here; polling and mutations retain inline progress. */
export function useLoadingSignal(loading: boolean) {
  const signal = useContext(LoadingContext);
  const id = useId();
  useLayoutEffect(() => {
    signal?.(id, loading);
    return () => signal?.(id, false);
  }, [id, loading, signal]);
}
