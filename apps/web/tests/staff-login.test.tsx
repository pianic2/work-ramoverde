import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@ramoverde/api-client';
import { App } from '../src/routes/App';

const mocks = vi.hoisted(() => ({
  passwordStep: vi.fn(),
  verifyCode: vi.fn(),
  verifyPasskey: vi.fn(),
  startTotpEnrollment: vi.fn(),
  confirmTotpEnrollment: vi.fn(),
  enrollPasskey: vi.fn(),
  sessionLogout: vi.fn(async () => undefined),
  logoutEverywhere: vi.fn(async () => undefined),
  me: { current: {} as Record<string, unknown> },
}));

vi.mock('../src/auth/session', () => mocks);
vi.mock('@ramoverde/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ramoverde/api-client')>()),
  useGetUsersMe: () => ({ ...mocks.me.current, queryKey: ['/api/v1/users/me'] }),
}));

const signedIn = { isSuccess: true, isPending: false, data: { data: { email: 'a@example.com' } } };
const anonymous = {
  isSuccess: false,
  isError: true,
  isPending: false,
  error: new ApiError(401, {}),
};

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function submitPassword() {
  await userEvent.type(screen.getByLabelText('Email'), 'staff@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'long-pass-phrase');
  await userEvent.click(screen.getByRole('button', { name: 'Continua' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.me.current = anonymous;
});

it('sends anonymous visitors of the backoffice to the Italian staff sign-in page', async () => {
  renderAt('/admin');
  expect(await screen.findByRole('heading', { name: 'Accesso staff' })).toBeInTheDocument();
  expect(screen.getByLabelText('Email')).toHaveAttribute('autocomplete', 'username');
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
});

it('shows one generic error when credentials are rejected', async () => {
  mocks.passwordStep.mockRejectedValueOnce(new ApiError(401, {}));
  renderAt('/admin/login');
  await submitPassword();
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Accesso non riuscito. Verifica i dati inseriti e riprova.',
  );
  expect(screen.getByLabelText('Password')).toHaveValue('');
});

it('requires the authenticator code after the password and only then opens the backoffice', async () => {
  mocks.passwordStep.mockResolvedValueOnce({
    status: 'mfa_required',
    methods: ['totp', 'recovery'],
  });
  mocks.verifyCode.mockImplementationOnce(async () => {
    mocks.me.current = signedIn;
    return { status: 'authenticated', methods: ['totp', 'recovery'] };
  });
  renderAt('/admin/login');
  await submitPassword();

  const code = await screen.findByLabelText('Codice dell’app di autenticazione');
  expect(code).toHaveAttribute('autocomplete', 'one-time-code');
  expect(code).toHaveAttribute('inputmode', 'numeric');
  await userEvent.type(code, '123456');
  await userEvent.click(screen.getByRole('button', { name: 'Verifica' }));

  expect(mocks.verifyCode).toHaveBeenCalledWith('totp', '123456');
  expect(await screen.findByRole('heading', { name: 'Area staff' })).toBeInTheDocument();
});

it('accepts a recovery code instead of the authenticator code', async () => {
  mocks.passwordStep.mockResolvedValueOnce({
    status: 'mfa_required',
    methods: ['totp', 'recovery'],
  });
  mocks.verifyCode.mockResolvedValueOnce({ status: 'authenticated', methods: [] });
  renderAt('/admin/login');
  await submitPassword();
  await userEvent.click(await screen.findByRole('button', { name: 'Usa un codice di recupero' }));
  await userEvent.type(screen.getByLabelText('Codice di recupero'), 'ABCDE-FGHJK');
  await userEvent.click(screen.getByRole('button', { name: 'Verifica' }));
  expect(mocks.verifyCode).toHaveBeenCalledWith('recovery', 'ABCDE-FGHJK');
});

it('offers the passkey first when one is registered', async () => {
  mocks.passwordStep.mockResolvedValueOnce({
    status: 'mfa_required',
    methods: ['webauthn', 'recovery'],
  });
  mocks.verifyPasskey.mockResolvedValueOnce({ status: 'authenticated', methods: [] });
  renderAt('/admin/login');
  await submitPassword();
  await userEvent.click(await screen.findByRole('button', { name: 'Usa la passkey' }));
  expect(mocks.verifyPasskey).toHaveBeenCalledOnce();
});

it('reports a rejected second factor without details', async () => {
  mocks.passwordStep.mockResolvedValueOnce({ status: 'mfa_required', methods: ['totp'] });
  mocks.verifyCode.mockRejectedValueOnce(new ApiError(401, {}));
  renderAt('/admin/login');
  await submitPassword();
  await userEvent.type(await screen.findByLabelText('Codice dell’app di autenticazione'), '000000');
  await userEvent.click(screen.getByRole('button', { name: 'Verifica' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Codice non valido');
});

it('enrolls an authenticator app and shows recovery codes once before entering', async () => {
  mocks.passwordStep.mockResolvedValueOnce({ status: 'mfa_enrollment_required', methods: [] });
  mocks.startTotpEnrollment.mockResolvedValueOnce({
    secret: 'JBSWY3DPEHPK3PXP',
    otpauth_uri: 'otpauth://totp/RamoVerde:staff@example.com?secret=JBSWY3DPEHPK3PXP',
  });
  mocks.confirmTotpEnrollment.mockResolvedValueOnce({
    status: 'authenticated',
    methods: ['totp', 'recovery'],
    recovery_codes: ['AAAAA-BBBBB', 'CCCCC-DDDDD'],
  });
  renderAt('/admin/login');
  await submitPassword();

  expect(
    await screen.findByRole('heading', { name: 'Configura la verifica in due passaggi' }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Usa un’app di autenticazione' }));
  expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText('Codice dell’app di autenticazione'), '654321');
  await userEvent.click(screen.getByRole('button', { name: 'Attiva' }));

  expect(mocks.confirmTotpEnrollment).toHaveBeenCalledWith('654321');
  expect(await screen.findByText('AAAAA-BBBBB')).toBeInTheDocument();
  mocks.me.current = signedIn;
  await userEvent.click(screen.getByRole('button', { name: 'Ho salvato i codici' }));
  expect(await screen.findByRole('heading', { name: 'Area staff' })).toBeInTheDocument();
});

it('shows the signed-in staff member and signs out', async () => {
  mocks.me.current = signedIn;
  renderAt('/admin');
  expect(await screen.findByText(/a@example.com/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Esci' }));
  await waitFor(() => expect(mocks.sessionLogout).toHaveBeenCalledOnce());
});
