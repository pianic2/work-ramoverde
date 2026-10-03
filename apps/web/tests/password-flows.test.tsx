import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@ramoverde/api-client';
import { App } from '../src/routes/App';

const mocks = vi.hoisted(() => ({
  changePassword: vi.fn(),
  requestPasswordReset: vi.fn(),
  confirmPasswordReset: vi.fn(),
  logoutEverywhere: vi.fn(async () => undefined),
  sessionLogout: vi.fn(async () => undefined),
  me: { current: {} as Record<string, unknown> },
}));

vi.mock('../src/auth/session', () => mocks);
vi.mock('@ramoverde/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ramoverde/api-client')>()),
  useGetUsersMe: () => ({ ...mocks.me.current, queryKey: ['/api/v1/users/me'] }),
}));

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const user = (expired: boolean) => ({
  isSuccess: true,
  isPending: false,
  data: { data: { email: 'a@example.com', password_change_required: expired } },
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.me.current = user(false);
});

it('forces an expired password to be changed before anything else', async () => {
  mocks.me.current = user(true);
  mocks.changePassword.mockImplementationOnce(async () => {
    mocks.me.current = user(false);
  });
  renderAt('/admin');
  expect(await screen.findByRole('heading', { name: 'Cambia la password' })).toBeInTheDocument();
  expect(screen.getByText(/password è scaduta/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText('Password attuale'), 'old-pass-phrase-1');
  await userEvent.type(screen.getByLabelText('Nuova password'), 'new-pass-phrase-2026');
  await userEvent.click(screen.getByRole('button', { name: 'Aggiorna password' }));
  expect(mocks.changePassword).toHaveBeenCalledWith('old-pass-phrase-1', 'new-pass-phrase-2026');
  expect(await screen.findByRole('heading', { name: 'Area staff' })).toBeInTheDocument();
});

it('shows the password policy messages returned by the server', async () => {
  mocks.me.current = user(true);
  mocks.changePassword.mockRejectedValueOnce(
    new ApiError(400, {
      error: { details: { new_password: ['La password è troppo comune.'] } },
    }),
  );
  renderAt('/admin');
  await userEvent.type(await screen.findByLabelText('Password attuale'), 'old-pass-phrase-1');
  await userEvent.type(screen.getByLabelText('Nuova password'), 'password12345');
  await userEvent.click(screen.getByRole('button', { name: 'Aggiorna password' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('La password è troppo comune.');
});

it('requests a reset link with a message that never reveals whether the account exists', async () => {
  mocks.me.current = { isPending: false, isError: true, error: new ApiError(401, {}) };
  mocks.requestPasswordReset.mockResolvedValueOnce(undefined);
  renderAt('/admin/password-reset');
  await userEvent.type(screen.getByLabelText('Email'), 'someone@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Invia il collegamento' }));
  expect(mocks.requestPasswordReset).toHaveBeenCalledWith('someone@example.com');
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Se l’indirizzo appartiene a un account staff attivo',
  );
});

it('sets a new password from the emailed link and asks to sign in again', async () => {
  mocks.me.current = { isPending: false, isError: true, error: new ApiError(401, {}) };
  mocks.confirmPasswordReset.mockResolvedValueOnce(undefined);
  renderAt('/admin/reset-password?uid=MQ&token=abc-123');
  await userEvent.type(screen.getByLabelText('Nuova password'), 'new-pass-phrase-2026');
  await userEvent.click(screen.getByRole('button', { name: 'Imposta la password' }));
  expect(mocks.confirmPasswordReset).toHaveBeenCalledWith('MQ', 'abc-123', 'new-pass-phrase-2026');
  expect(await screen.findByRole('status')).toHaveTextContent('Password aggiornata');
  expect(screen.getByRole('link', { name: 'Vai all’accesso' })).toHaveAttribute(
    'href',
    '/admin/login',
  );
});

it('signs out of every device', async () => {
  renderAt('/admin');
  await userEvent.click(await screen.findByRole('button', { name: 'Esci da tutti i dispositivi' }));
  await waitFor(() => expect(mocks.logoutEverywhere).toHaveBeenCalledOnce());
});
