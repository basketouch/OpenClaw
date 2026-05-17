import asyncio
import os
import shlex
import subprocess

SHELL_DEF = {
    "name": "run_shell",
    "description": (
        "Ejecuta un comando de shell en el servidor. Úsalo para administrar el sistema: "
        "ver logs, estado de contenedores, espacio en disco, editar configuración, "
        "reiniciar servicios, hacer deploys, etc. "
        "IMPORTANTE: pide confirmación al usuario antes de ejecutar comandos destructivos "
        "(rm, docker rm, reboot, etc.)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Comando bash a ejecutar",
            },
            "cwd": {
                "type": "string",
                "description": "Directorio de trabajo. Por defecto /root/openclaw-app",
            },
        },
        "required": ["command"],
    },
}


HOST_SHELL_DEF = {
    "name": "host_shell",
    "description": (
        "Ejecuta un comando con privilegios root completos en el servidor VPS host "
        "(fuera del contenedor Docker). "
        "Úsalo para: instalar/actualizar paquetes (apt), gestionar servicios (systemctl), "
        "editar archivos del sistema, ver journalctl, configurar el servidor, "
        "gestionar redes, crontab del sistema, etc. "
        "Para archivos del workspace o Docker usa run_shell. "
        "IMPORTANTE: confirma con el usuario antes de acciones destructivas o irreversibles."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Comando bash a ejecutar en el host con privilegios root",
            },
            "timeout": {
                "type": "integer",
                "description": "Tiempo máximo en segundos (por defecto 60)",
            },
        },
        "required": ["command"],
    },
}


async def run_host_shell(command: str, timeout: int = 60) -> dict:
    """Run command on the VPS host by entering PID 1 namespaces via nsenter."""
    nsenter_cmd = f"nsenter -t 1 -m -u -i -n -p -- bash -c {shlex.quote(command)}"
    try:
        proc = await asyncio.create_subprocess_shell(
            nsenter_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "Timeout", "returncode": -1}
        return {
            "stdout": stdout.decode(errors="replace").strip(),
            "stderr": stderr.decode(errors="replace").strip(),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
        }
    except Exception as e:
        return {"error": str(e), "returncode": -1}


async def run_shell(command: str, cwd: str = "/root/openclaw-app") -> dict:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd if os.path.isdir(cwd) else "/root/openclaw-app",
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "Timeout (60s)", "returncode": -1}

        return {
            "stdout": stdout.decode(errors="replace").strip(),
            "stderr": stderr.decode(errors="replace").strip(),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
        }
    except Exception as e:
        return {"error": str(e), "returncode": -1}
