import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, useGetUsersMe } from '@ramoverde/api-client';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ExpiredPasswordForm } from './PasswordPages';
import { logoutEverywhere, sessionLogout } from './session';

/** Backoffice landing (Sprint 2 builds the real UI). Authorization stays server-side. */
export function StaffHome() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const account = useGetUsersMe({ query: { retry: false } });
  const leave = async () => {
    queryClient.clear();
    navigate('/admin/login', { replace: true });
  };
  const logout = useMutation({ mutationFn: sessionLogout, onSettled: leave });
  const logoutAll = useMutation({ mutationFn: logoutEverywhere, onSettled: leave });

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

  const user = account.data?.data;
  return (
    <main className="shell">
      <header>
        <Link to="/">← RamoVerde</Link>
      </header>
      <section className="hero">
        <p className="eyebrow">BACKOFFICE</p>
        <h1>Area staff</h1>
        <p className="lede">Accesso effettuato come {user?.email}</p>
        {user?.password_change_required ? (
          <ExpiredPasswordForm
            onChanged={() => queryClient.invalidateQueries({ queryKey: account.queryKey })}
          />
        ) : null}
        <div className="actions">
          <button
            className="web-button"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            Esci
          </button>
          <button
            className="link-button"
            onClick={() => logoutAll.mutate()}
            disabled={logoutAll.isPending}
          >
            Esci da tutti i dispositivi
          </button>
        </div>
      </section>
    </main>
  );
}
