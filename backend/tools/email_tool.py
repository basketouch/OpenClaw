import re
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser

from imap_tools import A, MailBox

from config import GmailAccount, get_settings

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


# ─── Helpers ────────────────────────────────────────────────────────────────

class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


def _strip_html(html: str) -> str:
    s = _Stripper()
    try:
        s.feed(html)
        return s.get_text()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


def _get_account(name_or_email: str | None) -> GmailAccount:
    accounts = get_settings().gmail_accounts
    if not accounts:
        raise ValueError("No hay cuentas Gmail configuradas en .env (GMAIL_ACCOUNTS)")
    if not name_or_email:
        return accounts[0]
    q = name_or_email.lower()
    for acc in accounts:
        if acc.name.lower() == q or acc.email.lower() == q:
            return acc
    return accounts[0]


def _body(msg) -> str:
    if msg.text:
        return msg.text.strip()
    if msg.html:
        return _strip_html(msg.html)
    return ""


def _msg_summary(msg) -> dict:
    return {
        "uid": msg.uid,
        "de": msg.from_,
        "para": ", ".join(msg.to),
        "asunto": msg.subject,
        "fecha": msg.date_str,
        "leido": "\\Seen" in (msg.flags or []),
        "resumen": _body(msg)[:300],
    }


# ─── Tool definitions ────────────────────────────────────────────────────────

LIST_EMAILS_DEF = {
    "name": "list_emails",
    "description": "Lista los emails más recientes de una carpeta. Usa 'INBOX' para bandeja de entrada.",
    "input_schema": {
        "type": "object",
        "properties": {
            "account": {"type": "string", "description": "Nombre o email de la cuenta. Omitir para usar la primera."},
            "folder": {"type": "string", "description": "Carpeta: INBOX, Sent, Drafts, Spam. Por defecto: INBOX"},
            "limit": {"type": "integer", "description": "Número de emails a devolver (máx 20). Por defecto: 10"},
            "solo_no_leidos": {"type": "boolean", "description": "Si true, solo devuelve emails no leídos"},
        },
        "required": [],
    },
}


def list_emails(
    account: str | None = None,
    folder: str = "INBOX",
    limit: int = 10,
    solo_no_leidos: bool = False,
) -> dict:
    acc = _get_account(account)
    limit = min(limit, 20)
    try:
        with MailBox(IMAP_HOST).login(acc.email, acc.password, folder) as mb:
            if solo_no_leidos:
                msgs = list(mb.fetch(A(seen=False), limit=limit, bulk=True, mark_seen=False, reverse=True))
            else:
                msgs = list(mb.fetch(limit=limit, bulk=True, mark_seen=False, reverse=True))
        return {"cuenta": acc.email, "carpeta": folder, "total": len(msgs), "emails": [_msg_summary(m) for m in msgs]}
    except Exception as e:
        return {"error": str(e)}


SEARCH_EMAILS_DEF = {
    "name": "search_emails",
    "description": "Busca emails por remitente, asunto, texto o rango de fechas.",
    "input_schema": {
        "type": "object",
        "properties": {
            "account": {"type": "string", "description": "Nombre o email de la cuenta. Omitir para usar la primera."},
            "de": {"type": "string", "description": "Filtrar por remitente (email o nombre)"},
            "asunto": {"type": "string", "description": "Filtrar por texto en asunto"},
            "texto": {"type": "string", "description": "Filtrar por texto en el cuerpo"},
            "dias": {"type": "integer", "description": "Buscar en los últimos N días. Por defecto: 30"},
            "limit": {"type": "integer", "description": "Máximo de resultados. Por defecto: 10"},
        },
        "required": [],
    },
}


def search_emails(
    account: str | None = None,
    de: str | None = None,
    asunto: str | None = None,
    texto: str | None = None,
    dias: int = 30,
    limit: int = 10,
) -> dict:
    acc = _get_account(account)
    limit = min(limit, 20)
    fecha_desde = date.today() - timedelta(days=dias)

    kwargs: dict = {"date_gte": fecha_desde}
    if de:
        kwargs["from_"] = de
    if asunto:
        kwargs["subject"] = asunto
    if texto:
        kwargs["text"] = texto
    criteria = A(**kwargs)

    try:
        with MailBox(IMAP_HOST).login(acc.email, acc.password) as mb:
            msgs = list(mb.fetch(criteria, limit=limit, bulk=True, mark_seen=False, reverse=True))
        return {"cuenta": acc.email, "resultados": len(msgs), "emails": [_msg_summary(m) for m in msgs]}
    except Exception as e:
        return {"error": str(e)}


READ_EMAIL_DEF = {
    "name": "read_email",
    "description": "Lee el contenido completo de un email por su UID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "uid": {"type": "string", "description": "UID del email (obtenido de list_emails o search_emails)"},
            "account": {"type": "string", "description": "Nombre o email de la cuenta. Omitir para usar la primera."},
            "folder": {"type": "string", "description": "Carpeta donde está el email. Por defecto: INBOX"},
        },
        "required": ["uid"],
    },
}


