import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts, radius, spacing, touch } from '@/theme';

interface LoadStateProps {
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  message?: string;
}

/** Shared, accessible request status for screens that load API data. */
export function LoadState({ loading = false, error, onRetry, message = 'Loading…' }: LoadStateProps) {
  if (!loading && !error) return null;
  return (
    <View style={styles.container} accessibilityRole="summary">
      {loading ? (
        <>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.text}>{message}</Text>
        </>
      ) : (
        <>
          <Text style={styles.title}>Something went wrong</Text>
          <Text style={styles.text}>{error}</Text>
          {onRetry && (
            <Pressable accessibilityRole="button" onPress={onRetry} style={styles.button}>
              <Text style={styles.buttonText}>Try again</Text>
            </Pressable>
          )}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.xl },
  title: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: colors.text, textAlign: 'center' },
  text: { fontSize: fonts.size.md, color: colors.textMuted, textAlign: 'center' },
  button: { minHeight: touch, justifyContent: 'center', paddingHorizontal: spacing.xl, borderRadius: radius.pill, backgroundColor: colors.primary },
  buttonText: { color: '#FFFFFF', fontWeight: fonts.weight.bold, textAlign: 'center' },
});
