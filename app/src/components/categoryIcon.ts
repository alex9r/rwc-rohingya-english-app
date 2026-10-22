import type { Ionicons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';

type IconName = ComponentProps<typeof Ionicons>['name'];

const ICONS: Record<string, IconName> = {
  healthcare: 'medkit',
  education: 'school',
  housing: 'home',
  greetings: 'hand-left',
  transportation: 'bus',
  employment: 'briefcase',
  family: 'people',
};

export const categoryIcon = (id: string): IconName => ICONS[id] ?? 'apps';
