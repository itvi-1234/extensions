import { readFileSync } from "node:fs";

import { fail } from "./diagnostics.js";

const PLACEHOLDER = /\{\{(\w+)\}\}/g;
const WHOLE = /^\{\{(\w+)\}\}$/;

export function readTemplate(name: string): string {
  try {
    return readFileSync(new URL(`../../templates/${name}`, import.meta.url), "utf-8");
  } catch {
    return fail("toolchain", "RCT4001", name, `template '${name}' cannot be read`);
  }
}

function lookup(variables: Readonly<Record<string, unknown>>, key: string, template: string): unknown {
  if (!(key in variables)) {
    return fail("toolchain", "RCT4001", template, `template placeholder '{{${key}}}' has no value`);
  }
  return variables[key];
}

export function fillText(template: string, text: string, variables: Readonly<Record<string, unknown>>): string {
  return text.replace(PLACEHOLDER, (_match, key: string) => String(lookup(variables, key, template)));
}

/** Replaces `{{name}}` in every string of a parsed JSON template; a string that is only one placeholder takes the value as is. */
export function fillJson(template: string, value: unknown, variables: Readonly<Record<string, unknown>>): unknown {
  if (typeof value === "string") {
    const whole = WHOLE.exec(value);
    return whole ? lookup(variables, whole[1]!, template) : fillText(template, value, variables);
  }
  if (Array.isArray(value)) return value.map((item) => fillJson(template, item, variables));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, fillJson(template, item, variables)]),
    );
  }
  return value;
}
