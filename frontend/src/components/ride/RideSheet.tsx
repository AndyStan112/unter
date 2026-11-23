import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Box, ButtonBase, Paper } from '@mui/material';
import { useRideChrome } from './RideChrome';
export function RideSheet({ children, label }: { children: ReactNode; label: string }) {
  const element = useRef<HTMLDivElement>(null);
  const pointer = useRef({ y: 0, dragged: false });
  const [expanded, setExpanded] = useState(false);
  const { setSheetHeight } = useRideChrome();
  useEffect(() => {
    if (!element.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setSheetHeight(Math.ceil(entry.contentRect.height)),
    );
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      setSheetHeight(0);
    };
  }, [setSheetHeight]);
  return (
    <Paper
      ref={element}
      component="section"
      aria-label={label}
      data-ride-sheet
      sx={{
        position: 'absolute',
        zIndex: 600,
        bottom: { xs: 0, md: 20 },
        left: { xs: 0, md: 20 },
        width: { xs: '100%', md: 400 },
        borderRadius: { xs: '26px 26px 0 0', md: '26px' },
        boxShadow: '0 -4px 32px #17244418',
        overflow: 'hidden',
        height: expanded ? 'min(82dvh, 650px)' : 'auto',
        maxHeight: '82dvh',
        display: 'flex',
        flexDirection: 'column',
        '@media (min-width:600px) and (max-height:500px)': {
          width: 360,
          left: 16,
          bottom: 16,
          borderRadius: '24px',
          maxHeight: 'calc(100dvh - 100px)',
        },
      }}
    >
      <ButtonBase
        aria-label={expanded ? 'Collapse ride details' : 'Expand ride details'}
        aria-expanded={expanded}
        onPointerDown={(event) => {
          pointer.current = { y: event.clientY, dragged: false };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerUp={(event) => {
          const distance = event.clientY - pointer.current.y;
          pointer.current.dragged = Math.abs(distance) > 30;
          if (pointer.current.dragged) setExpanded(distance < 0);
        }}
        onClick={() => {
          if (!pointer.current.dragged) setExpanded((value) => !value);
          pointer.current.dragged = false;
        }}
        sx={{ height: 30, flexShrink: 0, width: '100%', touchAction: 'none' }}
      >
        <Box sx={{ width: 36, height: 4, borderRadius: 4, bgcolor: '#CDD2DA' }} />
      </ButtonBase>
      <Box
        sx={{
          overflowY: 'auto',
          overscrollBehavior: 'contain',
          px: 2.5,
          pb: 'max(20px, env(safe-area-inset-bottom))',
          maxHeight: expanded ? 'none' : 'calc(67dvh - 30px)',
          flex: expanded ? 1 : undefined,
        }}
      >
        {children}
      </Box>
    </Paper>
  );
}
