import { ApiError, configureApiClient, customFetch } from '@ramoverde/api-client';
import { afterEach, describe, expect, it, vi } from 'vitest';

function response(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: new Headers({ 'Content-Type': 'application/json' }),
    json: async () => body,
  } as Response;
}

describe('shared API transport', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    configureApiClient({ baseUrl: 'http://localhost:8000' });
  });

  it('refreshes an expired mobile access token once and retries with the rotated token', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(200, { status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);
    const refreshAccessToken = vi.fn(async () => 'rotated-token');
    configureApiClient({
      baseUrl: 'https://api.example.test',
      accessToken: async () => 'expired-token',
      refreshAccessToken,
    });

    const result = await customFetch<{
      data: { status: string };
      status: number;
      headers: Headers;
    }>('/api/v1/health/live');

    expect(result.data.status).toBe('ok');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer expired-token',
    );
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer rotated-token',
    );
    expect(refreshAccessToken).toHaveBeenCalledOnce();
  });

  it('skips access tokens and refresh for explicitly anonymous auth requests', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response(401, { detail: 'invalid' }));
    vi.stubGlobal('fetch', fetchMock);
    const accessToken = vi.fn(async () => 'stale-token');
    const refreshAccessToken = vi.fn(async () => 'rotated-token');
    configureApiClient({ baseUrl: 'https://api.example.test', accessToken, refreshAccessToken });

    await expect(
      customFetch('/api/v1/auth/token/refresh', {
        skipAccessToken: true,
        skipAuthRefresh: true,
      }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(accessToken).not.toHaveBeenCalled();
    expect(refreshAccessToken).not.toHaveBeenCalled();
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('Authorization')).toBe(false);
  });
});
