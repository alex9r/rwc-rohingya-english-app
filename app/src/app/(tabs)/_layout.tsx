import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import type { ColorValue } from 'react-native';
import { colors, fonts } from '@/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

function TabIcon({ name, color, size }: { name: IconName; color: ColorValue; size: number }) {
  return <Ionicons name={name} color={color as string} size={size} />;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarLabelStyle: { fontSize: fonts.size.sm, fontWeight: fonts.weight.medium },
        tabBarStyle: { height: 64, paddingTop: 6, backgroundColor: colors.surface },
        headerStyle: { backgroundColor: colors.background },
        headerTitleStyle: { color: colors.text },
        headerShadowVisible: false,
        sceneStyle: { backgroundColor: colors.background },
      }}
    >
      <Tabs.Screen
        name="speak"
        options={{ title: 'Speak', tabBarIcon: (p) => <TabIcon name="mic" {...p} /> }}
      />
      <Tabs.Screen
        name="words"
        options={{ title: 'Words', tabBarIcon: (p) => <TabIcon name="book" {...p} /> }}
      />
      <Tabs.Screen
        name="scenario"
        options={{ title: 'Scenario', tabBarIcon: (p) => <TabIcon name="chatbubbles" {...p} /> }}
      />
    </Tabs>
  );
}
