import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../src/routes/App';

vi.mock('@ramoverde/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ramoverde/api-client')>()),
  useGetUsersMe: () => ({ isError: false, error: undefined, queryKey: ['/api/v1/users/me'] }),
}));

describe('web shell', () => {
  it('renders the RamoVerde placeholder without template content', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'RamoVerde' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Area riservata' })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/starter|build the product/i);
  });
});
