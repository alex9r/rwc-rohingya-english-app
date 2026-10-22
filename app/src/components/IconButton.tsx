import { Ionicons } from '@expo/vector-icons';
import { ComponentProps } from 'react';
import { Pressable, StyleSheet } from 'react-native';
import { colors, touch } from '@/theme';

type Variant = 'soft' | 'glass' | 'solid';

interface Props {
  name: ComponentProps<typeof Ionicons>['name'];
  label: string;
  onPress: () => void;
  active?: boolean;
  disabled?: boolean;
  size?: number;
  variant?: Variant;
}

export function IconButton({
  name,
  label,
  onPress,
  active,
  disabled,
  size = 24,
  variant = 'soft',
}: Props) {
  const onGradient = variant === 'glass';
  const filled = variant === 'solid' || (variant === 'soft' && active);
  const iconColor = filled
    ? colors.textOnPrimary
    : onGradient && !active
      ? '#FFFFFF'
      : colors.primary;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled, selected: !!active }}
      onPress={onPress}
      disabled={disabled}
      hitSlop={6}
      android_ripple={{ color: 'rgba(255,255,255,0.3)', radius: touch / 2 }}
      style={({ pressed }) => [
        styles.btn,
        variant === 'soft' && styles.soft,
        onGradient && styles.glass,
        onGradient && active && styles.glassActive,
        filled && styles.filled,
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
    >
      <Ionicons name={name} size={size} color={iconColor} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: touch,
    height: touch,
    borderRadius: touch / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  soft: { backgroundColor: colors.primarySoft },
  glass: { backgroundColor: colors.glass, borderWidth: 1, borderColor: colors.glassBorder },
  glassActive: { backgroundColor: '#FFFFFF' },
  filled: { backgroundColor: colors.primary },
  pressed: { transform: [{ scale: 0.94 }], opacity: 0.9 },
  disabled: { opacity: 0.4 },
});
