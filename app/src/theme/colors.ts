// Light blue + white. Text on the gradient is white and large/bold only (>=3:1);
// all small text sits on white surfaces in navy.
export const colors = {
  sky: ['#8DB8F7', '#6A8CEB'] as const,
  primary: '#4C6FE6',
  primaryDark: '#3452C4',
  primarySoft: '#E6EEFF',
  background: '#EEF4FF',
  surface: '#FFFFFF',
  border: '#DCE6FA',
  text: '#14275F',
  textMuted: '#5C6B94',
  textOnPrimary: '#FFFFFF',
  glass: 'rgba(255,255,255,0.28)',
  glassBorder: 'rgba(255,255,255,0.55)',
  shadow: '#3B5BC9',
  recording: '#E5484D',
  danger: '#D64545',
  confidenceHigh: '#2E9E6B',
  confidenceMid: '#E0A030',
  confidenceLow: '#D64545',
} as const;
