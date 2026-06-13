import csv
import os
import json
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from models import (
    ServiceProject, PointRule, DeductionRule,
    ServiceRecord, MonthlySettlement
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

PROJECTS_FILE = os.path.join(DATA_DIR, "projects.csv")
POINT_RULES_FILE = os.path.join(DATA_DIR, "point_rules.csv")
DEDUCTION_RULES_FILE = os.path.join(DATA_DIR, "deduction_rules.csv")
RECORDS_FILE = os.path.join(DATA_DIR, "service_records.csv")
SETTLEMENTS_FILE = os.path.join(DATA_DIR, "monthly_settlements.csv")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def _init_csv_files():
    _ensure_data_dir()
    files = {
        PROJECTS_FILE: ["project_id", "project_name", "description", "created_at", "is_active"],
        POINT_RULES_FILE: ["rule_id", "rule_version", "project_id", "base_points_per_hour",
                           "quality_multiplier", "effective_date", "description", "created_at", "created_by"],
        DEDUCTION_RULES_FILE: ["deduction_id", "rule_version", "reason", "deduction_points",
                               "effective_date", "description", "created_at", "created_by"],
        RECORDS_FILE: ["record_id", "participant_name", "participant_id", "project_id",
                       "service_date", "start_time", "end_time", "duration_hours", "quality",
                       "remarks", "status", "registered_by", "registered_at", "reviewed_by",
                       "reviewed_at", "rejection_reason", "applicable_point_rule_id",
                       "applicable_point_version", "applicable_deduction_id",
                       "applicable_deduction_version", "calculated_points", "deduction_points",
                       "final_points", "month", "warnings"],
        SETTLEMENTS_FILE: ["settlement_id", "month", "participant_id", "participant_name",
                           "total_records", "total_hours", "base_points", "deduction_points",
                           "final_points", "settled_at", "settled_by"]
    }
    for filepath, headers in files.items():
        if not os.path.exists(filepath):
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(headers)


def _serialize_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _parse_date(val: str) -> Optional[date]:
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


def _parse_datetime(val: str) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None


def _parse_bool(val: str) -> bool:
    return val.lower() == "true"


def _parse_json(val: str):
    if not val:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None


_init_csv_files()


def _read_csv(filepath: str) -> List[Dict]:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_csv(filepath: str, headers: List[str], rows: List[Dict]):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _serialize_value(row.get(k, "")) for k in headers})


# ==================== Service Projects ====================

def list_projects() -> List[ServiceProject]:
    rows = _read_csv(PROJECTS_FILE)
    return [
        ServiceProject(
            project_id=r["project_id"],
            project_name=r["project_name"],
            description=r.get("description") or None,
            created_at=_parse_datetime(r["created_at"]),
            is_active=_parse_bool(r.get("is_active", "true"))
        ) for r in rows
    ]


def get_project(project_id: str) -> Optional[ServiceProject]:
    for p in list_projects():
        if p.project_id == project_id:
            return p
    return None


def save_project(project: ServiceProject):
    projects = list_projects()
    for i, p in enumerate(projects):
        if p.project_id == project.project_id:
            projects[i] = project
            break
    else:
        projects.append(project)
    headers = ["project_id", "project_name", "description", "created_at", "is_active"]
    rows = [p.dict() for p in projects]
    _write_csv(PROJECTS_FILE, headers, rows)


# ==================== Point Rules ====================

def list_point_rules() -> List[PointRule]:
    rows = _read_csv(POINT_RULES_FILE)
    return [
        PointRule(
            rule_id=r["rule_id"],
            rule_version=r["rule_version"],
            project_id=r["project_id"],
            base_points_per_hour=float(r["base_points_per_hour"]),
            quality_multiplier=_parse_json(r["quality_multiplier"]) or {},
            effective_date=_parse_date(r["effective_date"]),
            description=r.get("description") or None,
            created_at=_parse_datetime(r["created_at"]),
            created_by=r["created_by"]
        ) for r in rows
    ]


def get_point_rule(rule_id: str) -> Optional[PointRule]:
    for r in list_point_rules():
        if r.rule_id == rule_id:
            return r
    return None


def save_point_rule(rule: PointRule):
    rules = list_point_rules()
    for i, r in enumerate(rules):
        if r.rule_id == rule.rule_id:
            rules[i] = rule
            break
    else:
        rules.append(rule)
    headers = ["rule_id", "rule_version", "project_id", "base_points_per_hour",
               "quality_multiplier", "effective_date", "description", "created_at", "created_by"]
    rows = [r.dict() for r in rules]
    _write_csv(POINT_RULES_FILE, headers, rows)


def get_applicable_point_rule(project_id: str, service_date: date) -> Optional[PointRule]:
    rules = [r for r in list_point_rules() if r.project_id == project_id and r.effective_date <= service_date]
    if not rules:
        return None
    rules.sort(key=lambda r: r.effective_date, reverse=True)
    return rules[0]


# ==================== Deduction Rules ====================

