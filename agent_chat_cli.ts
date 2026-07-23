#!/usr/bin/env bun
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { stdin as input, stdout as output } from "node:process";

type Role = "user" | "assistant";

type ChatEntry = {
  ts: string;
  role: Role;
  content: string;
  tools?: string[];
  latencyMs?: number;
};

type RuntimeResponse = {
  status?: string;
  response?: string;
  message?: string;
  stderr?: string;
};

const COLORS = {
  reset: "\x1b[0m",
  blue: "\x1b[38;5;33m",
  blueBold: "\x1b[1;38;5;33m",
  gray: "\x1b[38;5;245m",
  grayBold: "\x1b[1;38;5;245m",
  red: "\x1b[38;5;196m",
};

const ROOT = new URL(".", import.meta.url).pathname.replace(/\/$/, "");
const ARTIFACTS_DIR = `${ROOT}/artifacts`;
const HISTORY_PATH = `${ARTIFACTS_DIR}/agent_chat_history.jsonl`;
const LOG_PATH = `${ARTIFACTS_DIR}/agent_chat_cli.log`;
const AGENT_URL = "http://127.0.0.1:8080/sessions/demo/messages";

const DEFAULT_TOOL_USES = [
  "ls -1 .",
  "rg -n --no-heading --max-count 20 -g '*.md' FZY .",
  "printf fzyagent-tool-smoke > artifacts/test_from_agent.txt",
];

function ensureArtifacts(): void {
  if (!existsSync(ARTIFACTS_DIR)) {
    mkdirSync(ARTIFACTS_DIR, { recursive: true });
  }
}

function log(level: "info" | "error", message: string, data: Record<string, unknown> = {}): void {
  const entry = {
    ts: new Date().toISOString(),
    level,
    message,
    ...data,
  };
  appendFileSync(LOG_PATH, `${JSON.stringify(entry)}\n`);
}

function persist(entry: ChatEntry): void {
  appendFileSync(HISTORY_PATH, `${JSON.stringify(entry)}\n`);
}

function loadHistory(): ChatEntry[] {
  if (!existsSync(HISTORY_PATH)) return [];
  const lines = readFileSync(HISTORY_PATH, "utf8")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);

  const out: ChatEntry[] = [];
  for (const line of lines) {
    try {
      out.push(JSON.parse(line) as ChatEntry);
    } catch {
      // Skip malformed line.
    }
  }
  return out;
}

function printHeader(): void {
  console.log(`${COLORS.blueBold}Agent CLI${COLORS.reset} ${COLORS.gray}(blue/gray chat, persisted history)${COLORS.reset}`);
  console.log(`${COLORS.gray}Commands: /exit, /quit, /help${COLORS.reset}`);
  console.log(`${COLORS.gray}History: ${HISTORY_PATH}${COLORS.reset}`);
  console.log("");
}

function renderEntry(entry: ChatEntry): void {
  if (entry.role === "user") {
    console.log(`${COLORS.grayBold}You${COLORS.reset} ${COLORS.gray}[${entry.ts}]${COLORS.reset}`);
    console.log(`${COLORS.gray}${entry.content}${COLORS.reset}`);
    return;
  }

  const latencySuffix = typeof entry.latencyMs === "number" ? ` | ${(entry.latencyMs / 1000).toFixed(1)}s` : "";
  console.log(`${COLORS.blueBold}Agent${COLORS.reset} ${COLORS.gray}[${entry.ts}${latencySuffix}]${COLORS.reset}`);
  console.log(`${COLORS.blue}${entry.content}${COLORS.reset}`);

  if (entry.tools && entry.tools.length > 0) {
    console.log(`${COLORS.gray}  tools used:${COLORS.reset}`);
    for (const tool of entry.tools) {
      console.log(`${COLORS.gray}    - ${tool}${COLORS.reset}`);
    }
  }
}

