import { useGetUsersMe, type MobileAuthFlow, type TotpSetup } from '@ramoverde/api-client';
import {
  Box,
  Button,
  CodeInline,
  Column,
  Heading,
  Input,
  PasswordInput,
  Text,
} from '@personal-library/react-native-components';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Linking } from 'react-native';
import {
  changePassword,
  completeSignIn,
  confirmTotpEnrollment,
  signOut,
  signOutEverywhere,
  startSignIn,
  startTotpEnrollment,
} from '../src/auth/tokens';

type Step =
  | { kind: 'password' }
  | { kind: 'verify'; flow: MobileAuthFlow; recovery: boolean }
  | { kind: 'enroll'; flow: MobileAuthFlow; totp: TotpSetup | null }
  | { kind: 'recovery-codes'; codes: string[] };

const GENERIC_ERROR = 'Accesso non riuscito. Verifica i dati inseriti e riprova.';
const PASSWORD_ERROR =
  'Cambio password non riuscito: controlla la password attuale e scegline una nuova di almeno 12 caratteri, non usata di recente.';
const CODE_ERROR = 'Codice non valido o scaduto. Riprova, oppure ricomincia l’accesso.';

/**
 * Staff sign-in for the mobile app: password, then a mandatory second factor (TOTP or a
 * recovery code; passkeys are web-only in Sprint 1). The MFA challenge stays in memory.
 */
export default function AccountScreen() {
  const queryClient = useQueryClient();
  const account = useGetUsersMe({ query: { retry: false } });
  const [step, setStep] = useState<Step>({ kind: 'password' });
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
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

  async function enter() {
    setStep({ kind: 'password' });
    setCode('');
    await queryClient.invalidateQueries({ queryKey: account.queryKey });
  }

  if (account.isSuccess && step.kind !== 'recovery-codes') {
    const reset = () => queryClient.resetQueries({ queryKey: account.queryKey });
    return (
      <Column gap="md" style={{ flex: 1, justifyContent: 'center', padding: 24 }}>
        <Heading level={1}>Il tuo account</Heading>
        <Box padding="md" radius="md" bg="surface">
          <Text>Accesso effettuato come {account.data.data.email}</Text>
        </Box>
        {account.data.data.password_change_required ? (
          <>
            <Heading level={2}>Cambia la password</Heading>
            <Text>La tua password è scaduta: per continuare scegline una nuova.</Text>
            <PasswordInput
              label="Password attuale"
              autoComplete="password"
              value={password}
              onChangeText={setPassword}
            />
            <PasswordInput
              label="Nuova password"
              autoComplete="password-new"
              helperText="Almeno 12 caratteri; puoi usare una frase lunga."
              value={newPassword}
              onChangeText={setNewPassword}
            />
            <Button
              label="Aggiorna password"
              disabled={busy}
              onPress={() =>
                void run(async () => {
                  try {
                    await changePassword(password, newPassword);
                    await queryClient.invalidateQueries({ queryKey: account.queryKey });
                  } finally {
                    setPassword('');
                    setNewPassword('');
                  }
                }, PASSWORD_ERROR)
              }
            />
            {error ? <Text accessibilityRole="alert">{error}</Text> : null}
          </>
        ) : null}
        <Button label="Esci" variant="secondary" onPress={() => void signOut().finally(reset)} />
        <Button
          label="Esci da tutti i dispositivi"
          variant="secondary"
          onPress={() => void signOutEverywhere().finally(reset)}
        />
      </Column>
    );
  }

  return (
    <Column gap="md" style={{ flex: 1, justifyContent: 'center', padding: 24 }}>
      <Heading level={1}>Accesso staff</Heading>
      {step.kind === 'password' ? (
        <>
          <Input
            label="Email"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
          />
          <PasswordInput
            label="Password"
            autoComplete="password"
            value={password}
            onChangeText={setPassword}
          />
          <Button
            label={busy ? 'Verifica in corso…' : 'Continua'}
            disabled={busy}
            onPress={() =>
              void run(async () => {
                try {
                  const flow = await startSignIn(email, password);
                  setStep(
                    flow.status === 'mfa_enrollment_required'
                      ? { kind: 'enroll', flow, totp: await startTotpEnrollment(flow.challenge) }
                      : { kind: 'verify', flow, recovery: !flow.methods.includes('totp') },
                  );
                } finally {
                  setPassword('');
                }
              }, GENERIC_ERROR)
            }
          />
        </>
      ) : null}
      {step.kind === 'verify' ? (
        <>
          <Text>Conferma l’accesso con il secondo fattore.</Text>
          <Input
            label={step.recovery ? 'Codice di recupero' : 'Codice dell’app di autenticazione'}
            autoCapitalize="characters"
            autoComplete="one-time-code"
            keyboardType={step.recovery ? 'default' : 'number-pad'}
            value={code}
            onChangeText={(value) => setCode(value.trim())}
          />
          <Button
            label="Verifica"
            disabled={busy}
            onPress={() =>
              void run(async () => {
                await completeSignIn(
                  step.flow.challenge,
                  step.recovery ? 'recovery' : 'totp',
                  code,
                );
                await enter();
              }, CODE_ERROR)
            }
          />
          {!step.recovery && step.flow.methods.includes('recovery') ? (
            <Button
              label="Usa un codice di recupero"
              variant="secondary"
              onPress={() => {
                setCode('');
                setStep({ ...step, recovery: true });
              }}
            />
          ) : null}
          {step.flow.methods.length === 0 ? (
            <Text>Questo account usa solo la passkey: accedi dal backoffice web.</Text>
          ) : null}
        </>
      ) : null}
      {step.kind === 'enroll' && step.totp ? (
        <>
          <Heading level={2}>Configura la verifica in due passaggi</Heading>
          <Text>
            È obbligatoria per tutto lo staff. Aggiungi questa chiave nell’app di autenticazione,
            poi inserisci il codice a 6 cifre.
          </Text>
          <CodeInline accessibilityLabel="Chiave segreta">{step.totp.secret}</CodeInline>
          <Button
            label="Apri l’app di autenticazione"
            variant="secondary"
            onPress={() => step.totp && void Linking.openURL(step.totp.otpauth_uri)}
          />
          <Input
            label="Codice dell’app di autenticazione"
            autoComplete="one-time-code"
            keyboardType="number-pad"
            value={code}
            onChangeText={(value) => setCode(value.trim())}
          />
          <Button
            label="Attiva"
            disabled={busy}
            onPress={() =>
              void run(async () => {
                const codes = await confirmTotpEnrollment(step.flow.challenge, code);
                setCode('');
                setStep({ kind: 'recovery-codes', codes });
              }, CODE_ERROR)
            }
          />
        </>
      ) : null}
      {step.kind === 'recovery-codes' ? (
        <>
          <Heading level={2}>Codici di recupero</Heading>
          <Text>
            Conservali in un luogo sicuro: ognuno funziona una sola volta. Non verranno mostrati di
            nuovo.
          </Text>
          {step.codes.map((value) => (
            <CodeInline key={value}>{value}</CodeInline>
          ))}
          <Button label="Ho salvato i codici" onPress={() => void enter()} />
        </>
      ) : null}
      {error ? <Text accessibilityRole="alert">{error}</Text> : null}
    </Column>
  );
}
