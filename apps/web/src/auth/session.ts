import {
  getAuthCsrf,
  postAuthSessionLogin,
  postAuthSessionLogout,
  postAuthSessionMfaTotpConfirm,
  postAuthSessionMfaTotpSetup,
  postAuthSessionMfaVerify,
  postAuthSessionMfaWebauthnOptions,
  postAuthSessionMfaWebauthnRegisterOptions,
  postAuthSessionMfaWebauthnRegisterVerify,
  type SessionAuthFlow,
  type TotpSetup,
} from '@ramoverde/api-client';
import { startAuthentication, startRegistration } from '@simplewebauthn/browser';

/**
 * Staff browser sign-in. Credentials live only in the HttpOnly session cookie; the CSRF
 * token is fetched per unsafe request (Django rotates it at sign-in) and never stored.
 */
async function csrfHeaders(): Promise<{ headers: Record<string, string> }> {
  const response = await getAuthCsrf();
  return { headers: { 'X-CSRFToken': response.data.csrfToken } };
}

export async function passwordStep(email: string, password: string): Promise<SessionAuthFlow> {
  return (await postAuthSessionLogin({ email, password }, await csrfHeaders())).data;
}

export async function verifyCode(
  method: 'totp' | 'recovery',
  code: string,
): Promise<SessionAuthFlow> {
  return (await postAuthSessionMfaVerify({ method, code }, await csrfHeaders())).data;
}

export async function verifyPasskey(): Promise<SessionAuthFlow> {
  const options = await postAuthSessionMfaWebauthnOptions(await csrfHeaders());
  const credential = await startAuthentication({
    optionsJSON: options.data.options as Parameters<typeof startAuthentication>[0]['optionsJSON'],
  });
  return (await postAuthSessionMfaVerify({ method: 'webauthn', credential }, await csrfHeaders()))
    .data;
}

export async function startTotpEnrollment(): Promise<TotpSetup> {
  return (await postAuthSessionMfaTotpSetup(await csrfHeaders())).data;
}

export async function confirmTotpEnrollment(code: string): Promise<SessionAuthFlow> {
  return (await postAuthSessionMfaTotpConfirm({ code }, await csrfHeaders())).data;
}

export async function enrollPasskey(name: string): Promise<SessionAuthFlow> {
  const options = await postAuthSessionMfaWebauthnRegisterOptions(await csrfHeaders());
  const credential = await startRegistration({
    optionsJSON: options.data.options as Parameters<typeof startRegistration>[0]['optionsJSON'],
  });
  return (await postAuthSessionMfaWebauthnRegisterVerify({ credential, name }, await csrfHeaders()))
    .data;
}

export async function sessionLogout(): Promise<void> {
  await postAuthSessionLogout(await csrfHeaders());
}
