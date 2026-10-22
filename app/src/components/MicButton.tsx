import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet } from 'react-native';
import { colors, radius } from '@/theme';

interface Props {
  recording: boolean;
  onPress: () => void;
  size?: number;
  disabled?: boolean;
}

export function MicButton({ recording, onPress, size = 88, disabled }: Props) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={recording ? 'Stop recording' : 'Start recording'}
      onPress={onPress}
      disabled={disabled}
      style={[
        styles.btn,
        { width: size, height: size, borderRadius: size / 2 },
        recording && styles.recording,
        disabled && styles.disabled,
      ]}
    >
      <Ionicons name={recording ? 'stop' : 'mic'} size={size * 0.45} color={colors.textOnPrimary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 3,
  },
  recording: { backgroundColor: colors.recording, borderRadius: radius.pill },
  disabled: { opacity: 0.5 },
});
