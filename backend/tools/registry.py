import asyncio
from typing import Any, Callable

_registry: dict[str, dict] = {}


def register(name: str, func: Callable, definition: dict) -> None:
    _registry[name] = {"func": func, "definition": definition}


def get_tool_definitions() -> list[dict]:
    return [entry["definition"] for entry in _registry.values()]


async def execute_tool(name: str, inputs: dict) -> Any:
    if name not in _registry:
        return f"Tool '{name}' no encontrado"
    func = _registry[name]["func"]
    if asyncio.iscoroutinefunction(func):
        return await func(**inputs)
    return func(**inputs)


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
from tools.admin_tool import SHELL_DEF, run_shell
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
register("create_scheduled_task", create_scheduled_task, SCHED_CREATE_DEF)
register("list_scheduled_tasks", list_scheduled_tasks, SCHED_LIST_DEF)
register("delete_scheduled_task", delete_scheduled_task, SCHED_DELETE_DEF)
register("toggle_scheduled_task", toggle_scheduled_task, SCHED_TOGGLE_DEF)
