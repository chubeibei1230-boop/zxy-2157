from datetime import date, datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models import (
    ServiceProject, PointRule, DeductionRule,
    ServiceRecord, MonthlySettlement, QualityLevel, RecordStatus,
    ServiceRecordAppeal, AppealCorrection
)
import services

app = FastAPI(
    title="社区志愿服务积分管理系统",
    description="社区志愿服务积分记录、规则配置和月度核算 RESTful API",
    version="1.0.0"
)


# ==================== Request Schemas ====================

class ProjectCreateRequest(BaseModel):
    project_name: str
    description: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    project_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PointRuleCreateRequest(BaseModel):
    project_id: str
    base_points_per_hour: float
    quality_multiplier: Dict[str, float] = {
        "优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0
    }
    effective_date: date
    created_by: str
    description: Optional[str] = None


class DeductionRuleCreateRequest(BaseModel):
    reason: str
    deduction_points: float
    effective_date: date
    created_by: str
    description: Optional[str] = None


class RecordCreateRequest(BaseModel):
    participant_name: str
    participant_id: str
    project_id: str
    service_date: date
    start_time: str
    end_time: str
    duration_hours: float
    registered_by: str
    quality: QualityLevel = "合格"
    remarks: Optional[str] = None


class RecordUpdateRequest(BaseModel):
    participant_name: Optional[str] = None
    participant_id: Optional[str] = None
    project_id: Optional[str] = None
    service_date: Optional[date] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Optional[float] = None
    quality: Optional[QualityLevel] = None
    remarks: Optional[str] = None


class RecordReviewRequest(BaseModel):
    reviewer: str
    approved: bool
    rejection_reason: Optional[str] = None
    deduction_rule_id: Optional[str] = None
    review_note: Optional[str] = None


class RecordVoidRequest(BaseModel):
    operator: str
    void_reason: Optional[str] = None


class ReviewApproveRequest(BaseModel):
    reviewer: str
    review_note: Optional[str] = None


class ReviewRejectRequest(BaseModel):
    reviewer: str
    rejection_reason: str
    review_note: Optional[str] = None


class ReviewDeductRequest(BaseModel):
    reviewer: str
    deduction_rule_id: str
    review_note: Optional[str] = None


class RecordSubmitRequest(BaseModel):
    operator: str


class SettlementRequest(BaseModel):
    month: str
    operator: str


class AppealSubmitRequest(BaseModel):
    record_id: str
    appeal_reason: str
    submitted_by: str
    supplementary_note: Optional[str] = None
    expected_result: Optional[str] = None


class AppealApproveRequest(BaseModel):
    handler: str
    correction: AppealCorrection
    handle_note: Optional[str] = None


class AppealRejectRequest(BaseModel):
    handler: str
    rejection_reason: str
    handle_note: Optional[str] = None


# ==================== Project APIs ====================

@app.post("/api/projects", response_model=ServiceProject, summary="创建服务项目")
def create_project(req: ProjectCreateRequest):
    project = services.create_project(req.project_name, req.description)
    return project


@app.get("/api/projects", response_model=List[ServiceProject], summary="获取所有服务项目")
def list_projects():
    return services.storage.list_projects()


@app.get("/api/projects/{project_id}", response_model=ServiceProject, summary="获取单个服务项目")
def get_project(project_id: str):
    project = services.storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@app.put("/api/projects/{project_id}", response_model=ServiceProject, summary="更新服务项目")
def update_project(project_id: str, req: ProjectUpdateRequest):
    project = services.update_project(project_id, req.project_name, req.description, req.is_active)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


# ==================== Point Rule APIs ====================

@app.post("/api/point-rules", response_model=PointRule, summary="创建积分规则（新版本）")
def create_point_rule(req: PointRuleCreateRequest):
    rule = services.create_point_rule(
        req.project_id, req.base_points_per_hour, req.quality_multiplier,
        req.effective_date, req.created_by, req.description
    )
    if not rule:
        raise HTTPException(status_code=400, detail="项目不存在，无法创建规则")
    return rule


@app.get("/api/point-rules", response_model=List[PointRule], summary="获取积分规则列表")
def list_point_rules(project_id: Optional[str] = None):
    if project_id:
        return services.list_point_rules_by_project(project_id)
    return services.storage.list_point_rules()


@app.get("/api/point-rules/applicable", response_model=Optional[PointRule], summary="获取适用的积分规则")
def get_applicable_point_rule(project_id: str, service_date: date):
    rule = services.storage.get_applicable_point_rule(project_id, service_date)
    if not rule:
        raise HTTPException(status_code=404, detail="在该服务日期无适用的积分规则")
    return rule


