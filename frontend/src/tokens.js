// Brightloop design tokens — JS mirror of tokens.css.
// Use this when you need a token value in JS (chart colors,
// styled-components theme, conditional inline styles) rather
// than in a stylesheet. Keep both files in sync by hand.

export const tokens = {
  color: {
    midnightIndigo: '#282B4A',
    vanilla: '#EEEBDA',
    surface: '#FFFFFF',
    muted: '#F6F5EE',
    border: '#DCD9C8',
    textPrimary: '#282B4A',
    textSecondary: '#6B7280',
    status: {
      active: { bg: '#DCFCE7', text: '#16A34A' },
      pending: { bg: '#FEF3C7', text: '#D97706' },
      overdue: { bg: '#FEE2E2', text: '#DC2626' },
    },
  },
  font: {
    family: "'Inter', sans-serif",
    h1: { size: '32px', weight: 700, lineHeight: 1.2 },
    h2: { size: '24px', weight: 600, lineHeight: 1.25 },
    h3: { size: '18px', weight: 600, lineHeight: 1.3 },
    body: { size: '14px', weight: 400, lineHeight: 1.5 },
    small: { size: '12px', weight: 400, lineHeight: 1.4 },
  },
  radius: {
    sm: '6px',
    md: '10px',
    full: '999px',
  },
  shadow: {
    card: '0 1px 2px rgba(40, 43, 74, 0.06)',
    elevated: '0 4px 12px rgba(40, 43, 74, 0.12)',
  },
  space: {
    1: '4px',
    2: '8px',
    3: '12px',
    4: '16px',
    5: '24px',
    6: '32px',
    7: '48px',
  },
};
