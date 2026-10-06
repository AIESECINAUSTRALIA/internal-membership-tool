/**
 * THE MUI THEME. All visual styling lives here (spec §2A.11).
 *
 * Rules for anyone editing the UI:
 *   - No one-off CSS files and no hardcoded colours in components. Use the theme:
 *     `color="primary"`, `sx={{ bgcolor: 'background.default' }}`, `theme.spacing(2)`.
 *   - If a component looks wrong everywhere, fix it HERE, once.
 *
 * WHY THE COLOURS LOOK ODD (accessibility, WCAG AA)
 *   Brand colours are optional accents, and TEXT IS ALWAYS BLACK OR WHITE (or the dark
 *   gray brand colour for quiet text). Several brand colours fail contrast with white
 *   text, and MUI picks white text on a colour whenever contrast is at least 3:1. That
 *   would put white on AIESEC blue at 3.98:1, which fails AA (needs 4.5:1). So:
 *     - every palette colour sets `contrastText` explicitly (table in spec §2A.11), and
 *     - `contrastThreshold` is raised to 4.5 as a safety net for any colour added later.
 *   HOVER shades of colours with BLACK text are deliberately LIGHTER than the base
 *   colour (MUI normally darkens). Darkening blue would push black text below 4.5:1.
 *
 * Light theme only. Dark mode is V2 (spec §1.6): when it lands, add a second palette
 * here rather than editing components.
 */
import { createTheme, alpha } from '@mui/material/styles'
import type { CSSProperties } from 'react'
// Lets the theme style the Data Grid (`components.MuiDataGrid`).
import type {} from '@mui/x-data-grid/themeAugmentation'

// ---------------------------------------------------------------------------
// Tokens. Brand values come from docs/brand_guidelines.md.
// ---------------------------------------------------------------------------

const BLACK = '#000000'
const WHITE = '#FFFFFF'
/** Decorative lines only (table rules, dividers). Component edges use slate instead. */
const DIVIDER = '#D9DBDF'

/** Brand colours. Use them as FILLS, borders, icons and marks, never as text colour. */
export const brand = {
  blue: '#037EF3', // AIESEC Blue. Black text on it: 5.28:1
  talent: '#0CB9C1', // Global Talent (oGTa). Black text: 8.73:1
  teacher: '#F48924', // Global Teacher (oGTe). Black text: 8.45:1
  volunteer: '#F85A40', // Global Volunteer (oGV). Black text: 6.53:1
  purple: '#7552CC', // Member Experience / Talent Management. White text: 5.48:1
  green: '#00c16e', // Black text: 8.85:1
  yellow: '#ffc845', // Black text: 13.60:1
  slate: '#52565E', // Dark gray. White text: 7.36:1, and 7.36:1 as text on white
  canvas: '#f5f5f5', // Light gray, page background. Black text: 19.26:1
} as const

// Extra theme fields ---------------------------------------------------------
declare module '@mui/material/styles' {
  interface Palette {
    /** Raw brand colours for marks, dots and fills (see `brand` above). */
    brand: typeof brand
  }
  interface PaletteOptions {
    brand?: typeof brand
  }
  interface TypographyVariants {
    /** Marcellus display type. Sign-in headline and product name only. */
    display: CSSProperties
    displaySm: CSSProperties
  }
  interface TypographyVariantsOptions {
    display?: CSSProperties
    displaySm?: CSSProperties
  }
}
declare module '@mui/material/Typography' {
  interface TypographyPropsVariantOverrides {
    display: true
    displaySm: true
  }
}

// ---------------------------------------------------------------------------
// Type. Two families, self-hosted with @fontsource (imported in main.tsx).
//   Lato: all everyday text (body, tables, forms, buttons, page titles).
//   Marcellus: a flared face that echoes the AIESEC wordmark. Used ONLY for the
//     sign-in and not-allocated headlines, the one brand moment.
// ---------------------------------------------------------------------------
const BODY_FONT = '"Lato", system-ui, "Segoe UI", Roboto, sans-serif'
const DISPLAY_FONT = '"Marcellus", Georgia, serif'

