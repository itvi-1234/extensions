# Future extension-binding work

This file records follow-up work. It is not an amendment to
`IMPLEMENTATION.md` and does not change the current implementation contract.

## Standardize emitter diagnostic codes

Define and document a shared diagnostic-code standard before treating the
Python emitter's current `RCP` codes as a stable public interface. The standard
should specify code ownership and ranges across the normalizer, emitters, and
orchestrator; the diagnostic fields and text format; how codes are versioned or
retired; and which negative conformance fixtures assert each diagnostic. Review
the existing Go `RCG` codes when assigning cross-language meanings. Code
numbers that look alike across languages must not silently imply the same error
unless the standard says so.

The Python emitter currently uses `RCP` for Runtime Conditions Python. The
following meanings describe the implementation as it stands; they are
provisional and require review as part of the standardization work.

| Code | Current meaning |
| --- | --- |
| `RCP1001` | YAML input cannot be read or exceeds the size limit. |
| `RCP1002` | YAML syntax, profile, structure, or resource-limit failure. |
| `RCP1003` | Binding-model field, value, or structural validation failure. |
| `RCP1004` | Unsupported binding-model `apiVersion`. |
| `RCP1005` | Unsupported binding-model `kind`. |
| `RCP1006` | Invalid Python package-target field or dependency metadata. |
| `RCP1007` | Target source directory does not match its package key. |
| `RCP1008` | Unsupported minimum Python version. |
| `RCP1009` | Target root extension or direct dependency set differs from the model. |
| `RCP1010` | Unknown structural shape kind. |
| `RCP1011` | Inconsistent extension closure or declaration ownership. |
| `RCP1012` | Inconsistent shape details, value domain, or unresolved reference. |
| `RCP2000` | A source name cannot be derived as a valid Python identifier. |
| `RCP2001` | Generated symbol requests or allocated names collide. |
| `RCP3001` | Source output directory is occupied or is a symbolic link. |
| `RCP3002` | Package output directory cannot be inspected or generated package files cannot be written. |
| `RCP4001` | Generated package source tree is unavailable, altered, or contains a symbolic link. |
| `RCP4002` | Pinned Python interpreter, build tools, or source formatter are unavailable, fail, or do not match the lock. |
| `RCP4003` | The pinned native Python package build fails. |
| `RCP4004` | Wheel, source distribution, or generated source file set is missing, undeclared, altered, or malformed. |
| `RCP4005` | Archive output directory is occupied or canonical archives cannot be written. |

Until the standardization work is done, keep these codes and their current
tests in place. Record any deliberate reassignment or split of a code with the
corresponding diagnostic fixtures and migration note.