def read_email(uid: str, account: str | None = None, folder: str = "INBOX") -> dict:
    acc = _get_account(account)
    try:
        with MailBox(IMAP_HOST).login(acc.email, acc.password, folder) as mb:
            msgs = list(mb.fetch(A(uid=[uid]), mark_seen=True))
        if not msgs:
            return {"error": f"Email con UID {uid} no encontrado"}
        msg = msgs[0]
        return {
            "uid": msg.uid,
            "de": msg.from_,
            "para": ", ".join(msg.to),
            "cc": ", ".join(msg.cc) if msg.cc else "",
            "asunto": msg.subject,
            "fecha": msg.date_str,
            "cuerpo": _body(msg),
            "adjuntos": [a.filename for a in msg.attachments],
        }
    except Exception as e:
        return {"error": str(e)}


SEND_EMAIL_DEF = {
    "name": "send_email",
    "description": "Envía un email desde una cuenta Gmail configurada.",
    "input_schema": {
        "type": "object",
        "properties": {
            "para": {"type": "string", "description": "Destinatario (email o lista separada por comas)"},
            "asunto": {"type": "string", "description": "Asunto del email"},
            "cuerpo": {"type": "string", "description": "Cuerpo del email en texto plano"},
            "account": {"type": "string", "description": "Nombre o email de la cuenta remitente. Omitir para usar la primera."},
            "cc": {"type": "string", "description": "Copia a (opcional, separado por comas)"},
        },
        "required": ["para", "asunto", "cuerpo"],
    },
}


def send_email(
    para: str,
    asunto: str,
    cuerpo: str,
    account: str | None = None,
    cc: str | None = None,
) -> dict:
    acc = _get_account(account)
    msg = MIMEMultipart()
    msg["From"] = acc.email
    msg["To"] = para
    msg["Subject"] = asunto
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    destinatarios = [p.strip() for p in para.split(",")]
    if cc:
        destinatarios += [p.strip() for p in cc.split(",")]

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(acc.email, acc.password)
            server.sendmail(acc.email, destinatarios, msg.as_string())
        return {"success": True, "de": acc.email, "para": para, "asunto": asunto}
    except Exception as e:
        return {"error": str(e), "success": False}


REPLY_EMAIL_DEF = {
    "name": "reply_email",
    "description": "Responde a un email existente citando el original.",
    "input_schema": {
        "type": "object",
        "properties": {
            "uid": {"type": "string", "description": "UID del email al que responder"},
            "cuerpo": {"type": "string", "description": "Texto de la respuesta"},
            "account": {"type": "string", "description": "Nombre o email de la cuenta. Omitir para usar la primera."},
            "folder": {"type": "string", "description": "Carpeta del email original. Por defecto: INBOX"},
            "responder_a_todos": {"type": "boolean", "description": "Si true, incluye todos los destinatarios originales en CC"},
        },
        "required": ["uid", "cuerpo"],
    },
}


def reply_email(
    uid: str,
    cuerpo: str,
    account: str | None = None,
    folder: str = "INBOX",
    responder_a_todos: bool = False,
) -> dict:
    acc = _get_account(account)
    try:
        with MailBox(IMAP_HOST).login(acc.email, acc.password, folder) as mb:
            originals = list(mb.fetch(A(uid=[uid]), mark_seen=False))
        if not originals:
            return {"error": f"Email con UID {uid} no encontrado"}

        original = originals[0]
        quoted = "\n".join(f"> {line}" for line in _body(original).splitlines())
        body_reply = f"{cuerpo}\n\n— Original de {original.from_} ({original.date_str}):\n{quoted}"

        asunto = original.subject if original.subject.startswith("Re:") else f"Re: {original.subject}"
        cc = None
        if responder_a_todos:
            otros = [t for t in original.to if t.lower() != acc.email.lower()]
            if otros:
                cc = ", ".join(otros)

        msg = MIMEMultipart()
        msg["From"] = acc.email
        msg["To"] = original.from_
        msg["Subject"] = asunto
        if cc:
            msg["Cc"] = cc
        if original.headers.get("message-id"):
            msg["In-Reply-To"] = original.headers["message-id"][0]
            msg["References"] = original.headers["message-id"][0]
        msg.attach(MIMEText(body_reply, "plain", "utf-8"))

        destinatarios = [original.from_]
        if cc:
            destinatarios += [p.strip() for p in cc.split(",")]

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(acc.email, acc.password)
            server.sendmail(acc.email, destinatarios, msg.as_string())

        return {"success": True, "respondido_a": original.from_, "asunto": asunto}
    except Exception as e:
        return {"error": str(e), "success": False}


LIST_ACCOUNTS_DEF = {
    "name": "list_email_accounts",
    "description": "Muestra las cuentas de email configuradas.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def list_email_accounts() -> dict:
    accounts = get_settings().gmail_accounts
    if not accounts:
        return {"cuentas": [], "mensaje": "No hay cuentas Gmail configuradas"}
    return {"cuentas": [{"nombre": a.name, "email": a.email} for a in accounts]}
