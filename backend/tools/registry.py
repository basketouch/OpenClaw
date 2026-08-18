import asyncio
from typing import Any, Callable, Iterable

_registry: dict[str, dict] = {}


def register(name: str, func: Callable, definition: dict) -> None:
    _registry[name] = {"func": func, "definition": definition}


def get_tool_definitions(names: Iterable[str] | None = None) -> list[dict]:
    if names is None:
        return [entry["definition"] for entry in _registry.values()]
    allowed = set(names)
    return [entry["definition"] for name, entry in _registry.items() if name in allowed]


def get_openai_tool_definitions(names: Iterable[str] | None = None) -> list[dict]:
    """Convierte las definiciones internas al formato nativo de Responses API."""
    tools = []
    for definition in get_tool_definitions(names):
        tools.append({
            "type": "function",
            "name": definition["name"],
            "description": definition.get("description", ""),
            "parameters": definition.get("input_schema", {"type": "object", "properties": {}}),
            "strict": False,
        })
    return tools


async def execute_tool(name: str, inputs: dict) -> Any:
    if name not in _registry:
        return f"Tool '{name}' no encontrado"
    func = _registry[name]["func"]
    if asyncio.iscoroutinefunction(func):
        return await func(**inputs)
    return func(**inputs)


# Perfiles: cada petición recibe solo las herramientas relevantes.
TOOL_PROFILES: dict[str, set[str]] = {
    "general": {
        "get_datetime", "list_workspace_files", "read_workspace_file", "write_workspace_file",
        "web_search", "list_scheduled_tasks", "create_scheduled_task",
        "delete_scheduled_task", "toggle_scheduled_task",
    },
    "communications": {
        "get_datetime", "list_email_accounts", "list_emails", "search_emails", "read_email",
        "send_email", "reply_email", "send_whatsapp_message", "send_whatsapp_voice",
        "whatsapp_status", "list_whatsapp_contacts", "search_whatsapp_contacts", "send_telegram",
    },
    "newsflow": {
        "get_datetime", "query_newsflow", "insert_newsflow", "update_newsflow", "web_search",
    },
    "admin": {
        "get_datetime", "list_workspace_files", "read_workspace_file", "write_workspace_file",
        "run_shell", "host_shell",
    },
}


def get_profile_tools(profile: str) -> list[dict]:
    return get_openai_tool_definitions(TOOL_PROFILES.get(profile, TOOL_PROFILES["general"]))


# Register built-in tools
from tools.datetime_tool import DEFINITION as DATETIME_DEF
from tools.datetime_tool import get_datetime
from tools.workspace_tool import LIST_DEF, READ_DEF, WRITE_DEF
from tools.workspace_tool import list_workspace_files, read_workspace_file, write_workspace_file
from tools.email_tool import (
    LIST_EMAILS_DEF, SEARCH_EMAILS_DEF, READ_EMAIL_DEF,
    SEND_EMAIL_DEF, REPLY_EMAIL_DEF, LIST_ACCOUNTS_DEF,
    list_emails, search_emails, read_email,
    send_email, reply_email, list_email_accounts,
)
from tools.whatsapp_tool import (
    SEND_MSG_DEF, SEND_VOICE_DEF, WA_STATUS_DEF, LIST_WA_CONTACTS_DEF, SEARCH_WA_CONTACTS_DEF,
    send_whatsapp_message, send_whatsapp_voice, whatsapp_status, list_whatsapp_contacts,
    search_whatsapp_contacts,
)
from tools.admin_tool import SHELL_DEF, HOST_SHELL_DEF, run_shell, run_host_shell
from tools.telegram_tool import SEND_TELEGRAM_DEF, send_telegram
from tools.supabase_tool import (
    QUERY_DEF as NF_QUERY_DEF, INSERT_DEF as NF_INSERT_DEF, UPDATE_DEF as NF_UPDATE_DEF,
    query_newsflow, insert_newsflow, update_newsflow,
)
from tools.search_tool import SEARCH_DEF, web_search
from tools.scheduler_tool import (
    CREATE_DEF as SCHED_CREATE_DEF,
    LIST_DEF as SCHED_LIST_DEF,
    DELETE_DEF as SCHED_DELETE_DEF,
    TOGGLE_DEF as SCHED_TOGGLE_DEF,
    create_scheduled_task, list_scheduled_tasks, delete_scheduled_task, toggle_scheduled_task,
)

register("get_datetime", get_datetime, DATETIME_DEF)
register("list_workspace_files", list_workspace_files, LIST_DEF)
register("read_workspace_file", read_workspace_file, READ_DEF)
register("write_workspace_file", write_workspace_file, WRITE_DEF)
register("list_email_accounts", list_email_accounts, LIST_ACCOUNTS_DEF)
register("list_emails", list_emails, LIST_EMAILS_DEF)
register("search_emails", search_emails, SEARCH_EMAILS_DEF)
register("read_email", read_email, READ_EMAIL_DEF)
register("send_email", send_email, SEND_EMAIL_DEF)
register("reply_email", reply_email, REPLY_EMAIL_DEF)
register("send_whatsapp_message", send_whatsapp_message, SEND_MSG_DEF)
register("send_whatsapp_voice", send_whatsapp_voice, SEND_VOICE_DEF)
register("whatsapp_status", whatsapp_status, WA_STATUS_DEF)
register("list_whatsapp_contacts", list_whatsapp_contacts, LIST_WA_CONTACTS_DEF)
register("search_whatsapp_contacts", search_whatsapp_contacts, SEARCH_WA_CONTACTS_DEF)
register("run_shell", run_shell, SHELL_DEF)
register("host_shell", run_host_shell, HOST_SHELL_DEF)
register("send_telegram", send_telegram, SEND_TELEGRAM_DEF)
register("query_newsflow", query_newsflow, NF_QUERY_DEF)
register("insert_newsflow", insert_newsflow, NF_INSERT_DEF)
register("update_newsflow", update_newsflow, NF_UPDATE_DEF)
register("web_search", web_search, SEARCH_DEF)
register("create_scheduled_task", create_scheduled_task, SCHED_CREATE_DEF)
register("list_scheduled_tasks", list_scheduled_tasks, SCHED_LIST_DEF)
register("delete_scheduled_task", delete_scheduled_task, SCHED_DELETE_DEF)
register("toggle_scheduled_task", toggle_scheduled_task, SCHED_TOGGLE_DEF)
