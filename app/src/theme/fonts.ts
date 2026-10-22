// System fonts for now; swap in a loaded family (expo-font) once one is chosen,
// ideally one with Hanifi Rohingya coverage.
export const fonts = {
  regular: undefined,
  family: { fontFamily: undefined },
  size: { xs: 12, sm: 14, md: 16, lg: 20, xl: 26, xxl: 34 },
  weight: { regular: '400', medium: '500', bold: '700' },
} as const;
