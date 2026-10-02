import { useGetHealthLive } from '@ramoverde/api-client';
import { Box, Column, Heading, Text } from '@personal-library/react-native-components';
import { Link } from 'expo-router';

export default function HomeScreen() {
  const health = useGetHealthLive();
  const state = health.isPending
    ? 'Verifica connessione API…'
    : health.isSuccess
      ? 'API connessa'
      : 'API non raggiungibile';

  return (
    <Column gap="md" style={{ flex: 1, justifyContent: 'center', padding: 24 }}>
      <Heading level={1}>RamoVerde Staff</Heading>
      <Text>App operativa riservata al personale RamoVerde.</Text>
      <Box padding="md" radius="md" bg="surface">
        <Text accessibilityRole="text">{state}</Text>
      </Box>
      <Link href="/account">Profilo</Link>
    </Column>
  );
}
