import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';
import type { Word } from '@/api/types';
import { colors, fonts, radius, spacing } from '@/theme';
import { IconButton } from './IconButton';

export interface WordItemProps {
  word: Word;
  saved: boolean;
  onToggleSave: () => void;
  onPlay: () => void;
}

const rohingyaText = (w: Word) => w.rohingya ?? w.rohingyalish ?? '— not translated yet —';

function Thumb({ word, size }: { word: Word; size: number }) {
  return word.imageUrl ? (
    <Image
      source={{ uri: word.imageUrl }}
      style={{ width: size, height: size, borderRadius: radius.md }}
    />
  ) : (
    <View style={[styles.thumb, { width: size, height: size }]}>
      <Ionicons name="image-outline" size={size * 0.4} color={colors.textMuted} />
    </View>
  );
}

export function WordCard({ word, saved, onToggleSave, onPlay }: WordItemProps) {
  return (
    <View style={styles.card}>
      <Thumb word={word} size={96} />
      <Text style={styles.rohingya}>{rohingyaText(word)}</Text>
      <Text style={styles.english}>{word.english}</Text>
      <View style={styles.actions}>
        <IconButton name="volume-high" label={`Play ${word.english}`} onPress={onPlay} />
        <IconButton
          name={saved ? 'bookmark' : 'bookmark-outline'}
          label={saved ? 'Unsave word' : 'Save word'}
          active={saved}
          onPress={onToggleSave}
        />
      </View>
    </View>
  );
}

export function WordRow({ word, saved, onToggleSave, onPlay }: WordItemProps) {
  return (
    <View style={styles.row}>
      <Thumb word={word} size={48} />
      <View style={styles.rowText}>
        <Text style={styles.rowRohingya}>{rohingyaText(word)}</Text>
        <Text style={styles.rowEnglish}>{word.english}</Text>
      </View>
      <IconButton name="volume-high" label={`Play ${word.english}`} onPress={onPlay} size={22} />
      <IconButton
        name={saved ? 'bookmark' : 'bookmark-outline'}
        label={saved ? 'Unsave word' : 'Save word'}
        active={saved}
        onPress={onToggleSave}
        size={22}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    margin: spacing.xs,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    alignItems: 'center',
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  thumb: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rohingya: {
    fontSize: fonts.size.lg,
    fontWeight: fonts.weight.bold,
    color: colors.text,
    textAlign: 'center',
  },
  english: { fontSize: fonts.size.md, color: colors.textMuted },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  rowText: { flex: 1 },
  rowRohingya: { fontSize: fonts.size.md, fontWeight: fonts.weight.bold, color: colors.text },
  rowEnglish: { fontSize: fonts.size.sm, color: colors.textMuted },
});
