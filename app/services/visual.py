"""Builds the frontend-agnostic layout payloads for the Resort grid and Houseboat hull dashboards."""
import math
from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Property, PropertyType, Unit, UnitStatus, UnitType
from app.schemas.visual import (BoatOutline, CabinSlot, CharterState, Floor, GridCell, LegendItem, VisualLayout)

COLORS = {"AVAILABLE": "#10b981", "BOOKED": "#e11d48", "ON_HOLD": "#f59e0b", "MAINTENANCE": "#8b5cf6"}
LABELS = {"AVAILABLE": "Available", "BOOKED": "Booked", "ON_HOLD": "On hold", "MAINTENANCE": "Maintenance"}
_RANK = {"AVAILABLE": 0, "ON_HOLD": 1, "BOOKED": 2, "MAINTENANCE": 3}
HULL_PATH = "M20 60 Q20 104 84 104 L320 104 Q384 104 400 60 Q384 16 320 16 L84 16 Q20 16 20 60 Z"


async def live_status(session: AsyncSession, tenant_id: UUID, property_id: UUID, start: date, end: date):
    units = (await session.execute(select(Unit).where(
        Unit.tenant_id == tenant_id, Unit.property_id == property_id, Unit.is_active.is_(True))
        .order_by(Unit.unit_name))).scalars().all()
    live = {u.id: {"status": "MAINTENANCE" if u.status == UnitStatus.MAINTENANCE else "AVAILABLE", "booking_id": None}
            for u in units}
    charters = {u.id for u in units if u.type == UnitType.WHOLE_BOAT}
    rows = (await session.execute(select(Booking.id, Booking.unit_id, Booking.status).where(
        Booking.tenant_id == tenant_id, Booking.property_id == property_id,
        Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        Booking.check_in < end, Booking.check_out > start,
        or_(Booking.status == BookingStatus.CONFIRMED, Booking.hold_expires_at > func.clock_timestamp())))).all()
    for bid, unit_id, bstatus in rows:
        st = "BOOKED" if bstatus == BookingStatus.CONFIRMED else "ON_HOLD"
        targets = list(live) if unit_id in charters else [unit_id]      # a charter blocks every cabin
        for uid in targets:
            if uid in live and _RANK[st] > _RANK[live[uid]["status"]]:
                live[uid] = {"status": st, "booking_id": bid}
    return units, live


def _legend() -> list[LegendItem]:
    return [LegendItem(status=k, color=COLORS[k], label=LABELS[k]) for k in COLORS]


async def build_layout(session: AsyncSession, prop: Property, start: date, end: date) -> VisualLayout:
    units, live = await live_status(session, prop.tenant_id, prop.id, start, end)
    base = dict(property_id=prop.id, property_name=prop.name, property_type=prop.type.value,
                check_in=start, check_out=end, legend=_legend())
    bookable = [u for u in units if u.type != UnitType.WHOLE_BOAT]
    summary = {k: 0 for k in COLORS}
    for u in bookable:
        summary[live[u.id]["status"]] += 1

    if prop.type == PropertyType.HOUSEBOAT:
        n = max(len(bookable), 1)
        per_row = math.ceil(n / 2)
        w = min(60.0, 280.0 / per_row)
        cabins = []
        for i, u in enumerate(bookable):
            lay = u.layout_json or {}
            st = live[u.id]
            cabins.append(CabinSlot(
                unit_id=u.id, name=u.unit_name,
                x=lay.get("x", 80 + (i // 2) * w), y=lay.get("y", 28 if i % 2 == 0 else 64),
                w=lay.get("w", w - 4), h=lay.get("h", 28),
                status=st["status"], color=COLORS[st["status"]], booking_id=st["booking_id"]))
        charter = next((u for u in units if u.type == UnitType.WHOLE_BOAT), None)
        return VisualLayout(**base, view="BOAT", summary=summary,
                            outline=BoatOutline(view_box="0 0 420 120", hull_path=HULL_PATH), cabins=cabins,
                            charter=CharterState(unit_id=charter.id, name=charter.unit_name,
                                                 status=live[charter.id]["status"],
                                                 color=COLORS[live[charter.id]["status"]]) if charter else None)

    cols_default = 4
    by_floor: dict[int, list[GridCell]] = defaultdict(list)
    for i, u in enumerate(bookable):
        lay = u.layout_json or {}
        st = live[u.id]
        by_floor[int(lay.get("floor", 1))].append(GridCell(
            unit_id=u.id, name=u.unit_name, unit_type=u.type.value,
            row=int(lay.get("row", i // cols_default)), col=int(lay.get("col", i % cols_default)),
            row_span=int(lay.get("row_span", 1)), col_span=int(lay.get("col_span", 1)),
            status=st["status"], color=COLORS[st["status"]], booking_id=st["booking_id"]))
    floors = [Floor(floor=f, label=f"Floor {f}", rows=max(c.row + c.row_span for c in cells),
                    columns=max(c.col + c.col_span for c in cells), cells=cells)
              for f, cells in sorted(by_floor.items())]
    return VisualLayout(**base, view="GRID", summary=summary, floors=floors)