export const theme = createTheme({
  palette: {
    mode: 'light',
    contrastThreshold: 4.5,
    tonalOffset: 0.2,
    primary: {
      main: brand.blue,
      light: '#6BB4F8',
      dark: '#3F9BF6', // LIGHTER on purpose: hover keeps black text above 4.5:1
      contrastText: BLACK,
    },
    secondary: {
      main: brand.slate,
      light: '#7A7E86',
      dark: '#3D4046',
      contrastText: WHITE,
    },
    error: { main: brand.volunteer, light: '#FA8F7E', dark: '#FA7D68', contrastText: BLACK },
    warning: { main: brand.yellow, light: '#FFD97A', dark: '#FFD36B', contrastText: BLACK },
    success: { main: brand.green, light: '#4DD69B', dark: '#33CE8B', contrastText: BLACK },
    info: { main: brand.blue, light: '#6BB4F8', dark: '#3F9BF6', contrastText: BLACK },
    text: {
      primary: BLACK,
      secondary: brand.slate, // quiet text: 7.36:1 on white, 6.7:1 on the canvas
      disabled: alpha(BLACK, 0.38), // disabled controls are exempt from contrast rules
    },
    background: { default: brand.canvas, paper: WHITE },
    divider: DIVIDER,
    action: {
      hover: alpha(BLACK, 0.05),
      selected: alpha(BLACK, 0.08),
      focus: alpha(BLACK, 0.12),
    },
    brand,
  },

  shape: { borderRadius: 6 },
  spacing: 8,

  typography: {
    fontFamily: BODY_FONT,
    fontWeightRegular: 400,
    fontWeightBold: 700,
    // Scale: 1.2 ratio, sentence case, left aligned. Hierarchy comes from size and weight.
    h1: { fontSize: '1.875rem', fontWeight: 700, lineHeight: 1.2 }, // 30px page title
    h2: { fontSize: '1.5rem', fontWeight: 700, lineHeight: 1.25 }, // 24px
    h3: { fontSize: '1.25rem', fontWeight: 700, lineHeight: 1.3 }, // 20px
    h4: { fontSize: '1.125rem', fontWeight: 700, lineHeight: 1.35 }, // 18px
    body1: { fontSize: '1rem', lineHeight: 1.5 }, // 16px
    body2: { fontSize: '0.9375rem', lineHeight: 1.5 }, // 15px, table cells (Lato sets small)
    caption: { fontSize: '0.875rem', lineHeight: 1.45 }, // 14px
    button: { fontWeight: 700, textTransform: 'none', letterSpacing: 0 }, // no all-caps
    display: { fontFamily: DISPLAY_FONT, fontWeight: 400, fontSize: '2.75rem', lineHeight: 1.15, letterSpacing: 0 }, // 44px
    displaySm: { fontFamily: DISPLAY_FONT, fontWeight: 400, fontSize: '2rem', lineHeight: 1.2, letterSpacing: 0 }, // 32px
  },

  components: {
    // ---- Page base + keyboard focus ---------------------------------------
    MuiCssBaseline: {
      styleOverrides: {
        // Visible focus on everything (WCAG 2.4.7): a 3px black ring with a gap, which
        // reads on white, on the gray canvas and on blue buttons. `body *` is deliberate:
        // MUI buttons set `outline: 0` with the same specificity as a bare `*`, and would win.
        'body *:focus-visible': { outline: `3px solid ${BLACK}`, outlineOffset: '2px' },
        // Text fields show focus with a thick black border instead (see OutlinedInput).
        'body .MuiInputBase-root *:focus-visible': { outline: 'none' },
        body: { backgroundColor: brand.canvas },
        // Respect "reduce motion" (WCAG 2.3.3): drop transitions and animations entirely.
        '@media (prefers-reduced-motion: reduce)': {
          '*, *::before, *::after': {
            animationDuration: '0.01ms !important',
            animationIterationCount: '1 !important',
            transitionDuration: '0.01ms !important',
            scrollBehavior: 'auto !important',
          },
        },
      },
    },

    // ---- Buttons -----------------------------------------------------------
    MuiButton: {
      // No pulsing focus ripple: it darkens the blue behind the black label. The 3px black
      // focus ring (see MuiCssBaseline) already shows where focus is.
      defaultProps: { disableElevation: true, disableFocusRipple: true },
      styleOverrides: {
        root: { minHeight: 44, paddingInline: 20 }, // 44px touch target
      },
      variants: [
        // Outlined buttons use the dark gray edge so they are 3:1 against white.
        {
          props: { variant: 'outlined', color: 'primary' },
          style: { color: BLACK, borderColor: brand.slate, '&:hover': { borderColor: BLACK, backgroundColor: alpha(BLACK, 0.05) } },
        },
        { props: { variant: 'text', color: 'primary' }, style: { color: BLACK } },
        // Large: the one main action on a page (sign-in).
        { props: { size: 'large' }, style: { minHeight: 52, fontSize: '1.0625rem' } },
      ],
    },
    MuiIconButton: {
      defaultProps: { disableFocusRipple: true },
      styleOverrides: { root: { color: BLACK } },
      // 44px touch target. Small icon buttons (inside the Data Grid header) stay compact.
      variants: [{ props: { size: 'medium' }, style: { minWidth: 44, minHeight: 44 } }],
    },

    // ---- Links: black, underlined (colour is never the only cue) ------------
    MuiLink: {
      defaultProps: { underline: 'always', color: 'inherit' },
    },

    // ---- Form fields ---------------------------------------------------------
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          backgroundColor: WHITE,
          // Field edges need 3:1 against white (WCAG 1.4.11), so use slate, not MUI's default.
          '& .MuiOutlinedInput-notchedOutline': { borderColor: brand.slate },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: BLACK },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: BLACK, borderWidth: 2 },
          '&.Mui-error .MuiOutlinedInput-notchedOutline': { borderColor: brand.volunteer, borderWidth: 2 },
        },
      },
    },
    // Error and focus text stays black: brand red is not allowed as text colour.
    MuiInputLabel: {
      styleOverrides: {
        root: { color: BLACK, '&.Mui-focused': { color: BLACK }, '&.Mui-error': { color: BLACK } },
      },
    },
    MuiFormLabel: { styleOverrides: { root: { color: BLACK, '&.Mui-focused': { color: BLACK }, '&.Mui-error': { color: BLACK } } } },
    MuiFormHelperText: {
      styleOverrides: {
        root: { color: brand.slate, marginInline: 0, '&.Mui-error': { color: BLACK, fontWeight: 700 } },
      },
    },

    // ---- Alerts: a coloured band + icon + black text (never colour alone) ---
    MuiAlert: {
      styleOverrides: {
        root: {
          color: BLACK,
          backgroundColor: WHITE,
          border: `1px solid ${brand.slate}`,
          borderLeftWidth: 6,
          '& .MuiAlert-icon': { color: BLACK },
        },
      },
      variants: [
        { props: { severity: 'success' }, style: { borderLeftColor: brand.green } },
        { props: { severity: 'info' }, style: { borderLeftColor: brand.blue } },
        { props: { severity: 'warning' }, style: { borderLeftColor: brand.yellow } },
        { props: { severity: 'error' }, style: { borderLeftColor: brand.volunteer } },
      ],
    },

    // ---- Chips (position and function pairs) -------------------------------------
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 400, height: 28 },
        outlined: { borderColor: brand.slate, color: BLACK },
      },
    },

    // ---- Surfaces ---------------------------------------------------------------
    MuiPaper: {
      styleOverrides: { outlined: { borderColor: DIVIDER } },
    },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 8 } } },
    MuiDialogTitle: { defaultProps: { variant: 'h3', component: 'h2' } },
    // Toasts sit bottom-centre so they never cover the sidebar.
    MuiSnackbar: { defaultProps: { anchorOrigin: { vertical: 'bottom', horizontal: 'center' } } },
    MuiAvatar: { styleOverrides: { root: { backgroundColor: brand.slate, color: WHITE, fontWeight: 700 } } },

    // ---- Sidebar navigation -------------------------------------------------------
    // Selected page: light gray fill + a 4px blue bar + bold text. Three cues, so the
    // current page never depends on colour alone.
    MuiListItemButton: {
      styleOverrides: {
        root: {
          position: 'relative',
          borderRadius: 6,
          minHeight: 44,
          '&.Mui-selected': {
            backgroundColor: brand.canvas,
            '& .MuiListItemText-primary': { fontWeight: 700 },
            '&:hover': { backgroundColor: '#ECECEC' },
            '&::before': {
              content: '""',
              position: 'absolute',
              left: 0,
              top: 8,
              bottom: 8,
              width: 4,
              borderRadius: 2,
              backgroundColor: brand.blue,
            },
          },
        },
      },
    },
    MuiListItemIcon: { styleOverrides: { root: { color: BLACK, minWidth: 40 } } },

    // ---- Plain tables (Profile) ------------------------------------------------------
    MuiTableCell: {
      styleOverrides: {
        root: { borderBottomColor: DIVIDER },
        head: { fontWeight: 700, backgroundColor: brand.canvas, color: BLACK },
      },
    },

    // ---- Data Grid (Membership summary) ----------------------------------------------
    // Slate header with white text (7.36:1). Body stays white with black text.
    MuiDataGrid: {
      defaultProps: { disableRowSelectionOnClick: true },
      styleOverrides: {
        root: {
          borderColor: DIVIDER,
          backgroundColor: WHITE,
          fontSize: '0.875rem',
          '& .MuiDataGrid-columnHeaders, & .MuiDataGrid-columnHeader, & .MuiDataGrid-filler, & .MuiDataGrid-scrollbarFiller': {
            backgroundColor: brand.slate,
            color: WHITE,
          },
          '& .MuiDataGrid-columnHeaderTitle': { fontWeight: 700 },
          '& .MuiDataGrid-columnHeader .MuiSvgIcon-root': { color: WHITE },
          // The sort button keeps a paper-coloured fill by default, which shows as a white blob on slate.
          '& .MuiDataGrid-columnHeader .MuiIconButton-root': { color: WHITE, backgroundColor: 'transparent', '&:hover': { backgroundColor: alpha(WHITE, 0.16) } },
          '& .MuiDataGrid-columnSeparator': { color: alpha(WHITE, 0.4) },
          '& .MuiDataGrid-cell': { borderColor: '#E7E9EC', alignItems: 'center', display: 'flex' },
          // The grid's default blue focus box is too faint on slate. Header: white. Cells: black.
          '& .MuiDataGrid-columnHeader:focus, & .MuiDataGrid-columnHeader:focus-within': { outline: `2px solid ${WHITE}`, outlineOffset: '-3px' },
          '& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within': { outline: `2px solid ${BLACK}`, outlineOffset: '-2px' },
          '& .MuiDataGrid-row:hover': { backgroundColor: alpha(BLACK, 0.04) }, // row highlight helps tracking across columns
          '& .MuiDataGrid-footerContainer': { borderColor: DIVIDER },
        },
      },
    },
  },
})
