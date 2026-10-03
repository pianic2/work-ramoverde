import { render, screen } from '@testing-library/react-native';
import { Box, Button, Column, Text, ThemeProvider } from '@personal-library/react-native-components';

function LibrarySurface() {
  return <ThemeProvider><Column gap="sm"><Box padding="md" radius="md" bg="surface"><Text>Library rendered</Text></Box><Button label="Continue" onPress={() => undefined} /></Column></ThemeProvider>;
}

describe('personal component library integration', () => {
  it('resolves and renders public root exports inside its theme provider', () => {
    render(<LibrarySurface />);
    expect(screen.getByText('Library rendered')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeTruthy();
  });
});
