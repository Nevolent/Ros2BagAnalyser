export async function request<T>(path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    signal,
    credentials: 'same-origin',
    cache: 'no-store',
    ...(body !== undefined
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      : {}),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail?.message;
    throw new Error(
      typeof message === 'string' ? message : `Request failed (HTTP ${response.status}).`,
    );
  }
  return response.json() as Promise<T>;
}
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Request failed.';
export function numericId(id: string): number {
  if (!/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id)))
    throw new Error('Invalid recording ID.');
  return Number(id);
}
