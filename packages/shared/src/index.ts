export const API_VERSION = 'v1';

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}
