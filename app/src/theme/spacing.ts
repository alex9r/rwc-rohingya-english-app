// 4/8-point grid.
export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 } as const;
export const radius = { sm: 12, md: 20, lg: 28, sheet: 32, pill: 999 } as const;
/** Minimum touch target (>= 44pt iOS / 48dp Android). */
export const touch = 48;
/** Space screens reserve at the bottom for the floating tab bar (excl. safe-area inset). */
export const TAB_BAR_SPACE = 88;
