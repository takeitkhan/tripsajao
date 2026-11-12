from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

LiveStatus = Literal["AVAILABLE", "BOOKED", "ON_HOLD", "MAINTENANCE"]


class LegendItem(BaseModel):
    status: LiveStatus
    color: str
    label: str


class GridCell(BaseModel):
    unit_id: UUID
    name: str
    unit_type: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    status: LiveStatus
    color: str
    booking_id: UUID | None = None


class Floor(BaseModel):
    floor: int
    label: str
    rows: int
    columns: int
    cells: list[GridCell]


class BoatOutline(BaseModel):
    view_box: str
    hull_path: str


class CabinSlot(BaseModel):
    unit_id: UUID
    name: str
    x: float
    y: float
    w: float
    h: float
    status: LiveStatus
    color: str
    booking_id: UUID | None = None


class CharterState(BaseModel):
    unit_id: UUID
    name: str
    status: LiveStatus
    color: str


class VisualLayout(BaseModel):
    property_id: UUID
    property_name: str
    property_type: str
    view: Literal["GRID", "BOAT"]
    check_in: date
    check_out: date
    legend: list[LegendItem]
    summary: dict[str, int]
    floors: list[Floor] | None = None          # GRID
    outline: BoatOutline | None = None         # BOAT
    cabins: list[CabinSlot] | None = None      # BOAT
    charter: CharterState | None = None        # BOAT (whole-boat unit, if configured)