@app.get("/api/point-rules/{rule_id}", response_model=PointRule, summary="获取单个积分规则")
def get_point_rule(rule_id: str):
    rule = services.storage.get_point_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="积分规则不存在")
    return rule


# ==================== Deduction Rule APIs ====================

@app.post("/api/deduction-rules", response_model=DeductionRule, summary="创建扣减规则（新版本）")
def create_deduction_rule(req: DeductionRuleCreateRequest):
    rule = services.create_deduction_rule(
        req.reason, req.deduction_points, req.effective_date,
        req.created_by, req.description
    )
    return rule


@app.get("/api/deduction-rules", response_model=List[DeductionRule], summary="获取扣减规则列表")
def list_deduction_rules():
    return services.storage.list_deduction_rules()


@app.get("/api/deduction-rules/{deduction_id}", response_model=DeductionRule, summary="获取单个扣减规则")
def get_deduction_rule(deduction_id: str):
    rule = services.storage.get_deduction_rule(deduction_id)
    if not rule:
        raise HTTPException(status_code=404, detail="扣减规则不存在")
    return rule


# ==================== Service Record APIs ====================

@app.post("/api/records", summary="创建服务记录")
def create_record(req: RecordCreateRequest):
    record, warnings, error = services.create_record(
        req.participant_name, req.participant_id, req.project_id,
        req.service_date, req.start_time, req.end_time, req.duration_hours,
        req.registered_by, req.quality, req.remarks
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {
        "record": record,
        "warnings": warnings
    }


@app.get("/api/records", response_model=List[ServiceRecord], summary="查询服务记录")
def query_records(
    participant_id: Optional[str] = None,
    participant_name: Optional[str] = None,
    project_id: Optional[str] = None,
    rule_version: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None,
    registered_by: Optional[str] = None
):
    return services.query_records(
        participant_id, participant_name, project_id,
        rule_version, status, month, registered_by
    )


@app.get("/api/records/{record_id}", response_model=ServiceRecord, summary="获取单个服务记录")
def get_record(record_id: str):
    record = services.storage.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


@app.put("/api/records/{record_id}", response_model=ServiceRecord, summary="更新服务记录")
def update_record(record_id: str, req: RecordUpdateRequest):
    record, error = services.update_record(record_id, **req.dict(exclude_unset=True))
    if error:
        raise HTTPException(status_code=400, detail=error)
    return record


@app.post("/api/records/{record_id}/submit", response_model=ServiceRecord, summary="提交记录进入待复核")
def submit_record(record_id: str, req: RecordSubmitRequest):
    record, error = services.submit_record(record_id, req.operator)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return record


@app.post("/api/records/{record_id}/review", response_model=ServiceRecord, summary="复核服务记录")
def review_record(record_id: str, req: RecordReviewRequest):
    record, error = services.review_record(
        record_id, req.reviewer, req.approved,
        req.rejection_reason, req.deduction_rule_id, req.review_note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return record


@app.post("/api/records/{record_id}/void", response_model=ServiceRecord, summary="作废服务记录")
def void_record(record_id: str, req: RecordVoidRequest):
    record = services.void_record(record_id, req.operator, req.void_reason)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


# ==================== Review Workstation APIs ====================

@app.get("/api/review/pending", summary="查询待复核记录列表（复核工作台）")
def query_pending_review(
    month: Optional[str] = None,
    project_id: Optional[str] = None,
    participant_id: Optional[str] = None,
    participant_name: Optional[str] = None,
    anomaly_type: Optional[str] = Query(None, description="异常类型：duplicate(重复登记)、duration(时长异常)、missing_rule(规则缺失)、all(全部)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    return services.query_pending_review(
        month=month, project_id=project_id,
        participant_id=participant_id, participant_name=participant_name,
        anomaly_type=anomaly_type, page=page, page_size=page_size
    )


@app.get("/api/review/{record_id}", summary="获取复核详情（复核工作台）")
def get_review_detail(record_id: str):
    detail = services.get_review_detail(record_id)
    if not detail:
        raise HTTPException(status_code=404, detail="记录不存在")
    return detail


@app.post("/api/review/{record_id}/approve", response_model=ServiceRecord, summary="通过复核（复核工作台）")
def approve_review(record_id: str, req: ReviewApproveRequest):
    record, error = services.review_record(
        record_id, req.reviewer, approved=True,
        review_note=req.review_note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return record


@app.post("/api/review/{record_id}/reject", response_model=ServiceRecord, summary="退回复核（复核工作台）")
def reject_review(record_id: str, req: ReviewRejectRequest):
    record, error = services.review_record(
        record_id, req.reviewer, approved=False,
        rejection_reason=req.rejection_reason,
        review_note=req.review_note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return record


@app.post("/api/review/{record_id}/deduct", response_model=ServiceRecord, summary="扣减后通过（复核工作台）")
def deduct_and_approve_review(record_id: str, req: ReviewDeductRequest):
    record, error = services.review_record(
        record_id, req.reviewer, approved=True,
        deduction_rule_id=req.deduction_rule_id,
        review_note=req.review_note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return record


@app.post("/api/review/{record_id}/void", response_model=ServiceRecord, summary="作废记录（复核工作台）")
def void_review(record_id: str, req: RecordVoidRequest):
    record = services.void_record(record_id, req.operator, req.void_reason)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


# ==================== Detection APIs ====================

@app.get("/api/detect/duplicates/{record_id}", summary="检测重复登记")
def detect_duplicates(record_id: str):
    record = services.storage.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    duplicates = services.detect_duplicate_records(record)
    return {
        "record_id": record_id,
        "has_duplicate": len(duplicates) > 0,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates
    }


@app.get("/api/detect/backlog", summary="检测复核积压")
def detect_backlog():
    return services.detect_review_backlog()


# ==================== Statistics APIs ====================

@app.get("/api/statistics/personal-summary", summary="个人积分汇总")
def personal_point_summary(
    participant_id: Optional[str] = None,
    month: Optional[str] = None
):
    return services.get_personal_point_summary(participant_id, month)


@app.get("/api/statistics/project-ranking", summary="项目贡献排行")
def project_contribution_ranking(month: Optional[str] = None):
    return services.get_project_contribution_ranking(month)


@app.get("/api/statistics/rejection-reasons", summary="退回原因分布")
def rejection_reason_distribution(month: Optional[str] = None):
    return services.get_rejection_reason_distribution(month)


# ==================== Monthly Settlement APIs ====================

@app.post("/api/settlements", summary="执行月度核算")
def run_settlement(req: SettlementRequest):
    result = services.run_monthly_settlement(req.month, req.operator)
    return result


@app.get("/api/settlements", response_model=List[MonthlySettlement], summary="查询月度核算结果")
def list_settlements(
    month: Optional[str] = None,
    participant_id: Optional[str] = None
):
    return services.get_settlements(month, participant_id)


# ==================== CSV Export APIs ====================

@app.get("/api/export/records", summary="导出服务记录CSV")
def export_records_csv(
    participant_id: Optional[str] = None,
    month: Optional[str] = None,
    status: Optional[str] = None
):
    records = services.query_records(
        participant_id=participant_id, month=month, status=status
    )
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "记录ID", "参与人姓名", "参与人ID", "项目ID", "服务日期",
        "开始时间", "结束时间", "时长(小时)", "质量", "备注",
        "状态", "登记人", "登记时间", "复核人", "复核时间",
        "退回原因", "复核备注", "积分规则版本", "扣减规则版本",
        "基础积分", "扣减积分", "最终积分", "月份", "警告信息"
    ])
    for r in records:
        writer.writerow([
            r.record_id, r.participant_name, r.participant_id, r.project_id,
            r.service_date, r.start_time, r.end_time, r.duration_hours,
            r.quality, r.remarks or "", r.status, r.registered_by,
            r.registered_at, r.reviewed_by or "", r.reviewed_at or "",
            r.rejection_reason or "", r.review_note or "",
            r.applicable_point_version or "",
            r.applicable_deduction_version or "",
            r.calculated_points or 0, r.deduction_points or 0,
            r.final_points or 0, r.month or "",
            "; ".join(r.warnings or [])
        ])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename=service_records_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@app.get("/api/export/settlements", summary="导出月度核算CSV")
def export_settlements_csv(month: Optional[str] = None):
    settlements = services.get_settlements(month=month)
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "核算ID", "月份", "参与人ID", "参与人姓名",
        "记录数", "总时长(小时)", "基础积分", "扣减积分", "最终积分",
        "核算时间", "核算人"
    ])
    for s in settlements:
        writer.writerow([
            s.settlement_id, s.month, s.participant_id, s.participant_name,
            s.total_records, s.total_hours, s.base_points,
            s.deduction_points, s.final_points, s.settled_at, s.settled_by
        ])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename=monthly_settlements_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


# ==================== Appeal APIs ====================

@app.post("/api/appeals", response_model=ServiceRecordAppeal, summary="提交服务记录申诉")
def submit_appeal(req: AppealSubmitRequest):
    appeal, error = services.submit_appeal(
        req.record_id, req.appeal_reason, req.submitted_by,
        req.supplementary_note, req.expected_result
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return appeal


@app.get("/api/appeals", response_model=List[ServiceRecordAppeal], summary="查询申诉列表")
def query_appeals(
    status: Optional[str] = None,
    month: Optional[str] = None,
    participant_id: Optional[str] = None,
    participant_name: Optional[str] = None,
    project_id: Optional[str] = None
):
    return services.query_appeals(
        status=status, month=month,
        participant_id=participant_id,
        participant_name=participant_name,
        project_id=project_id
    )


@app.get("/api/appeals/{appeal_id}", summary="获取申诉详情")
def get_appeal_detail(appeal_id: str):
    detail = services.get_appeal_detail(appeal_id)
    if not detail:
        raise HTTPException(status_code=404, detail="申诉不存在")
    return detail


@app.post("/api/appeals/{appeal_id}/approve", response_model=ServiceRecordAppeal, summary="通过申诉并更正积分")
def approve_appeal(appeal_id: str, req: AppealApproveRequest):
    appeal, error = services.approve_appeal(
        appeal_id, req.handler, req.correction, req.handle_note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return appeal


@app.post("/api/appeals/{appeal_id}/reject", response_model=ServiceRecordAppeal, summary="驳回申诉")
def reject_appeal(appeal_id: str, req: AppealRejectRequest):
    appeal, error = services.reject_appeal(
        appeal_id, req.handler, req.rejection_reason, req.handle_note
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return appeal


@app.get("/api/records/{record_id}/appeals", response_model=List[ServiceRecordAppeal], summary="获取某记录的申诉列表")
def get_record_appeals(record_id: str):
    return services.get_appeals_by_record(record_id)


# ==================== Monthly Reconciliation Statement APIs ====================

@app.get("/api/reconciliation", summary="查询个人月度积分对账单")
def get_monthly_reconciliation(
    month: str = Query(..., description="月份，格式 YYYY-MM"),
    participant_id: Optional[str] = Query(None, description="参与人ID"),
    participant_name: Optional[str] = Query(None, description="参与人姓名（模糊匹配）")
):
    return services.get_monthly_reconciliation(
        month=month,
        participant_id=participant_id,
        participant_name=participant_name
    )


@app.get("/api/export/reconciliation", summary="导出个人月度积分对账单CSV")
def export_reconciliation_csv(
    month: str = Query(..., description="月份，格式 YYYY-MM"),
    participant_id: Optional[str] = Query(None, description="参与人ID"),
    participant_name: Optional[str] = Query(None, description="参与人姓名（模糊匹配）")
):
    result = services.get_monthly_reconciliation(
        month=month,
        participant_id=participant_id,
        participant_name=participant_name
    )
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "月份", "参与人ID", "参与人姓名",
        "记录ID", "服务日期", "项目ID", "项目名称",
        "服务时长(小时)", "质量等级", "基础积分", "扣减积分", "最终积分",
        "复核结果", "复核人", "复核时间",
        "申诉积分变化说明",
        "汇总-记录数", "汇总-总时长", "汇总-基础积分", "汇总-扣减积分", "汇总-最终积分",
        "核算一致性"
    ])
    for stmt in result["statements"]:
        for i, detail in enumerate(stmt["details"]):
            appeal_desc_parts = []
            for ac in detail["appeal_changes"]:
                if ac["status"] == "已通过":
                    appeal_desc_parts.append(
                        f"申诉{ac['appeal_id']}通过: {'; '.join(ac['changes']) or '无变更'}"
                    )
                elif ac["status"] == "已驳回":
                    appeal_desc_parts.append(
                        f"申诉{ac['appeal_id']}驳回: {ac.get('rejection_reason', '')}"
                    )
            appeal_desc = " | ".join(appeal_desc_parts) if appeal_desc_parts else ""

            consistency = ""
            if i == 0 and stmt.get("consistency_check"):
                consistency = "一致" if stmt["consistency_check"]["is_consistent"] else "不一致"

            writer.writerow([
                stmt["month"] if i == 0 else "",
                stmt["participant_id"] if i == 0 else "",
                stmt["participant_name"] if i == 0 else "",
                detail["record_id"],
                detail["service_date"],
                detail["project_id"],
                detail["project_name"],
                detail["duration_hours"],
                detail["quality"],
                detail["base_points"],
                detail["deduction_points"],
                detail["final_points"],
                detail["review_result"],
                detail["reviewed_by"] or "",
                detail["reviewed_at"] or "",
                appeal_desc,
                stmt["summary"]["total_records"] if i == 0 else "",
                stmt["summary"]["total_hours"] if i == 0 else "",
                stmt["summary"]["base_points"] if i == 0 else "",
                stmt["summary"]["deduction_points"] if i == 0 else "",
                stmt["summary"]["final_points"] if i == 0 else "",
                consistency,
            ])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename=reconciliation_{month}_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@app.get("/", summary="系统健康检查")
def root():
    return {
        "service": "社区志愿服务积分管理系统",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8114)
