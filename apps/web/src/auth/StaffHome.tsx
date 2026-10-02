import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, useGetUsersMe } from '@ramoverde/api-client';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { sessionLogout } from './session';

/** Backoffice landing (Sprint 2 builds the real UI). Authorization stays server-side. */
export function StaffHome() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const account = useGetUsersMe({ query: { retry: false } });
  const logout = useMutation({
    mutationFn: sessionLogout,
    onSettled: async () => {
      queryClient.clear();
      navigate('/admin/login', { replace: true });
    },
  });

  if (account.isPending) return <p className="shell">Caricamento…</p>;
  if (account.isError) {
    if (account.error instanceof ApiError && [401, 403].includes(account.error.status)) {
      return <Navigate to="/admin/login" replace />;
    }
    return (
      <main className="shell">
        <p role="alert">Servizio non disponibile. Riprova più tardi.</p>
      </main>
    );
  }

  return (
    <main className="shell">
      <header>
        <Link to="/">← RamoVerde</Link>
      </header>
      <section className="hero">
        <p className="eyebrow">BACKOFFICE</p>
        <h1>Area staff</h1>
        <p className="lede">Accesso effettuato come {account.data?.data.email}</p>
        <button className="web-button" onClick={() => logout.mutate()} disabled={logout.isPending}>
          Esci
        </button>
      </section>
    </main>
  );
}
