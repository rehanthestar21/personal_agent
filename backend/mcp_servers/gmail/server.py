import base64
import sys
from email.mime.text import MIMEText
from pathlib import Path

from googleapiclient.discovery import build
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).parent.parent))
from google_auth import get_google_creds

server = Server("gmail")

_service = None


def _get_service():
    global _service
    if not _service:
        creds = get_google_creds()
        _service = build("gmail", "v1", credentials=creds)
    return _service


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_inbox",
            description="Read recent emails from the inbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of emails to fetch. Default 5."},
                    "query": {"type": "string", "description": "Optional search query (e.g. 'from:prof@ucl.ac.uk', 'is:unread', 'subject:assignment')"},
                },
            },
        ),
        Tool(
            name="send_email",
            description="Send an email.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                },
                "required": ["to", "subject", "body"],
            },
        ),
        Tool(
            name="reply_to_email",
            description="Reply to the most recent email matching a search query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query to find the email to reply to"},
                    "body": {"type": "string", "description": "Reply text"},
                },
                "required": ["query", "body"],
            },
        ),
        Tool(
            name="search_emails",
            description="Search emails with a query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query"},
                    "count": {"type": "integer", "description": "Number of results. Default 5."},
                },
                "required": ["query"],
            },
        ),
    ]


def _get_email_snippet(svc, msg_id: str) -> dict:
    msg = svc.users().messages().get(userId="me", id=msg_id, format="metadata",
                                      metadataHeaders=["From", "Subject", "Date"]).execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "from": headers.get("From", "Unknown"),
        "subject": headers.get("Subject", "No subject"),
        "date": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
        "threadId": msg.get("threadId", ""),
    }


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    svc = _get_service()

    if name == "read_inbox":
        count = arguments.get("count", 5)
        query = arguments.get("query", "")
        q = query if query else "in:inbox"

        results = svc.users().messages().list(userId="me", q=q, maxResults=count).execute()
        messages = results.get("messages", [])

        if not messages:
            return [TextContent(type="text", text="No emails found.")]

        lines = []
        for m in messages:
            info = _get_email_snippet(svc, m["id"])
            lines.append(f"From: {info['from']}\nSubject: {info['subject']}\n{info['snippet']}\n")

        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "send_email":
        to = arguments["to"]
        subject = arguments["subject"]
        body = arguments["body"]

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return [TextContent(type="text", text=f"Email sent to {to}: {subject}")]

    elif name == "reply_to_email":
        query = arguments["query"]
        body = arguments["body"]

        results = svc.users().messages().list(userId="me", q=query, maxResults=1).execute()
        messages = results.get("messages", [])
        if not messages:
            return [TextContent(type="text", text=f"No email found matching '{query}'")]

        original = svc.users().messages().get(userId="me", id=messages[0]["id"], format="metadata",
                                               metadataHeaders=["From", "Subject", "Message-ID"]).execute()
        headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}

        reply = MIMEText(body)
        reply["to"] = headers.get("From", "")
        reply["subject"] = "Re: " + headers.get("Subject", "")
        reply["In-Reply-To"] = headers.get("Message-ID", "")
        reply["References"] = headers.get("Message-ID", "")

        raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={
            "raw": raw,
            "threadId": original.get("threadId", ""),
        }).execute()
        return [TextContent(type="text", text=f"Replied to: {headers.get('Subject', query)}")]

    elif name == "search_emails":
        query = arguments["query"]
        count = arguments.get("count", 5)

        results = svc.users().messages().list(userId="me", q=query, maxResults=count).execute()
        messages = results.get("messages", [])

        if not messages:
            return [TextContent(type="text", text=f"No emails matching '{query}'")]

        lines = []
        for m in messages:
            info = _get_email_snippet(svc, m["id"])
            lines.append(f"From: {info['from']} | Subject: {info['subject']} | {info['snippet'][:80]}")

        return [TextContent(type="text", text="\n".join(lines))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
