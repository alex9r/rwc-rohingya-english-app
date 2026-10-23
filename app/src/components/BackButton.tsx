import { useRouter } from 'expo-router';
import { IconButton } from './IconButton';

/** Glass back button for gradient headers. Falls back to `fallback` when there's no history (web reload). */
export function BackButton({
  fallback,
  icon = 'chevron-back',
}: {
  fallback: string;
  icon?: 'chevron-back' | 'close';
}) {
  const router = useRouter();
  return (
    <IconButton
      variant="glass"
      name={icon}
      label={icon === 'close' ? 'Close' : 'Go back'}
      onPress={() => (router.canGoBack() ? router.back() : router.replace(fallback as never))}
    />
  );
}
