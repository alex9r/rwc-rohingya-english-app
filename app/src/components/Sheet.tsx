import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, radius, shadow } from '@/theme';

/** White rounded sheet that rises over the gradient header. */
export function Sheet({ children }: { children: ReactNode }) {
  return <View style={styles.sheet}>{children}</View>;
}

const styles = StyleSheet.create({
  sheet: {
    flex: 1,
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    overflow: 'hidden',
    ...shadow.card,
  },
});
