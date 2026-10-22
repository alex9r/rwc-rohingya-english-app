import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { Category, Scenario } from '@/api/types';
import { BackButton } from '@/components/BackButton';
import { GradientScreen } from '@/components/GradientScreen';
import { Sheet } from '@/components/Sheet';
import { useAppState } from '@/state/AppState';
import { colors, fonts, radius, spacing, TAB_BAR_SPACE } from '@/theme';

export default function ScenarioCategory() {
  const { categoryId } = useLocalSearchParams<{ categoryId: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { progress } = useAppState();
  const [category, setCategory] = useState<Category | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);

  useEffect(() => {
    api.getCategories().then((all) => setCategory(all.find((c) => c.id === categoryId) ?? null));
    api.getScenarios(categoryId).then(setScenarios);
  }, [categoryId]);

  return (
    <GradientScreen>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <BackButton fallback="/scenario" />
        <Text style={styles.title}>{category?.name ?? 'Scenarios'}</Text>
        {category && <Text style={styles.sub}>{category.description}</Text>}
      </View>
      <Sheet>
        <FlatList
          data={scenarios}
          keyExtractor={(s) => s.id}
          contentContainerStyle={[
            styles.list,
            { paddingBottom: insets.bottom + TAB_BAR_SPACE + spacing.xl },
          ]}
          renderItem={({ item }) => {
            const done = progress?.completedScenarioIds.includes(item.id);
            return (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${item.title}${done ? ', completed' : ''}`}
                onPress={() => router.push(`/scenario/${item.id}`)}
                style={({ pressed }) => [styles.row, pressed && { opacity: 0.92 }]}
              >
                <View style={[styles.badge, done && styles.badgeDone]}>
                  <Ionicons
                    name={done ? 'checkmark' : 'chatbubble-ellipses'}
                    size={24}
                    color={done ? '#FFFFFF' : colors.primary}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{item.title}</Text>
                  <Text style={styles.meta}>
                    {item.turns.length} steps{done ? '  ·  Completed' : ''}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={22} color={colors.textMuted} />
              </Pressable>
            );
          }}
        />
      </Sheet>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xl,
    gap: spacing.md,
    alignItems: 'flex-start',
  },
  title: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  sub: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: '#FFFFFF', opacity: 0.9 },
  list: { padding: spacing.xl, gap: spacing.md },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  badge: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeDone: { backgroundColor: colors.confidenceHigh },
  name: { fontSize: fonts.size.md, fontWeight: fonts.weight.bold, color: colors.text },
  meta: { fontSize: fonts.size.sm, color: colors.textMuted },
});
