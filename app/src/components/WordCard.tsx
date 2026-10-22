import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { Word } from '@/api/types';
import { colors, fonts, radius, shadow, spacing } from '@/theme';
import { IconButton } from './IconButton';

export interface WordItemProps {
  word: Word;
  saved: boolean;
  onToggleSave: (id: string) => void;
  onPlay: (word: Word) => void;
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

function WordCardBase({ word, saved, onToggleSave, onPlay }: WordItemProps) {
  return (
    <View style={styles.card}>
      <Thumb word={word} size={88} />
      <Text style={styles.rohingya}>{rohingyaText(word)}</Text>
      <Text style={styles.english}>{word.english}</Text>
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
    </View>
  );
}

function WordRowBase({ word, saved, onToggleSave, onPlay }: WordItemProps) {
  return (
    <View style={styles.row}>
      <Thumb word={word} size={48} />
      <View style={styles.rowText}>
        <Text style={styles.rowRohingya}>{rohingyaText(word)}</Text>
        <Text style={styles.rowEnglish}>{word.english}</Text>
      </View>
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowText: { flex: 1 },
  rowRohingya: { fontSize: fonts.size.md, fontWeight: fonts.weight.bold, color: colors.text },
  rowEnglish: { fontSize: fonts.size.sm, color: colors.textMuted },
});
