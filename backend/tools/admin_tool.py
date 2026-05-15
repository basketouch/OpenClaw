import asyncio
import os
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
