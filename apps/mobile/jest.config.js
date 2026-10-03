const path = require('node:path');
const libraryPackageJsonPath = require.resolve('@personal-library/react-native-components/package.json');
const libraryPackage = require(libraryPackageJsonPath);
const libraryPublicEntry = path.resolve(
  path.dirname(libraryPackageJsonPath),
  libraryPackage.exports['.'].import,
);

module.exports = {
  preset: 'jest-expo',
  testMatch: ['**/tests/**/*.test.ts?(x)'],
  transformIgnorePatterns: [
    '/node_modules/(?!(.pnpm|react-native|@react-native|@react-native-community|expo|@expo|@expo-google-fonts|react-navigation|@react-navigation|@sentry/react-native|native-base|standard-navigation|@personal-library))',
    '/node_modules/react-native-reanimated/plugin/',
    '/node_modules/@react-native/babel-preset/',
  ],
  moduleNameMapper: {
    '^@personal-library/react-native-components$': libraryPublicEntry,
  },
};