def list_deduction_rules() -> List[DeductionRule]:
    rows = _read_csv(DEDUCTION_RULES_FILE)
    return [
        DeductionRule(
            deduction_id=r["deduction_id"],
            rule_version=r["rule_version"],
            reason=r["reason"],
            deduction_points=float(r["deduction_points"]),
            effective_date=_parse_date(r["effective_date"]),
            description=r.get("description") or None,
            created_at=_parse_datetime(r["created_at"]),
            created_by=r["created_by"]
        ) for r in rows
    ]


def get_deduction_rule(deduction_id: str) -> Optional[DeductionRule]:
    for r in list_deduction_rules():
        if r.deduction_id == deduction_id:
            return r
    return None


def save_deduction_rule(rule: DeductionRule):
    rules = list_deduction_rules()
    for i, r in enumerate(rules):
        if r.deduction_id == rule.deduction_id:
            rules[i] = rule
            break
    else:
        rules.append(rule)
    headers = ["deduction_id", "rule_version", "reason", "deduction_points",
               "effective_date", "description", "created_at", "created_by"]
    rows = [r.dict() for r in rules]
    _write_csv(DEDUCTION_RULES_FILE, headers, rows)


# ==================== Service Records ====================

def _row_to_record(r: Dict) -> ServiceRecord:
    warnings_raw = _parse_json(r.get("warnings", ""))
    return ServiceRecord(
        record_id=r["record_id"],
        participant_name=r["participant_name"],
        participant_id=r["participant_id"],
        project_id=r["project_id"],
        service_date=_parse_date(r["service_date"]),
        start_time=r["start_time"],
        end_time=r["end_time"],
        duration_hours=float(r["duration_hours"]),
        quality=r["quality"],
        remarks=r.get("remarks") or None,
        status=r["status"],
        registered_by=r["registered_by"],
        registered_at=_parse_datetime(r["registered_at"]),
        reviewed_by=r.get("reviewed_by") or None,
        reviewed_at=_parse_datetime(r.get("reviewed_at", "")),
        rejection_reason=r.get("rejection_reason") or None,
        applicable_point_rule_id=r.get("applicable_point_rule_id") or None,
        applicable_point_version=r.get("applicable_point_version") or None,
        applicable_deduction_id=r.get("applicable_deduction_id") or None,
        applicable_deduction_version=r.get("applicable_deduction_version") or None,
        calculated_points=float(r["calculated_points"]) if r.get("calculated_points") else None,
        deduction_points=float(r["deduction_points"]) if r.get("deduction_points") else None,
        final_points=float(r["final_points"]) if r.get("final_points") else None,
        month=r.get("month") or None,
        warnings=warnings_raw if isinstance(warnings_raw, list) else []
    )


def list_records() -> List[ServiceRecord]:
    rows = _read_csv(RECORDS_FILE)
    return [_row_to_record(r) for r in rows]


def get_record(record_id: str) -> Optional[ServiceRecord]:
    for r in list_records():
        if r.record_id == record_id:
            return r
    return None


def save_record(record: ServiceRecord):
    records = list_records()
    for i, r in enumerate(records):
        if r.record_id == record.record_id:
            records[i] = record
            break
    else:
        records.append(record)
    headers = ["record_id", "participant_name", "participant_id", "project_id",
               "service_date", "start_time", "end_time", "duration_hours", "quality",
               "remarks", "status", "registered_by", "registered_at", "reviewed_by",
               "reviewed_at", "rejection_reason", "applicable_point_rule_id",
               "applicable_point_version", "applicable_deduction_id",
               "applicable_deduction_version", "calculated_points", "deduction_points",
               "final_points", "month", "warnings"]
    rows = [r.dict() for r in records]
    _write_csv(RECORDS_FILE, headers, rows)


# ==================== Monthly Settlements ====================

def list_settlements() -> List[MonthlySettlement]:
    rows = _read_csv(SETTLEMENTS_FILE)
    return [
        MonthlySettlement(
            settlement_id=r["settlement_id"],
            month=r["month"],
            participant_id=r["participant_id"],
            participant_name=r["participant_name"],
            total_records=int(r["total_records"]),
            total_hours=float(r["total_hours"]),
            base_points=float(r["base_points"]),
            deduction_points=float(r["deduction_points"]),
            final_points=float(r["final_points"]),
            settled_at=_parse_datetime(r["settled_at"]),
            settled_by=r["settled_by"]
        ) for r in rows
    ]


def save_settlement(settlement: MonthlySettlement):
    settlements = list_settlements()
    for i, s in enumerate(settlements):
        if s.settlement_id == settlement.settlement_id:
            settlements[i] = settlement
            break
    else:
        settlements.append(settlement)
    headers = ["settlement_id", "month", "participant_id", "participant_name",
               "total_records", "total_hours", "base_points", "deduction_points",
               "final_points", "settled_at", "settled_by"]
    rows = [s.dict() for s in settlements]
    _write_csv(SETTLEMENTS_FILE, headers, rows)


def delete_settlements_by_month(month: str):
    settlements = [s for s in list_settlements() if s.month != month]
    headers = ["settlement_id", "month", "participant_id", "participant_name",
               "total_records", "total_hours", "base_points", "deduction_points",
               "final_points", "settled_at", "settled_by"]
    rows = [s.dict() for s in settlements]
    _write_csv(SETTLEMENTS_FILE, headers, rows)
