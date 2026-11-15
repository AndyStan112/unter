export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/${path}`, {
      method,
      credentials: 'same-origin',
      cache: 'no-store',
      signal: AbortSignal.timeout(path === 'run' ? 120000 : 15000),
      headers: { 'Content-Type': 'application/json', 'X-Unter-Request': '1' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError('Connection lost. Reconnect and try again.', 0);
  }
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok)
    throw new ApiError(
      response.status === 401
        ? 'Sign in with the server’s shared development login, then retry.'
        : data?.message ||
            (typeof data?.detail === 'string' ? data.detail : 'Please check the submitted values.'),
      response.status,
      data?.error,
    );
  return data as T;
}
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong. Please retry.';
