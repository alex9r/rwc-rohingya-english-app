import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useState } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { colors } from '@/theme';

/** Glossy decorative orb. Breathes gently only while `active` (recording). */
export function Orb({ active, size = 168 }: { active: boolean; size?: number }) {
  const scale = useState(() => new Animated.Value(1))[0];

  useEffect(() => {
    if (!active) {
      scale.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(scale, { toValue: 1.08, duration: 900, useNativeDriver: true }),
        Animated.timing(scale, { toValue: 1, duration: 900, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [active, scale]);

  return (
    <Animated.View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        styles.halo,
        { width: size + 32, height: size + 32, borderRadius: size, transform: [{ scale }] },
      ]}
    >
      <LinearGradient
        colors={['#FFFFFF', '#D5E4FF', '#A9C3F8']}
        start={{ x: 0.2, y: 0.05 }}
        end={{ x: 0.85, y: 1 }}
        style={{ width: size, height: size, borderRadius: size / 2 }}
      />
      <View
        style={[
          styles.gloss,
          { width: size * 0.34, height: size * 0.2, top: size * 0.2, left: size * 0.3 },
        ]}
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  halo: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.22)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  gloss: {
    position: 'absolute',
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.8)',
    transform: [{ rotate: '-25deg' }],
  },
});
