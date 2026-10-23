# Expo / React Native review: `app/` skeleton

Run against commit `7f63249` using `javascript-react-native-expo-reviewer`, `expo-react-native-performance`,
`frontend-design` and `mobile-app-ui-design`. Fixes landed in the commit after it.

## Fixed

| ID | Severity | Finding | Fix |
|---|---|---|---|
| RN-MEMO / list-memoize-items | HIGH | `WordCard`/`WordRow` re-rendered on every parent state change; `renderItem` and handlers were recreated each render, and `onPress` closures captured the item. | `memo()` on both; `renderItem`/`renderChip` in `useCallback`; callbacks take the id/word (`onToggleSave(id)`, `onPlay(word)`) so references stay stable. |
| RN-JANK | HIGH | Search hit the (future) API on every keystroke, synchronously. | `useDeferredValue(query)` drives the fetch; stale responses are dropped. |
| RN-FLATLIST | MEDIUM | No windowing hints. | `initialNumToRender`, `windowSize`, `removeClippedSubviews`, `keyboardShouldPersistTaps`. `getItemLayout` skipped: card heights vary with text. |
| RN-PERMISSIONS | HIGH | Camera/mic denial showed a dead-end alert; camera always re-requested. | Check existing status first; permanently denied -> "Open Settings" prompt (`utils/permissions.ts`). |
| EXPO-PLUGINS | HIGH | Permission strings hand-written in `infoPlist`. | Moved to `expo-audio` / `expo-image-picker` plugin config; `infoPlist` removed. |
| ERROR-BOUNDARY | HIGH | A render error would white-screen the app. | Expo Router `ErrorBoundary` export in the root layout with a retry button. |
| ERROR-NETWORK | MEDIUM | Translate calls had no failure path; busy spinner could stick. | `try/catch/finally` around the calls with an alert. Recorder start/stop also wrapped. |
| RN-SAFEAREA | HIGH | Hard-coded `paddingTop` (`spacing * 1.5`) for the notch. | `useSafeAreaInsets()` everywhere; bottom inset feeds the floating tab bar spacing. |
| RN-ANIMATION | HIGH | n/a (new motion) | Mic pulse and orb breathing use `Animated` with `useNativeDriver: true`, and run only while recording. |
| RN-PRESSABLE | MEDIUM | No press feedback. | Pressed scale/opacity, `android_ripple`, `accessibilityState` (disabled/selected/busy). |
| RN-IMAGE | HIGH | `expo-image` used without caching hints. | `cachePolicy="memory-disk"`, `recyclingKey`, `transition`, accessibility label. |
| RN-ACCESSIBILITY | HIGH | Save/play labels were generic. | Labels include the word ("Save Doctor"). Decorative orb hidden from screen readers. |
| mem-cleanup | MEDIUM | TTS could keep talking after leaving a screen. | `Speech.stop()` before each play and on unmount. |
| RN-TOUCH | MEDIUM | Filter chips and segmented items were 40px, below the 44pt minimum. | Both raised to 44px; icon buttons stay 48px. |

## Deliberately not changed

- **list-use-flashlist**: lists hold ~12 mock words. Switch to FlashList when the real dictionary lands (100+ words).
- **EXPO-CONFIG (`app.config.js`)** / **EAS-BUILD** / **EAS-UPDATE** / **Sentry**: no env-specific config, builds or release pipeline yet. Revisit when the backend URL exists.
- **STATE-QUERY / STATE-PERSIST**: saved words are in memory; add React Query + persistence with the real API.
- **NAV-TYPES**: Expo Router typed routes can be enabled once there are params.
- **expo-ui**: iOS-only SwiftUI; app targets iOS and Android.
- **Custom font**: system font for now. Pick one with Hanifi Rohingya glyph coverage first.

## Design pass (frontend-design + mobile-app-ui-design)

Reference: the screenshot added to the repo (periwinkle gradient, white sheets, frosted circle buttons, glossy orb,
floating pill nav), adapted to **light blue + white**.

- **Palette (60/30/10):** white / light-blue surfaces as the base, navy text, `#4C6FE6` as the accent (CTAs, mic, active states). Shadows are blue-tinted, not grey.
- **Contrast:** white text only on the gradient and only large + bold (>= 22px). Small text is navy on white.
- **Type:** 4 sizes (14/16/22/32), 2 weights. **Spacing:** 4/8 grid.
- **Layout:** gradient hero + white sheet (Words, Scenario); gradient hero + white control card (Speak), mic in the thumb zone; floating icon-first tab bar whose active tab shows its label.
- **Peak moment:** the Speak result, with big white translation, confidence badge and one-tap read/replay/save.
- **Empty state:** Words empty list now tells the user what to do.
