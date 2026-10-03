import { getAuthCsrf, postAuthSessionLogin, postAuthSessionLogout } from '@ramoverde/api-client';

async function csrfToken(): Promise<string> {
  const response = await getAuthCsrf();
  return response.data.csrfToken;
}

export async function sessionLogin(email: string, password: string): Promise<void> {
  const csrf = await csrfToken();
  await postAuthSessionLogin({ email, password }, { headers: { 'X-CSRFToken': csrf } });
}

export async function sessionLogout(): Promise<void> {
  const csrf = await csrfToken();
  await postAuthSessionLogout({ headers: { 'X-CSRFToken': csrf } });
}
