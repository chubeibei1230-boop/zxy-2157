import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

from models import (
    ServiceProject, PointRule, DeductionRule,
    ServiceRecord, MonthlySettlement, QualityLevel,
    ServiceRecordAppeal, AppealCorrection, TimelineEvent
)
import storage


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ==================== Project Management ====================

def create_project(project_name: str, description: Optional[str] = None) -> ServiceProject:
    project = ServiceProject(
        project_id=generate_id("proj"),
        project_name=project_name,
        description=description
    )
    storage.save_project(project)
    return project


def update_project(project_id: str, project_name: Optional[str] = None,
                   description: Optional[str] = None, is_active: Optional[bool] = None) -> Optional[ServiceProject]:
    project = storage.get_project(project_id)
    if not project:
        return None
    if project_name is not None:
        project.project_name = project_name
    if description is not None:
        project.description = description
    if is_active is not None:
        project.is_active = is_active
    storage.save_project(project)
    return project


# ==================== Point Rule Management ====================

def _get_next_version(project_id: str) -> str:
    rules = [r for r in storage.list_point_rules() if r.project_id == project_id]
    version_num = len(rules) + 1
    return f"v{version_num}"


def create_point_rule(project_id: str, base_points_per_hour: float,
                      quality_multiplier: Dict[str, float],
                      effective_date: date, created_by: str,
                      description: Optional[str] = None) -> Optional[PointRule]:
    if not storage.get_project(project_id):
        return None
    rule = PointRule(
        rule_id=generate_id("prule"),
        rule_version=_get_next_version(project_id),
        project_id=project_id,
        base_points_per_hour=base_points_per_hour,
        quality_multiplier=quality_multiplier,
        effective_date=effective_date,
        description=description,
        created_by=created_by
    )
    storage.save_point_rule(rule)
    return rule


def list_point_rules_by_project(project_id: str) -> List[PointRule]:
    rules = [r for r in storage.list_point_rules() if r.project_id == project_id]
    rules.sort(key=lambda r: r.effective_date, reverse=True)
    return rules


# ==================== Deduction Rule Management ====================

def _get_next_deduction_version() -> str:
    rules = storage.list_deduction_rules()
    version_num = len(rules) + 1
    return f"v{version_num}"


def create_deduction_rule(reason: str, deduction_points: float,
                          effective_date: date, created_by: str,
                          description: Optional[str] = None) -> DeductionRule:
    rule = DeductionRule(
        deduction_id=generate_id("drule"),
        rule_version=_get_next_deduction_version(),
        reason=reason,
        deduction_points=deduction_points,
        effective_date=effective_date,
        description=description,
        created_by=created_by
    )
    storage.save_deduction_rule(rule)
    return rule


def list_deduction_rules_by_date(effective_date: Optional[date] = None) -> List[DeductionRule]:
    rules = storage.list_deduction_rules()
    if effective_date:
        rules = [r for r in rules if r.effective_date <= effective_date]
    rules.sort(key=lambda r: r.effective_date, reverse=True)
    return rules


# ==================== Record Detection & Validation ====================

def detect_duplicate_records(record: ServiceRecord) -> List[ServiceRecord]:
    """检测同一人员同一时间段的重复登记"""
    all_records = storage.list_records()
    duplicates = []
    for existing in all_records:
        if existing.record_id == record.record_id:
            continue
        if existing.status == "作废":
            continue
        if existing.participant_id != record.participant_id:
            continue
        if existing.service_date != record.service_date:
            continue
        def to_minutes(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)
        e_start, e_end = to_minutes(existing.start_time), to_minutes(existing.end_time)
        r_start, r_end = to_minutes(record.start_time), to_minutes(record.end_time)
        if max(e_start, r_start) < min(e_end, r_end):
            duplicates.append(existing)
    return duplicates


