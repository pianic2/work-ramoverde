import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  {
    ignores: [
      '**/node_modules/**',
      '**/.venv/**',
      '**/dist/**',
      '**/build/**',
      '**/coverage/**',
      '**/generated/**',
      'apps/backend/staticfiles/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module' },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      ...reactHooks.configs.flat.recommended.rules,
    },
  },
  {
    files: ['**/babel.config.js', '**/jest.config.js'],
    languageOptions: { globals: { module: 'readonly', require: 'readonly' } },
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
];
