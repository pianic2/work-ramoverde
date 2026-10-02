import { postAuthToken, postAuthTokenLogout, postAuthTokenRefresh } from '@ramoverde/api-client';
import * as SecureStore from 'expo-secure-store';
import { refreshSession, signIn, signOut } from '../src/auth/tokens';

jest.mock('@ramoverde/api-client', () => ({
  ApiError: class ApiError extends Error {},
  postAuthToken: jest.fn(),
  postAuthTokenLogout: jest.fn(),
  postAuthTokenRefresh: jest.fn(),
}));
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const stored = new Map<string, string>();
const tokenResponse = (access: string, refresh: string) =>
  ({ data: { access, refresh } }) as Awaited<ReturnType<typeof postAuthToken>>;

beforeEach(() => {
  stored.clear();
  jest.clearAllMocks();
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => stored.get(key) ?? null);
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
    stored.set(key, value);
  });
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
    stored.delete(key);
  });
  jest.mocked(postAuthTokenLogout).mockResolvedValue({} as Awaited<ReturnType<typeof postAuthTokenLogout>>);
});

function deferredRefresh() {
  let resolve!: (value: Awaited<ReturnType<typeof postAuthTokenRefresh>>) => void;
  const promise = new Promise<Awaited<ReturnType<typeof postAuthTokenRefresh>>>((done) => {
    resolve = done;
  });
  jest.mocked(postAuthTokenRefresh).mockReturnValue(promise);
  return (access: string, refresh: string) =>
    resolve(tokenResponse(access, refresh) as Awaited<ReturnType<typeof postAuthTokenRefresh>>);
}

it('does not restore tokens when refresh completes after sign-out', async () => {
  jest.mocked(postAuthToken).mockResolvedValue(tokenResponse('old-access', 'old-refresh'));
  await signIn('old@example.com', 'password');
  const resolve = deferredRefresh();
  const refreshing = refreshSession();
  await Promise.resolve();
  expect(postAuthTokenRefresh).toHaveBeenCalledTimes(1);
  await signOut();
  resolve('rotated-access', 'rotated-refresh');
  expect(await refreshing).toBeNull();
  expect(stored.size).toBe(0);
});

it('does not replace a new account with an older in-flight refresh', async () => {
  jest.mocked(postAuthToken).mockResolvedValueOnce(tokenResponse('old-access', 'old-refresh'));
  await signIn('old@example.com', 'password');
  const resolve = deferredRefresh();
  const refreshing = refreshSession();
  await Promise.resolve();
  expect(postAuthTokenRefresh).toHaveBeenCalledTimes(1);
  jest.mocked(postAuthToken).mockResolvedValueOnce(tokenResponse('new-access', 'new-refresh'));
  await signIn('new@example.com', 'password');
  resolve('rotated-access', 'rotated-refresh');
  expect(await refreshing).toBeNull();
  expect(stored.get('ramoverde.access-token')).toBe('new-access');
  expect(stored.get('ramoverde.refresh-token')).toBe('new-refresh');
});

it('revokes the refresh token even when local deletion fails', async () => {
  jest.mocked(postAuthToken).mockResolvedValue(tokenResponse('access', 'refresh'));
  await signIn('person@example.com', 'password');
  jest.mocked(SecureStore.deleteItemAsync).mockRejectedValueOnce(new Error('storage unavailable'));

  await expect(signOut()).rejects.toThrow('storage unavailable');
  expect(postAuthTokenLogout).toHaveBeenCalledWith({ refresh: 'refresh' });
});

it('clears the old session before a concurrent new sign-in writes tokens', async () => {
  jest.mocked(postAuthToken).mockResolvedValueOnce(tokenResponse('old-access', 'old-refresh'));
  await signIn('old@example.com', 'password');
  jest.mocked(postAuthToken).mockResolvedValueOnce(tokenResponse('new-access', 'new-refresh'));

  const loggingOut = signOut();
  const loggingIn = signIn('new@example.com', 'password');
  await Promise.all([loggingOut, loggingIn]);

  expect(postAuthTokenLogout).toHaveBeenCalledWith({ refresh: 'old-refresh' });
  expect(stored.get('ramoverde.access-token')).toBe('new-access');
  expect(stored.get('ramoverde.refresh-token')).toBe('new-refresh');
});
