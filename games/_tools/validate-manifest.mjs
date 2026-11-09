#!/usr/bin/env node
// Validates every games/<slug>/game.json against game-manifest.schema.json.
// No external deps: implements the small subset of JSON Schema draft-07
// actually used by that schema (type, required, properties, additionalProperties,
// enum, pattern, minimum, items, $ref into #/definitions).
//
// Usage: node games/_tools/validate-manifest.mjs

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";

const TOOLS_DIR = dirname(fileURLToPath(import.meta.url));
const GAMES_DIR = dirname(TOOLS_DIR);
const schema = JSON.parse(readFileSync(join(TOOLS_DIR, "game-manifest.schema.json"), "utf8"));

function resolveRef(ref) {
  const key = ref.replace("#/definitions/", "");
  return schema.definitions[key];
}

function validate(node, schemaNode, path, errors) {
  if (schemaNode.$ref) schemaNode = resolveRef(schemaNode.$ref);

  if (schemaNode.type === "object") {
    if (typeof node !== "object" || node === null || Array.isArray(node)) {
      errors.push(`${path}: expected object`);
      return;
    }
    for (const key of schemaNode.required || []) {
      if (!(key in node)) errors.push(`${path}: missing required field "${key}"`);
    }
    const props = schemaNode.properties || {};
    const additionalAllowed = schemaNode.additionalProperties;
    for (const key of Object.keys(node)) {
      if (props[key]) {
        validate(node[key], props[key], `${path}.${key}`, errors);
      } else if (additionalAllowed === false) {
        errors.push(`${path}: unexpected field "${key}"`);
      } else if (additionalAllowed && typeof additionalAllowed === "object") {
        validate(node[key], additionalAllowed, `${path}.${key}`, errors);
      }
    }
  } else if (schemaNode.type === "array") {
    if (!Array.isArray(node)) {
      errors.push(`${path}: expected array`);
      return;
    }
    if (schemaNode.items) node.forEach((item, i) => validate(item, schemaNode.items, `${path}[${i}]`, errors));
  } else if (schemaNode.type === "string") {
    if (typeof node !== "string") {
      errors.push(`${path}: expected string`);
      return;
    }
    if (schemaNode.enum && !schemaNode.enum.includes(node)) {
      errors.push(`${path}: "${node}" is not one of [${schemaNode.enum.join(", ")}]`);
    }
    if (schemaNode.pattern && !new RegExp(schemaNode.pattern).test(node)) {
      errors.push(`${path}: "${node}" does not match pattern ${schemaNode.pattern}`);
    }
  } else if (schemaNode.type === "number") {
    if (typeof node !== "number") {
      errors.push(`${path}: expected number`);
      return;
    }
    if (schemaNode.minimum !== undefined && node < schemaNode.minimum) {
      errors.push(`${path}: ${node} is below minimum ${schemaNode.minimum}`);
    }
  } else if (schemaNode.type === "boolean") {
    if (typeof node !== "boolean") errors.push(`${path}: expected boolean`);
  }
}

function validateManifest(manifestPath) {
  const errors = [];
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch (e) {
    return [`could not parse JSON: ${e.message}`];
  }

  validate(manifest, schema, "game.json", errors);

  // Semantic checks beyond plain schema shape.
  const gameDir = dirname(manifestPath);
  const slugFromDir = basename(gameDir);
  if (manifest.slug && manifest.slug !== slugFromDir) {
    errors.push(`game.json.slug "${manifest.slug}" does not match folder name "${slugFromDir}"`);
  }
  if (manifest.entry && !existsSync(join(gameDir, manifest.entry))) {
    errors.push(`game.json.entry "${manifest.entry}" does not exist in ${gameDir}`);
  }
  if (manifest.thumbnail && !existsSync(join(gameDir, manifest.thumbnail))) {
    errors.push(`game.json.thumbnail "${manifest.thumbnail}" does not exist in ${gameDir}`);
  }
  if (!existsSync(join(gameDir, "LICENSE"))) {
    errors.push(`missing LICENSE file in ${gameDir}`);
  }
  if (!existsSync(join(gameDir, "CREDITS.md"))) {
    errors.push(`missing CREDITS.md in ${gameDir}`);
  }

  return errors;
}

function findManifests(dir) {
  return readdirSync(dir)
    .filter((name) => !name.startsWith("_"))
    .map((name) => join(dir, name))
    .filter((p) => statSync(p).isDirectory())
    .map((p) => join(p, "game.json"))
    .filter((p) => existsSync(p));
}

const manifests = findManifests(GAMES_DIR);
if (manifests.length === 0) {
  console.log("No game.json files found under games/.");
  process.exit(0);
}

let failed = 0;
for (const manifestPath of manifests) {
  const slug = basename(dirname(manifestPath));
  const errors = validateManifest(manifestPath);
  if (errors.length === 0) {
    console.log(`OK    ${slug}`);
  } else {
    failed++;
    console.log(`FAIL  ${slug}`);
    for (const err of errors) console.log(`        ${err}`);
  }
}

console.log(`\n${manifests.length - failed}/${manifests.length} manifests valid.`);
process.exit(failed > 0 ? 1 : 0);
