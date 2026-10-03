import { defineConfig } from 'orval';

export default defineConfig({
  productApi: {
    input: { target: './openapi/openapi.yaml' },
    output: {
      target: './packages/api-client/src/generated/api.ts',
      schemas: './packages/api-client/src/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      mode: 'split',
      clean: true,
      override: {
        query: { version: 5 },
        fetch: { includeHttpResponseReturnType: true },
        mutator: { path: './packages/api-client/src/fetcher.ts', name: 'customFetch' },
      },
    },
  },
});
