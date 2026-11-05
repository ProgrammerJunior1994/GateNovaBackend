from datetime import datetime, timezone, date
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from pydantic import BaseModel
import os

from .database import Base, engine, get_db
from . import models, schemas

Base.metadata.create_all(bind=engine)

app = FastAPI(title="GateNova API", version="1.0.0",
              description="API de administración del sistema GateNova.")

origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RFIDRequest(BaseModel):
    uid: str
    access_type: str

class RFIDRequest(BaseModel):
    uid: str
    access_type: str


@app.post("/api/rfid")
def read_rfid(data: RFIDRequest, db: Session = Depends(get_db)):

    uid = data.uid.strip().upper().replace(" ", "")

    if data.access_type not in {"entry", "exit"}:
        raise HTTPException(422, "Tipo de acceso no válido.")

    point = db.scalar(
        select(models.AccessPoint).where(
            models.AccessPoint.direction == data.access_type,
            models.AccessPoint.status == "active"
        )
    )

    if not point:
        raise HTTPException(409, "No existe un punto de acceso activo para esta dirección.")

    card = db.scalar(
        select(models.Card).where(
            func.upper(func.replace(models.Card.card_code, " ", "")) == uid
        )
    )

    vehicle = None
    reason = None
    result = "denied"

    if not card:
        reason = "Tarjeta no registrada."

    elif card.status != "active":
        reason = "La tarjeta no está activa."

    else:
        vehicles = db.scalars(
            select(models.Vehicle).where(
                models.Vehicle.user_id == card.user_id,
                models.Vehicle.status == "active"
            )
        ).all()

        if len(vehicles) == 1:
            vehicle = vehicles[0]
            result = "authorized"
            reason = "Acceso autorizado."
        elif len(vehicles) == 0:
            reason = "El usuario no tiene un vehículo activo."
        else:
            reason = "El usuario tiene más de un vehículo activo."

    log = models.AccessLog(
        access_type=data.access_type,
        access_result=result,
        card_id=card.card_id if card else None,
        vehicle_id=vehicle.vehicle_id if vehicle else None,
        access_point_id=point.access_point_id,
        card_code_read=data.uid,
        reason=reason
    )

    db.add(log)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "No se pudo registrar el acceso.")

    return {
        "access_result": result,
        "message": reason,
        "uid": data.uid,
        "access_type": data.access_type,
        "vehicle_id": vehicle.vehicle_id if vehicle else None
    }


@app.on_event("startup")
def create_default_points():
    db = next(get_db())
    try:
        if db.scalar(select(func.count()).select_from(models.AccessPoint)) == 0:
            db.add_all([
                models.AccessPoint(name="Entrada principal", location="Portón norte",
                                   direction="entry", status="active"),
                models.AccessPoint(name="Salida principal", location="Portón norte",
                                   direction="exit", status="active"),
            ])
            db.commit()
    finally:
        db.close()


def save_or_409(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El dato ya existe o viola una regla de la base de datos.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=400, detail="No se pudo guardar el registro.")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "GateNova"}


