// System font for now. Pick a family with Hanifi Rohingya coverage before loading one.
// Scale is capped at 4 sizes / 2 weights to keep hierarchy obvious.
export const fonts = {
  size: { sm: 14, md: 16, lg: 22, xl: 32 },
  weight: { regular: '400', bold: '700' },
} as const;
