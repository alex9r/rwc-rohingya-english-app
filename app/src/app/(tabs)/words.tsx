import { Ionicons } from '@expo/vector-icons';
import { useCallback, useDeferredValue, useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
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
import { useSavedWords } from '@/hooks/useSavedWords';
import { colors, fonts, radius, spacing, TAB_BAR_SPACE, touch } from '@/theme';

type ViewMode = 'cards' | 'table';
const VIEW_OPTIONS = [
  { value: 'cards', label: 'Cards' },
  { value: 'table', label: 'Table' },
] as const;
const ALL: Category = { id: '', name: 'All', description: '' };

export default function WordsScreen() {
  const insets = useSafeAreaInsets();
  const [view, setView] = useState<ViewMode>('cards');
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);
  const [categoryId, setCategoryId] = useState<string | undefined>();
  const [categories, setCategories] = useState<Category[]>([ALL]);
  const [words, setWords] = useState<Word[]>([]);
  const { saved, toggle } = useSavedWords();
  const { recording, toggle: toggleMic } = useRecorder();
  const play = usePlayAudio();

  useEffect(() => {
    api.getCategories().then((c) => setCategories([ALL, ...c]));
  }, []);

  useEffect(() => {
    let live = true;
    api.getWords({ categoryId, query: deferredQuery }).then((w) => live && setWords(w));
    return () => {
      live = false;
    };
  }, [categoryId, deferredQuery]);

  const onVoiceSearch = async () => {
    const uri = await toggleMic();
    if (uri) setWords(await api.searchWordByVoice(uri));
  };

  // Stable callbacks so memoized rows don't re-render when unrelated state changes.
  const onPlay = useCallback(
    (w: Word) => play({ url: w.audioUrl, fallbackText: w.english }),
    [play],
  );

  const renderWord = useCallback(
    ({ item }: { item: Word }) => {
      const props = { word: item, saved: saved.has(item.id), onToggleSave: toggle, onPlay };
      return view === 'cards' ? <WordCard {...props} /> : <WordRow {...props} />;
    },
    [view, saved, toggle, onPlay],
  );

  const renderChip = useCallback(
    ({ item }: { item: Category }) => {
      const active = (item.id || undefined) === categoryId;
      return (
        <Pressable
          onPress={() => setCategoryId(item.id || undefined)}
          style={[styles.chip, active && styles.chipActive]}
          accessibilityRole="button"
          accessibilityState={{ selected: active }}
        >
          <Text style={[styles.chipText, active && styles.chipTextActive]}>{item.name}</Text>
        </Pressable>
      );
    },
    [categoryId],
  );

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
              onChangeText={setQuery}
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
        <Segmented options={VIEW_OPTIONS as never} value={view} onChange={setView} />
      </View>

      <Sheet>
        <FlatList
          horizontal
          data={categories}
          keyExtractor={(c) => c.id || 'all'}
          renderItem={renderChip}
          showsHorizontalScrollIndicator={false}
          style={styles.chips}
          contentContainerStyle={styles.chipsContent}
        />
        <FlatList
          key={view}
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
          ListEmptyComponent={<Text style={styles.empty}>No words found. Try another search.</Text>}
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
  chips: { flexGrow: 0, marginTop: spacing.lg },
  chipsContent: { paddingHorizontal: spacing.xl, gap: spacing.sm, paddingBottom: spacing.md },
  chip: {
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
  grid: { paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  empty: {
    textAlign: 'center',
    color: colors.textMuted,
    fontSize: fonts.size.md,
    marginTop: spacing.xxl,
  },
});
