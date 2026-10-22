import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { Animated, Pressable, StyleSheet, View } from 'react-native';
import { colors, shadow } from '@/theme';

interface Props {
  recording: boolean;
  onPress: () => void;
  size?: number;
  disabled?: boolean;
}

export function MicButton({ recording, onPress, size = 88, disabled }: Props) {
  const pulse = useState(() => new Animated.Value(0))[0];

  // Pulse only while recording (a response to the user's tap), on the native driver.
  useEffect(() => {
    if (!recording) {
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.timing(pulse, { toValue: 1, duration: 1200, useNativeDriver: true }),
    );
    loop.start();
    return () => loop.stop();
  }, [recording, pulse]);

  const ringStyle = {
    opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0] }),
    transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.6] }) }],
  };

  return (
    <View style={{ width: size, height: size }}>
      {recording && (
        <Animated.View
          pointerEvents="none"
          style={[styles.ring, { borderRadius: size / 2 }, ringStyle]}
        />
      )}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={recording ? 'Stop recording' : 'Start recording'}
        accessibilityState={{ disabled: !!disabled, busy: recording }}
        onPress={onPress}
        disabled={disabled}
        style={({ pressed }) => [
          styles.btn,
          { width: size, height: size, borderRadius: size / 2 },
          recording && styles.recording,
          pressed && { transform: [{ scale: 0.95 }] },
          disabled && { opacity: 0.5 },
        ]}
      >
        <Ionicons name={recording ? 'stop' : 'mic'} size={size * 0.42} color="#FFFFFF" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  btn: {
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: 'rgba(255,255,255,0.7)',
    ...shadow.glow,
  },
  recording: { backgroundColor: colors.recording },
  ring: { ...StyleSheet.absoluteFill, backgroundColor: colors.recording },
});
