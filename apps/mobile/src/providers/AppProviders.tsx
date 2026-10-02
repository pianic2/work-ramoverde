import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configureApiClient } from '@ramoverde/api-client';
import { ThemeProvider } from '@personal-library/react-native-components';
import type { PropsWithChildren } from 'react';
import { apiOrigin } from '../api-url';
import { readAccessToken, refreshSession } from '../auth/tokens';
import { secureThemeStorage } from '../theme-storage';

configureApiClient({
  baseUrl: apiOrigin(process.env.EXPO_PUBLIC_API_URL, __DEV__),
  accessToken: readAccessToken,
  refreshAccessToken: refreshSession,
});

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000 } },
});

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider persistTheme storage={secureThemeStorage} storageKey="ramoverde.theme">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}
