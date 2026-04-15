import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import express from "express";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = path.join(__dirname, "auth_state");
const PORT = parseInt(process.env.WA_BRIDGE_PORT || "9777");
const VERTEX_BACKEND_URL = (process.env.VERTEX_BACKEND_URL || "http://localhost:9000").replace(/\/$/, "");
const MAX_MESSAGES_PER_CHAT = 100;

let sock = null;
let connectionReady = false;

/** Real-time message store: messages received while bridge is running. Fixes poor retrieval of very recent messages (e.g. 10 seconds ago). */
const messageStore = new Map(); // jid -> [{ from, text, timestamp, id }]

function storeMessage(m, contactHint) {
  const jid = m.key?.remoteJid || m.key?.participant;
  if (!jid) return;
  const text = m.message?.conversation || m.message?.extendedTextMessage?.text || "[media]";
  const from = m.key.fromMe ? "me" : (m.pushName || contactHint || "unknown");
  const id = m.key?.id;
  const timestamp = m.messageTimestamp;
  if (!id) return;
  let list = messageStore.get(jid) || [];
  if (list.some((x) => x.id === id)) return;
  list.unshift({ from, text, timestamp, id });
  list = list.slice(0, MAX_MESSAGES_PER_CHAT);
  messageStore.set(jid, list);
}

async function startWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    defaultQueryTimeoutMs: 60000,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("messages.upsert", ({ messages, type }) => {
    for (const m of messages || []) {
      storeMessage(m);
      if (!m.key?.fromMe && m.key?.id) {
        const jid = m.key?.remoteJid || m.key?.participant;
        const text = m.message?.conversation || m.message?.extendedTextMessage?.text || "[media]";
        const fromName = m.pushName || "unknown";
        notifyVertexIncoming(jid, fromName, text, m.key.id, m.messageTimestamp);
      }
    }
  });

  sock.ev.on("messaging-history.set", ({ messages }) => {
    for (const m of messages || []) {
      storeMessage(m);
    }
  });

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log("\n[WhatsApp] Scan this QR code with your phone:\n");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "open") {
      connectionReady = true;
      console.log("[WhatsApp] Connected.");
    }
    if (connection === "close") {
      connectionReady = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code !== DisconnectReason.loggedOut) {
        console.log("[WhatsApp] Reconnecting...");
        startWhatsApp();
      } else {
        console.log("[WhatsApp] Logged out. Delete auth_state/ and restart to re-scan.");
      }
    }
  });
}

function notifyVertexIncoming(jid, fromName, text, id, timestamp) {
  const url = `${VERTEX_BACKEND_URL}/api/v1/whatsapp/incoming`;
  const body = JSON.stringify({ jid, from: fromName, text, id, timestamp: timestamp || null });
  console.log("[Bridge] notifying Vertex: from=%s jid=%s", fromName, jid);
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  })
    .then((res) => {
      if (!res.ok) console.error("[Bridge] vertex webhook HTTP %s", res.status);
    })
    .catch((err) => console.error("[Bridge] vertex webhook failed:", err.message));
}

async function findJid(nameOrNumber) {
  if (nameOrNumber.includes("@")) return nameOrNumber;

  const digits = nameOrNumber.replace(/[^0-9]/g, "");
  if (digits.length >= 7) {
    return `${digits}@s.whatsapp.net`;
  }

  const lower = nameOrNumber.toLowerCase();

  if (sock) {
    try {
      const groups = await sock.groupFetchAllParticipating();
      for (const [jid, group] of Object.entries(groups)) {
        if (group.subject?.toLowerCase().includes(lower)) return jid;
      }
    } catch {}
  }

  return null;
}

const app = express();
app.use(express.json());

app.get("/status", (req, res) => {
  res.json({ connected: connectionReady });
});

app.post("/send", async (req, res) => {
  const { contact, message } = req.body;
  if (!connectionReady) return res.status(503).json({ error: "WhatsApp not connected" });
  if (!contact || !message) return res.status(400).json({ error: "contact and message required" });

  const jid = await findJid(contact);
  if (!jid) return res.status(404).json({ error: `Contact not found: ${contact}` });

  try {
    await sock.sendMessage(jid, { text: message });
    res.json({ ok: true, jid });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/read", async (req, res) => {
  const { contact, count = 5 } = req.body;
  if (!connectionReady) return res.status(503).json({ error: "WhatsApp not connected" });

  const jid = await findJid(contact);
  if (!jid) return res.status(404).json({ error: `Contact not found: ${contact}` });

  const list = messageStore.get(jid) || [];
  const formatted = list.slice(0, Math.max(1, count)).map((m) => ({
    from: m.from,
    text: m.text,
    timestamp: m.timestamp,
    id: m.id,
  }));

  if (formatted.length > 0) {
    return res.json({ jid, messages: formatted });
  }

  res.json({
    jid,
    messages: [],
    note: "No messages yet. Messages are stored as they arrive while the bridge is running. Ask again after receiving a new message, or ensure the bridge was running when the message was sent.",
  });
});

app.get("/contacts", async (req, res) => {
  if (!connectionReady) return res.status(503).json({ error: "WhatsApp not connected" });

  try {
    const groups = await sock.groupFetchAllParticipating();
    const groupList = Object.entries(groups).map(([jid, g]) => ({
      jid,
      name: g.subject,
      type: "group",
    }));
    res.json({ contacts: groupList, note: "For individuals, use their phone number with country code." });
  } catch (e) {
    res.json({ contacts: [], error: e.message });
  }
});

app.listen(PORT, () => {
  console.log(`[WhatsApp Bridge] HTTP API on port ${PORT}`);
  startWhatsApp();
});
