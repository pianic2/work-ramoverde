import { Link, Route, Routes } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, useGetUsersMe } from '@ramoverde/api-client';
import { useState } from 'react';
import { sessionLogin, sessionLogout } from '../auth/session';

function Home() {
  return (
    <main className="shell">
      <header>
        <strong>RamoVerde</strong>
        <nav>
          <Link to="/account">Area riservata</Link>
        </nav>
      </header>
      <section className="hero">
        <h1>RamoVerde</h1>
        <p className="lede">Il nuovo sito di RAMO VERDE SRL è in preparazione.</p>
      </section>
    </main>
  );
}

function Account() {
  const queryClient = useQueryClient();
  const account = useGetUsersMe({ query: { retry: false } });
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: () => sessionLogin(email, password),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: account.queryKey }),
  });
  const logout = useMutation({
    mutationFn: sessionLogout,
    onSuccess: () => queryClient.resetQueries({ queryKey: account.queryKey }),
  });
  const showAccountError =
    login.isError ||
    (account.isError && !(account.error instanceof ApiError && account.error.status === 401));

  return (
    <main className="shell">
      <header>
        <Link to="/">← Home</Link>
      </header>
      <section className="hero">
        <p className="eyebrow">AUTHENTICATED AREA</p>
        <h1>Your account</h1>
        {account.isSuccess ? (
          <>
            <p className="lede">Signed in as {account.data.data.email}</p>
            <button
              className="web-button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
            >
              Sign out
            </button>
          </>
        ) : (
          <form
            className="login-form"
            onSubmit={(event) => {
              event.preventDefault();
              login.mutate();
            }}
          >
            <label>
              Email
              <input
                autoComplete="username"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="web-button" disabled={login.isPending}>
              {login.isPending ? 'Signing in…' : 'Sign in'}
            </button>
            {showAccountError ? (
              <p role="alert">Sign-in failed. Check the API response and try again.</p>
            ) : null}
          </form>
        )}
      </section>
    </main>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/account" element={<Account />} />
      <Route
        path="*"
        element={
          <main className="shell">
            <h1>Page not found</h1>
            <Link to="/">Return home</Link>
          </main>
        }
      />
    </Routes>
  );
}
