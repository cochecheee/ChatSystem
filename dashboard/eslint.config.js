import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';
import { defineConfig, globalIgnores } from 'eslint/config';

export default defineConfig([
  globalIgnores(['dist', 'node_modules', 'playwright-report', 'test-results', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      prettier,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // Codebase quy ước dùng `// eslint-disable-next-line react-hooks/exhaustive-deps`
      // cho mount-once effect. Giữ là warn để dev thấy nhưng không block CI.
      'react-hooks/exhaustive-deps': 'warn',
      // react-hooks v7 rule mới — false-positive khi setState đồng bộ trong effect
      // dùng cho data loading. Tắt cho tới khi pages được rewrite sang TanStack Query.
      'react-hooks/set-state-in-effect': 'off',
      // Context provider + hook đi cùng file là pattern hợp lệ. Để warn để biết
      // file nào có thể tách (cleanup khi có thời gian) nhưng không block CI.
      'react-refresh/only-export-components': 'warn',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
    },
  },
]);