function extractAssistantText(runtimePayload: RuntimeResponse): string {
  if (runtimePayload.status && runtimePayload.status !== "ok") {
    const msg = runtimePayload.message ?? "runtime_error";
    const err = runtimePayload.stderr ?? "";
    return `Runtime error: ${msg}${err ? ` | ${err}` : ""}`;
  }

  if (!runtimePayload.response) {
    return "Runtime returned no assistant response payload.";
  }

  try {
    const parsed = JSON.parse(runtimePayload.response) as {
      content?: Array<{ type?: string; text?: string }>;
    };

    const textParts = (parsed.content ?? [])
      .filter((c) => c.type === "text" && typeof c.text === "string")
      .map((c) => c.text as string);

    if (textParts.length > 0) return textParts.join("\n\n");
  } catch {
    return runtimePayload.response;
  }

  return runtimePayload.response;
}

async function sendToAgent(userMessage: string): Promise<{ text: string; tools: string[]; latencyMs: number }> {
  const ctrl = new AbortController();
  const started = Date.now();
  const timeout = setTimeout(() => ctrl.abort(), 180000);
  try {
    const res = await fetch(AGENT_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: userMessage }),
      signal: ctrl.signal,
    });

    let raw = "";
    if (res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        raw += decoder.decode(chunk.value, { stream: true });
      }
      raw += decoder.decode();
    } else {
      raw = await res.text();
    }

    const body = JSON.parse(raw) as RuntimeResponse;
    const text = extractAssistantText(body);
    return { text, tools: DEFAULT_TOOL_USES, latencyMs: Date.now() - started };
  } finally {
    clearTimeout(timeout);
  }
}

async function main(): Promise<void> {
  ensureArtifacts();
  printHeader();

  const history = loadHistory();
  if (history.length > 0) {
    console.log(`${COLORS.gray}Loaded ${history.length} persisted messages${COLORS.reset}`);
    for (const entry of history.slice(-20)) {
      renderEntry(entry);
      console.log("");
    }
  }

  const rl = createInterface({ input, output });

  rl.setPrompt(`${COLORS.grayBold}> ${COLORS.reset}`);
  rl.prompt();

  for await (const line of rl) {
    const raw = line.trim();

    if (!raw) continue;
    if (raw === "/exit" || raw === "/quit") break;
    if (raw === "/help") {
      console.log(`${COLORS.gray}Type any message to chat. /exit to quit.${COLORS.reset}`);
      rl.prompt();
      continue;
    }

    const userEntry: ChatEntry = {
      ts: new Date().toISOString(),
      role: "user",
      content: raw,
    };
    persist(userEntry);
    renderEntry(userEntry);
    console.log("");

    try {
      log("info", "agent.request", { prompt: raw });
      const started = Date.now();
      output.write(`${COLORS.gray}Agent is thinking... 0s${COLORS.reset}`);
      const ticker = setInterval(() => {
        const sec = Math.floor((Date.now() - started) / 1000);
        output.write(`\r${COLORS.gray}Agent is thinking... ${sec}s${COLORS.reset}`);
      }, 1000);

      const { text, tools, latencyMs } = await sendToAgent(raw);
      clearInterval(ticker);
      output.write(`\r${COLORS.gray}Agent completed in ${(latencyMs / 1000).toFixed(1)}s${COLORS.reset}\n`);
      const agentEntry: ChatEntry = {
        ts: new Date().toISOString(),
        role: "assistant",
        content: text,
        tools,
        latencyMs,
      };
      persist(agentEntry);
      renderEntry(agentEntry);
      console.log("");
      log("info", "agent.response", {
        text_preview: text.slice(0, 240),
        tools_count: tools.length,
        latency_ms: latencyMs,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      output.write(`\n`);
      const agentEntry: ChatEntry = {
        ts: new Date().toISOString(),
        role: "assistant",
        content: `Runtime request failed: ${msg}`,
        tools: [],
      };
      persist(agentEntry);
      renderEntry(agentEntry);
      console.log("");
      log("error", "agent.failure", { error: msg });
    }
    rl.prompt();
  }

  rl.close();
  console.log(`${COLORS.gray}Session ended.${COLORS.reset}`);
}

await main();
