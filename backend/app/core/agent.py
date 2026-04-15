import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools.base import ToolException
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.config import Settings
from app.core.delegation import DelegationService
from app.core.mcp_host import MCPHost
from app.core.memory import MemoryStore
from app.core.prompts import CONTACTS, build_delegated_system_prompt, build_system_prompt

logger = logging.getLogger("vertex.agent")

VERTEX_SIGNATURE = " sent by Vertex"


def _wrap_send_message_tool(original_tool: StructuredTool) -> StructuredTool:
    """Wrap whatsapp__send_message so every message gets ' sent by Vertex' appended."""

    async def _send_with_signature(contact: str, message: str) -> str:
        signed = (message or "").strip()
        if not signed.endswith(VERTEX_SIGNATURE):
            signed = signed + VERTEX_SIGNATURE
        return await original_tool.ainvoke({"contact": contact, "message": signed})

    return StructuredTool.from_function(
        name=original_tool.name,
        description=original_tool.description,
        coroutine=_send_with_signature,
        args_schema=original_tool.args_schema,
    )


class VertexAgent:
    """LangGraph ReAct agent with long-term memory and MCP tools.
    
    Short-term memory (conversation history) resets each backend restart.
    Long-term memory (facts, preferences) persists in SQLite forever.
    """

    def __init__(
        self,
        settings: Settings,
        mcp_host: MCPHost,
        delegation_service: DelegationService | None = None,
    ) -> None:
        self._settings = settings
        self._mcp = mcp_host
        self._delegation_service = delegation_service
        self._checkpointer = MemorySaver()
        self._memory = MemoryStore(settings)
        # Set by process_delegated_message for the duration of the run so escalate_to_user knows the contact
        self._current_delegated_contact: tuple[str, str] | None = None  # (contact_name, contact_jid)

        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        )

        self._graph = None
        self._delegated_graph = None
        self._delegated_checkpointer = MemorySaver()  # separate from main so delegated threads stay isolated

    def _get_main_tools(self) -> list:
        tools = list(self._mcp.get_tools())
        if self._delegation_service:
            ds = self._delegation_service

            async def _delegate(contact: str) -> str:
                ds.activate(contact)
                asyncio.create_task(self._take_over_latest_message(contact))
                return f"Done. I'll now respond to {contact}'s WhatsApp messages. Replying to their latest message now; each reply will be signed 'sent by Vertex'."

            async def _undelegate(contact: str) -> str:
                ds.deactivate(contact)
                return f"Stopped responding to {contact}'s messages."

            tools.append(
                StructuredTool.from_function(
                    name="delegate_conversation",
                    description="Start responding to a contact's WhatsApp messages on the user's behalf. Use when the user says e.g. 'respond to Keya's messages' or 'handle Keya's WhatsApp'. Call with the contact name (e.g. Keya).",
                    coroutine=_delegate,
                )
            )
            async def _clear_escalation(contact: str) -> str:
                ds.clear_escalation(contact)
                return f"Escalation cleared for {contact}. I'll resume responding to their messages when they write."

            tools.append(
                StructuredTool.from_function(
                    name="undelegate_conversation",
                    description="Stop responding to a contact's WhatsApp messages. Use when the user says to stop handling that contact.",
                    coroutine=_undelegate,
                )
            )
            tools.append(
                StructuredTool.from_function(
                    name="clear_escalation",
                    description="Resume auto-responding to a contact after they asked for the user. Use when the user says e.g. 'resume responding to Keya' or 'I've got it, you can handle Keya again'. Call with the contact name (e.g. Keya).",
                    coroutine=_clear_escalation,
                )
            )
        return tools

    def _get_delegated_tools(self) -> list:
        base = self._mcp.get_tools()
        out = []
        for t in base:
            if t.name == "whatsapp__send_message":
                out.append(_wrap_send_message_tool(t))
            else:
                out.append(t)
        if self._delegation_service:

            async def _escalate_to_user(reason: str) -> str:
                cur = self._current_delegated_contact
                if not cur:
                    return "No active delegated conversation to escalate."
                contact_name, contact_jid = cur
                esc_id = self._delegation_service.set_escalated(contact_jid, contact_name, reason)
                if esc_id is not None:
                    try:
                        from app.core import fcm
                        await asyncio.to_thread(
                            fcm.send_escalation_push_if_configured,
                            contact_name,
                            reason,
                            esc_id,
                            self._settings.firebase_credentials_path or "",
                        )
                    except Exception as e:
                        logger.warning("fcm escalation push failed: %s", e)
                return (
                    f"Escalated to {self._settings.vertex_user_name}. Reason: {reason}. "
                    "They will be notified and will take over the conversation. Do not send further automated replies to this contact until they resume."
                )

            out.append(
                StructuredTool.from_function(
                    name="escalate_to_user",
                    description=(
                        "Use when the contact says they want to talk to the user directly, "
                        "or want the user to take over, or to contact the user. Call with a short reason (e.g. 'Keya wants to talk to Rehan directly'). "
                        "This notifies the user and stops automated replies until they resume."
                    ),
                    coroutine=_escalate_to_user,
                )
            )
        return out

    def _ensure_graph(self):
        tools = self._get_main_tools()
        self._graph = create_react_agent(
            self._llm,
            tools=tools,
            checkpointer=self._checkpointer,
        )
        logger.info("[agent] graph built with %d tools", len(tools))

    def _ensure_delegated_graph(self):
        if self._delegated_graph is not None:
            return
        tools = self._get_delegated_tools()
        self._delegated_graph = create_react_agent(
            self._llm,
            tools=tools,
            checkpointer=self._delegated_checkpointer,
        )
        logger.info("[agent] delegated graph built with %d tools", len(tools))

    async def process_stream(self, transcript: str, session_id: str | None = None) -> AsyncGenerator[dict, None]:
        if not self._graph:
            self._ensure_graph()

        now = datetime.now(timezone.utc).strftime("%A %B %d, %Y at %H:%M UTC")

        memory_summary = self._memory.get_memory_summary(max_chars=3000)
        system_prompt = build_system_prompt(
            self._settings.vertex_user_name,
            self._settings.vertex_user_location,
            now,
            memory_summary=memory_summary,
            github_username=self._settings.github_username,
        )

        config = {"configurable": {"thread_id": session_id or "default"}}

        existing = self._graph.get_state(config)
        has_history = existing.values and existing.values.get("messages")

        if has_history:
            messages = [HumanMessage(content=transcript)]
        else:
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=transcript)]

        logger.info("[agent] processing: \"%s\" session=%s has_history=%s memories=%d",
                     transcript, session_id, has_history, len(memory_summary))
        yield {"type": "status", "message": "Thinking..."}

        tools_used: list[str] = []
        last_reply = ""

        for attempt in range(2):
            try:
                logger.info("[agent] starting astream_events (attempt %d)", attempt + 1)
                async for event in self._graph.astream_events(
                    {"messages": messages},
                    config=config,
                    version="v2",
                ):
                    kind = event.get("event", "")

                    if kind == "on_chat_model_start":
                        logger.info("[agent] AI started thinking...")
                    
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "")
                        display_name = tool_name.replace("__", " → ")
                        tools_used.append(tool_name)
                        logger.info("[agent] tool_call: %s", tool_name)
                        yield {"type": "status", "message": f"Calling {display_name}..."}

                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "")
                        display_name = tool_name.replace("__", " → ")
                        output = event.get("data", {}).get("output", "")
                        logger.info("[agent] tool_result: %s (%d chars)", tool_name, len(str(output)))
                        yield {"type": "status", "message": f"{display_name} responded"}

                    elif kind == "on_chat_model_end":
                        output = event.get("data", {}).get("output", None)
                        if output and isinstance(output, AIMessage) and output.content and not output.tool_calls:
                            last_reply = output.content

                break

            except (ValueError, ToolException, Exception) as e:
                if isinstance(e, ValueError) and attempt == 0 and "tool_calls" in str(e):
                    logger.warning("[agent] corrupted history, resetting session=%s", session_id)
                    self._graph = None
                    self._ensure_graph()
                    messages = [SystemMessage(content=system_prompt), HumanMessage(content=transcript)]
                    config = {"configurable": {"thread_id": f"{session_id}_reset"}}
                    yield {"type": "status", "message": "Recovering..."}
                    continue
                
                if isinstance(e, (ToolException, Exception)) and attempt == 0:
                    logger.warning("[agent] tool or execution error, retrying session=%s: %s", session_id, e)
                    yield {"type": "status", "message": "Retrying after error..."}
                    continue
                
                raise

        if last_reply:
            logger.info("[agent] final reply (%d chars): %s", len(last_reply), last_reply[:150])
            yield {"type": "status", "message": "Generating speech..."}
            yield {
                "type": "result",
                "reply": last_reply,
                "tools_used": tools_used,
                "session_id": session_id,
            }

            conversation = f"User: {transcript}\nAssistant: {last_reply}"
            asyncio.create_task(self._memory.extract_and_store(conversation))
        else:
            logger.warning("[agent] no reply generated")
            msg = "I hit a technical hiccup. Can you repeat your request again?"
            yield {
                "type": "result",
                "reply": msg,
                "tools_used": tools_used,
                "session_id": session_id,
            }

    async def process_delegated_message(
        self,
        contact_name: str,
        contact_jid: str,
        message_text: str,
        message_id: str,
    ) -> None:
        """Run the side agent for one incoming WhatsApp message from a delegated contact."""
        if not self._delegation_service:
            logger.warning("[delegated] no delegation service")
            return
        self._ensure_delegated_graph()
        now = datetime.now(timezone.utc).strftime("%A %B %d, %Y at %H:%M UTC")
        system_prompt = build_delegated_system_prompt(
            self._settings.vertex_user_name,
            self._settings.vertex_user_location,
            now,
            contact_name=contact_name,
        )
        thread_id = self._delegation_service.get_thread_id(contact_jid)
        config = {"configurable": {"thread_id": thread_id}}
        existing = self._delegated_graph.get_state(config)
        has_history = bool(existing.values and existing.values.get("messages"))
        if has_history:
            messages = [HumanMessage(content=message_text)]
        else:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=message_text),
            ]
        logger.info("[delegated] processing from %s (jid=%s) thread=%s len=%d", contact_name, contact_jid, thread_id, len(message_text))
        self._current_delegated_contact = (contact_name, contact_jid)
        try:
            result = await self._delegated_graph.ainvoke({"messages": messages}, config=config)
            self._maybe_send_delegated_final_reply(contact_name, contact_jid, result)
        except ValueError as e:
            err_str = str(e)
            if "tool_calls" in err_str and ("ToolMessage" in err_str or "INVALID_CHAT_HISTORY" in err_str):
                logger.warning("[delegated] corrupted thread %s, retrying with fresh thread", thread_id)
                self._delegation_service.set_thread_id_override(contact_jid, f"delegated_{contact_jid}_{message_id}")
                fresh_config = {"configurable": {"thread_id": self._delegation_service.get_thread_id(contact_jid)}}
                fresh_messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message_text),
                ]
                result = await self._delegated_graph.ainvoke({"messages": fresh_messages}, config=fresh_config)
                await self._maybe_send_delegated_final_reply(contact_name, contact_jid, result)
            else:
                logger.exception("[delegated] error: %s", e)
                await self._send_delegated_fallback(contact_name, contact_jid)
        except (ToolException, Exception) as e:
            logger.exception("[delegated] error: %s", e)
            await self._send_delegated_fallback(contact_name, contact_jid)
        finally:
            self._current_delegated_contact = None
            self._delegation_service.mark_processed(contact_jid, message_id)

    def _resolve_contact_for_bridge(self, contact: str) -> str:
        """Resolve a name (e.g. Keya) to a number so the bridge's findJid can resolve it."""
        key = (contact or "").strip().lower()
        if key in CONTACTS:
            return CONTACTS[key]
        return contact

    async def _take_over_latest_message(self, contact: str) -> None:
        """After activating delegation, fetch the contact's latest message and reply immediately (real take-over)."""
        if not self._delegation_service or not self._delegation_service.is_active():
            return
        base = (self._settings.whatsapp_bridge_url or "").rstrip("/")
        if not base:
            return
        contact_for_bridge = self._resolve_contact_for_bridge(contact)
        url = f"{base}/read"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json={"contact": contact_for_bridge, "count": 10})
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("[take_over] failed to fetch last message for %s: %s", contact, e)
            return
        jid = data.get("jid")
        if not jid and contact_for_bridge:
            digits = re.sub(r"[^0-9]", "", contact_for_bridge)
            if len(digits) >= 7:
                jid = f"{digits}@s.whatsapp.net"
        if not jid:
            logger.warning("[take_over] no jid for %s, skipping", contact)
            return
        messages = data.get("messages") or []
        # First message from the contact (not from me)
        for m in messages:
            if (m.get("from") or "").lower() == "me":
                continue
            text = (m.get("text") or "").strip()
            msg_id = m.get("id") or f"takeover_{jid}_{id(m)}"
            if not text:
                continue
            contact_name = m.get("from") or contact
            logger.info("[take_over] replying to latest from %s (jid=%s) len=%d", contact_name, jid, len(text))
            await self.process_delegated_message(
                contact_name=contact_name,
                contact_jid=jid,
                message_text=text,
                message_id=msg_id,
            )
            return
        logger.info("[take_over] no incoming message from %s to reply to", contact)

    async def _maybe_send_delegated_final_reply(
        self, contact_name: str, contact_jid: str, invoke_result: dict,
    ) -> None:
        """If the delegated agent returned a text reply but did not call send_message, send that text to the contact."""
        messages = invoke_result.get("messages") if isinstance(invoke_result, dict) else None
        if not messages:
            return
        try:
            msg_list = list(messages) if not isinstance(messages, list) else messages
        except Exception:
            return
        send_message_used = False
        last_ai_content = None
        for m in msg_list:
            if isinstance(m, AIMessage):
                content = m.content
                if isinstance(content, str) and content.strip():
                    last_ai_content = content.strip()
                tc = getattr(m, "tool_calls", None) or []
                for t in tc:
                    if isinstance(t, dict) and t.get("name") == "whatsapp__send_message":
                        send_message_used = True
                        break
                    if getattr(t, "name", None) == "whatsapp__send_message":
                        send_message_used = True
                        break
        if send_message_used or not last_ai_content:
            return
        logger.info("[delegated] sending agent's final text to %s (no send_message call)", contact_name)
        await self._send_delegated_text(contact_name, last_ai_content)

    async def _send_delegated_fallback(self, contact_name: str, contact_jid: str) -> None:
        """Send a short fallback WhatsApp message when the delegated run crashes so the contact isn't left with no reply."""
        message = "Sorry, I hit a technical hiccup with that. Can you try again? sent by Vertex"
        await self._send_delegated_text(contact_name, message)

    async def _send_delegated_text(self, contact_name: str, text: str) -> None:
        """Send a WhatsApp message to the delegated contact via the bridge. Appends signature if missing."""
        base = (self._settings.whatsapp_bridge_url or "").rstrip("/")
        if not base:
            logger.warning("[delegated] no bridge URL, cannot send text")
            return
        msg = (text or "").strip()
        if msg and not msg.endswith(VERTEX_SIGNATURE):
            msg = msg + VERTEX_SIGNATURE
        if not msg:
            return
        url = f"{base}/send"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={"contact": contact_name, "message": msg})
            logger.info("[delegated] sent text to %s len=%d", contact_name, len(msg))
        except Exception as e:
            logger.warning("[delegated] send failed: %s", e)
