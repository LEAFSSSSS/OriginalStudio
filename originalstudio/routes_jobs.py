from fastapi import APIRouter, Query, Request

from .schemas import JobCreate


router = APIRouter(prefix="/api/jobs")


@router.get("")
def jobs(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    return request.app.state.jobs.list(limit)


@router.post("", status_code=202)
def create_job(payload: JobCreate, request: Request):
    return request.app.state.jobs.create(payload.model_dump())


@router.get("/{identifier}")
def job(identifier: int, request: Request):
    return request.app.state.jobs.get(identifier, detail=True)


@router.post("/{identifier}/stop")
def stop(identifier: int, request: Request):
    return request.app.state.jobs.stop(identifier)


@router.post("/{identifier}/resume")
def resume(identifier: int, request: Request):
    return request.app.state.jobs.resume(identifier)
