import { createContext, useContext, type Dispatch, type SetStateAction } from 'react';
export type RidePanel = 'menu' | 'history' | 'earnings' | 'settings' | null;
export const RideChrome = createContext<{
  sheetHeight: number;
  setSheetHeight: Dispatch<SetStateAction<number>>;
  openPanel: (panel: RidePanel) => void;
}>({ sheetHeight: 0, setSheetHeight: () => {}, openPanel: () => {} });
export const useRideChrome = () => useContext(RideChrome);
