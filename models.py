from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

RecordStatus = Literal["待登记", "待复核", "已计入", "已退回", "作废"]
QualityLevel = Literal["优秀", "良好", "合格", "不合格"]
AppealStatus = Literal["待处理", "处理中", "已通过", "已驳回"]


class AppealCorrection(BaseModel):
    quality: Optional[QualityLevel] = None
    duration_hours: Optional[float] = None
    deduction_rule_id: Optional[str] = None
    clear_deduction_rule: bool = False
    deduction_points: Optional[float] = None
    final_points: Optional[float] = None
    note: Optional[str] = None


class TimelineEvent(BaseModel):
    event_type: str
    operator: str
    operated_at: datetime = Field(default_factory=datetime.now)
    description: str


class ServiceRecordAppeal(BaseModel):
    appeal_id: str
    record_id: str
    participant_id: str
    participant_name: str
    project_id: str
    service_date: date
    month: str
    appeal_reason: str
    supplementary_note: Optional[str] = None
    expected_result: Optional[str] = None
    status: AppealStatus = "待处理"
    submitted_by: str
    submitted_at: datetime = Field(default_factory=datetime.now)
    handler: Optional[str] = None
    handled_at: Optional[datetime] = None
    handle_note: Optional[str] = None
    rejection_reason: Optional[str] = None
    correction: Optional[AppealCorrection] = None
    original_calculated_points: Optional[float] = None
    original_deduction_points: Optional[float] = None
    original_final_points: Optional[float] = None
    original_quality: Optional[QualityLevel] = None
    original_duration_hours: Optional[float] = None
    original_status: Optional[RecordStatus] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)


class ServiceProject(BaseModel):
    project_id: str
    project_name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True


class PointRule(BaseModel):
    rule_id: str
    rule_version: str
    project_id: str
    base_points_per_hour: float
    quality_multiplier: dict = Field(default_factory=lambda: {
        "优秀": 1.5,
        "良好": 1.2,
        "合格": 1.0,
        "不合格": 0.0
    })
    effective_date: date
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str


class DeductionRule(BaseModel):
    deduction_id: str
    rule_version: str
    reason: str
    deduction_points: float
    effective_date: date
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str


class ServiceRecord(BaseModel):
    record_id: str
    participant_name: str
    participant_id: str
    project_id: str
    service_date: date
    start_time: str
    end_time: str
    duration_hours: float
    quality: QualityLevel = "合格"
    remarks: Optional[str] = None
    status: RecordStatus = "待登记"
    registered_by: str
    registered_at: datetime = Field(default_factory=datetime.now)
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    review_note: Optional[str] = None
    applicable_point_rule_id: Optional[str] = None
    applicable_point_version: Optional[str] = None
    applicable_deduction_id: Optional[str] = None
    applicable_deduction_version: Optional[str] = None
    calculated_points: Optional[float] = None
    deduction_points: Optional[float] = None
    final_points: Optional[float] = None
    month: Optional[str] = None
    warnings: Optional[List[str]] = Field(default_factory=list)


class MonthlySettlement(BaseModel):
    settlement_id: str
    month: str
    participant_id: str
    participant_name: str
    total_records: int = 0
    total_hours: float = 0.0
    base_points: float = 0.0
    deduction_points: float = 0.0
    final_points: float = 0.0
    is_official: bool = False
    settled_at: datetime = Field(default_factory=datetime.now)
    settled_by: str
