const rawApiUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8010/api/v1';
const parsedApiUrl = new URL(rawApiUrl);

if (import.meta.env.PROD && parsedApiUrl.protocol !== 'https:') {
  throw new Error('VITE_API_BASE_URL must use HTTPS in production');
}

export const apiBaseUrl = parsedApiUrl.toString().replace(/\/$/, '');
