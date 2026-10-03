import { ApiError } from '@ramoverde/api-client';
import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { changePassword, confirmPasswordReset, requestPasswordReset } from './session';

/** User-facing validation messages from the API error envelope (password policy). */
export function apiMessages(error: unknown, fallback: string): string[] {
  if (error instanceof ApiError && error.status === 400) {
    const details = (error.body as { error?: { details?: Record<string, unknown> } })?.error
      ?.details;
    const messages = Object.values(details ?? {})
      .flat()
      .filter((value): value is string => typeof value === 'string');
    if (messages.length) return messages;
  }
  return [fallback];
}

function Shell(props: { title: string; children: ReactNode }) {
  return (
    <main className="shell">
      <header>
        <Link to="/admin/login">← Accesso staff</Link>
      </header>
      <section className="hero" aria-labelledby="password-title">
        <p className="eyebrow">AREA RISERVATA</p>
        <h1 id="password-title">{props.title}</h1>
        {props.children}
      </section>
    </main>
  );
}

function NewPasswordField(props: { value: string; onChange: (value: string) => void }) {
  return (
    <>
      <label>
        Nuova password
        <input
          autoComplete="new-password"
          type="password"
          minLength={12}
          aria-describedby="new-password-help"
          value={props.value}
          onChange={(event) => props.onChange(event.target.value)}
          required
        />
      </label>
      <small id="new-password-help">
        Almeno 12 caratteri; puoi usare una frase lunga. Non riutilizzare password recenti.
      </small>
    </>
  );
}

/** Mandatory change of an expired password (shown inside the signed-in backoffice). */
export function ExpiredPasswordForm(props: { onChanged: () => Promise<void> }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await changePassword(current, next);
      await props.onChanged();
    } catch (error) {
      const stale = error instanceof ApiError && error.status === 403;
      setErrors(
        stale
          ? ['Per sicurezza esci e accedi di nuovo, poi cambia la password.']
          : apiMessages(error, 'Cambio password non riuscito. Riprova.'),
      );
    } finally {
      setCurrent('');
      setNext('');
      setBusy(false);
    }
  };

  return (
    <form className="login-form" onSubmit={(event) => void submit(event)}>
      <h2>Cambia la password</h2>
      <p>La tua password è scaduta: per continuare scegline una nuova.</p>
      <label>
        Password attuale
        <input
          autoComplete="current-password"
          type="password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
          required
        />
      </label>
      <NewPasswordField value={next} onChange={setNext} />
      <button className="web-button" disabled={busy}>
        Aggiorna password
      </button>
      {errors.length ? (
        <div role="alert">
          {errors.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      ) : null}
    </form>
  );
}

export function PasswordResetRequest() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await requestPasswordReset(email);
    } catch {
      // Same answer whatever happened: never reveal whether the account exists.
    } finally {
      setBusy(false);
      setSent(true);
    }
  };

  return (
    <Shell title="Password dimenticata">
      {sent ? (
        <p role="status">
          Se l’indirizzo appartiene a un account staff attivo, riceverai un’email con un
          collegamento valido per 30 minuti.
        </p>
      ) : (
        <form className="login-form" onSubmit={(event) => void submit(event)}>
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
          <button className="web-button" disabled={busy}>
            Invia il collegamento
          </button>
        </form>
      )}
    </Shell>
  );
}

export function PasswordResetConfirm() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await confirmPasswordReset(params.get('uid') ?? '', params.get('token') ?? '', password);
      setDone(true);
    } catch (error) {
      setErrors(apiMessages(error, 'Collegamento non valido o scaduto. Richiedine uno nuovo.'));
    } finally {
      setPassword('');
      setBusy(false);
    }
  };

  return (
    <Shell title="Reimposta la password">
      {done ? (
        <>
          <p role="status">
            Password aggiornata. Tutte le sessioni sono state chiuse: accedi di nuovo con la
            verifica in due passaggi.
          </p>
          <Link className="web-button" to="/admin/login">
            Vai all’accesso
          </Link>
        </>
      ) : (
        <form className="login-form" onSubmit={(event) => void submit(event)}>
          <NewPasswordField value={password} onChange={setPassword} />
          <button className="web-button" disabled={busy}>
            Imposta la password
          </button>
          {errors.length ? (
            <div role="alert">
              {errors.map((message) => (
                <p key={message}>{message}</p>
              ))}
            </div>
          ) : null}
        </form>
      )}
    </Shell>
  );
}
