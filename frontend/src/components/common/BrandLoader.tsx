import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Box, Typography, useMediaQuery } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { keyframes } from '@emotion/react';
import { brand } from '../../theme/theme';

const draw = keyframes`
  0% { stroke-dashoffset: 1; }
  55%, 72% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: -1; }
`;
const breathe = keyframes`
  0%, 100% { transform: scale(.94); opacity: .45; }
  50% { transform: scale(1.06); opacity: .8; }
`;
type Phase = 'drawing' | 'wordmark' | 'leaving' | 'hidden';

/** A single overlay carries the U animation across route and initial-data loading. */
export function BrandLoader({ loading, children }: { loading: boolean; children: ReactNode }) {
  const theme = useTheme();
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const gradientId = useId();
  const [phase, setPhase] = useState<Phase>('drawing');
  const started = useRef(Date.now());
  const visible = loading || phase !== 'hidden';
  const drawing = loading || phase === 'drawing';

  useEffect(() => {
    if (loading) {
      started.current = Date.now();
      setPhase('drawing');
      return;
    }
    if (reducedMotion) {
      setPhase('hidden');
      return;
    }
    // Finish the first stroke before revealing the word, even on a warm cache.
    const reveal = setTimeout(
      () => setPhase('wordmark'),
      Math.max(0, 720 - (Date.now() - started.current)),
    );
    const leave = setTimeout(
      () => setPhase('leaving'),
      Math.max(0, 720 - (Date.now() - started.current)) + 650,
    );
    const hide = setTimeout(
      () => setPhase('hidden'),
      Math.max(0, 720 - (Date.now() - started.current)) + 930,
    );
    return () => {
      clearTimeout(reveal);
      clearTimeout(leave);
      clearTimeout(hide);
    };
  }, [loading, reducedMotion]);

  return (
    <>
      <Box
        inert={visible}
        aria-hidden={visible || undefined}
        aria-busy={loading}
        sx={{ minHeight: '100dvh' }}
      >
        {children}
      </Box>
      {visible && (
        <Box
          role="status"
          aria-live="polite"
          aria-label="Loading Unter"
          data-phase={drawing ? 'drawing' : phase}
          sx={{
            position: 'fixed',
            inset: 0,
            zIndex: theme.zIndex.modal + 1,
            display: 'grid',
            placeItems: 'center',
            overflow: 'hidden',
            bgcolor: brand.loadingBackground,
            backgroundImage: `radial-gradient(ellipse at 22% 28%, ${alpha(theme.palette.primary.main, 0.18)}, transparent 56%), radial-gradient(ellipse at 82% 78%, ${alpha(theme.palette.secondary.main, 0.22)}, transparent 60%)`,
            opacity: !loading && phase === 'leaving' ? 0 : 1,
            transition: reducedMotion ? 'none' : 'opacity 280ms ease',
            '@media (prefers-reduced-motion: reduce)': {
              '& *': { animation: 'none !important', transition: 'none !important' },
            },
          }}
        >
          <Box
            aria-hidden="true"
            sx={{
              position: 'absolute',
              width: 'min(78vw, 540px)',
              aspectRatio: '1',
              borderRadius: '50%',
              border: `1px solid ${alpha(theme.palette.secondary.main, 0.1)}`,
              boxShadow: `0 0 0 56px ${alpha(theme.palette.secondary.main, 0.025)}, 0 0 0 112px ${alpha(theme.palette.primary.main, 0.025)}`,
              animation: reducedMotion ? 'none' : `${breathe} 3.2s ease-in-out infinite`,
            }}
          />
          <Box sx={{ position: 'relative', width: 'min(82vw, 380px)', textAlign: 'center' }}>
            <Box
              component="svg"
              aria-hidden="true"
              viewBox="0 0 300 120"
              sx={{ width: '100%', overflow: 'visible', display: 'block' }}
            >
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
                  <stop stopColor={theme.palette.secondary.main} />
                  <stop offset="1" stopColor={theme.palette.primary.main} />
                </linearGradient>
              </defs>
              <Box
                component="g"
                sx={{
                  transform: `translateX(${drawing ? 104 : 20}px)`,
                  transition: reducedMotion ? 'none' : 'transform 500ms cubic-bezier(.22,1,.36,1)',
                }}
              >
                <path
                  d="M16 40 V67 C16 100 76 100 76 67 V40"
                  fill="none"
                  stroke={alpha(theme.palette.secondary.main, 0.1)}
                  strokeWidth="14"
                  strokeLinecap="round"
                />
                <Box
                  component="path"
                  d="M16 40 V67 C16 100 76 100 76 67 V40"
                  pathLength="1"
                  fill="none"
                  stroke={`url(#${gradientId})`}
                  strokeWidth="14"
                  strokeLinecap="round"
                  sx={{
                    strokeDasharray: '1 1',
                    strokeDashoffset: 0,
                    animation:
                      drawing && !reducedMotion
                        ? `${draw} 1.2s cubic-bezier(.45,0,.25,1) infinite`
                        : 'none',
                  }}
                />
              </Box>
              <Box
                component="g"
                sx={{
                  opacity: drawing ? 0 : 1,
                  transform: drawing ? 'translateX(10px)' : 'translateX(0)',
                  transition: reducedMotion
                    ? 'none'
                    : 'opacity 320ms 90ms ease, transform 480ms 90ms ease',
                }}
              >
                <text
                  x="104"
                  y="93"
                  fill={theme.palette.text.primary}
                  fontFamily={theme.typography.fontFamily}
                  fontSize="88"
                  fontWeight="900"
                  letterSpacing="-5"
                >
                  nter
                </text>
                <circle cx="266" cy="85" r="7" fill={theme.palette.primary.main} />
              </Box>
            </Box>
            <Typography
              variant="overline"
              color="secondary"
              sx={{ display: 'block', mt: 2, fontSize: 10, letterSpacing: '.3em', opacity: 0.7 }}
            >
              On your way
            </Typography>
          </Box>
        </Box>
      )}
    </>
  );
}
