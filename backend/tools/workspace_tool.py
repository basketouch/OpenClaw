from pathlib import Path

from config import get_settings


def _workspace() -> Path:
    path = Path(get_settings().workspace_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe(workspace: Path, filename: str) -> Path:
    target = (workspace / filename).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise PermissionError("Ruta fuera del workspace no permitida")
    return target


LIST_DEF = {
    "name": "list_workspace_files",
    "description": "Lista archivos y carpetas en el workspace de trabajo.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subdirectory": {
                "type": "string",
                "description": "Subdirectorio opcional a listar (ej: 'notas', 'proyectos')",
            }
        },
        "required": [],
    },
}


def list_workspace_files(subdirectory: str = "") -> dict:
    workspace = _workspace()
    target = (workspace / subdirectory).resolve() if subdirectory else workspace

    if not target.exists():
        return {"error": f"Directorio no encontrado: {subdirectory}"}

    files, dirs = [], []
    for item in sorted(target.iterdir()):
        rel = str(item.relative_to(workspace))
        if item.is_file():
            files.append({"name": item.name, "path": rel, "size_bytes": item.stat().st_size})
        elif item.is_dir():
            dirs.append({"name": item.name, "path": rel})

    return {"files": files, "directories": dirs}


READ_DEF = {
    "name": "read_workspace_file",
    "description": "Lee el contenido de un archivo del workspace.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Ruta del archivo relativa al workspace (ej: 'notas/ideas.md')",
            }
        },
        "required": ["filename"],
    },
}


def read_workspace_file(filename: str) -> dict:
    workspace = _workspace()
    try:
        path = _safe(workspace, filename)
    except PermissionError as e:
        return {"error": str(e)}

    if not path.exists():
        return {"error": f"Archivo no encontrado: {filename}"}

    try:
        content = path.read_text(encoding="utf-8")
        return {"content": content, "filename": filename, "characters": len(content)}
    except Exception as e:
        return {"error": str(e)}


WRITE_DEF = {
    "name": "write_workspace_file",
    "description": "Crea o escribe un archivo en el workspace.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Ruta del archivo relativa al workspace (ej: 'notas/tarea.md')",
            },
            "content": {
                "type": "string",
                "description": "Contenido del archivo",
            },
            "mode": {
                "type": "string",
                "enum": ["write", "append"],
                "description": "'write' para sobreescribir (default), 'append' para añadir al final",
            },
        },
        "required": ["filename", "content"],
    },
}


def write_workspace_file(filename: str, content: str, mode: str = "write") -> dict:
    workspace = _workspace()
    try:
        path = _safe(workspace, filename)
    except PermissionError as e:
        return {"error": str(e), "success": False}

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if mode == "append":
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            path.write_text(content, encoding="utf-8")
        return {"success": True, "filename": filename, "characters": len(content)}
    except Exception as e:
        return {"error": str(e), "success": False}
