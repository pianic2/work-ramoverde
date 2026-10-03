import {
  postAuthToken,
  postAuthTokenLogout,
  postAuthTokenMfaTotpConfirm,
  postAuthTokenMfaVerify,
  postAuthTokenRefresh,
} from '@ramoverde/api-client';
import * as SecureStore from 'expo-secure-store';
import {
  completeSignIn,
  confirmTotpEnrollment,
  refreshSession,
  signOut,
  startSignIn,
} from '../src/auth/tokens';

jest.mock('@ramoverde/api-client', () => ({
  ApiError: class ApiError extends Error {},
  postAuthToken: jest.fn(),
  postAuthTokenLogout: jest.fn(),
  postAuthTokenMfaTotpConfirm: jest.fn(),
  postAuthTokenMfaTotpSetup: jest.fn(),
  postAuthTokenMfaVerify: jest.fn(),
  postAuthTokenRefresh: jest.fn(),
}));
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const stored = new Map<string, string>();
const tokenResponse = (access: string, refresh: string) =>
  ({ data: { access, refresh } }) as Awaited<ReturnType<typeof postAuthTokenMfaVerify>>;

async function signIn(_email: string, _password: string) {
  await completeSignIn('challenge', 'totp', '123456');
}

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
  jest
    .mocked(postAuthTokenLogout)
    .mockResolvedValue({} as Awaited<ReturnType<typeof postAuthTokenLogout>>);
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
  jest.mocked(postAuthTokenMfaVerify).mockResolvedValue(tokenResponse('old-access', 'old-refresh'));
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
  jest
    .mocked(postAuthTokenMfaVerify)
    .mockResolvedValueOnce(tokenResponse('old-access', 'old-refresh'));
  await signIn('old@example.com', 'password');
  const resolve = deferredRefresh();
  const refreshing = refreshSession();
  await Promise.resolve();
  expect(postAuthTokenRefresh).toHaveBeenCalledTimes(1);
  jest
    .mocked(postAuthTokenMfaVerify)
    .mockResolvedValueOnce(tokenResponse('new-access', 'new-refresh'));
  await signIn('new@example.com', 'password');
  resolve('rotated-access', 'rotated-refresh');
  expect(await refreshing).toBeNull();
  expect(stored.get('ramoverde.access-token')).toBe('new-access');
  expect(stored.get('ramoverde.refresh-token')).toBe('new-refresh');
});

it('revokes the refresh token even when local deletion fails', async () => {
  jest.mocked(postAuthTokenMfaVerify).mockResolvedValue(tokenResponse('access', 'refresh'));
  await signIn('person@example.com', 'password');
  jest.mocked(SecureStore.deleteItemAsync).mockRejectedValueOnce(new Error('storage unavailable'));

  await expect(signOut()).rejects.toThrow('storage unavailable');
  expect(postAuthTokenLogout).toHaveBeenCalledWith({ refresh: 'refresh' });
});

it('clears the old session before a concurrent new sign-in writes tokens', async () => {
  jest
    .mocked(postAuthTokenMfaVerify)
    .mockResolvedValueOnce(tokenResponse('old-access', 'old-refresh'));
  await signIn('old@example.com', 'password');
  jest
    .mocked(postAuthTokenMfaVerify)
    .mockResolvedValueOnce(tokenResponse('new-access', 'new-refresh'));

  const loggingOut = signOut();
  const loggingIn = signIn('new@example.com', 'password');
  await Promise.all([loggingOut, loggingIn]);

  expect(postAuthTokenLogout).toHaveBeenCalledWith({ refresh: 'old-refresh' });
  expect(stored.get('ramoverde.access-token')).toBe('new-access');
  expect(stored.get('ramoverde.refresh-token')).toBe('new-refresh');
});

it('never stores anything after the password step alone', async () => {
  jest.mocked(postAuthToken).mockResolvedValue({
    data: { status: 'mfa_required', methods: ['totp'], challenge: 'signed-challenge' },
  } as Awaited<ReturnType<typeof postAuthToken>>);
  const flow = await startSignIn('op@example.com', 'long-pass-phrase');
  expect(flow.challenge).toBe('signed-challenge');
  expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
});

it('stores the token pair only after the second factor succeeds', async () => {
  jest.mocked(postAuthTokenMfaVerify).mockResolvedValue(tokenResponse('access', 'refresh'));
  await completeSignIn('signed-challenge', 'recovery', 'ABCDE-FGHJK');
  expect(postAuthTokenMfaVerify).toHaveBeenCalledWith({
    challenge: 'signed-challenge',
    method: 'recovery',
    code: 'ABCDE-FGHJK',
  });
  expect(stored.get('ramoverde.access-token')).toBe('access');
  expect(stored.get('ramoverde.refresh-token')).toBe('refresh');
});

it('returns recovery codes from enrollment without persisting them', async () => {
  jest.mocked(postAuthTokenMfaTotpConfirm).mockResolvedValue({
    data: { access: 'a', refresh: 'r', recovery_codes: ['AAAAA-BBBBB'] },
  } as Awaited<ReturnType<typeof postAuthTokenMfaTotpConfirm>>);
  const codes = await confirmTotpEnrollment('signed-challenge', '123456');
  expect(codes).toEqual(['AAAAA-BBBBB']);
  expect([...stored.values()]).toEqual(['a', 'r']);
});
