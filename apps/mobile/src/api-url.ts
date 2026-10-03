export function apiOrigin(rawUrl: string | undefined, isDevelopment: boolean): string {
  const url = new URL(rawUrl ?? 'http://localhost:8010/api/v1');
  if (!isDevelopment && url.protocol !== 'https:') {
    throw new Error('EXPO_PUBLIC_API_URL must use HTTPS in release builds');
  }
  return url.origin;
}
