from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import uvicorn
from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from .database import DatabaseClient, Priority, TaskState
from .dependencies import get_db, verify_queue_auth

app = FastAPI()


@app.get("/health")
async def health_check(db: DatabaseClient = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Check database connection
        db.client.admin.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}


class QueueCreate(BaseModel):
    queue_name: str
    password: str


class TaskSubmit(BaseModel):
    queue_name: str
    password: str
    task_name: Optional[str] = None
    args: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = {}
    heartbeat_interval: Optional[int] = 60


@app.post("/api/v1/queues")
async def create_queue(queue: QueueCreate, db: DatabaseClient = Depends(get_db)):
    """Create a new queue"""
    _id = db.create_queue(queue.queue_name, queue.password)
    return {"status": "success", "queue_id": _id}


@app.get("/api/v1/queues")
async def get_queue(
    password: str,
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    db: DatabaseClient = Depends(get_db),
):
    """Get queue information"""
    if not queue_id and not queue_name:
        raise HTTPException(
            status_code=422, detail="Either queue_id or queue_name must be provided"
        )

    query = {}
    if queue_id:
        query["_id"] = ObjectId(queue_id)
    if queue_name:
        query["queue_name"] = queue_name

    queue = db.queues.find_one(query)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    # Verify password
    if not db.security.verify_password(password, queue["password"]):
        raise HTTPException(status_code=401, detail="Invalid password")

    return {
        "queue_id": str(queue["_id"]),
        "queue_name": queue["queue_name"],
        "status": "active",
        "created_at": queue["created_at"],
    }


@app.delete("/api/v1/queues")
async def delete_queue(
    password: str,
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    db: DatabaseClient = Depends(get_db),
):
    """Delete a queue"""
    if not queue_id and not queue_name:
        raise HTTPException(
            status_code=422, detail="Either queue_id or queue_name must be provided"
        )

    # Find and verify queue
    query = {}
    if queue_id:
        query["_id"] = queue_id
    if queue_name:
        query["queue_name"] = queue_name

    queue = db.queues.find_one(query)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    # Verify password
    if not db.security.verify_password(password, queue["password"]):
        raise HTTPException(status_code=401, detail="Invalid password")

    return {"status": "success"}


@app.post("/api/v1/tasks")
async def submit_task(
    task: TaskSubmit,
    db: DatabaseClient = Depends(get_db),
):
    """Submit a task to the queue"""
    queue = db.queues.find_one({"queue_name": task.queue_name})
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    task_id = db.submit_task(
        queue_name=task.queue_name,
        task_name=task.task_name,
        args=task.args,
        metadata=task.metadata,
        heartbeat_interval=task.heartbeat_interval,
    )
    return {"status": "success", "task_id": task_id}


@app.get("/api/v1/tasks/next")
async def get_next_task(
    db: DatabaseClient = Depends(get_db),
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    worker_name: Optional[str] = None,
    eta_max: str = "2h",
    start_heartbeat: bool = False,
):
    """Get next available task from queue"""
    if not queue_id and not queue_name:
        raise HTTPException(
            status_code=422, detail="Either queue_id or queue_name must be provided"
        )

    query = {}
    if queue_id:
        query["_id"] = queue_id
    if queue_name:
        query["queue_name"] = queue_name

    queue = db.queues.find_one(query)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    task = db.fetch_task(
        queue_name=queue["queue_name"],
        worker_id=str(uuid4()),
        worker_name=worker_name,
        eta_max=eta_max,
    )
    if not task:
        return {"status": "no_task"}
    task_id = str(task.pop("_id"))
    task["task_id"] = task_id
    return {
        "status": "success",
        "task_id": task_id,
        "args": task["args"],
        "metadata": task["metadata"],
    }


@app.get("/api/v1/tasks")
async def get_task(
    password: str,
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    task_id: Optional[str] = None,
    task_name: Optional[str] = None,
    db: DatabaseClient = Depends(get_db),
):
    """Get tasks matching the criteria"""
    if not queue_id and not queue_name:
        raise HTTPException(
            status_code=422, detail="Either queue_id or queue_name must be provided"
        )

    # Verify queue access first
    queue_query = {}
    if queue_id:
        queue_query["_id"] = ObjectId(queue_id)
    if queue_name:
        queue_query["queue_name"] = queue_name

    queue = db.queues.find_one(queue_query)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    if not db.security.verify_password(password, queue["password"]):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Build task query
    task_query = {}
    if task_id:
        task_query["_id"] = task_id
    if task_name:
        task_query["task_name"] = task_name
    if queue_id:
        task_query["queue_id"] = queue_id
    if queue_name:
        task_query["queue_name"] = queue_name

    tasks = list(db.tasks.find(task_query))
    for task in tasks:
        task_id = str(task.pop("_id"))
        task["task_id"] = task_id
        # Ensure queue_id is a string
        if "queue_id" in task:
            task["queue_id"] = str(task["queue_id"])

    return {"status": "success", "tasks": tasks}


@app.patch("/api/v1/tasks/{task_id}")
async def update_task_status(
    task_id: str,
    status: str,
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
    db: DatabaseClient = Depends(get_db),
):
    """Update task status (complete, failed, etc)"""
    query = {"_id": task_id}
    if queue_id:
        query["queue_id"] = queue_id
    if queue_name:
        query["queue_name"] = queue_name

    task = db.tasks.find_one_and_update(
        query,
        {
            "$set": {
                "status": status,
                "summary": summary or {},
                "last_modified": datetime.now(timezone.utc),
            }
        },
        return_document=True,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success"}


@app.post("/api/v1/tasks/{task_id}/heartbeat")
async def task_heartbeat(
    task_id: str,
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    db: DatabaseClient = Depends(get_db),
):
    """Update task heartbeat timestamp."""
    query = {"_id": task_id}
    if queue_id:
        query["queue_id"] = queue_id
    if queue_name:
        query["queue_name"] = queue_name

    task = db.tasks.find_one_and_update(
        query,
        {"$set": {"last_heartbeat": datetime.now(timezone.utc)}},
        return_document=True,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success"}


if __name__ == "__main__":
    from .config import ServerConfig

    config = ServerConfig()
    uvicorn.run(app, host=config.api_host, port=config.api_port)