@app.get("/api/dashboard", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    today = date.today()
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    access_today = db.scalar(select(func.count()).select_from(models.AccessLog).where(
        models.AccessLog.access_datetime >= start, models.AccessLog.access_datetime <= end)) or 0
    denied_today = db.scalar(select(func.count()).select_from(models.AccessLog).where(
        models.AccessLog.access_datetime >= start, models.AccessLog.access_datetime <= end,
        models.AccessLog.access_result == "denied")) or 0
    active_points = db.scalar(select(func.count()).select_from(models.AccessPoint).where(
        models.AccessPoint.status == "active")) or 0
    total_points = db.scalar(select(func.count()).select_from(models.AccessPoint)) or 0

    logs = db.scalars(select(models.AccessLog).where(
        models.AccessLog.access_result == "authorized"
    ).order_by(models.AccessLog.access_datetime.asc())).all()
    inside = set()
    for log in logs:
        if log.vehicle_id is None:
            continue
        if log.access_type == "entry":
            inside.add(log.vehicle_id)
        elif log.access_type == "exit":
            inside.discard(log.vehicle_id)

    return {
        "access_today": access_today,
        "vehicles_inside_estimate": len(inside),
        "denied_today": denied_today,
        "active_points": active_points,
        "total_points": total_points,
    }


@app.get("/api/user-roles")
def list_user_roles(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT e.enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'rol_user'
        ORDER BY e.enumsortorder
    """)).all()
    return [row[0] for row in rows]


def paginated_response(items, total, page, page_size, schema):
    return {
        "items": [schema.model_validate(item).model_dump(mode="json") for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def pagination_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
):
    return page, page_size


@app.get("/api/users", response_model=schemas.PaginatedResponse)
def list_users(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    page, page_size = pagination
    query = select(models.User).order_by(models.User.user_id.desc())
    total = db.scalar(select(func.count()).select_from(models.User)) or 0
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return paginated_response(items, total, page, page_size, schemas.UserOut)


@app.post("/api/users", response_model=schemas.UserOut, status_code=201)
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    allowed_roles = set(list_user_roles(db))
    if data.role not in allowed_roles:
        raise HTTPException(422, f"El rol debe coincidir con uno de los valores del tipo rol_user: {', '.join(sorted(allowed_roles))}.")
    item = models.User(**data.model_dump())
    db.add(item)
    save_or_409(db)
    db.refresh(item)
    return item


@app.put("/api/users/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, data: schemas.UserUpdate, db: Session = Depends(get_db)):
    item = db.get(models.User, user_id)
    if not item:
        raise HTTPException(404, "Usuario no encontrado.")

    allowed_roles = set(list_user_roles(db))
    if data.role not in allowed_roles:
        raise HTTPException(422, f"El rol debe coincidir con uno de los valores del tipo rol_user: {', '.join(sorted(allowed_roles))}.")

    for key, value in data.model_dump().items():
        setattr(item, key, value)

    save_or_409(db)
    db.refresh(item)
    return item


@app.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    item = db.get(models.User, user_id)
    if not item:
        raise HTTPException(404, "Usuario no encontrado.")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se puede eliminar: el usuario tiene tarjetas o vehículos relacionados.")
    return None


@app.get("/api/vehicles", response_model=schemas.PaginatedResponse)
def list_vehicles(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    page, page_size = pagination
    total = db.scalar(select(func.count()).select_from(models.Vehicle)) or 0
    items = db.scalars(select(models.Vehicle).order_by(models.Vehicle.vehicle_id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return paginated_response(items, total, page, page_size, schemas.VehicleOut)


@app.post("/api/vehicles", response_model=schemas.VehicleOut, status_code=201)
def create_vehicle(data: schemas.VehicleCreate, db: Session = Depends(get_db)):
    if data.status not in {"active", "inactive"}:
        raise HTTPException(422, "El estado debe ser active o inactive.")
    if not db.get(models.User, data.user_id):
        raise HTTPException(404, "El usuario relacionado no existe.")
    item = models.Vehicle(**data.model_dump())
    db.add(item)
    save_or_409(db)
    db.refresh(item)
    return item


@app.delete("/api/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Vehicle, vehicle_id)
    if not item:
        raise HTTPException(404, "Vehículo no encontrado.")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se puede eliminar: el vehículo aparece en el historial de accesos.")
    return None


@app.get("/api/cards", response_model=schemas.PaginatedResponse)
def list_cards(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    page, page_size = pagination
    total = db.scalar(select(func.count()).select_from(models.Card)) or 0
    items = db.scalars(select(models.Card).order_by(models.Card.card_id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return paginated_response(items, total, page, page_size, schemas.CardOut)


@app.post("/api/cards", response_model=schemas.CardOut, status_code=201)
def create_card(data: schemas.CardCreate, db: Session = Depends(get_db)):
    if data.status not in {"active", "disabled", "lost"}:
        raise HTTPException(422, "Estado no válido.")
    if not db.get(models.User, data.user_id):
        raise HTTPException(404, "El usuario relacionado no existe.")
    item = models.Card(**data.model_dump())
    db.add(item)
    save_or_409(db)
    db.refresh(item)
    return item


@app.delete("/api/cards/{card_id}", status_code=204)
def delete_card(card_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Card, card_id)
    if not item:
        raise HTTPException(404, "Tarjeta no encontrada.")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se puede eliminar: la tarjeta aparece en el historial de accesos.")
    return None


@app.get("/api/access-points", response_model=schemas.PaginatedResponse)
def list_access_points(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    page, page_size = pagination
    total = db.scalar(select(func.count()).select_from(models.AccessPoint)) or 0
    items = db.scalars(select(models.AccessPoint).order_by(models.AccessPoint.access_point_id)
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return paginated_response(items, total, page, page_size, schemas.AccessPointOut)


@app.post("/api/access-points", response_model=schemas.AccessPointOut, status_code=201)
def create_access_point(data: schemas.AccessPointCreate, db: Session = Depends(get_db)):
    if data.direction not in {"entry", "exit"}:
        raise HTTPException(422, "La dirección debe ser entry o exit.")
    if data.status not in {"active", "inactive"}:
        raise HTTPException(422, "El estado debe ser active o inactive.")
    item = models.AccessPoint(**data.model_dump())
    db.add(item)
    save_or_409(db)
    db.refresh(item)
    return item


@app.delete("/api/access-points/{access_point_id}", status_code=204)
def delete_access_point(access_point_id: int, db: Session = Depends(get_db)):
    item = db.get(models.AccessPoint, access_point_id)
    if not item:
        raise HTTPException(404, "Punto de acceso no encontrado.")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se puede eliminar: el punto aparece en el historial.")
    return None


@app.get("/api/access-logs", response_model=schemas.PaginatedResponse)
def list_access_logs(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    page, page_size = pagination
    total = db.scalar(select(func.count()).select_from(models.AccessLog)) or 0
    items = db.scalars(select(models.AccessLog).order_by(models.AccessLog.access_datetime.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return paginated_response(items, total, page, page_size, schemas.AccessLogOut)


@app.post("/api/access-logs", response_model=schemas.AccessLogOut, status_code=201)
def create_access_log(data: schemas.AccessLogCreate, db: Session = Depends(get_db)):
    if data.access_type not in {"entry", "exit"}:
        raise HTTPException(422, "El tipo debe ser entry o exit.")
    if data.access_result not in {"authorized", "denied"}:
        raise HTTPException(422, "El resultado debe ser authorized o denied.")
    point = db.get(models.AccessPoint, data.access_point_id)
    if not point:
        raise HTTPException(404, "El punto de acceso no existe.")
    if data.card_id is not None and not db.get(models.Card, data.card_id):
        raise HTTPException(404, "La tarjeta no existe.")
    if data.vehicle_id is not None and not db.get(models.Vehicle, data.vehicle_id):
        raise HTTPException(404, "El vehículo no existe.")
    item = models.AccessLog(**data.model_dump())
    db.add(item)
    save_or_409(db)
    db.refresh(item)
    return item
