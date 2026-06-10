from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7
from app.models.amenity import Amenity, program_amenities


class TreatmentFocus(Base):
    __tablename__ = "treatment_focuses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    image_url: Mapped[str | None] = mapped_column(String(500))
    icon: Mapped[str | None] = mapped_column(String(80))
    display_order: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0", index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    programs: Mapped[list["TreatmentProgram"]] = relationship(back_populates="focus")


class TreatmentProgramType(StrEnum):
    SESSION = "session"
    STAY_PACKAGE = "stay_package"


class TreatmentStayPackageKind(StrEnum):
    TREATMENT = "treatment"
    SPECIAL = "special"


class TreatmentGuestApplicability(StrEnum):
    ALL = "all"
    ADULT = "adult"
    CHILD = "child"


class TreatmentProgram(Base):
    __tablename__ = "treatment_programs"
    __table_args__ = (
        CheckConstraint(
            "min_nights IS NULL OR min_nights > 0",
            name="ck_treatment_programs_min_nights_positive",
        ),
        CheckConstraint(
            "max_nights IS NULL OR max_nights > 0",
            name="ck_treatment_programs_max_nights_positive",
        ),
        CheckConstraint(
            "max_nights IS NULL OR min_nights IS NULL OR max_nights >= min_nights",
            name="ck_treatment_programs_nights_order",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="ck_treatment_programs_duration_positive",
        ),
        CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_treatment_programs_price_non_negative",
        ),
        CheckConstraint(
            "group_size_min IS NULL OR group_size_min > 0",
            name="ck_treatment_programs_group_size_min_positive",
        ),
        CheckConstraint(
            "group_size_max IS NULL OR group_size_max > 0",
            name="ck_treatment_programs_group_size_max_positive",
        ),
        CheckConstraint(
            "group_size_max IS NULL OR group_size_min IS NULL "
            "OR group_size_max >= group_size_min",
            name="ck_treatment_programs_group_size_order",
        ),
        CheckConstraint(
            "medical_exam_count >= 0",
            name="ck_treatment_programs_medical_exam_count_non_negative",
        ),
        CheckConstraint(
            "medical_procedure_count >= 0",
            name="ck_treatment_programs_medical_procedure_count_non_negative",
        ),
        CheckConstraint(
            "sauna_entries IS NULL OR sauna_entries >= 0",
            name="ck_treatment_programs_sauna_entries_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    focus_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("treatment_focuses.id", ondelete="SET NULL"),
        index=True,
    )
    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    program_type: Mapped[TreatmentProgramType] = mapped_column(
        SQLEnum(
            TreatmentProgramType,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=TreatmentProgramType.SESSION,
        server_default=TreatmentProgramType.SESSION.value,
        index=True,
    )
    stay_package_kind: Mapped[TreatmentStayPackageKind] = mapped_column(
        SQLEnum(
            TreatmentStayPackageKind,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=TreatmentStayPackageKind.TREATMENT,
        server_default=TreatmentStayPackageKind.TREATMENT.value,
        index=True,
    )
    guest_applicability: Mapped[TreatmentGuestApplicability] = mapped_column(
        SQLEnum(
            TreatmentGuestApplicability,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=TreatmentGuestApplicability.ALL,
        server_default=TreatmentGuestApplicability.ALL.value,
    )

    min_nights: Mapped[int | None] = mapped_column(Integer)
    max_nights: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))

    instructor_name: Mapped[str | None] = mapped_column(String(255))
    instructor_bio: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    group_size_min: Mapped[int | None] = mapped_column(Integer)
    group_size_max: Mapped[int | None] = mapped_column(Integer)

    what_to_bring: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    medical_exam_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    medical_procedure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    drink_cure_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sauna_entries: Mapped[int | None] = mapped_column(Integer)
    pool_access_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    included_services: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default_stay_package: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    amenities: Mapped[list[Amenity]] = relationship(
        secondary=program_amenities, back_populates="programs"
    )
    focus: Mapped[TreatmentFocus | None] = relationship(back_populates="programs")
