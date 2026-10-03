import { useQueryClient } from '@tanstack/react-query';
import type { MfaMethodEnum, SessionAuthFlow, TotpSetup } from '@ramoverde/api-client';
import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  confirmTotpEnrollment,
  enrollPasskey,
  passwordStep,
  startTotpEnrollment,
  verifyCode,
  verifyPasskey,
} from './session';

type Step =
  | { kind: 'password' }
  | { kind: 'verify'; methods: MfaMethodEnum[]; useRecovery: boolean }
  | { kind: 'enroll'; totp: TotpSetup | null }
  | { kind: 'recovery-codes'; codes: string[] };

const GENERIC_ERROR = 'Accesso non riuscito. Verifica i dati inseriti e riprova.';
const CODE_ERROR = 'Codice non valido o scaduto. Riprova, oppure ricomincia l’accesso.';

/** Staff sign-in: password, then a mandatory second factor (or its first enrollment). */
export function StaffLogin() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>({ kind: 'password' });
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>, message: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch {
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function finish(flow: SessionAuthFlow) {
    setPassword('');
    setCode('');
    if (flow.recovery_codes?.length) {
      setStep({ kind: 'recovery-codes', codes: flow.recovery_codes });
      return;
    }
    await enter();
  }

  async function enter() {
    await queryClient.invalidateQueries();
    navigate('/admin', { replace: true });
  }

  const submitPassword = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      try {
        const flow = await passwordStep(email, password);
        setPassword('');
        setStep(
          flow.status === 'mfa_enrollment_required'
            ? { kind: 'enroll', totp: null }
            : { kind: 'verify', methods: flow.methods, useRecovery: false },
        );
      } catch (failure) {
        setPassword('');
        throw failure;
      }
    }, GENERIC_ERROR);
  };

  let body: ReactNode;
  if (step.kind === 'password') {
    body = (
      <form className="login-form" onSubmit={submitPassword}>
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
        <button className="web-button" disabled={busy}>
          {busy ? 'Verifica in corso…' : 'Continua'}
        </button>
        <Link to="/admin/password-reset">Password dimenticata?</Link>
      </form>
    );
  } else if (step.kind === 'verify') {
    const recovery = step.useRecovery || !step.methods.includes('totp');
    const canUseCode = step.methods.includes('totp') || step.methods.includes('recovery');
    body = (
      <div className="login-form">
        <p>Conferma l’accesso con il secondo fattore.</p>
        {step.methods.includes('webauthn') ? (
          <button
            className="web-button"
            type="button"
            disabled={busy}
            onClick={() => void run(async () => finish(await verifyPasskey()), CODE_ERROR)}
          >
            Usa la passkey
          </button>
        ) : null}
        {canUseCode ? (
          <form
            className="login-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run(
                async () => finish(await verifyCode(recovery ? 'recovery' : 'totp', code)),
                CODE_ERROR,
              );
            }}
          >
            <CodeField recovery={recovery} value={code} onChange={setCode} />
            <button className="web-button" disabled={busy}>
              Verifica
            </button>
          </form>
        ) : null}
        {!step.useRecovery && step.methods.includes('recovery') && step.methods.includes('totp') ? (
          <button
            className="link-button"
            type="button"
            onClick={() => {
              setCode('');
              setStep({ ...step, useRecovery: true });
            }}
          >
            Usa un codice di recupero
          </button>
        ) : null}
      </div>
    );
  } else if (step.kind === 'enroll') {
    body = (
      <div className="login-form">
        <h2>Configura la verifica in due passaggi</h2>
        <p>
          La verifica in due passaggi è obbligatoria per tutto lo staff. Consigliamo una passkey
          (impronta, volto o chiave di sicurezza); in alternativa usa un’app di autenticazione.
        </p>
        <button
          className="web-button"
          type="button"
          disabled={busy}
          onClick={() =>
            void run(async () => finish(await enrollPasskey('Passkey RamoVerde')), CODE_ERROR)
          }
        >
          Crea una passkey
        </button>
        {step.totp === null ? (
          <button
            className="link-button"
            type="button"
            disabled={busy}
            onClick={() =>
              void run(
                async () => setStep({ kind: 'enroll', totp: await startTotpEnrollment() }),
                GENERIC_ERROR,
              )
            }
          >
            Usa un’app di autenticazione
          </button>
        ) : (
          <form
            className="login-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run(async () => finish(await confirmTotpEnrollment(code)), CODE_ERROR);
            }}
          >
            <p>
              Aggiungi questa chiave nell’app di autenticazione (oppure apri il{' '}
              <a href={step.totp.otpauth_uri}>collegamento di configurazione</a>), poi inserisci il
              codice a 6 cifre.
            </p>
            <code aria-label="Chiave segreta">{step.totp.secret}</code>
            <CodeField recovery={false} value={code} onChange={setCode} />
            <button className="web-button" disabled={busy}>
              Attiva
            </button>
          </form>
        )}
      </div>
    );
  } else {
    body = (
      <div className="login-form">
        <h2>Codici di recupero</h2>
        <p>
          Conservali in un luogo sicuro: ognuno funziona una sola volta se perdi l’accesso al
          secondo fattore. Non verranno mostrati di nuovo.
        </p>
        <ul aria-label="Codici di recupero">
          {step.codes.map((value) => (
            <li key={value}>
              <code>{value}</code>
            </li>
          ))}
        </ul>
        <button className="web-button" type="button" onClick={() => void enter()}>
          Ho salvato i codici
        </button>
      </div>
    );
  }

  return (
    <main className="shell">
      <header>
        <Link to="/">← RamoVerde</Link>
      </header>
      <section className="hero" aria-labelledby="staff-login-title">
        <p className="eyebrow">AREA RISERVATA</p>
        <h1 id="staff-login-title">Accesso staff</h1>
        {body}
        {error ? <p role="alert">{error}</p> : null}
      </section>
    </main>
  );
}

function CodeField(props: { recovery: boolean; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      {props.recovery ? 'Codice di recupero' : 'Codice dell’app di autenticazione'}
      <input
        autoComplete="one-time-code"
        inputMode={props.recovery ? 'text' : 'numeric'}
        maxLength={props.recovery ? 16 : 6}
        value={props.value}
        onChange={(event) => props.onChange(event.target.value.trim())}
        required
      />
    </label>
  );
}
