import { Ionicons } from '@expo/vector-icons';
import { ComponentProps } from 'react';
import { Pressable, StyleSheet } from 'react-native';
import { colors, touch } from '@/theme';

interface Props {
  name: ComponentProps<typeof Ionicons>['name'];
  label: string;
  onPress: () => void;
  active?: boolean;
  disabled?: boolean;
  size?: number;
}

export function IconButton({ name, label, onPress, active, disabled, size = 26 }: Props) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled}
      hitSlop={6}
      style={[styles.btn, active && styles.active, disabled && { opacity: 0.4 }]}
    >
      <Ionicons name={name} size={size} color={active ? colors.textOnPrimary : colors.primary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: touch - 8,
    height: touch - 8,
    borderRadius: (touch - 8) / 2,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  active: { backgroundColor: colors.primary },
});
