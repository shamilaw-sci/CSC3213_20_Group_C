// Lets plain `node` (>= 23.6, which strips TS types natively) run these
// framework-free tests: retries an extensionless relative import as `.ts`.
// No test runner is installed, and this avoids adding one for a few scripts.
//
//   node --import ./src/__tests__/resolve-ts.mjs src/__tests__/<file>.test.ts
import { registerHooks } from 'node:module';

registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (err) {
      if (err?.code === 'ERR_MODULE_NOT_FOUND' && /^\.\.?\//.test(specifier)) {
        return nextResolve(`${specifier}.ts`, context);
      }
      throw err;
    }
  },
});
