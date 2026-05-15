import asyncio
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_token
import scheduler as sched

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _sh(cmd: str, timeout: int = 10) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()
    except asyncio.TimeoutError:
        proc.kill()
        return "", "timeout"


@router.get("/stats")
async def stats(_: str = Depends(verify_token)):
    # Read from /proc directly — no awk quoting issues
    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()[0]
    except Exception:
        load = "—"

    try:
        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                meminfo[k.strip()] = int(v.strip().split()[0])
        total = meminfo.get("MemTotal", 0) // 1024
        avail = meminfo.get("MemAvailable", 0) // 1024
        used = total - avail
        mem = f"{used}MB / {total}MB"
    except Exception:
        mem = "—"

    disk_out, _ = await _sh("df -h / 2>/dev/null | tail -1")
    parts = disk_out.split()
    disk = f"{parts[2]}/{parts[1]} ({parts[4]})" if len(parts) >= 5 else "—"

    uptime_out, _ = await _sh("uptime -p 2>/dev/null")
    uptime = uptime_out or "—"

    return {"disk": disk, "memory": mem, "load": load, "uptime": uptime}


@router.get("/containers")
async def containers(_: str = Depends(verify_token)):
    out, err = await _sh("docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'")
    if err:
        return {"containers": [], "error": err[:300]}
    result = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            name, status, image = parts
            result.append({
                "name": name.strip(),
                "status": status.strip(),
                "image": image.strip().split("/")[-1],
                "up": "Up" in status,
            })
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
