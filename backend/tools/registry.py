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


_ENGLISH_COACH_TOOLS = {
    "save_english_phrase", "search_english_phrases", "get_english_review",
    "record_english_result", "get_english_progress",
}


TOOL_PROFILES: dict[str, set[str]] = {
    "general": {
        "get_datetime",
        "web_search", "list_scheduled_tasks", "create_scheduled_task",
        "delete_scheduled_task", "toggle_scheduled_task",
        "search_notion", "read_notion_page", "append_notion_note",
        "query_notion_actions", "upsert_notion_action",
    } | _ENGLISH_COACH_TOOLS,
    "communications": {
        "get_datetime", "list_email_accounts", "list_emails", "search_emails", "read_email",
        "send_email", "reply_email", "send_telegram",
    } | _ENGLISH_COACH_TOOLS,
    "newsflow": {
        "get_datetime", "query_newsflow", "insert_newsflow", "update_newsflow", "web_search",
    } | _ENGLISH_COACH_TOOLS,
    "admin": {
        "get_datetime", "list_workspace_files", "read_workspace_file", "write_workspace_file",
        "run_shell", "host_shell",
    } | _ENGLISH_COACH_TOOLS,
    "english": {
        "get_datetime", "save_english_phrase", "search_english_phrases", "get_english_review",
        "record_english_result", "get_english_progress",
        "search_notion", "read_notion_page", "create_notion_page",
    } | _ENGLISH_COACH_TOOLS,
    "hornbills": {
        "get_datetime", "search_notion", "read_notion_page", "get_hornbills_hub", "get_hornbills_destinations",
        "read_notion_data_source", "create_notion_database_record", "update_notion_database_record", "query_notion_actions",
    } | _ENGLISH_COACH_TOOLS,
    "cutsports": {
        "get_datetime", "search_notion", "read_notion_page", "read_notion_data_source",
        "create_notion_database_record", "update_notion_database_record", "get_cutsports_destinations",
    } | _ENGLISH_COACH_TOOLS,
    "drawsports": {
        "get_datetime", "search_notion", "read_notion_page", "read_notion_data_source",
        "create_notion_database_record", "update_notion_database_record", "get_drawsports_destinations",
    } | _ENGLISH_COACH_TOOLS,
    "the_analyst": {
        "get_datetime", "search_notion", "read_notion_page", "read_notion_data_source",
        "create_notion_database_record", "update_notion_database_record", "get_the_analyst_destinations",
    } | _ENGLISH_COACH_TOOLS,
    "comunidad": {
        "get_datetime", "search_notion", "read_notion_page", "read_notion_data_source",
        "create_notion_database_record", "update_notion_database_record", "get_comunidad_destinations",
    } | _ENGLISH_COACH_TOOLS,
    "basketouch_hub": {
        "get_datetime", "search_notion", "read_notion_page", "read_notion_data_source",
        "create_notion_database_record", "update_notion_database_record", "get_basketouch_hub_destinations",
        "query_notion_actions", "upsert_notion_action",
    } | _ENGLISH_COACH_TOOLS,
}


def get_profile_tools(profile: str) -> list[dict]:
    return get_openai_tool_definitions(TOOL_PROFILES.get(profile, TOOL_PROFILES["general"]))


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
from hornbills_catalog import DESTINATIONS_DEF, get_hornbills_destinations
from cutsports_catalog import DESTINATIONS_DEF as CUTSPORTS_DESTINATIONS_DEF, get_cutsports_destinations
from drawsports_catalog import DESTINATIONS_DEF as DRAWSPORTS_DESTINATIONS_DEF, get_drawsports_destinations
from the_analyst_catalog import DESTINATIONS_DEF as THE_ANALYST_DESTINATIONS_DEF, get_the_analyst_destinations
from comunidad_catalog import DESTINATIONS_DEF as COMUNIDAD_DESTINATIONS_DEF, get_comunidad_destinations
from basketouch_hub_catalog import DESTINATIONS_DEF as BASKETOUCH_HUB_DESTINATIONS_DEF, get_basketouch_hub_destinations
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
from tools.english_tool import (
    SAVE_DEF as EN_SAVE_DEF, SEARCH_DEF as EN_SEARCH_DEF, REVIEW_DEF as EN_REVIEW_DEF,
    RESULT_DEF as EN_RESULT_DEF, PROGRESS_DEF as EN_PROGRESS_DEF,
    save_english_phrase, search_english_phrases, get_english_review,
    record_english_result, get_english_progress,
)
from tools.notion_tool import (
    SEARCH_DEF as NOTION_SEARCH_DEF, READ_DEF as NOTION_READ_DEF, CREATE_PAGE_DEF as NOTION_CREATE_PAGE_DEF,
    QUERY_ACTIONS_DEF as NOTION_QUERY_ACTIONS_DEF, UPSERT_ACTION_DEF as NOTION_UPSERT_ACTION_DEF,
    HORNBILLS_HUB_DEF, APPEND_NOTE_DEF, READ_DATA_SOURCE_DEF, CREATE_DATABASE_RECORD_DEF, UPDATE_DATABASE_RECORD_DEF,
    search_notion, read_notion_page, create_notion_page, query_notion_actions, upsert_notion_action,
    get_hornbills_hub, append_notion_note, read_notion_data_source, create_notion_database_record, update_notion_database_record,
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
register("save_english_phrase", save_english_phrase, EN_SAVE_DEF)
register("search_english_phrases", search_english_phrases, EN_SEARCH_DEF)
register("get_english_review", get_english_review, EN_REVIEW_DEF)
register("record_english_result", record_english_result, EN_RESULT_DEF)
register("get_english_progress", get_english_progress, EN_PROGRESS_DEF)
register("search_notion", search_notion, NOTION_SEARCH_DEF)
register("read_notion_page", read_notion_page, NOTION_READ_DEF)
register("create_notion_page", create_notion_page, NOTION_CREATE_PAGE_DEF)
register("get_hornbills_hub", get_hornbills_hub, HORNBILLS_HUB_DEF)
register("append_notion_note", append_notion_note, APPEND_NOTE_DEF)
register("get_hornbills_destinations", get_hornbills_destinations, DESTINATIONS_DEF)
register("get_cutsports_destinations", get_cutsports_destinations, CUTSPORTS_DESTINATIONS_DEF)
register("get_drawsports_destinations", get_drawsports_destinations, DRAWSPORTS_DESTINATIONS_DEF)
register("get_the_analyst_destinations", get_the_analyst_destinations, THE_ANALYST_DESTINATIONS_DEF)
register("get_comunidad_destinations", get_comunidad_destinations, COMUNIDAD_DESTINATIONS_DEF)
register("get_basketouch_hub_destinations", get_basketouch_hub_destinations, BASKETOUCH_HUB_DESTINATIONS_DEF)
register("read_notion_data_source", read_notion_data_source, READ_DATA_SOURCE_DEF)
register("create_notion_database_record", create_notion_database_record, CREATE_DATABASE_RECORD_DEF)
register("update_notion_database_record", update_notion_database_record, UPDATE_DATABASE_RECORD_DEF)
register("query_notion_actions", query_notion_actions, NOTION_QUERY_ACTIONS_DEF)
register("upsert_notion_action", upsert_notion_action, NOTION_UPSERT_ACTION_DEF)
