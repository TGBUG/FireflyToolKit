#!/usr/bin/env node
/**
 * Fail the deploy when the CMS configuration and the theme's content schema have
 * drifted apart.
 *
 * Both directions of drift are silent in the CMS but not in the build, which is
 * why this runs in the deploy workflow rather than in the setup tool:
 *
 *   - A field the CMS declares that the schema does not know is stripped by Zod
 *     without complaint. The editor reports a successful save and the value goes
 *     nowhere.
 *   - A field the schema requires that the CMS does not declare cannot be filled
 *     in at all, so the build fails -- but only after an entry is published.
 *
 * The schema is read by scanning the TypeScript rather than by importing it:
 * `src/content.config.ts` imports from `astro:content`, which only resolves
 * inside Astro. The file changes rarely enough for a small scanner to be a
 * better trade than pulling in a parser.
 *
 * Run by the deploy workflow as:
 *     node .github/scripts/check-schema.mjs
 */

import { readFileSync } from 'node:fs';

const CONFIG_PATH = 'public/admin/config.json';
const SCHEMA_PATH = 'src/content.config.ts';

/** Fields the CMS legitimately declares that have no place in the Zod schema. */
const ALLOWED_EXTRAS = new Set([
  'body', // content, not front matter
  'slug', // written by the theme's own new-post script, ignored by its routing
  '_slug', // the toolkit's own field, consumed by the `path` template
]);

/** Widget -> the Zod kind it should be paired with. Mismatches warn, never fail. */
const WIDGET_KINDS = {
  string: 'string',
  text: 'string',
  markdown: 'string',
  richtext: 'string',
  image: 'string',
  file: 'string',
  select: 'string',
  color: 'string',
  code: 'string',
  hidden: 'string',
  relation: 'string',
  datetime: 'date',
  boolean: 'boolean',
  number: 'number',
  list: 'array',
  object: 'object',
  map: 'object',
  keyvalue: 'object',
};

/** Zod kinds worth comparing a widget against; anything else is left alone. */
const KNOWN_KINDS = new Set(['string', 'date', 'boolean', 'number', 'array', 'object']);

const OPTIONAL_MARKERS = ['.optional()', '.nullish()', '.default('];

// ---------------------------------------------------------------------------
// Reading the theme's TypeScript schema
// ---------------------------------------------------------------------------

/** Remove // and block comments, leaving string literals alone. */
const stripComments = (text) => {
  let out = '';
  let index = 0;
  let quote = null;
  while (index < text.length) {
    const char = text[index];
    if (quote) {
      out += char;
      if (char === '\\') {
        out += text[index + 1] ?? '';
        index += 2;
        continue;
      }
      if (char === quote) quote = null;
      index += 1;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      out += char;
      index += 1;
      continue;
    }
    if (char === '/' && text[index + 1] === '/') {
      const newline = text.indexOf('\n', index);
      if (newline === -1) break;
      index = newline;
      continue;
    }
    if (char === '/' && text[index + 1] === '*') {
      const end = text.indexOf('*/', index + 2);
      index = end === -1 ? text.length : end + 2;
      continue;
    }
    out += char;
    index += 1;
  }
  return out;
};

/** Index of the brace closing the one at `open`. */
const matchingBrace = (text, open) => {
  let depth = 0;
  let index = open;
  let quote = null;
  while (index < text.length) {
    const char = text[index];
    if (quote) {
      if (char === '\\') {
        index += 2;
        continue;
      }
      if (char === quote) quote = null;
      index += 1;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      index += 1;
      continue;
    }
    if (char === '{') depth += 1;
    else if (char === '}') {
      depth -= 1;
      if (depth === 0) return index;
    }
    index += 1;
  }
  throw new Error('unbalanced braces in the schema');
};

/** Split on commas that are not nested inside brackets or strings. */
const splitTopLevel = (text) => {
  const parts = [];
  let current = '';
  let depth = 0;
  let quote = null;
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (quote) {
      current += char;
      if (char === '\\') {
        current += text[index + 1] ?? '';
        index += 2;
        continue;
      }
      if (char === quote) quote = null;
      index += 1;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      current += char;
    } else if ('([{'.includes(char)) {
      depth += 1;
      current += char;
    } else if (')]}'.includes(char)) {
      depth -= 1;
      current += char;
    } else if (char === ',' && depth === 0) {
      parts.push(current);
      current = '';
    } else {
      current += char;
    }
    index += 1;
  }
  parts.push(current);
  return parts;
};

