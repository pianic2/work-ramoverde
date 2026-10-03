import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@personal-library/react-native-components';
import AccountScreen from '../app/account';
import * as auth from '../src/auth/tokens';

jest.mock('../src/auth/tokens', () => ({
  startSignIn: jest.fn(),
  completeSignIn: jest.fn(),
  startTotpEnrollment: jest.fn(),
  confirmTotpEnrollment: jest.fn(),
  signOut: jest.fn(),
}));
const me: { current: Record<string, unknown> } = {
  current: { isPending: false, isSuccess: false },
};
jest.mock('@ramoverde/api-client', () => ({
  useGetUsersMe: () => ({ ...me.current, queryKey: ['/api/v1/users/me'] }),
}));

function renderScreen() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ThemeProvider>
        <AccountScreen />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

async function submitPassword() {
  fireEvent.changeText(screen.getByLabelText('Email'), 'op@example.com');
  fireEvent.changeText(screen.getByLabelText('Password'), 'long-pass-phrase');
  fireEvent.press(screen.getByRole('button', { name: 'Continua' }));
}

beforeEach(() => {
  jest.clearAllMocks();
  me.current = { isPending: false, isSuccess: false };
});

it('asks for the second factor after the password and completes with the challenge', async () => {
  jest.mocked(auth.startSignIn).mockResolvedValue({
    status: 'mfa_required',
    methods: ['totp', 'recovery'],
    challenge: 'signed',
  });
  jest.mocked(auth.completeSignIn).mockResolvedValue();
  renderScreen();
  expect(screen.getByText('Accesso staff')).toBeTruthy();
  await submitPassword();

  const code = await screen.findByLabelText('Codice dell’app di autenticazione');
  fireEvent.changeText(code, '123456');
  fireEvent.press(screen.getByRole('button', { name: 'Verifica' }));
  await waitFor(() => expect(auth.completeSignIn).toHaveBeenCalledWith('signed', 'totp', '123456'));
});

it('shows a generic Italian error when the password step fails', async () => {
  jest.mocked(auth.startSignIn).mockRejectedValue(new Error('401'));
  renderScreen();
  await submitPassword();
  expect(
    await screen.findByText('Accesso non riuscito. Verifica i dati inseriti e riprova.'),
  ).toBeTruthy();
});

it('enrolls TOTP on first sign-in and shows the recovery codes once', async () => {
  jest.mocked(auth.startSignIn).mockResolvedValue({
    status: 'mfa_enrollment_required',
    methods: [],
    challenge: 'signed',
  });
  jest.mocked(auth.startTotpEnrollment).mockResolvedValue({
    secret: 'JBSWY3DPEHPK3PXP',
    otpauth_uri: 'otpauth://totp/RamoVerde:op@example.com?secret=JBSWY3DPEHPK3PXP',
  });
  jest.mocked(auth.confirmTotpEnrollment).mockResolvedValue(['AAAAA-BBBBB']);
  renderScreen();
  await submitPassword();

  expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeTruthy();
  fireEvent.changeText(screen.getByLabelText('Codice dell’app di autenticazione'), '654321');
  fireEvent.press(screen.getByRole('button', { name: 'Attiva' }));
  expect(await screen.findByText('AAAAA-BBBBB')).toBeTruthy();
  expect(auth.confirmTotpEnrollment).toHaveBeenCalledWith('signed', '654321');
});

it('shows the signed-in account in Italian with sign-out', () => {
  me.current = { isPending: false, isSuccess: true, data: { data: { email: 'op@example.com' } } };
  renderScreen();
  expect(screen.getByText('Accesso effettuato come op@example.com')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Esci' })).toBeTruthy();
});
