export type ApiRequestInit = RequestInit & {
  skipAccessToken?: boolean;
  skipAuthRefresh?: boolean;
};
export type ApiConfiguration = {
  baseUrl: string;
  accessToken?: () => Promise<string | null>;
  refreshAccessToken?: () => Promise<string | null>;
};
let configuration: ApiConfiguration = { baseUrl: 'http://localhost:8000' };

export function configureApiClient(next: ApiConfiguration): void {
  configuration = next;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API request failed (${status})`);
    this.name = 'ApiError';
  }
}

export async function customFetch<T>(url: string, options: ApiRequestInit = {}): Promise<T> {
  const { skipAccessToken = false, skipAuthRefresh = false, ...requestOptions } = options;
  const accessToken = skipAccessToken ? null : await configuration.accessToken?.();
  const send = (token: string | null | undefined) => {
    const headers = new Headers(requestOptions.headers);
    headers.set('Accept', 'application/json');
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return fetch(new URL(url, configuration.baseUrl), {
      ...requestOptions,
      credentials: 'include',
      headers,
    });
  };

  let response = await send(accessToken);
  if (
    response.status === 401 &&
    accessToken &&
    configuration.refreshAccessToken &&
    !skipAuthRefresh
  ) {
    const refreshedToken = await configuration.refreshAccessToken();
    if (refreshedToken) response = await send(refreshedToken);
  }
  const data = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, data);
  return { data, status: response.status, headers: response.headers } as T;
}
