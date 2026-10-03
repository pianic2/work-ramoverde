import {
  ApiError,
  postAuthToken,
  postAuthTokenLogout,
  postAuthTokenRefresh,
} from '@ramoverde/api-client';
import * as SecureStore from 'expo-secure-store';

const ACCESS_KEY = 'product.access-token';
const REFRESH_KEY = 'product.refresh-token';
let authGeneration = 0;
let tokenWrites: Promise<void> = Promise.resolve();
let refreshInFlight: { generation: number; promise: Promise<string | null> } | null = null;

function queueTokenWrite(action: () => Promise<void>): Promise<void> {
  const write = tokenWrites.then(action);
  tokenWrites = write.catch(() => undefined);
  return write;
}

function writeForCurrentSession(generation: number, action: () => Promise<void>): Promise<void> {
  return queueTokenWrite(() => (generation === authGeneration ? action() : Promise.resolve()));
}

export async function signIn(email: string, password: string): Promise<void> {
  const generation = ++authGeneration;
  const response = await postAuthToken({ email, password });
  const tokens = response.data;
  await writeForCurrentSession(generation, async () => {
    await SecureStore.setItemAsync(ACCESS_KEY, tokens.access);
    await SecureStore.setItemAsync(REFRESH_KEY, tokens.refresh);
  });
}

export function refreshSession(): Promise<string | null> {
  const generation = authGeneration;
  if (!refreshInFlight || refreshInFlight.generation !== generation) {
    const promise = rotateTokens(generation).finally(() => {
      if (refreshInFlight?.promise === promise) refreshInFlight = null;
    });
    refreshInFlight = { generation, promise };
  }
  return refreshInFlight.promise;
}

async function rotateTokens(generation: number): Promise<string | null> {
  const refresh = await SecureStore.getItemAsync(REFRESH_KEY);
  if (!refresh || generation !== authGeneration) return null;
  try {
    const response = await postAuthTokenRefresh(
      { refresh },
      { skipAccessToken: true, skipAuthRefresh: true },
    );
    const tokens = response.data;
    await writeForCurrentSession(generation, async () => {
      await SecureStore.setItemAsync(ACCESS_KEY, tokens.access);
      await SecureStore.setItemAsync(REFRESH_KEY, tokens.refresh);
    });
    return generation === authGeneration ? tokens.access : null;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await writeForCurrentSession(generation, clearTokens);
    }
    return null;
  }
}

export async function signOut(): Promise<void> {
  ++authGeneration;
  let refresh: string | null = null;
  try {
    await queueTokenWrite(async () => {
      refresh = await SecureStore.getItemAsync(REFRESH_KEY);
      await clearTokens();
    });
  } finally {
    if (refresh) await postAuthTokenLogout({ refresh });
  }
}

async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ]);
}
