import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { Category, Scenario } from '@/api/types';
import { categoryIcon } from '@/components/categoryIcon';
import { GradientScreen } from '@/components/GradientScreen';
import { ProgressBar } from '@/components/ProgressBar';
import { Sheet } from '@/components/Sheet';
import { useAppState } from '@/state/AppState';
import { colors, fonts, radius, shadow, spacing, TAB_BAR_SPACE } from '@/theme';

/** Landing: pick a situation (category) before choosing a specific scenario. */
export default function ScenarioLanding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { progress } = useAppState();
  const [categories, setCategories] = useState<Category[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);

  useEffect(() => {
    api.getCategories().then(setCategories);
    api.getScenarios().then(setScenarios);
  }, []);

  const withScenarios = categories.filter((c) => scenarios.some((s) => s.categoryId === c.id));

  return (
    <GradientScreen>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.title}>Practice a situation</Text>
        <Text style={styles.sub}>Pick a topic, then talk it through.</Text>
      </View>
      <Sheet>
        <FlatList
          data={withScenarios}
          numColumns={2}
          keyExtractor={(c) => c.id}
          contentContainerStyle={[
            styles.grid,
            { paddingBottom: insets.bottom + TAB_BAR_SPACE + spacing.xl },
          ]}
          renderItem={({ item }) => {
            const total = scenarios.filter((s) => s.categoryId === item.id).length;
            const done =
              progress?.categories.find((c) => c.categoryId === item.id)?.scenariosDone ?? 0;
            return (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${item.name}, ${done} of ${total} scenarios done`}
                onPress={() => router.push(`/scenario/category/${item.id}`)}
                style={({ pressed }) => [styles.card, pressed && { opacity: 0.92 }]}
              >
                <View style={styles.icon}>
                  <Ionicons name={categoryIcon(item.id)} size={32} color={colors.primary} />
                </View>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.meta}>
                  {total} {total === 1 ? 'scenario' : 'scenarios'}
                </Text>
                <ProgressBar value={total ? done / total : 0} />
              </Pressable>
            );
          }}
        />
      </Sheet>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl, gap: spacing.sm },
  title: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  sub: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: '#FFFFFF', opacity: 0.9 },
  grid: { padding: spacing.md, paddingTop: spacing.xl },
  card: {
    flex: 1,
    margin: spacing.sm,
    padding: spacing.lg,
    gap: spacing.sm,
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    ...shadow.card,
  },
  icon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: {
    fontSize: fonts.size.md,
    fontWeight: fonts.weight.bold,
    color: colors.text,
    textAlign: 'center',
  },
  meta: { fontSize: fonts.size.sm, color: colors.textMuted },
});
