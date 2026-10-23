import { Alert, Linking } from 'react-native';

/** Shown when a permission was permanently denied; the only fix is the Settings app. */
export function promptOpenSettings(title: string, message: string) {
  Alert.alert(title, message, [
    { text: 'Not now', style: 'cancel' },
    { text: 'Open Settings', onPress: () => void Linking.openSettings() },
  ]);
}
