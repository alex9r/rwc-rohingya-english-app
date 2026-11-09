import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BackButton } from '@/components/BackButton';
import { GradientScreen } from '@/components/GradientScreen';
import { PhrasePractice } from '@/components/PhrasePractice';
import { Sheet } from '@/components/Sheet';
import { colors, fonts, spacing } from '@/theme';

export default function PhrasesScreen() {
  const insets = useSafeAreaInsets();

  return (
    <GradientScreen>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <BackButton fallback="/learn" />
        <Text style={styles.title}>Phrase Practice</Text>
        <Text style={styles.subtitle}>Practice speaking everyday English phrases.</Text>
      </View>
      <Sheet>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]}>
          <PhrasePractice />
        </ScrollView>
      </Sheet>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl, gap: spacing.md },
  title: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  subtitle: { fontSize: fonts.size.md, color: '#FFFFFF', opacity: 0.9 },
  content: { paddingTop: spacing.md },
});
