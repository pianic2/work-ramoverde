# Mobile UI ownership

`@personal-library/react-native-components` is the canonical reusable native UI layer. It is a real dependency and is used on the home and account routes. The current selected release is `0.1.0-rc.2` from the intentional `rc` distribution tag. It peers on React `>=19.2.3 <20.0.0` and React Native `>=0.86.0 <0.87.0`; Expo SDK 57's compatible baseline is React 19.2.3 and RN 0.86.3.

The package has a root-only public export map. It documents `ThemeProvider`, `ThemeAppShell`, `Box`, `Column`, `Text`, `Heading`, `Button`, `Card`, `Input` and other components as beta public candidates; stable promotions are not assumed. This template uses root exports only. App screens compose `Column`, `Box`, `Text`, `Heading` and `Button`; `ThemeProvider` is initialized in `AppProviders`. SecureStore backs theme persistence using the package's public `ThemeStorageAdapter` boundary.

Generic reusable native primitives belong in the personal library. Product/domain components belong in the generated app. Before UI work, inspect the installed package metadata, peer ranges, root types and consumer docs. Prefer reuse, then composition, then a thin behavioral adapter. A missing generic primitive should get only a minimal app-specific fallback plus an improvement note for the library maintainers.

Upgrade by choosing a published stable library release when available. Confirm its peers, inspect changelog/docs/public exports, align Expo/RN/React using Expo's SDK compatibility map, install SDK-compatible modules via `npx expo install`, then run `expo-doctor`, package peer checks, mobile render tests and `expo export`. Never deep-import internals or copy the library into the template. The explicit RC exception ends when a compatible stable library release exists.
