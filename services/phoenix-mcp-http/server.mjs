#!/usr/bin/env node
/**
 * Streamable HTTP MCP server wrapping @arizeai/phoenix-mcp tools.
 * Deploy to Cloud Run; ADK agents connect via StreamableHTTPConnectionParams.
 */
import { randomUUID } from "node:crypto";

import { createPhoenixClient } from "@arizeai/phoenix-mcp/build/client.js";
import { resolveConfig } from "@arizeai/phoenix-mcp/build/config.js";
import { initializeAnnotationConfigTools } from "@arizeai/phoenix-mcp/build/annotationConfigTools.js";
import { initializeDatasetTools } from "@arizeai/phoenix-mcp/build/datasetTools.js";
import { initializeExperimentTools } from "@arizeai/phoenix-mcp/build/experimentTools.js";
import { initializeProjectTools } from "@arizeai/phoenix-mcp/build/projectTools.js";
import { initializePromptTools } from "@arizeai/phoenix-mcp/build/promptTools.js";
import { initializeSessionTools } from "@arizeai/phoenix-mcp/build/sessionTools.js";
import { initializeSpanTools } from "@arizeai/phoenix-mcp/build/spanTools.js";
import { initializeSupportTools } from "@arizeai/phoenix-mcp/build/supportTools.js";
import { initializeTraceTools } from "@arizeai/phoenix-mcp/build/traceTools.js";
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";
import cors from "cors";

/** @typedef {import('@modelcontextprotocol/sdk/server/streamableHttp.js').EventStore} EventStore */

/** Minimal in-memory event store for MCP session resumability. */
class InMemoryEventStore {
  constructor() {
    /** @type {Map<string, { streamId: string, message: unknown }>} */
    this.events = new Map();
  }

  generateEventId(streamId) {
    return `${streamId}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }

  getStreamIdFromEventId(eventId) {
    const parts = eventId.split("_");
    return parts.length > 0 ? parts[0] : "";
  }

  async storeEvent(streamId, message) {
    const eventId = this.generateEventId(streamId);
    this.events.set(eventId, { streamId, message });
    return eventId;
  }

  async replayEventsAfter(lastEventId, { send }) {
    if (!lastEventId || !this.events.has(lastEventId)) {
      return "";
    }
    const streamId = this.getStreamIdFromEventId(lastEventId);
    if (!streamId) {
      return "";
    }
    let foundLastEvent = false;
    const sortedEvents = [...this.events.entries()].sort((a, b) =>
      a[0].localeCompare(b[0]),
    );
    for (const [eventId, { streamId: eventStreamId, message }] of sortedEvents) {
      if (eventStreamId !== streamId) {
        continue;
      }
      if (eventId === lastEventId) {
        foundLastEvent = true;
        continue;
      }
      if (foundLastEvent) {
        await send(eventId, message);
      }
    }
    return streamId;
  }
}

function phoenixHostFromEnv() {
  return (
    process.env.PHOENIX_HOST ||
    process.env.PHOENIX_COLLECTOR_ENDPOINT ||
    ""
  ).replace(/\/$/, "");
}

const config = resolveConfig({ commandLineOptions: {} });
if (phoenixHostFromEnv()) {
  config.baseUrl = phoenixHostFromEnv();
}
if (!config.apiKey && process.env.PHOENIX_API_KEY) {
  config.apiKey = process.env.PHOENIX_API_KEY;
}
if (!config.project && process.env.PHOENIX_PROJECT_NAME) {
  config.project = process.env.PHOENIX_PROJECT_NAME;
}

if (!config.baseUrl || !config.apiKey) {
  console.error(
    "Missing Phoenix config: set PHOENIX_API_KEY and PHOENIX_HOST " +
      "(or PHOENIX_COLLECTOR_ENDPOINT).",
  );
  process.exit(1);
}

const client = createPhoenixClient({ config });

function buildPhoenixMcpServer() {
  const server = new McpServer({
    name: "phoenix-mcp-server",
    version: "1.1.0",
  });
  initializePromptTools({ client, server });
  initializeExperimentTools({ client, server });
  initializeDatasetTools({ client, server });
  initializeProjectTools({ client, server });
  initializeTraceTools({ client, server, defaultProject: config.project });
  initializeSpanTools({ client, server, defaultProject: config.project });
  initializeSessionTools({ client, server, defaultProject: config.project });
  initializeAnnotationConfigTools({ client, server });
  initializeSupportTools({ server });
  return server;
}

const MCP_SERVICE_API_KEY = process.env.MCP_SERVICE_API_KEY || "";
const PORT = Number.parseInt(process.env.PORT || "8080", 10);

// Cloud Run: bind 0.0.0.0 without DNS rebinding filter (platform handles routing).
const app = createMcpExpressApp({ host: "0.0.0.0" });

app.use(
  cors({
    exposedHeaders: [
      "WWW-Authenticate",
      "Mcp-Session-Id",
      "Last-Event-Id",
      "Mcp-Protocol-Version",
    ],
    origin: "*",
  }),
);

app.get("/health", (_req, res) => {
  res.json({ status: "healthy", service: "phoenix-mcp-http" });
});

function requireServiceAuth(req, res, next) {
  if (!MCP_SERVICE_API_KEY) {
    next();
    return;
  }
  const auth = req.headers.authorization || "";
  if (auth === `Bearer ${MCP_SERVICE_API_KEY}`) {
    next();
    return;
  }
  res.status(401).json({ error: "unauthorized" });
}

/** @type {Record<string, StreamableHTTPServerTransport>} */
const transports = {};

const mcpPostHandler = async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  try {
    let transport;
    if (sessionId && transports[sessionId]) {
      transport = transports[sessionId];
    } else if (!sessionId && isInitializeRequest(req.body)) {
      const eventStore = new InMemoryEventStore();
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        eventStore,
        onsessioninitialized: (sid) => {
          transports[sid] = transport;
        },
      });
      transport.onclose = () => {
        const sid = transport.sessionId;
        if (sid && transports[sid]) {
          delete transports[sid];
        }
      };
      const server = buildPhoenixMcpServer();
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
      return;
    } else if (sessionId) {
      res.status(404).json({
        jsonrpc: "2.0",
        error: { code: -32001, message: "Session not found" },
        id: null,
      });
      return;
    } else {
      res.status(400).json({
        jsonrpc: "2.0",
        error: { code: -32000, message: "Bad Request: Session ID required" },
        id: null,
      });
      return;
    }
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error("MCP POST error:", error);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: "2.0",
        error: { code: -32603, message: "Internal server error" },
        id: null,
      });
    }
  }
};

const mcpGetHandler = async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  if (!sessionId || !transports[sessionId]) {
    res.status(400).send("Invalid or missing session ID");
    return;
  }
  await transports[sessionId].handleRequest(req, res);
};

const mcpDeleteHandler = async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  if (!sessionId || !transports[sessionId]) {
    res.status(404).send("Session not found");
    return;
  }
  await transports[sessionId].handleRequest(req, res);
};

app.post("/mcp", requireServiceAuth, mcpPostHandler);
app.get("/mcp", requireServiceAuth, mcpGetHandler);
app.delete("/mcp", requireServiceAuth, mcpDeleteHandler);

app.listen(PORT, "0.0.0.0", () => {
  console.error(
    `Phoenix MCP Streamable HTTP listening on :${PORT}/mcp ` +
      `(Phoenix: ${config.baseUrl})`,
  );
});
