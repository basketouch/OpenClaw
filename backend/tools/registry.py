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
