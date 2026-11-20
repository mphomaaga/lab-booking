/** An inline error box. Pass `errorMessage(error)` or any plain-English text. */
export function ErrorMessage({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div className="error-message" role="alert">
      {message}
    </div>
  );
}
