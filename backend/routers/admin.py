import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_token
import scheduler as sched

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _sh(cmd: str, timeout: int = 10) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace").strip()
    except asyncio.TimeoutError:
        proc.kill()
        return ""


@router.get("/stats")
async def stats(_: str = Depends(verify_token)):
    disk, mem, load, uptime = await asyncio.gather(
        _sh("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")'\"'\"'}'"),
        _sh("free -m | awk 'NR==2{printf \"%dMB / %dMB\", $3, $2}'"),
        _sh("cat /proc/loadavg | awk '{print $1}'"),
        _sh("uptime -p"),
    )
    return {"disk": disk, "memory": mem, "load": load, "uptime": uptime}


@router.get("/containers")
async def containers(_: str = Depends(verify_token)):
    out = await _sh("docker ps --format '{{.Names}}|||{{.Status}}|||{{.Image}}'")
    result = []
    for line in out.splitlines():
        parts = line.split("|||")
        if len(parts) == 3:
            name, status, image = parts
            up = "Up" in status
            result.append({"name": name.strip(), "status": status.strip(),
                            "image": image.strip(), "up": up})
    return {"containers": result}


@router.get("/tasks")
async def tasks(_: str = Depends(verify_token)):
    return {"tasks": sched.list_jobs()}


class ToggleBody(BaseModel):
    enabled: bool


@router.patch("/tasks/{job_id}")
async def toggle_task(job_id: str, body: ToggleBody, _: str = Depends(verify_token)):
    ok = sched.toggle_job(job_id, body.enabled)
    return {"success": ok}


@router.delete("/tasks/{job_id}")
async def delete_task(job_id: str, _: str = Depends(verify_token)):
    ok = sched.delete_job(job_id)
    return {"success": ok}


@router.post("/deploy")
async def deploy(_: str = Depends(verify_token)):
    asyncio.create_task(
        asyncio.create_subprocess_shell("cd /root/openclaw-app && bash deploy.sh")
    )
    return {"message": "Deploy iniciado. La app se reiniciará en ~30 segundos."}
