import { createTheme } from '@mui/material/styles';

// Shared design tokens. Change the brand, fonts and component defaults here.
export const brand = {
  pink: '#C6007E',
  blue: '#163EAB',
  ink: '#172444',
  muted: '#64708A',
  background: '#F7F8FC',
  border: '#E5E8F1',
};

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: brand.pink, contrastText: '#FFFFFF' },
    secondary: { main: brand.blue, contrastText: '#FFFFFF' },
    background: { default: brand.background, paper: '#FFFFFF' },
    text: { primary: brand.ink, secondary: brand.muted },
    divider: brand.border,
  },
  typography: {
    fontFamily: 'Roboto, system-ui, sans-serif',
    h1: {
      fontSize: 'clamp(2.5rem, 5vw, 4.75rem)',
      fontWeight: 800,
      lineHeight: 1.05,
      letterSpacing: '-0.045em',
    },
    h2: { fontSize: 'clamp(1.8rem, 3vw, 2.75rem)', fontWeight: 750, letterSpacing: '-0.035em' },
    h3: { fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.025em' },
    h4: { fontSize: '1.2rem', fontWeight: 700 },
    h6: { fontSize: '1rem', fontWeight: 700 },
    button: { textTransform: 'none', fontWeight: 700 },
    body2: { lineHeight: 1.65 },
    overline: { fontWeight: 700, letterSpacing: '0.16em', lineHeight: 1.8 },
  },
  shape: { borderRadius: 16 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        '*': { boxSizing: 'border-box' },
        body: { margin: 0 },
        a: { color: 'inherit' },
        '#root': { minHeight: '100dvh' },
        '.leaflet-container': {
          fontFamily: 'Roboto, system-ui, sans-serif',
          width: '100%',
          height: '100%',
          zIndex: 0,
        },
        '.leaflet-control-attribution': { fontSize: '10px' },
        pre: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 12, padding: '11px 20px', minHeight: 44 },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: { outlined: { borderColor: brand.border } },
    },
    MuiCard: {
      defaultProps: { variant: 'outlined' },
      styleOverrides: { root: { borderRadius: 20 } },
    },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 12 } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600, borderRadius: 8 } } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 700, minHeight: 52 } } },
    MuiTableCell: {
      styleOverrides: {
        head: { color: brand.muted, fontWeight: 700 },
        root: { borderColor: brand.border },
      },
    },
  },
});
export default theme;
