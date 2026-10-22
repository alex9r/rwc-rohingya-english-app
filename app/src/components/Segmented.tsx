import { Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts, radius, spacing } from '@/theme';

interface Props<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}

export function Segmented<T extends string>({ options, value, onChange }: Props<T>) {
  return (
    <View style={styles.wrap}>
      {options.map((o) => (
        <Pressable
          key={o.value}
          accessibilityRole="button"
          accessibilityState={{ selected: o.value === value }}
          onPress={() => onChange(o.value)}
          style={[styles.item, o.value === value && styles.active]}
        >
          <Text style={[styles.text, o.value === value && styles.activeText]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    backgroundColor: colors.primarySoft,
    borderRadius: radius.pill,
    padding: 3,
  },
  item: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.pill, alignItems: 'center' },
  active: { backgroundColor: colors.primary },
  text: { fontSize: fonts.size.sm, fontWeight: fonts.weight.medium, color: colors.primary },
  activeText: { color: colors.textOnPrimary },
});
