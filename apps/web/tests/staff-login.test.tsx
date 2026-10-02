import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@ramoverde/api-client';
import { App } from '../src/routes/App';

const mocks = vi.hoisted(() => ({
  sessionLogin: vi.fn(),
  sessionLogout: vi.fn(async () => undefined),
  me: { current: { isSuccess: false, isError: true, isPending: false } as Record<string, unknown> },
}));

vi.mock('../src/auth/session', () => ({
  sessionLogin: mocks.sessionLogin,
  sessionLogout: mocks.sessionLogout,
}));
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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.me.current = {
    isSuccess: false,
    isError: true,
    isPending: false,
    error: new ApiError(401, {}),
  };
});

it('sends anonymous visitors of the backoffice to the Italian staff sign-in page', async () => {
  renderAt('/admin');
  expect(await screen.findByRole('heading', { name: 'Accesso staff' })).toBeInTheDocument();
  expect(screen.getByLabelText('Email')).toHaveAttribute('autocomplete', 'username');
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
});

it('shows one generic error when credentials are rejected', async () => {
  mocks.sessionLogin.mockRejectedValueOnce(new ApiError(401, { error: { code: 'x' } }));
  renderAt('/admin/login');
  await userEvent.type(screen.getByLabelText('Email'), 'staff@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'wrong-password');
  await userEvent.click(screen.getByRole('button', { name: 'Accedi' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Accesso non riuscito');
  expect(mocks.sessionLogin).toHaveBeenCalledWith('staff@example.com', 'wrong-password');
});

it('shows the signed-in staff member and signs out', async () => {
  mocks.me.current = { isSuccess: true, isPending: false, data: { data: { email: 'a@example.com' } } };
  renderAt('/admin');
  expect(await screen.findByText(/a@example.com/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Esci' }));
  await waitFor(() => expect(mocks.sessionLogout).toHaveBeenCalledOnce());
});
