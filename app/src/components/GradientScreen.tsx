import { LinearGradient } from 'expo-linear-gradient';
import { ReactNode } from 'react';
import { StyleSheet } from 'react-native';
import { colors } from '@/theme';

export function GradientScreen({ children }: { children: ReactNode }) {
  return (
    <LinearGradient colors={colors.sky} style={styles.fill}>
      {children}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({ fill: { flex: 1 } });
