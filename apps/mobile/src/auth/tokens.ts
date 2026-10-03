import {
  ApiError,
  postAuthPasswordChange,
  postAuthSessionsRevokeAll,
  postAuthToken,
  postAuthTokenLogout,
  postAuthTokenMfaTotpConfirm,
  postAuthTokenMfaTotpSetup,
  postAuthTokenMfaVerify,
  postAuthTokenRefresh,
  type MobileAuthFlow,
  type MobileMfaMethodEnum,
  type MobileTokenResponse,
  type TotpSetup,
} from '@ramoverde/api-client';
import * as SecureStore from 'expo-secure-store';

const ACCESS_KEY = 'ramoverde.access-token';
const REFRESH_KEY = 'ramoverde.refresh-token';
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

/** Current access token for the API transport. Tokens live only in Expo SecureStore. */
export function readAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

/**
 * Password step. Never yields tokens: the returned short-lived challenge stays in memory
 * and must be completed with a second factor (TOTP or recovery code on mobile).
 */
export async function startSignIn(email: string, password: string): Promise<MobileAuthFlow> {
  return (await postAuthToken({ email, password })).data;
}

async function storeTokens(tokens: MobileTokenResponse): Promise<void> {
  const generation = ++authGeneration;
  await writeForCurrentSession(generation, async () => {
    await SecureStore.setItemAsync(ACCESS_KEY, tokens.access);
    await SecureStore.setItemAsync(REFRESH_KEY, tokens.refresh);
  });
}

export async function completeSignIn(
  challenge: string,
  method: MobileMfaMethodEnum,
  code: string,
): Promise<void> {
  await storeTokens((await postAuthTokenMfaVerify({ challenge, method, code })).data);
}

export async function startTotpEnrollment(challenge: string): Promise<TotpSetup> {
  return (await postAuthTokenMfaTotpSetup({ challenge })).data;
}

/** First enrollment: stores the tokens and returns recovery codes to show once (not stored). */
export async function confirmTotpEnrollment(challenge: string, code: string): Promise<string[]> {
  const tokens = (await postAuthTokenMfaTotpConfirm({ challenge, code })).data;
  await storeTokens(tokens);
  return tokens.recovery_codes ?? [];
}

/** Change the (possibly expired) password; the server re-issues this device's tokens. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const response = await postAuthPasswordChange({
    current_password: currentPassword,
    new_password: newPassword,
  });
  if (response.status === 200) await storeTokens(response.data);
}

/** Global logout: revoke every web session and mobile token of the account, then clear. */
export async function signOutEverywhere(): Promise<void> {
  try {
    await postAuthSessionsRevokeAll();
  } finally {
    ++authGeneration;
    await queueTokenWrite(clearTokens);
  }
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
