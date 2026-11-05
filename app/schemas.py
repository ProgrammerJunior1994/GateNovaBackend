from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Any


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    institutional_code: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=80)
    role: str


class UserUpdate(BaseModel):
    institutional_code: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=80)
    role: str


class UserOut(ORMModel):
    user_id: int
    institutional_code: int
    name: str
    last_name: str
    role: str


class VehicleCreate(BaseModel):
    trademark: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=50)
    plate: str = Field(min_length=1, max_length=20)
    user_id: int
    status: str = "active"


class VehicleOut(ORMModel):
    vehicle_id: int
    trademark: str
    model: str
    plate: str
    user_id: int
    status: str


class CardCreate(BaseModel):
    card_code: str = Field(min_length=1, max_length=50)
    user_id: int
    status: str = "active"


class CardOut(ORMModel):
    card_id: int
    card_code: str
    user_id: int
    status: str
    assigned_at: datetime


class AccessPointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    location: str = Field(min_length=1, max_length=120)
    direction: str
    status: str = "active"


class AccessPointOut(ORMModel):
    access_point_id: int
    name: str
    location: str
    direction: str
    status: str


class AccessLogCreate(BaseModel):
    access_type: str
    access_result: str
    access_point_id: int
    card_id: int | None = None
    vehicle_id: int | None = None
    card_code_read: str | None = None
    reason: str | None = None


class AccessLogOut(ORMModel):
    access_log_id: int
    access_datetime: datetime
    access_type: str
    access_result: str
    card_id: int | None
    vehicle_id: int | None
    access_point_id: int
    card_code_read: str | None
    reason: str | None


class DashboardOut(BaseModel):
    access_today: int
    vehicles_inside_estimate: int
    denied_today: int
    active_points: int
    total_points: int


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int
