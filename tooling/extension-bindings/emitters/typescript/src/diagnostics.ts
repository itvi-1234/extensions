export interface Diagnostic {
  readonly category: string;
  readonly code: string;
  readonly coordinate: string;
  readonly message: string;
  readonly jsonPointer: string;
}

export class DiagnosticError extends Error {
  readonly diagnostic: Diagnostic;

  constructor(diagnostic: Diagnostic) {
    const location = diagnostic.jsonPointer
      ? `${diagnostic.coordinate} ${diagnostic.jsonPointer}`
      : diagnostic.coordinate;
    super(`${diagnostic.code} ${location}: ${diagnostic.message}`);
    this.name = "DiagnosticError";
    this.diagnostic = diagnostic;
  }
}

export function fail(
  category: string,
  code: string,
  coordinate: string,
  message: string,
  jsonPointer = "",
): never {
  throw new DiagnosticError({ category, code, coordinate, message, jsonPointer });
}
