from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.finance import Program, ProgramCreate
from app.schemas.inventory import CostPerAnimal

from typing import List
from supabase import Client

router = APIRouter()


@router.get("/programs", response_model=List[Program])
async def get_programs(supabase: Client = Depends(get_supabase)):
    response = supabase.table("programs").select("*").execute()
    return response.data


@router.post("/programs", response_model=Program)
async def create_program(program: ProgramCreate, supabase: Client = Depends(get_supabase)):
    response = supabase.table("programs").insert(program.model_dump()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create program")
    return response.data[0]


@router.get("/programs/cost-per-animal", response_model=List[CostPerAnimal])
async def get_program_cost_per_animal(supabase: Client = Depends(get_supabase)):
    tx_response = supabase.table("inventory_transactions") \
        .select("program_id, quantity, inventory_items(unit_cost)") \
        .eq("transaction_type", "Issue") \
        .not_.is_("program_id", "null") \
        .execute()

    cost_by_program: dict[int, float] = {}
    for tx in tx_response.data:
        pid = tx.get("program_id")
        if pid is None:
            continue
        unit_cost = (tx.get("inventory_items") or {}).get("unit_cost", 0) or 0
        quantity = tx.get("quantity", 0) or 0
        cost_by_program[pid] = cost_by_program.get(pid, 0.0) + quantity * unit_cost

    if not cost_by_program:
        return []

    program_ids = list(cost_by_program.keys())
    prog_response = supabase.table("programs") \
        .select("id, program_name, total_animals_treated") \
        .in_("id", program_ids) \
        .execute()

    results: List[CostPerAnimal] = []
    for prog in prog_response.data:
        pid = prog["id"]
        total_cost = cost_by_program.get(pid, 0.0)
        animals = prog.get("total_animals_treated") or 0
        cost_per_animal = (total_cost / animals) if animals > 0 else 0.0
        results.append(CostPerAnimal(
            program_id=pid,
            program_name=prog["program_name"],
            total_cost=round(total_cost, 2),
            animals_treated=animals,
            cost_per_animal=round(cost_per_animal, 2),
        ))

    results.sort(key=lambda r: r.cost_per_animal, reverse=True)
    return results
