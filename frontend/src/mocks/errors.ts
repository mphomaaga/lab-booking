import type { ErrorCode, ErrorDetail } from "../api/types";

/** Thrown by the mock rules and turned into the contract's error body by the handlers. */
export class MockHttpError extends Error {
  readonly status: number;
  readonly code: ErrorCode;
  readonly details?: ErrorDetail[];

  constructor(status: number, code: ErrorCode, message: string, details?: ErrorDetail[]) {
    super(message);
    this.name = "MockHttpError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function notAuthenticated(): MockHttpError {
  return new MockHttpError(401, "not_authenticated", "Please log in.");
}

export function validationError(details: ErrorDetail[]): MockHttpError {
  return new MockHttpError(422, "validation_error", "The request is not valid.", details);
}
