import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { api, errorMessage } from '../services/api';
import { useOnline } from './useOnline';
import type {
  ActivityEvent,
  Observation,
  Proposal,
  Report,
  Run,
  Schedule,
} from '../types/dashboard';
interface DashboardData {
  schedule: Schedule | null;
  observations: Observation[];
  reports: Report[];
  runs: Run[];
  activity: ActivityEvent[];
  proposals: Proposal[];
}
interface DashboardContextValue extends DashboardData {
  loading: boolean;
  busy: boolean;
  online: boolean;
  message: string;
  clearMessage: () => void;
  refresh: () => Promise<void>;
  execute: (action: () => Promise<unknown>, success?: string) => Promise<boolean>;
  runReport: () => Promise<boolean>;
}
const initial: DashboardData = {
  schedule: null,
  observations: [],
  reports: [],
  runs: [],
  activity: [],
  proposals: [],
};
const Context = createContext<DashboardContextValue | null>(null);
export function DashboardProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState(initial),
    [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  const lock = useRef(false),
    poll = useRef<Promise<void> | null>(null),
    mounted = useRef(true);
  const online = useOnline();
  const refresh = useCallback(async () => {
    if (!navigator.onLine) {
      setLoading(false);
      return;
    }
    try {
      const schedule = await api<Schedule>('schedule');
      if (mounted.current) setData((old) => ({ ...old, schedule }));
      const paths = ['observations', 'reports', 'runs', 'activity', 'proposals'] as const;
      await Promise.all(
        paths.map(async (path) => {
          try {
            const rows = await api<DashboardData[typeof path]>(path);
            if (mounted.current) setData((old) => ({ ...old, [path]: rows }));
          } catch (error) {
            if (mounted.current) setMessage(errorMessage(error));
          }
        }),
      );
    } catch (error) {
      if (mounted.current) setMessage(errorMessage(error));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    const tick = () => {
      if (lock.current || poll.current) return;
      poll.current = refresh().finally(() => {
        poll.current = null;
      });
    };
    tick();
    const timer = window.setInterval(tick, 30000);
    window.addEventListener('online', tick);
    return () => {
      mounted.current = false;
      clearInterval(timer);
      window.removeEventListener('online', tick);
    };
  }, [refresh]);
  async function execute(action: () => Promise<unknown>, success = '') {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setMessage('');
    try {
      if (poll.current) await poll.current;
      if (!navigator.onLine) throw new Error('Reconnect before making changes.');
      await action();
      await refresh();
      setMessage(success);
      return true;
    } catch (error) {
      setMessage(errorMessage(error));
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const runReport = () =>
    execute(async () => {
      const run = await api<Run>('run', 'POST');
      if (run.status !== 'completed')
        throw new Error(run.error || `Report ${run.status}. See execution history.`);
    }, 'Report ready. Review the proposals before approving any changes.');
  return (
    <Context.Provider
      value={{
        ...data,
        loading,
        busy,
        online,
        message,
        refresh,
        execute,
        runReport,
        clearMessage: () => setMessage(''),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useDashboard() {
  const value = useContext(Context);
  if (!value) throw new Error('Missing DashboardProvider');
  return value;
}
