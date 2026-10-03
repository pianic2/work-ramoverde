# Mobile instructions

Before creating a generic React Native UI primitive, inspect `@personal-library/react-native-components` first. It is the canonical mobile UI layer, a required dependency, and must be visibly used by app screens.

Use its documented public root exports only. Do not import private paths, copy source, vendor components, patch node_modules, or recreate generic buttons, text, layout, cards, inputs, feedback, tokens, themes or providers it already supplies. Compose existing library components; add a thin adapter only for application behavior. Local domain components are appropriate for product concepts. If a generic primitive is missing, add only the minimum app-specific fallback and document it as a library improvement candidate.

Use generated `@ramoverde/api-client`, Expo Router and TanStack Query. Keep native secrets in Expo SecureStore through the auth boundary. Do not introduce a competing design system or put RN UI in `packages/shared`. Validate with typecheck, a representative library render test, Expo Doctor and `expo export` when available.
