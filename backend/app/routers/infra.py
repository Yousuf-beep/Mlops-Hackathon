"""Runtime-infrastructure routes.

Two projections of a single discovery pass over the container runtime: the raw
container inventory, and the browsable endpoints grouped by environment. Both
read the same cached snapshot, so a dashboard requesting both in one tick costs
one look at the Docker socket rather than two.

These routes are read-only and expose no container environment variables — the
only thing derived from a container's environment is the name of the deployment
environment it belongs to. That keeps them the same shape as the rest of the
dashboard's analytics surface: unauthenticated reads of things that are already
observable, and nothing that could be used to change the running system.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.infra import discover
from app.schemas import ContainerRead, EnvironmentGroup, InfraSnapshot

router = APIRouter(prefix="/v1/infra", tags=["infrastructure"])


@router.get(
    "/snapshot",
    response_model=InfraSnapshot,
    summary="Discovered containers and their endpoints",
)
async def get_snapshot() -> InfraSnapshot:
    """Return everything discovery knows about the running stack.

    Never fails on an unreachable runtime: when the Docker Engine cannot be
    contacted the response is a well-formed snapshot with ``available: false``
    and a ``reason``, so the dashboard can explain the empty panel instead of
    rendering an error where a table should be.

    Returns:
        InfraSnapshot: Containers, their published endpoints, and those
        endpoints grouped by environment.
    """
    return await discover()


@router.get(
    "/containers",
    response_model=list[ContainerRead],
    summary="List discovered containers",
)
async def list_containers() -> list[ContainerRead]:
    """Return the container inventory alone.

    Returns:
        list[ContainerRead]: Running containers first, then stopped ones.
    """
    return (await discover()).containers


@router.get(
    "/environments",
    response_model=list[EnvironmentGroup],
    summary="Web endpoints grouped by environment",
)
async def list_environments() -> list[EnvironmentGroup]:
    """Return browsable endpoints, one group per environment.

    Returns:
        list[EnvironmentGroup]: Always three groups in pipeline order —
        development, QA, production — whether or not each has services.
    """
    return (await discover()).environments
