/** @file Test-only deferred promise gates shared by controlled async-boundary tests. */

export interface Deferred<Value> {
  readonly promise: Promise<Value>;
  resolve(value: Value): void;
}

/**
 * Hold one asynchronous result until a test releases it.
 * @returns A promise gate with a resolver.
 * @example
 * const response = deferred<Response>();
 * response.resolve(new Response(null, {status: 204}));
 */
export function deferred<Value>(): Deferred<Value> {
  const resolvers: ((value: Value) => void)[] = [];
  const promise = new Promise<Value>((resolve) => {
    resolvers.push(resolve);
  });
  return {
    promise,
    resolve(value) {
      const resolver = resolvers[0];
      if (!resolver) throw new Error('The deferred promise has no resolver.');
      resolver(value);
    }
  };
}
