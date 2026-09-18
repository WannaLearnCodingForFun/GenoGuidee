export function humanError(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Unable to complete this request. Check that the backend is running.";
}
