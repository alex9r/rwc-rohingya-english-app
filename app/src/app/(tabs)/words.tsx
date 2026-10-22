import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { api } from '@/api/client';
import type { Category, Word } from '@/api/types';
import { IconButton } from '@/components/IconButton';
import { Segmented } from '@/components/Segmented';
import { WordCard, WordRow } from '@/components/WordCard';
import { useRecorder } from '@/hooks/useRecorder';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useSavedWords } from '@/hooks/useSavedWords';
import { colors, fonts, radius, spacing } from '@/theme';

type View_ = 'cards' | 'table';

export default function WordsScreen() {
  const [view, setView] = useState<View_>('cards');
  const [query, setQuery] = useState('');
  const [categoryId, setCategoryId] = useState<string | undefined>();
  const [categories, setCategories] = useState<Category[]>([]);
  const [words, setWords] = useState<Word[]>([]);
  const { saved, toggle } = useSavedWords();
  const { recording, toggle: toggleMic } = useRecorder();
  const play = usePlayAudio();

  useEffect(() => {
    api.getCategories().then(setCategories);
  }, []);

  useEffect(() => {
    let live = true;
    api.getWords({ categoryId, query }).then((w) => live && setWords(w));
    return () => {
      live = false;
    };
  }, [categoryId, query]);

  const onVoiceSearch = async () => {
    const uri = await toggleMic();
    if (uri) setWords(await api.searchWordByVoice(uri));
  };

  const renderWord = (word: Word) => {
    const props = {
      word,
      saved: saved.has(word.id),
      onToggleSave: () => toggle(word.id),
      onPlay: () => play({ url: word.audioUrl, fallbackText: word.english }),
    };
    return view === 'cards' ? <WordCard {...props} /> : <WordRow {...props} />;
  };

  return (
    <View style={styles.container}>
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
          />
        </View>
        <IconButton
          name={recording ? 'stop' : 'mic'}
          label="Search by voice"
          active={recording}
          onPress={onVoiceSearch}
        />
      </View>

      <View style={styles.pad}>
        <Segmented
          options={[
            { value: 'cards', label: 'Cards' },
            { value: 'table', label: 'Table' },
          ]}
          value={view}
          onChange={setView}
        />
      </View>

      <FlatList
        horizontal
        data={[{ id: '', name: 'All' } as Category, ...categories]}
        keyExtractor={(c) => c.id || 'all'}
        showsHorizontalScrollIndicator={false}
        style={styles.chips}
        contentContainerStyle={styles.chipsContent}
        renderItem={({ item }) => {
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
        }}
      />

      <FlatList
        key={view}
        data={words}
        numColumns={view === 'cards' ? 2 : 1}
        keyExtractor={(w) => w.id}
        renderItem={({ item }) => renderWord(item)}
        contentContainerStyle={view === 'cards' ? styles.grid : undefined}
        ListEmptyComponent={<Text style={styles.empty}>No words found.</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: spacing.xxl * 1.5 },
  pad: { paddingHorizontal: spacing.lg, marginBottom: spacing.sm },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  search: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    height: 48,
  },
  input: { flex: 1, fontSize: fonts.size.md, color: colors.text },
  chips: { flexGrow: 0 },
  chipsContent: { paddingHorizontal: spacing.lg, gap: spacing.sm, paddingBottom: spacing.sm },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: fonts.size.sm, color: colors.text },
  chipTextActive: { color: colors.textOnPrimary, fontWeight: fonts.weight.bold },
  grid: { paddingHorizontal: spacing.md },
  empty: { textAlign: 'center', color: colors.textMuted, marginTop: spacing.xl },
});
