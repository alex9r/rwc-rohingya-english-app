import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { Word } from '@/api/types';
import { colors, fonts, radius, shadow, spacing } from '@/theme';
import { IconButton } from './IconButton';

export interface WordItemProps {
  word: Word;
  saved: boolean;
  /** Best pronunciation score so far, if the word has been practiced. */
  score?: number;
  onToggleSave: (id: string) => void;
  onPlay: (word: Word) => void;
  onOpen: (word: Word) => void;
}

const rohingyaText = (w: Word) => w.rohingya ?? w.rohingyalish ?? 'Not translated yet';

function Thumb({ word, size }: { word: Word; size: number }) {
  return word.imageUrl ? (
    <Image
      source={{ uri: word.imageUrl }}
      style={{ width: size, height: size, borderRadius: size / 2 }}
      contentFit="cover"
      transition={150}
      cachePolicy="memory-disk"
      recyclingKey={word.id}
      accessibilityLabel={word.english}
    />
  ) : (
    <View style={[styles.thumb, { width: size, height: size, borderRadius: size / 2 }]}>
      <Ionicons name="image-outline" size={size * 0.4} color={colors.primary} />
    </View>
  );
}

function PracticePill({ score }: { score?: number }) {
  const done = score !== undefined;
  return (
    <View style={[styles.pill, done && styles.pillDone]}>
      <Ionicons
        name={done ? 'checkmark-circle' : 'mic'}
        size={18}
        color={done ? colors.confidenceHigh : colors.primary}
      />
      <Text style={[styles.pillText, done && { color: colors.text }]}>
        {done ? `Best ${score}` : 'Practice'}
      </Text>
    </View>
  );
}

// Open-area Pressables and IconButtons are siblings, never nested: on web each renders
// as a <button>, and nested buttons are invalid HTML (React warns / breaks hydration).
function WordCardBase({ word, saved, score, onToggleSave, onPlay, onOpen }: WordItemProps) {
  const open = () => onOpen(word);
  const openLabel = `Practice saying ${word.english}`;
  return (
    <View style={styles.card}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={openLabel}
        onPress={open}
        style={({ pressed }) => [styles.openArea, pressed && { opacity: 0.85 }]}
      >
        <Thumb word={word} size={88} />
        <Text style={styles.rohingya}>{rohingyaText(word)}</Text>
        <Text style={styles.english}>{word.english}</Text>
      </Pressable>
      <View style={styles.actions}>
        <IconButton
          name="volume-high"
          label={`Play ${word.english}`}
          onPress={() => onPlay(word)}
        />
        <IconButton
          name={saved ? 'bookmark' : 'bookmark-outline'}
          label={saved ? `Unsave ${word.english}` : `Save ${word.english}`}
          active={saved}
          onPress={() => onToggleSave(word.id)}
        />
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel={openLabel} onPress={open}>
        <PracticePill score={score} />
      </Pressable>
    </View>
  );
}

function WordRowBase({ word, saved, score, onToggleSave, onPlay, onOpen }: WordItemProps) {
  return (
    <View style={styles.row}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Practice saying ${word.english}`}
        onPress={() => onOpen(word)}
        style={styles.rowOpen}
      >
        <Thumb word={word} size={48} />
        <View style={styles.rowText}>
          <Text style={styles.rowRohingya}>{rohingyaText(word)}</Text>
          <Text style={styles.rowEnglish}>
            {word.english}
            {score !== undefined ? `  ·  Best ${score}` : ''}
          </Text>
        </View>
      </Pressable>
      <IconButton
        name="volume-high"
        label={`Play ${word.english}`}
        onPress={() => onPlay(word)}
        size={22}
      />
      <IconButton
        name={saved ? 'bookmark' : 'bookmark-outline'}
        label={saved ? `Unsave ${word.english}` : `Save ${word.english}`}
        active={saved}
        onPress={() => onToggleSave(word.id)}
        size={22}
      />
    </View>
  );
}

// Memoized: with stable callbacks, toggling one word re-renders only that item.
export const WordCard = memo(WordCardBase);
export const WordRow = memo(WordRowBase);

const styles = StyleSheet.create({
  card: {
    flex: 1,
    margin: spacing.sm,
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    alignItems: 'center',
    gap: spacing.xs,
    ...shadow.card,
  },
  openArea: { alignItems: 'center', gap: spacing.xs, alignSelf: 'stretch' },
  thumb: { backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  rohingya: {
    fontSize: fonts.size.lg,
    fontWeight: fonts.weight.bold,
    color: colors.text,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  english: { fontSize: fonts.size.md, color: colors.textMuted },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
    minHeight: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
  },
  pillDone: { backgroundColor: '#E3F6EC' },
  pillText: { fontSize: fonts.size.sm, fontWeight: fonts.weight.bold, color: colors.primary },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowOpen: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  rowText: { flex: 1 },
  rowRohingya: { fontSize: fonts.size.md, fontWeight: fonts.weight.bold, color: colors.text },
  rowEnglish: { fontSize: fonts.size.sm, color: colors.textMuted },
});
