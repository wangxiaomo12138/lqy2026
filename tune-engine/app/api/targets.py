"""Target 与 Benchmark 管理接口"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tune_models import BenchmarkCase, TargetRegistry
from app.schemas.tune_schemas import BenchmarkCasesImport, TargetCreate

router = APIRouter(prefix="/api/v1", tags=["targets"])


@router.post("/targets")
def create_target(body: TargetCreate, db: Session = Depends(get_db)):
    existing = db.query(TargetRegistry).filter(TargetRegistry.target_id == body.target_id).first()
    if existing:
        raise HTTPException(400, f"target_id 已存在: {body.target_id}")

    config = body.model_dump()
    row = TargetRegistry(
        target_id=body.target_id,
        name=body.name,
        description=body.description,
        type=body.type,
        entry_ref=body.entry_ref,
        config_json=config,
        benchmark_suite_id=body.benchmark_suite_id,
        evaluator_id=body.evaluator_id,
        enabled=body.enabled,
        version=body.version,
    )
    db.add(row)
    db.commit()
    return {"target_id": body.target_id, "version": body.version, "enabled": body.enabled}


@router.get("/targets")
def list_targets(db: Session = Depends(get_db)):
    rows = db.query(TargetRegistry).all()
    return [{"target_id": r.target_id, "name": r.name, "entry_ref": r.entry_ref, "enabled": r.enabled} for r in rows]


@router.get("/targets/{target_id}")
def get_target(target_id: str, db: Session = Depends(get_db)):
    row = db.query(TargetRegistry).filter(TargetRegistry.target_id == target_id).first()
    if not row:
        raise HTTPException(404, "Target 不存在")
    return row.config_json


@router.post("/benchmarks/{suite_id}/cases")
def import_cases(suite_id: str, body: BenchmarkCasesImport, db: Session = Depends(get_db)):
    count = 0
    for case in body.cases:
        existing = (
            db.query(BenchmarkCase)
            .filter(BenchmarkCase.suite_id == suite_id, BenchmarkCase.case_id == case["case_id"])
            .first()
        )
        if existing:
            existing.input_json = case["input"]
            existing.ground_truth_json = case.get("ground_truth")
            existing.weight = case.get("weight", 1.0)
            existing.tags = case.get("tags")
        else:
            db.add(BenchmarkCase(
                suite_id=suite_id,
                case_id=case["case_id"],
                input_json=case["input"],
                ground_truth_json=case.get("ground_truth"),
                weight=case.get("weight", 1.0),
                tags=case.get("tags"),
            ))
        count += 1
    db.commit()
    return {"suite_id": suite_id, "imported": count}


@router.post("/targets/import-file")
def import_target_from_file(file_path: str, db: Session = Depends(get_db)):
    """从 JSON 文件导入 target（开发用）"""
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(404, f"文件不存在: {file_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    body = TargetCreate(**data)
    return create_target(body, db)
