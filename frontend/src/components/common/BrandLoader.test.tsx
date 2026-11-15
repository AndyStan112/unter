import { act, cleanup, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import theme from '../../theme/theme';
import { BrandLoader } from './BrandLoader';

function motion(reduced: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}
const view = (loading: boolean) => (
  <ThemeProvider theme={theme}>
    <BrandLoader loading={loading}>
      <button>Ready content</button>
    </BrandLoader>
  </ThemeProvider>
);
beforeEach(() => {
  vi.useFakeTimers();
  motion(false);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('keeps the screen blocked while loading, then reveals the word and releases content', () => {
  const { rerender } = render(view(true));
  act(() => vi.advanceTimersByTime(5000));
  expect(screen.getByRole('status').getAttribute('data-phase')).toBe('drawing');
  expect(screen.getByText('Ready content').closest('[inert]')).not.toBeNull();
  rerender(view(false));
  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByRole('status').getAttribute('data-phase')).toBe('wordmark');
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.queryByRole('status')).toBeNull();
  expect(screen.getByRole('button').closest('[inert]')).toBeNull();
});

it('cancels the exit if another page starts loading before the reveal finishes', () => {
  const { rerender } = render(view(true));
  rerender(view(false));
  act(() => vi.advanceTimersByTime(750));
  expect(screen.getByRole('status').getAttribute('data-phase')).toBe('wordmark');
  rerender(view(true));
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByRole('status').getAttribute('data-phase')).toBe('drawing');
  rerender(view(false));
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.queryByRole('status')).toBeNull();
});

it('does not delay access to ready content when reduced motion is requested', () => {
  motion(true);
  const { rerender } = render(view(true));
  expect(screen.getByRole('status')).toBeTruthy();
  rerender(view(false));
  expect(screen.queryByRole('status')).toBeNull();
  expect(screen.getByRole('button')).toBeTruthy();
});