const DEFINE_COLLECTION = /defineCollection\s*\(\s*\{/g;
const BASE = /base:\s*["']\.\/src\/content\/([^"']+)["']/;
const SCHEMA = /schema:\s*/;
const ZOD_OBJECT = /z\.object\s*\(\s*\{/;
// The method name may sit on the next line: the theme writes some fields as
// `link: z\n    .array(`.
const ZOD_KIND = /^\s*z\s*\.\s*([A-Za-z]+)/;
const FIELD = /^\s*([A-Za-z_$][\w$]*)\s*:\s*([\s\S]+)$/;

/** collection name -> field name -> { kind, required } */
export const parseSchema = (source) => {
  const text = stripComments(source);
  const collections = {};
  DEFINE_COLLECTION.lastIndex = 0;
  let match;
  while ((match = DEFINE_COLLECTION.exec(text)) !== null) {
    const blockStart = text.indexOf('{', match.index + match[0].length - 1);
    const block = text.slice(blockStart, matchingBrace(text, blockStart) + 1);

    const base = block.match(BASE);
    if (!base) continue;
    const name = base[1];

    const schema = block.match(SCHEMA);
    const object = schema ? ZOD_OBJECT.exec(block.slice(schema.index + schema[0].length)) : null;
    if (!object) {
      collections[name] = {};
      continue;
    }
    const offset = schema.index + schema[0].length + object.index;
    const innerStart = block.indexOf('{', offset + object[0].length - 1);
    const inner = block.slice(innerStart, matchingBrace(block, innerStart) + 1);

    const fields = {};
    for (const segment of splitTopLevel(inner.slice(1, -1))) {
      const found = segment.match(FIELD);
      if (!found) continue;
      const kind = found[2].match(ZOD_KIND);
      fields[found[1]] = {
        kind: kind ? kind[1].toLowerCase() : null,
        required: !OPTIONAL_MARKERS.some((marker) => found[2].includes(marker)),
      };
    }
    collections[name] = fields;
  }
  return collections;
};

// ---------------------------------------------------------------------------
// Reading the CMS configuration
// ---------------------------------------------------------------------------

/** collection name -> field name -> { widget, required } */
export const parseConfig = (document) => {
  const collections = {};
  for (const collection of document.collections ?? []) {
    const folder = String(collection.folder ?? '').replace(/\/+$/, '');
    const name = folder.split('/').pop() || collection.name;
    const fields = {};
    for (const field of collection.fields ?? []) {
      if (!field.name) continue;
      // Nested `fields:` under a list widget describe list items, not front
      // matter keys, so they are deliberately not walked.
      fields[field.name] = {
        widget: field.widget ?? null,
        required: field.required !== false,
      };
    }
    collections[name] = fields;
  }
  return collections;
};

// ---------------------------------------------------------------------------
// Comparison
// ---------------------------------------------------------------------------

export const compare = (schema, config) => {
  const findings = [];

  for (const [name, fields] of Object.entries(config)) {
    if (!(name in schema)) {
      findings.push({
        level: 'error',
        message: `collection '${name}' has no matching collection in the schema`,
      });
      continue;
    }
    const zodFields = schema[name];

    for (const [field, declared] of Object.entries(fields)) {
      if (ALLOWED_EXTRAS.has(field)) continue;
      if (!(field in zodFields)) {
        findings.push({
          level: 'error',
          message:
            `${name}.${field}: declared in config.json but absent from the schema, ` +
            'so the value would be written and then silently dropped',
        });
        continue;
      }
      const expected = WIDGET_KINDS[declared.widget];
      const actual = zodFields[field].kind;
      if (expected && KNOWN_KINDS.has(actual) && expected !== actual) {
        findings.push({
          level: 'warning',
          message:
            `${name}.${field}: widget '${declared.widget}' implies ${expected} ` +
            `but the schema declares ${actual}`,
        });
      }
    }

    for (const [field, zod] of Object.entries(zodFields)) {
      if (zod.required && !(field in fields)) {
        findings.push({
          level: 'error',
          message:
            `${name}.${field}: required by the schema but not declared in config.json, ` +
            'so the editor cannot supply it and the build will fail',
        });
      }
      if (zod.required && field in fields && fields[field].required === false) {
        findings.push({
          level: 'error',
          message:
            `${name}.${field}: required by the schema but marked required:false in ` +
            'config.json, so the editor will let it be saved empty',
        });
      }
    }
  }
  return findings;
};

// ---------------------------------------------------------------------------

const main = () => {
  const schema = parseSchema(readFileSync(SCHEMA_PATH, 'utf8'));
  const config = parseConfig(JSON.parse(readFileSync(CONFIG_PATH, 'utf8')));
  const findings = compare(schema, config);

  const order = { error: 0, warning: 1 };
  findings.sort((a, b) => order[a.level] - order[b.level]);

  for (const finding of findings) {
    const annotation = finding.level === 'error' ? 'error' : 'warning';
    console.log(`::${annotation}::${finding.message}`);
    console.log(`  ${finding.level.padEnd(8)} ${finding.message}`);
  }

  const errors = findings.filter((finding) => finding.level === 'error').length;
  if (errors === 0 && findings.length === 0) {
    console.log('schema check: the CMS configuration matches the theme (0 findings)');
  }
  console.log(`\nschema check: ${errors} error(s), ${findings.length - errors} warning(s)`);

  if (errors > 0) {
    console.log(
      '\nThe theme\'s content schema and public/admin/config.json disagree. Reconcile them,\n' +
        'then re-run the setup tool\'s inject to bring config.json back in line.',
    );
    process.exit(1);
  }
};

main();
