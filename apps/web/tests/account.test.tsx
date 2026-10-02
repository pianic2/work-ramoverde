import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { App } from '../src/routes/App';

const { sessionLogout } = vi.hoisted(() => ({ sessionLogout: vi.fn(async () => undefined) }));

vi.mock('../src/auth/session', () => ({ sessionLogin: vi.fn(), sessionLogout }));
vi.mock('@ramoverde/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ramoverde/api-client')>()),
  useGetUsersMe: () => ({
    isSuccess: true,
    data: { data: { email: 'alice@example.com' } },
    queryKey: ['/api/v1/users/me'],
  }),
}));

it('clears cached account data after signing out', async () => {
  const queryClient = new QueryClient();
  const queryKey = ['/api/v1/users/me'];
  queryClient.setQueryData(queryKey, { data: { email: 'alice@example.com' } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/account']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  await waitFor(() => expect(queryClient.getQueryData(queryKey)).toBeUndefined());
  expect(sessionLogout).toHaveBeenCalledOnce();
});
