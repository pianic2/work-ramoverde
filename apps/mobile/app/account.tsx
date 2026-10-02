import { useGetUsersMe } from '@ramoverde/api-client';
import {
  Box,
  Button,
  Column,
  Heading,
  Input,
  PasswordInput,
  Text,
} from '@personal-library/react-native-components';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { signIn, signOut } from '../src/auth/tokens';

export default function AccountScreen() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const account = useGetUsersMe({ query: { retry: false } });
  const login = useMutation({
    mutationFn: () => signIn(email, password),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: account.queryKey }),
  });
  const logout = useMutation({
    mutationFn: signOut,
    onSettled: () => queryClient.resetQueries({ queryKey: account.queryKey }),
  });

  return (
    <Column gap="md" style={{ flex: 1, justifyContent: 'center', padding: 24 }}>
      <Heading level={1}>Your account</Heading>
      {account.isPending ? (
        <Text>Loading account…</Text>
      ) : account.isSuccess ? (
        <>
          <Box padding="md" radius="md" bg="surface">
            <Text>Signed in as {account.data.data.email}</Text>
          </Box>
          <Button label="Sign out" variant="secondary" onPress={() => logout.mutate()} />
        </>
      ) : (
        <>
          <Text>Sign in to view account details.</Text>
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
            label={login.isPending ? 'Signing in…' : 'Sign in'}
            disabled={login.isPending}
            onPress={() => login.mutate()}
          />
          {login.isError ? (
            <Text accessibilityRole="alert">
              Sign-in failed. Check your credentials and try again.
            </Text>
          ) : null}
        </>
      )}
    </Column>
  );
}
