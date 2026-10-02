import * as SecureStore from 'expo-secure-store';
import type { ThemeStorageAdapter } from '@personal-library/react-native-components';

export const secureThemeStorage: ThemeStorageAdapter = {
  getItem: (key) => SecureStore.getItemAsync(key),
  setItem: (key, value) => SecureStore.setItemAsync(key, value),
  removeItem: (key) => SecureStore.deleteItemAsync(key),
};
