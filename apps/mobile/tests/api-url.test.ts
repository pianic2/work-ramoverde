import { apiOrigin } from '../src/api-url';

describe('mobile API configuration', () => {
  it('allows the local HTTP API only in development', () => {
    expect(apiOrigin(undefined, true)).toBe('http://localhost:8010');
    expect(() => apiOrigin(undefined, false)).toThrow(/HTTPS/);
    expect(() => apiOrigin('http://api.example.com/api/v1', false)).toThrow(/HTTPS/);
  });

  it('accepts an explicit HTTPS API in release builds', () => {
    expect(apiOrigin('https://api.example.com/api/v1', false)).toBe('https://api.example.com');
  });
});
