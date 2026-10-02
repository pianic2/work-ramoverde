import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { sessionLogin } from './session';

export function StaffLogin() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: () => sessionLogin(email, password),
    onSuccess: async () => {
      setPassword('');
      await queryClient.invalidateQueries();
      navigate('/admin', { replace: true });
    },
    onError: () => setPassword(''),
  });

  return (
    <main className="shell">
      <header>
        <Link to="/">← RamoVerde</Link>
      </header>
      <section className="hero" aria-labelledby="staff-login-title">
        <p className="eyebrow">AREA RISERVATA</p>
        <h1 id="staff-login-title">Accesso staff</h1>
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
            {login.isPending ? 'Accesso in corso…' : 'Accedi'}
          </button>
          {login.isError ? (
            <p role="alert">Accesso non riuscito. Verifica le credenziali e riprova.</p>
          ) : null}
        </form>
      </section>
    </main>
  );
}