def detect_duration_anomaly(record: ServiceRecord) -> Tuple[bool, Optional[str]]:
    """检测服务时长异常"""
    def to_minutes(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    calc_duration = (to_minutes(record.end_time) - to_minutes(record.start_time)) / 60.0
    if calc_duration <= 0:
        return True, "结束时间必须晚于开始时间"
    if abs(calc_duration - record.duration_hours) > 0.1:
        return True, f"登记时长({record.duration_hours}h)与时间段计算时长({calc_duration:.1f}h)不符"
    if record.duration_hours > 16:
        return True, f"服务时长({record.duration_hours}h)超过单日最大合理值16小时"
    if record.duration_hours < 0.5:
        return True, f"服务时长({record.duration_hours}h)过短，少于0.5小时"
    return False, None


def detect_review_backlog() -> Dict:
    """检测复核积压"""
    records = storage.list_records()
    pending = [r for r in records if r.status == "待复核"]
    now = datetime.now()
    backlog = []
    for r in pending:
        if r.registered_at:
            hours = (now - r.registered_at).total_seconds() / 3600
            if hours > 48:
                backlog.append({
                    "record_id": r.record_id,
                    "participant_name": r.participant_name,
                    "registered_at": r.registered_at.isoformat(),
                    "pending_hours": round(hours, 1)
                })
    return {
        "total_pending": len(pending),
        "backlog_count": len(backlog),
        "backlog_records": backlog
    }


def detect_missing_rules(record: ServiceRecord) -> bool:
    """检测规则缺失"""
    rule = storage.get_applicable_point_rule(record.project_id, record.service_date)
    return rule is None


# ==================== Record Management ====================

def _calculate_points(record: ServiceRecord, point_rule: PointRule) -> Tuple[float, Optional[str]]:
    multiplier = point_rule.quality_multiplier.get(record.quality, 0.0)
    return record.duration_hours * point_rule.base_points_per_hour * multiplier, point_rule.rule_version


def create_record(participant_name: str, participant_id: str, project_id: str,
                  service_date: date, start_time: str, end_time: str,
                  duration_hours: float, registered_by: str,
                  quality: QualityLevel = "合格", remarks: Optional[str] = None) -> Tuple[Optional[ServiceRecord], List[str], Optional[str]]:
    if not storage.get_project(project_id):
        return None, [], "项目不存在，无法登记服务记录"
    record = ServiceRecord(
        record_id=generate_id("rec"),
        participant_name=participant_name,
        participant_id=participant_id,
        project_id=project_id,
        service_date=service_date,
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration_hours,
        quality=quality,
        remarks=remarks,
        status="待登记",
        registered_by=registered_by,
        month=service_date.strftime("%Y-%m")
    )
    warnings = []

    duplicates = detect_duplicate_records(record)
    if duplicates:
        dup_info = ", ".join([f"{d.record_id}({d.start_time}-{d.end_time})" for d in duplicates[:3]])
        warnings.append(f"疑似重复登记: {dup_info}")

    has_duration_issue, duration_msg = detect_duration_anomaly(record)
    if has_duration_issue:
        warnings.append(f"时长异常: {duration_msg}")

    if detect_missing_rules(record):
        warnings.append("规则缺失: 该项目在服务日期无可用积分规则")
    else:
        point_rule = storage.get_applicable_point_rule(record.project_id, record.service_date)
        if point_rule:
            record.applicable_point_rule_id = point_rule.rule_id
            record.applicable_point_version = point_rule.rule_version
            calc_points, _ = _calculate_points(record, point_rule)
            record.calculated_points = calc_points
            record.deduction_points = 0.0
            record.final_points = calc_points

    record.warnings = warnings
    storage.save_record(record)
    return record, warnings, None


def submit_record(record_id: str, operator: str) -> Tuple[Optional[ServiceRecord], Optional[str]]:
    record = storage.get_record(record_id)
    if not record:
        return None, "记录不存在"
    if record.status != "待登记":
        return None, f"当前状态为「{record.status}」，只有「待登记」的记录可以提交复核"
    record.status = "待复核"
    storage.save_record(record)
    return record, None


def review_record(record_id: str, reviewer: str, approved: bool,
                  rejection_reason: Optional[str] = None,
                  deduction_rule_id: Optional[str] = None,
                  review_note: Optional[str] = None) -> Tuple[Optional[ServiceRecord], Optional[str]]:
    record = storage.get_record(record_id)
    if not record:
        return None, "记录不存在"
    if record.status != "待复核":
        return None, f"当前状态为「{record.status}」，只有「待复核」的记录可以复核"

    old_calc_points = record.calculated_points or 0.0
    old_ded_points = record.deduction_points or 0.0
    old_final_points = record.final_points if record.final_points is not None else old_calc_points - old_ded_points
    old_duration = record.duration_hours
    old_status = record.status

    record.reviewed_by = reviewer
    record.reviewed_at = datetime.now()

    if approved:
        if not record.applicable_point_rule_id:
            point_rule = storage.get_applicable_point_rule(record.project_id, record.service_date)
            if point_rule:
                record.applicable_point_rule_id = point_rule.rule_id
                record.applicable_point_version = point_rule.rule_version
                calc_points, _ = _calculate_points(record, point_rule)
                record.calculated_points = calc_points
                if record.deduction_points is None:
                    record.deduction_points = 0.0
                record.final_points = record.calculated_points - record.deduction_points
        if deduction_rule_id:
            ded_rule = storage.get_deduction_rule(deduction_rule_id)
            if not ded_rule:
                return None, "扣减规则不存在"
            if ded_rule.effective_date > record.service_date:
                return None, (f"扣减规则生效日期({ded_rule.effective_date})晚于服务日期({record.service_date})，"
                              f"不能将该扣减规则应用于此历史记录")
            record.applicable_deduction_id = ded_rule.deduction_id
            record.applicable_deduction_version = ded_rule.rule_version
            record.deduction_points = ded_rule.deduction_points
            if record.calculated_points is not None:
                record.final_points = record.calculated_points - record.deduction_points
        record.status = "已计入"
    else:
        record.status = "已退回"
        record.rejection_reason = rejection_reason or "未说明原因"

    record.review_note = review_note

    storage.save_record(record)

    _update_settlement_after_correction(
        record, old_calc_points, old_ded_points,
        old_final_points, old_duration, old_status, reviewer
    )

    return record, None


def void_record(record_id: str, operator: str, void_reason: Optional[str] = None) -> Optional[ServiceRecord]:
    record = storage.get_record(record_id)
    if not record:
        return None

    old_calc_points = record.calculated_points or 0.0
    old_ded_points = record.deduction_points or 0.0
    old_final_points = record.final_points if record.final_points is not None else old_calc_points - old_ded_points
    old_duration = record.duration_hours
    old_status = record.status

    record.status = "作废"
    record.reviewed_by = operator
    record.reviewed_at = datetime.now()
    record.rejection_reason = void_reason or record.rejection_reason or "作废处理"
    record.review_note = void_reason

    storage.save_record(record)

    _update_settlement_after_correction(
        record, old_calc_points, old_ded_points,
        old_final_points, old_duration, old_status, operator
    )

    return record


def update_record(record_id: str, **kwargs) -> Tuple[Optional[ServiceRecord], Optional[str]]:
    record = storage.get_record(record_id)
    if not record:
        return None, "记录不存在"
    if record.status not in ["待登记", "已退回"]:
        return None, f"当前状态为「{record.status}」，只有「待登记」或「已退回」的记录可以修改"
    for key, value in kwargs.items():
        if hasattr(record, key) and value is not None:
            setattr(record, key, value)
    if "service_date" in kwargs:
        record.month = record.service_date.strftime("%Y-%m")
    if kwargs.get("project_id") and not storage.get_project(record.project_id):
        return None, "目标项目不存在"

    warnings = []
    duplicates = detect_duplicate_records(record)
    if duplicates:
        dup_info = ", ".join([f"{d.record_id}({d.start_time}-{d.end_time})" for d in duplicates[:3]])
        warnings.append(f"疑似重复登记: {dup_info}")
    has_duration_issue, duration_msg = detect_duration_anomaly(record)
    if has_duration_issue:
        warnings.append(f"时长异常: {duration_msg}")
    if detect_missing_rules(record):
        warnings.append("规则缺失: 该项目在服务日期无可用积分规则")
    else:
        point_rule = storage.get_applicable_point_rule(record.project_id, record.service_date)
        if point_rule:
            record.applicable_point_rule_id = point_rule.rule_id
            record.applicable_point_version = point_rule.rule_version
            calc_points, _ = _calculate_points(record, point_rule)
            record.calculated_points = calc_points
            record.deduction_points = record.deduction_points or 0.0
            record.final_points = record.calculated_points - record.deduction_points
    record.warnings = warnings
    if record.status == "已退回":
        record.status = "待登记"
    record.rejection_reason = None
    record.reviewed_by = None
    record.reviewed_at = None
    storage.save_record(record)
    return record, None


# ==================== Query & Filter ====================

def query_records(participant_id: Optional[str] = None,
                  participant_name: Optional[str] = None,
                  project_id: Optional[str] = None,
                  rule_version: Optional[str] = None,
                  status: Optional[str] = None,
                  month: Optional[str] = None,
                  registered_by: Optional[str] = None) -> List[ServiceRecord]:
    records = storage.list_records()
    if participant_id:
        records = [r for r in records if r.participant_id == participant_id]
    if participant_name:
        records = [r for r in records if participant_name in r.participant_name]
    if project_id:
        records = [r for r in records if r.project_id == project_id]
    if rule_version:
        records = [r for r in records if r.applicable_point_version == rule_version or r.applicable_deduction_version == rule_version]
    if status:
        records = [r for r in records if r.status == status]
    if month:
        records = [r for r in records if r.month == month]
    if registered_by:
        records = [r for r in records if r.registered_by == registered_by]
    records.sort(key=lambda r: r.registered_at, reverse=True)
    return records


# ==================== Review Workstation ====================

AnomalyType = Literal["duplicate", "duration", "missing_rule", "all"]


def query_pending_review(
    month: Optional[str] = None,
    project_id: Optional[str] = None,
    participant_id: Optional[str] = None,
    participant_name: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Dict:
    """查询待复核记录，支持多维度筛选和异常类型过滤"""
    records = query_records(status="待复核", month=month, project_id=project_id,
                            participant_id=participant_id, participant_name=participant_name)

    if anomaly_type and anomaly_type != "all":
        keyword_map = {
            "duplicate": "疑似重复登记",
            "duration": "时长异常",
            "missing_rule": "规则缺失"
        }
        keyword = keyword_map.get(anomaly_type, "")
        if keyword:
            records = [r for r in records if any(keyword in w for w in (r.warnings or []))]

    total = len(records)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    paged_records = records[start:end]

    project_map = {p.project_id: p.project_name for p in storage.list_projects()}

    record_list = []
    for r in paged_records:
        record_list.append({
            "record_id": r.record_id,
            "participant_id": r.participant_id,
            "participant_name": r.participant_name,
            "project_id": r.project_id,
            "project_name": project_map.get(r.project_id, "未知项目"),
            "service_date": r.service_date,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "duration_hours": r.duration_hours,
            "quality": r.quality,
            "status": r.status,
            "calculated_points": r.calculated_points,
            "deduction_points": r.deduction_points,
            "final_points": r.final_points,
            "month": r.month,
            "warnings": r.warnings or [],
            "registered_by": r.registered_by,
            "registered_at": r.registered_at,
            "has_duplicate": any("疑似重复登记" in w for w in (r.warnings or [])),
            "has_duration_anomaly": any("时长异常" in w for w in (r.warnings or [])),
            "has_missing_rule": any("规则缺失" in w for w in (r.warnings or [])),
        })

    anomaly_stats = {
        "total_pending": len(query_records(status="待复核")),
        "duplicate_count": len([r for r in query_records(status="待复核")
                                if any("疑似重复登记" in w for w in (r.warnings or []))]),
        "duration_anomaly_count": len([r for r in query_records(status="待复核")
                                       if any("时长异常" in w for w in (r.warnings or []))]),
        "missing_rule_count": len([r for r in query_records(status="待复核")
                                   if any("规则缺失" in w for w in (r.warnings or []))]),
    }

    return {
        "total": total,
        "total_pages": total_pages,
        "page": page,
        "page_size": page_size,
        "records": record_list,
        "anomaly_stats": anomaly_stats
    }


def get_review_detail(record_id: str) -> Optional[Dict]:
    """获取复核详情：基础信息、适用积分规则、扣减规则候选项、历史申诉"""
    record = storage.get_record(record_id)
    if not record:
        return None

    project = storage.get_project(record.project_id)
    project_name = project.project_name if project else "未知项目"

    point_rule = None
    if record.applicable_point_rule_id:
        point_rule = storage.get_point_rule(record.applicable_point_rule_id)
    else:
        point_rule = storage.get_applicable_point_rule(record.project_id, record.service_date)

    deduction_rules = list_deduction_rules_by_date(record.service_date)
    deduction_candidates = []
    for dr in deduction_rules:
        deduction_candidates.append({
            "deduction_id": dr.deduction_id,
            "rule_version": dr.rule_version,
            "reason": dr.reason,
            "deduction_points": dr.deduction_points,
            "description": dr.description,
            "is_applicable": dr.effective_date <= record.service_date
        })

    appeals = storage.get_appeals_by_record(record_id)
    appeal_list = []
    for a in appeals:
        appeal_list.append({
            "appeal_id": a.appeal_id,
            "status": a.status,
            "appeal_reason": a.appeal_reason,
            "supplementary_note": a.supplementary_note,
            "expected_result": a.expected_result,
            "submitted_by": a.submitted_by,
            "submitted_at": a.submitted_at,
            "handler": a.handler,
            "handled_at": a.handled_at,
            "handle_note": a.handle_note,
            "rejection_reason": a.rejection_reason,
        })

    duplicate_records = detect_duplicate_records(record)
    duplicate_list = []
    for dr in duplicate_records:
        dup_project = storage.get_project(dr.project_id)
        duplicate_list.append({
            "record_id": dr.record_id,
            "project_name": dup_project.project_name if dup_project else "未知项目",
            "service_date": dr.service_date,
            "start_time": dr.start_time,
            "end_time": dr.end_time,
            "duration_hours": dr.duration_hours,
            "status": dr.status,
            "participant_name": dr.participant_name,
        })

    has_duration_issue, duration_msg = detect_duration_anomaly(record)

    return {
        "record": {
            "record_id": record.record_id,
            "participant_id": record.participant_id,
            "participant_name": record.participant_name,
            "project_id": record.project_id,
            "project_name": project_name,
            "service_date": record.service_date,
            "start_time": record.start_time,
            "end_time": record.end_time,
            "duration_hours": record.duration_hours,
            "quality": record.quality,
            "remarks": record.remarks,
            "status": record.status,
            "registered_by": record.registered_by,
            "registered_at": record.registered_at,
            "reviewed_by": record.reviewed_by,
            "reviewed_at": record.reviewed_at,
            "rejection_reason": record.rejection_reason,
            "review_note": record.review_note,
            "calculated_points": record.calculated_points,
            "deduction_points": record.deduction_points,
            "final_points": record.final_points,
            "month": record.month,
            "warnings": record.warnings or [],
        },
        "applicable_point_rule": point_rule.dict() if point_rule else None,
        "deduction_candidates": deduction_candidates,
        "current_deduction": {
            "deduction_id": record.applicable_deduction_id,
            "deduction_version": record.applicable_deduction_version,
            "deduction_points": record.deduction_points,
        } if record.applicable_deduction_id else None,
        "appeal_history": appeal_list,
        "duplicate_records": duplicate_list,
        "duration_anomaly": {
            "has_issue": has_duration_issue,
            "message": duration_msg
        },
        "missing_rule": point_rule is None,
    }


# ==================== Statistics ====================

def get_personal_point_summary(participant_id: Optional[str] = None,
                                month: Optional[str] = None) -> List[Dict]:
    records = query_records(status="已计入", month=month)
    summary = defaultdict(lambda: {
        "participant_id": "",
        "participant_name": "",
        "total_records": 0,
        "total_hours": 0.0,
        "base_points": 0.0,
        "deduction_points": 0.0,
        "final_points": 0.0
    })
    for r in records:
        if participant_id and r.participant_id != participant_id:
            continue
        key = r.participant_id
        s = summary[key]
        s["participant_id"] = r.participant_id
        s["participant_name"] = r.participant_name
        s["total_records"] += 1
        s["total_hours"] += r.duration_hours
        s["base_points"] += r.calculated_points or 0.0
        s["deduction_points"] += r.deduction_points or 0.0
        s["final_points"] += r.final_points or 0.0
    result = list(summary.values())
    result.sort(key=lambda x: x["final_points"], reverse=True)
    return result


def get_project_contribution_ranking(month: Optional[str] = None) -> List[Dict]:
    records = query_records(status="已计入", month=month)
    project_stats = defaultdict(lambda: {
        "project_id": "",
        "project_name": "",
        "total_records": 0,
        "total_participants": set(),
        "total_hours": 0.0,
        "total_points": 0.0
    })
    projects = {p.project_id: p.project_name for p in storage.list_projects()}
    for r in records:
        s = project_stats[r.project_id]
        s["project_id"] = r.project_id
        s["project_name"] = projects.get(r.project_id, "未知项目")
        s["total_records"] += 1
        s["total_participants"].add(r.participant_id)
        s["total_hours"] += r.duration_hours
        s["total_points"] += r.final_points or 0.0
    result = []
    for s in project_stats.values():
        s["total_participants"] = len(s["total_participants"])
        result.append(s)
    result.sort(key=lambda x: x["total_points"], reverse=True)
    return result


def get_rejection_reason_distribution(month: Optional[str] = None) -> List[Dict]:
    records = query_records(status="已退回", month=month)
    reason_count = defaultdict(int)
    for r in records:
        reason = r.rejection_reason or "未说明原因"
        reason_count[reason] += 1
    result = [{"reason": k, "count": v} for k, v in reason_count.items()]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


# ==================== Monthly Settlement ====================

def run_monthly_settlement(month: str, operator: str) -> Dict:
    """执行月度核算，规则版本锁定：按记录当时的规则计算"""
    storage.delete_settlements_by_month(month)
    records = query_records(status="已计入", month=month)

    by_participant = defaultdict(list)
    for r in records:
        by_participant[r.participant_id].append(r)

    settlements = []
    settlement_details = []
    for pid, recs in by_participant.items():
        total_records = len(recs)
        total_hours = sum(r.duration_hours for r in recs)
        base_points = 0.0
        deduction_points = 0.0
        final_points = 0.0
        for r in recs:
            if r.applicable_point_rule_id:
                point_rule = storage.get_point_rule(r.applicable_point_rule_id)
                if point_rule:
                    multiplier = point_rule.quality_multiplier.get(r.quality, 0.0)
                    calc = r.duration_hours * point_rule.base_points_per_hour * multiplier
                    base_points += calc
                    if r.final_points is None:
                        r.calculated_points = calc
                        r.deduction_points = r.deduction_points or 0.0
                        r.final_points = calc - r.deduction_points
                        storage.save_record(r)
                else:
                    base_points += r.calculated_points or 0.0
            else:
                base_points += r.calculated_points or 0.0
            deduction_points += r.deduction_points or 0.0
            final_points += r.final_points if r.final_points is not None else ((r.calculated_points or 0.0) - (r.deduction_points or 0.0))

        participant_name = recs[0].participant_name

        settlement = MonthlySettlement(
            settlement_id=generate_id("setl"),
            month=month,
            participant_id=pid,
            participant_name=participant_name,
            total_records=total_records,
            total_hours=round(total_hours, 2),
            base_points=round(base_points, 2),
            deduction_points=round(deduction_points, 2),
            final_points=round(final_points, 2),
            settled_by=operator
        )
        storage.save_settlement(settlement)
        settlements.append(settlement)
        settlement_details.append({
            "participant_id": pid,
            "participant_name": participant_name,
            "total_records": total_records,
            "total_hours": round(total_hours, 2),
            "final_points": round(final_points, 2)
        })

    return {
        "month": month,
        "total_participants": len(settlements),
        "total_points": round(sum(s.final_points for s in settlements), 2),
        "details": settlement_details
    }


def get_settlements(month: Optional[str] = None,
                     participant_id: Optional[str] = None) -> List[MonthlySettlement]:
    settlements = storage.list_settlements()
    if month:
        settlements = [s for s in settlements if s.month == month]
    if participant_id:
        settlements = [s for s in settlements if s.participant_id == participant_id]
    settlements.sort(key=lambda s: s.final_points, reverse=True)
    return settlements


# ==================== Service Record Appeals ====================

def submit_appeal(record_id: str, appeal_reason: str, submitted_by: str,
                  supplementary_note: Optional[str] = None,
                  expected_result: Optional[str] = None) -> Tuple[Optional[ServiceRecordAppeal], Optional[str]]:
    record = storage.get_record(record_id)
    if not record:
        return None, "服务记录不存在"
    if record.status not in ["已退回", "已计入"]:
        return None, f"当前记录状态为「{record.status}」，只有「已退回」或「已计入」的记录可以申诉"

    existing_appeals = storage.get_appeals_by_record(record_id)
    pending_appeals = [a for a in existing_appeals if a.status in ["待处理", "处理中"]]
    if pending_appeals:
        return None, "该记录已有待处理的申诉，请勿重复提交"

    appeal = ServiceRecordAppeal(
        appeal_id=generate_id("appeal"),
        record_id=record_id,
        participant_id=record.participant_id,
        participant_name=record.participant_name,
        project_id=record.project_id,
        service_date=record.service_date,
        month=record.month or "",
        appeal_reason=appeal_reason,
        supplementary_note=supplementary_note,
        expected_result=expected_result,
        status="待处理",
        submitted_by=submitted_by,
        original_calculated_points=record.calculated_points,
        original_deduction_points=record.deduction_points,
        original_final_points=record.final_points,
        original_quality=record.quality,
        original_duration_hours=record.duration_hours,
        original_status=record.status,
        timeline=[
            TimelineEvent(
                event_type="提交申诉",
                operator=submitted_by,
                description=f"提交申诉，原因：{appeal_reason}"
            )
        ]
    )
    storage.save_appeal(appeal)
    return appeal, None


def query_appeals(status: Optional[str] = None,
                  month: Optional[str] = None,
                  participant_id: Optional[str] = None,
                  participant_name: Optional[str] = None,
                  project_id: Optional[str] = None) -> List[ServiceRecordAppeal]:
    appeals = storage.list_appeals()
    if status:
        appeals = [a for a in appeals if a.status == status]
    if month:
        appeals = [a for a in appeals if a.month == month]
    if participant_id:
        appeals = [a for a in appeals if a.participant_id == participant_id]
    if participant_name:
        appeals = [a for a in appeals if participant_name in a.participant_name]
    if project_id:
        appeals = [a for a in appeals if a.project_id == project_id]
    appeals.sort(key=lambda a: a.submitted_at, reverse=True)
    return appeals


def get_appeal_detail(appeal_id: str) -> Optional[Dict]:
    appeal = storage.get_appeal(appeal_id)
    if not appeal:
        return None
    record = storage.get_record(appeal.record_id)
    original_record_snapshot = {
        "record_id": appeal.record_id,
        "participant_id": appeal.participant_id,
        "participant_name": appeal.participant_name,
        "project_id": appeal.project_id,
        "service_date": appeal.service_date,
        "month": appeal.month,
        "quality": appeal.original_quality,
        "duration_hours": appeal.original_duration_hours,
        "status": appeal.original_status,
        "calculated_points": appeal.original_calculated_points,
        "deduction_points": appeal.original_deduction_points,
        "final_points": appeal.original_final_points,
    }
    return {
        "appeal": appeal,
        "original_record": original_record_snapshot,
        "current_record": record
    }


def _recalculate_record_points(record: ServiceRecord) -> ServiceRecord:
    point_rule = None
    if record.applicable_point_rule_id:
        point_rule = storage.get_point_rule(record.applicable_point_rule_id)
    if not point_rule:
        point_rule = storage.get_applicable_point_rule(record.project_id, record.service_date)
        if point_rule:
            record.applicable_point_rule_id = point_rule.rule_id
            record.applicable_point_version = point_rule.rule_version

    if point_rule:
        multiplier = point_rule.quality_multiplier.get(record.quality, 0.0)
        record.calculated_points = record.duration_hours * point_rule.base_points_per_hour * multiplier
    else:
        record.calculated_points = record.calculated_points or 0.0

    if record.deduction_points is None:
        record.deduction_points = 0.0

    record.final_points = record.calculated_points - record.deduction_points
    return record


def _update_settlement_after_correction(record: ServiceRecord,
                                        old_calc_points: float, old_ded_points: float,
                                        old_final_points: float, old_duration: float, old_status: str,
                                        operator: str):
    if not record.month:
        return

    new_calc_points = record.calculated_points or 0.0
    new_ded_points = record.deduction_points or 0.0
    new_final_points = record.final_points if record.final_points is not None else new_calc_points - new_ded_points
    new_duration = record.duration_hours
    new_status = record.status

    was_counted = old_status == "已计入"
    is_counted = new_status == "已计入"

    if not was_counted and not is_counted:
        return

    settlements = storage.list_settlements()
    target_settlement = None
    for s in settlements:
        if s.month == record.month and s.participant_id == record.participant_id:
            target_settlement = s
            break

    if not target_settlement and is_counted:
        target_settlement = MonthlySettlement(
            settlement_id=generate_id("setl"),
            month=record.month,
            participant_id=record.participant_id,
            participant_name=record.participant_name,
            settled_by=operator
        )
    elif not target_settlement:
        return

    if was_counted and is_counted:
        calc_diff = new_calc_points - old_calc_points
        ded_diff = new_ded_points - old_ded_points
        duration_diff = new_duration - old_duration
        target_settlement.base_points = round(target_settlement.base_points + calc_diff, 2)
        target_settlement.deduction_points = round(target_settlement.deduction_points + ded_diff, 2)
        target_settlement.total_hours = round(target_settlement.total_hours + duration_diff, 2)
        target_settlement.final_points = round(target_settlement.final_points + (new_final_points - old_final_points), 2)
    elif was_counted and not is_counted:
        target_settlement.total_records -= 1
        target_settlement.base_points = round(target_settlement.base_points - old_calc_points, 2)
        target_settlement.deduction_points = round(target_settlement.deduction_points - old_ded_points, 2)
        target_settlement.total_hours = round(target_settlement.total_hours - old_duration, 2)
        target_settlement.final_points = round(target_settlement.final_points - old_final_points, 2)
    elif not was_counted and is_counted:
        target_settlement.total_records += 1
        target_settlement.base_points = round(target_settlement.base_points + new_calc_points, 2)
        target_settlement.deduction_points = round(target_settlement.deduction_points + new_ded_points, 2)
        target_settlement.total_hours = round(target_settlement.total_hours + new_duration, 2)
        target_settlement.final_points = round(target_settlement.final_points + new_final_points, 2)

    target_settlement.settled_at = datetime.now()
    target_settlement.settled_by = operator
    storage.save_settlement(target_settlement)


def approve_appeal(appeal_id: str, handler: str,
                   correction: AppealCorrection,
                   handle_note: Optional[str] = None) -> Tuple[Optional[ServiceRecordAppeal], Optional[str]]:
    appeal = storage.get_appeal(appeal_id)
    if not appeal:
        return None, "申诉不存在"
    if appeal.status not in ["待处理", "处理中"]:
        return None, f"当前申诉状态为「{appeal.status}」，只有待处理或处理中的申诉可以通过"

    record = storage.get_record(appeal.record_id)
    if not record:
        return None, "关联的服务记录不存在"

    old_calc_points = record.calculated_points or 0.0
    old_ded_points = record.deduction_points or 0.0
    old_final_points = record.final_points if record.final_points is not None else old_calc_points - old_ded_points
    old_duration = record.duration_hours
    old_status = record.status
    old_values = {
        "quality": record.quality,
        "duration_hours": record.duration_hours,
        "deduction_rule_id": record.applicable_deduction_id,
        "deduction_points": record.deduction_points,
        "final_points": record.final_points,
        "status": record.status,
    }

    if correction.quality is not None:
        record.quality = correction.quality
    if correction.duration_hours is not None:
        record.duration_hours = correction.duration_hours
    if correction.deduction_rule_id is not None:
        ded_rule = storage.get_deduction_rule(correction.deduction_rule_id)
        if not ded_rule:
            return None, "扣减规则不存在"
        if ded_rule.effective_date > record.service_date:
            return None, f"扣减规则生效日期({ded_rule.effective_date})晚于服务日期({record.service_date})，不能应用"
        record.applicable_deduction_id = ded_rule.deduction_id
        record.applicable_deduction_version = ded_rule.rule_version
        record.deduction_points = ded_rule.deduction_points
    if correction.clear_deduction_rule:
        record.applicable_deduction_id = None
        record.applicable_deduction_version = None
        record.deduction_points = 0.0
    if correction.deduction_points is not None:
        record.deduction_points = correction.deduction_points

    record = _recalculate_record_points(record)

    if correction.final_points is not None:
        record.final_points = correction.final_points

    if record.status == "已退回":
        record.status = "已计入"
        record.rejection_reason = None

    storage.save_record(record)

    _update_settlement_after_correction(
        record, old_calc_points, old_ded_points,
        old_final_points, old_duration, old_status, handler
    )

    new_values = {
        "quality": record.quality,
        "duration_hours": record.duration_hours,
        "deduction_rule_id": record.applicable_deduction_id,
        "deduction_points": record.deduction_points,
        "final_points": record.final_points,
        "status": record.status,
    }
    changed_fields = [f"{key}: {old_values[key]} -> {new_values[key]}" for key in old_values if old_values[key] != new_values[key]]

    appeal.status = "已通过"
    appeal.handler = handler
    appeal.handled_at = datetime.now()
    appeal.handle_note = handle_note
    appeal.correction = correction
    appeal.timeline.append(
        TimelineEvent(
            event_type="申诉通过",
            operator=handler,
            description=f"申诉通过，处理说明：{handle_note or '无'}；更正内容：{'; '.join(changed_fields) if changed_fields else '无字段变更'}"
        )
    )
    storage.save_appeal(appeal)

    return appeal, None


def reject_appeal(appeal_id: str, handler: str,
                  rejection_reason: str,
                  handle_note: Optional[str] = None) -> Tuple[Optional[ServiceRecordAppeal], Optional[str]]:
    appeal = storage.get_appeal(appeal_id)
    if not appeal:
        return None, "申诉不存在"
    if appeal.status not in ["待处理", "处理中"]:
        return None, f"当前申诉状态为「{appeal.status}」，只有待处理或处理中的申诉可以驳回"

    appeal.status = "已驳回"
    appeal.handler = handler
    appeal.handled_at = datetime.now()
    appeal.handle_note = handle_note
    appeal.rejection_reason = rejection_reason
    appeal.timeline.append(
        TimelineEvent(
            event_type="申诉驳回",
            operator=handler,
            description=f"申诉驳回，原因：{rejection_reason}"
        )
    )
    storage.save_appeal(appeal)
    return appeal, None


def get_appeals_by_record(record_id: str) -> List[ServiceRecordAppeal]:
    return storage.get_appeals_by_record(record_id)
