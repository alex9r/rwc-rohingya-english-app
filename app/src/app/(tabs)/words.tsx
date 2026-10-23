import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { Category, Word } from '@/api/types';
import { GradientScreen } from '@/components/GradientScreen';
import { IconButton } from '@/components/IconButton';
import { Segmented } from '@/components/Segmented';
import { Sheet } from '@/components/Sheet';
import { WordCard, WordRow } from '@/components/WordCard';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { useAppState } from '@/state/AppState';
import { colors, fonts, radius, spacing, TAB_BAR_SPACE, touch } from '@/theme';

type ViewMode = 'cards' | 'table';
const VIEW_OPTIONS = [
  { value: 'cards', label: 'Cards' },
  { value: 'table', label: 'Table' },
] as const;

/** Special filter value for the Saved chip (kept in the URL: /words?category=saved). */
const SAVED = 'saved';

export default function WordsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ category?: string }>();
  // The filter lives in the URL so other screens (Learn) can deep-link into it.
  const filter = params.category || undefined;
  const showSaved = filter === SAVED;

  const [view, setView] = useState<ViewMode>('cards');
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetched, setFetched] = useState<Word[]>([]);
  const [voiceResults, setVoiceResults] = useState<Word[] | null>(null);
  const { saved, toggleSaved, progress } = useAppState();
  const { recording, toggle: toggleMic } = useRecorder();
  const play = usePlayAudio();

  useEffect(() => {
    api.getCategories().then(setCategories);
  }, []);

  useEffect(() => {
    let live = true;
    api
      .getWords({ categoryId: showSaved ? undefined : filter, query: deferredQuery })
      .then((w) => live && setFetched(w));
    return () => {
      live = false;
    };
  }, [filter, showSaved, deferredQuery]);

  const words = useMemo(() => {
    const base = voiceResults ?? fetched;
    return showSaved ? base.filter((w) => saved.has(w.id)) : base;
  }, [voiceResults, fetched, showSaved, saved]);

  const setFilter = useCallback(
    (value?: string) => {
      setVoiceResults(null);
      router.setParams({ category: value });
    },
    [router],
  );

  const onVoiceSearch = async () => {
    const uri = await toggleMic();
    if (uri) setVoiceResults(await api.searchWordByVoice(uri));
  };

  // Stable callbacks so memoized rows don't re-render when unrelated state changes.
  const onPlay = useCallback(
    (w: Word) => play({ url: w.audioUrl, fallbackText: w.english }),
    [play],
  );
  const onOpen = useCallback((w: Word) => router.push(`/word/${w.id}`), [router]);

  const wordScores = progress?.wordScores;
  const renderWord = useCallback(
    ({ item }: { item: Word }) => {
      const props = {
        word: item,
        saved: saved.has(item.id),
        score: wordScores?.[item.id],
        onToggleSave: toggleSaved,
        onPlay,
        onOpen,
      };
      return view === 'cards' ? <WordCard {...props} /> : <WordRow {...props} />;
    },
    [view, saved, wordScores, toggleSaved, onPlay, onOpen],
  );

  const chips = useMemo(
    () => [
      { id: '', name: 'All', icon: null },
      {
        id: SAVED,
        name: `Saved${saved.size ? ` (${saved.size})` : ''}`,
        icon: 'bookmark' as const,
      },
      ...categories.map((c) => ({ id: c.id, name: c.name, icon: null })),
    ],
    [categories, saved.size],
  );

  const emptyText = showSaved
    ? 'No saved words yet. Tap the bookmark on a word to save it here.'
    : 'No words found. Try another search.';

  return (
    <GradientScreen>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.title}>Words</Text>
        <View style={styles.searchRow}>
          <View style={styles.search}>
            <Ionicons name="search" size={20} color={colors.textMuted} />
            <TextInput
              style={styles.input}
              value={query}
              onChangeText={(t) => {
                setVoiceResults(null);
                setQuery(t);
              }}
              placeholder="Search English or Rohingyalish"
              placeholderTextColor={colors.textMuted}
              autoCorrect={false}
              returnKeyType="search"
              accessibilityLabel="Search words"
            />
          </View>
          <IconButton
            variant="glass"
            name={recording ? 'stop' : 'mic'}
            label={recording ? 'Stop voice search' : 'Search by voice'}
            active={recording}
            onPress={onVoiceSearch}
          />
        </View>
        <Segmented options={VIEW_OPTIONS} value={view} onChange={setView} />
      </View>

      <Sheet>
        {/* A plain horizontal ScrollView with a fixed row height: a horizontal FlatList here
            got squeezed to ~0 height by the vertical list below it (chips appeared cut off). */}
        <View style={styles.chipsWrap}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipsContent}
          >
            {chips.map((c) => {
              const active = (c.id || undefined) === filter;
              return (
                <Pressable
                  key={c.id || 'all'}
                  onPress={() => setFilter(c.id || undefined)}
                  style={[styles.chip, active && styles.chipActive]}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                >
                  {c.icon && (
                    <Ionicons name={c.icon} size={16} color={active ? '#FFFFFF' : colors.primary} />
                  )}
                  <Text style={[styles.chipText, active && styles.chipTextActive]}>{c.name}</Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>
        <FlatList
          key={view}
          style={styles.list}
          data={words}
          numColumns={view === 'cards' ? 2 : 1}
          keyExtractor={(w) => w.id}
          renderItem={renderWord}
          initialNumToRender={8}
          windowSize={7}
          removeClippedSubviews
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={[
            view === 'cards' && styles.grid,
            { paddingBottom: insets.bottom + TAB_BAR_SPACE + spacing.xl },
          ]}
          ListEmptyComponent={<Text style={styles.empty}>{emptyText}</Text>}
        />
      </Sheet>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl, gap: spacing.lg },
  title: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  search: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    height: touch,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: '#FFFFFF',
  },
  input: { flex: 1, fontSize: fonts.size.md, color: colors.text },
  // Fixed height + no shrink so the sibling list can never squash the chips.
  chipsWrap: { height: 44 + spacing.lg + spacing.md, flexShrink: 0 },
  chipsContent: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.sm,
    alignItems: 'center',
  },
  chip: {
    flexDirection: 'row',
    gap: spacing.xs,
    minHeight: 44,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipActive: { backgroundColor: colors.primary },
  chipText: { fontSize: fonts.size.sm, color: colors.primary, fontWeight: fonts.weight.bold },
  chipTextActive: { color: '#FFFFFF' },
  list: { flex: 1 },
  grid: { paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  empty: {
    textAlign: 'center',
    color: colors.textMuted,
    fontSize: fonts.size.md,
    marginTop: spacing.xxl,
    paddingHorizontal: spacing.xl,
  },
});
