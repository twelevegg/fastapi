
from fastapi import APIRouter, BackgroundTasks
from app.services.simulation_service import simulation_service

router = APIRouter()

@router.post("/start")
async def start_simulation(background_tasks: BackgroundTasks):
    """
    Triggers the call simulation in the background.
    """
    background_tasks.add_task(simulation_service.run_simulation)
    return {"status": "started", "message": "Simulation triggered in background"}
