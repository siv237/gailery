"""API endpoints for persons"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
import logging

from database import get_db
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/persons", tags=["persons"])


def _db_write(cmd, params=None, timeout=5):
    try:
        from mqtt_client import create_api_mqtt
        mq = create_api_mqtt()
        if mq and mq.is_worker_alive("pipeline"):
            result = mq.db_write(cmd, params, timeout=timeout)
            if result.get("ok") or "timeout" not in result.get("error", "").lower():
                return result
    except Exception:
        pass
    return _db_write_direct(cmd, params)


def _db_write_direct(cmd, params):
    from database import get_db
    db = get_db()
    try:
        if cmd == "update_persona":
            persona = db.update_persona(
                params.get("persona_id"),
                display_name=params.get("display_name"),
                comment=params.get("comment"),
                clear_display_name=params.get("clear_display_name", False),
                clear_comment=params.get("clear_comment", False),
            )
            if not persona:
                return {"ok": False, "error": "Person not found"}
            db.invalidate_for_persona(params.get("persona_id"))
            fc_map = db.face_count_map()
            return {"ok": True, "persona": dict(persona), "face_count": fc_map.get(persona["persona_id"], 0)}
        elif cmd == "merge_personas":
            source = params.get("source_persona_id")
            target = params.get("target_persona_id")
            if not source or not target:
                return {"ok": False, "error": "source_persona_id and target_persona_id required"}
            success = db.merge_personas(source, target)
            if success:
                db.invalidate_for_persona(target)
                return {"ok": True}
            return {"ok": False, "error": "Failed to merge"}
        elif cmd == "delete_persona":
            persona_id = params.get("persona_id")
            if not persona_id:
                return {"ok": False, "error": "persona_id required"}
            persona = db.get_persona(persona_id)
            if not persona:
                return {"ok": False, "error": "Person not found"}
            db.delete_persona(persona_id)
            return {"ok": True}
        else:
            return {"ok": False, "error": f"unknown db command: {cmd}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class FaceSearchRequest(BaseModel):
    embedding: List[float]
    limit: int = 10
    threshold: float = 0.5


class PersonaUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    comment: Optional[str] = None
    clear_display_name: bool = False
    clear_comment: bool = False


def _persona_response(p, fc_map, face_map=None):
    r = {
        "persona_id": p["persona_id"],
        "name": p["name"],
        "display_name": p.get("display_name"),
        "comment": p.get("comment"),
        "face_count": fc_map.get(p["persona_id"], 0),
    }
    if face_map and p["persona_id"] in face_map:
        r["face_id"] = face_map[p["persona_id"]]
    return r


@router.get("/")
async def get_all_persons(limit: int = 500, offset: int = 0, named_only: bool = False):
    try:
        db = get_db()
        cur = db.sqlite.cursor()

        where = "WHERE p.display_name IS NOT NULL" if named_only else ""
        total = cur.execute(f"SELECT COUNT(*) FROM personas p {where}").fetchone()[0]

        rows = cur.execute(
            f"SELECT p.persona_id, p.name, p.display_name, p.comment, "
            f"(SELECT COUNT(*) FROM faces WHERE persona_id = p.persona_id) as face_count, "
            f"(SELECT MIN(face_id) FROM faces WHERE persona_id = p.persona_id) as face_id "
            f"FROM personas p {where} ORDER BY face_count DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()

        result = []
        for r in rows:
            result.append({
                "persona_id": r[0],
                "name": r[1],
                "display_name": r[2],
                "comment": r[3],
                "face_count": r[4],
                "face_id": r[5],
            })
        return {"total": total, "persons": result}
    except Exception as e:
        logger.error(f"Failed to get persons: {e}")
        raise HTTPException(status_code=500, detail="Failed to get persons")


@router.get("/names")
async def get_display_names():
    try:
        db = get_db()
        return db.get_display_names()
    except Exception as e:
        logger.error(f"Failed to get names: {e}")
        raise HTTPException(status_code=500, detail="Failed to get names")


@router.get("/by_name/{display_name}")
async def get_persons_by_name(display_name: str):
    try:
        db = get_db()
        fc_map = db.face_count_map()
        personas = db.get_personas_by_name(display_name)
        result = []
        for p in personas:
            result.append({
                "persona_id": p["persona_id"],
                "name": p["name"],
                "display_name": p.get("display_name"),
                "comment": p.get("comment"),
                "face_count": fc_map.get(p["persona_id"], 0),
                "face_id": p.get("face_id"),
            })
        return result
    except Exception as e:
        logger.error(f"Failed to get persons by name: {e}")
        raise HTTPException(status_code=500, detail="Failed to get persons")


@router.get("/{persona_id}")
async def get_person(persona_id: str):
    try:
        db = get_db()
        persona = db.get_persona(persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Person not found")
        fc_map = db.face_count_map()
        return _persona_response(persona, fc_map)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get person {persona_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get person")


@router.get("/{persona_id}/faces")
async def get_person_faces(persona_id: str, limit: int = 100, dedupe_by_photo: bool = True):
    try:
        db = get_db()
        faces = db.get_faces_for_persona(persona_id, limit)

        if dedupe_by_photo:
            best_by_photo = {}
            for face in faces:
                photo_id = face["photo_id"]
                prev = best_by_photo.get(photo_id)
                if prev is None or float(face.get("confidence", 0.0)) > float(prev.get("confidence", 0.0)):
                    best_by_photo[photo_id] = face
            faces = list(best_by_photo.values())

        faces = sorted(faces, key=lambda f: float(f.get("confidence", 0.0)), reverse=True)

        result = []
        for face in faces:
            result.append({
                "face_id": face["face_id"],
                "photo_id": face["photo_id"],
                "bbox_x1": face["bbox_x1"],
                "bbox_y1": face["bbox_y1"],
                "bbox_x2": face["bbox_x2"],
                "bbox_y2": face["bbox_y2"],
                "confidence": face["confidence"]
            })
        return result
    except Exception as e:
        logger.error(f"Failed to get faces for persona {persona_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get faces")


@router.put("/{persona_id}")
async def update_person(persona_id: str, req: PersonaUpdateRequest):
    result = _db_write("update_persona", {
        "persona_id": persona_id,
        "display_name": req.display_name,
        "comment": req.comment,
        "clear_display_name": req.clear_display_name,
        "clear_comment": req.clear_comment,
    })
    if not result.get("ok"):
        if "not found" in result.get("error", "").lower():
            raise HTTPException(status_code=404, detail="Person not found")
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to update person"))
    persona = result.get("persona", {})
    return {
        "persona_id": persona.get("persona_id", persona_id),
        "name": persona.get("name", ""),
        "display_name": persona.get("display_name"),
        "comment": persona.get("comment"),
        "face_count": result.get("face_count", 0),
    }


@router.put("/batch/by_name")
async def update_persons_by_name(old_name: str, req: PersonaUpdateRequest):
    try:
        db = get_db()
        personas = db.get_personas_by_name(old_name)
        fc_map = db.face_count_map()
        results = []
        for p in personas:
            r = _db_write("update_persona", {
                "persona_id": p["persona_id"],
                "display_name": req.display_name,
                "comment": req.comment,
                "clear_display_name": req.clear_display_name,
                "clear_comment": req.clear_comment,
            })
            if r.get("ok"):
                persona = r.get("persona", {})
                results.append({
                    "persona_id": persona.get("persona_id", p["persona_id"]),
                    "name": persona.get("name", ""),
                    "display_name": persona.get("display_name"),
                    "comment": persona.get("comment"),
                    "face_count": r.get("face_count", 0),
                })
        return {"updated": len(results), "personas": results}
    except Exception as e:
        logger.error(f"Failed to batch update: {e}")
        raise HTTPException(status_code=500, detail="Failed to batch update")


@router.post("/merge")
async def merge_persons(source_persona_id: str, target_persona_id: str):
    result = _db_write("merge_personas", {
        "source_persona_id": source_persona_id,
        "target_persona_id": target_persona_id,
    })
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to merge persons"))
    return {"success": True, "message": f"Merged {source_persona_id} into {target_persona_id}"}


@router.delete("/{persona_id}")
async def delete_person(persona_id: str):
    result = _db_write("delete_persona", {"persona_id": persona_id})
    if not result.get("ok"):
        if "not found" in result.get("error", "").lower():
            raise HTTPException(status_code=404, detail="Person not found")
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to delete person"))
    return {"success": True, "message": f"Deleted persona {persona_id}"}


@router.post("/search")
async def search_similar_faces(request: FaceSearchRequest):
    try:
        db = get_db()
        results = db.search_similar_faces(
            embedding=request.embedding,
            limit=request.limit,
            threshold=request.threshold
        )
        formatted_results = []
        for result in results:
            face = db.get_face(result["face_id"])
            formatted_results.append({
                "face_id": result["face_id"],
                "photo_id": face.get("photo_id") if face else None,
                "persona_id": result.get("persona_id"),
                "similarity": result.get("similarity", 0.0),
                "confidence": face.get("confidence") if face else None,
            })
        return formatted_results
    except Exception as e:
        logger.error(f"Failed to search similar faces: {e}")
        raise HTTPException(status_code=500, detail="Failed to search similar faces")
