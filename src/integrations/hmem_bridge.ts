// Node bridge from Python to the Meterless H-MEM engine.
//
// Runs the official H-MEM reference implementation vendored in
// vendor/meterless-hmem (unmodified). Python (src/integrations/
// meterless_engine.py) starts this once per call:
//
//   node --experimental-transform-types --no-warnings hmem_bridge.ts
//
// stdin:  one JSON command {op, persistDir, ...}
// stdout: one JSON result
//
// State lives in <persistDir>/state.json and the append-only trust ledger
// in <persistDir>/ledger.jsonl, both written by H-MEM itself.

import { HMEM } from "../../vendor/meterless-hmem/index.ts";
import type { MemoryRecord } from "../../vendor/meterless-hmem/index.ts";

const KEY_TAG = "qp-key:";
const SEP = " :: ";

type Command =
  | { op: "remember"; persistDir: string; key: string; value: unknown; tags?: string[]; confidence?: number }
  | { op: "recall"; persistDir: string; query: string; topN?: number; threshold?: number }
  | { op: "count"; persistDir: string };

function keyOf(m: MemoryRecord): string | undefined {
  const tag = m.tags.find((t) => t.startsWith(KEY_TAG));
  return tag ? tag.slice(KEY_TAG.length) : undefined;
}

function valueOf(m: MemoryRecord, key: string): unknown {
  const prefix = key + SEP;
  const raw = m.content.startsWith(prefix) ? m.content.slice(prefix.length) : m.content;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString("utf-8");
}

function run(cmd: Command): unknown {
  const hmem = new HMEM({ persistDir: cmd.persistDir, actor: "quantpilot" });

  if (cmd.op === "remember") {
    // A newer write for the same key supersedes the older record.
    const previous = hmem.store
      .all()
      .filter((m) => keyOf(m) === cmd.key && !m.supersededBy)
      .sort((a, b) => b.timestamp - a.timestamp || b.id.localeCompare(a.id))[0];
    const record = hmem.add({
      content: cmd.key + SEP + JSON.stringify(cmd.value),
      type: "factual",
      tags: [KEY_TAG + cmd.key, ...(cmd.tags ?? [])],
      confidence: cmd.confidence ?? 0.9,
      source: "quantpilot",
      provenance: { origin: "manual", learnedAt: Date.now(), label: "quantpilot remember()" },
      supersedes: previous?.id,
    });
    if (previous) hmem.store.update(previous.id, { supersededBy: record.id });
    return { id: record.id, supersedes: previous?.id ?? null };
  }

  if (cmd.op === "recall") {
    const result = hmem.query(cmd.query, { topN: cmd.topN, threshold: cmd.threshold });
    const seen = new Set<string>();
    const items = [];
    for (const { memory, relevance } of result.memories) {
      if (memory.supersededBy) continue;
      const key = keyOf(memory) ?? memory.id;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({ id: memory.id, key, value: valueOf(memory, key), relevance, layer: memory.layer });
    }
    return { items, strategy: result.trace.strategy };
  }

  if (cmd.op === "count") {
    return { count: hmem.store.all().filter((m) => !m.supersededBy).length };
  }

  throw new Error(`unknown op: ${(cmd as { op: string }).op}`);
}

readStdin()
  .then((text) => {
    const out = run(JSON.parse(text) as Command);
    process.stdout.write(JSON.stringify({ ok: true, result: out }) + "\n");
  })
  .catch((error: Error) => {
    process.stdout.write(JSON.stringify({ ok: false, error: String(error?.message ?? error) }) + "\n");
    process.exitCode = 1;
  });
