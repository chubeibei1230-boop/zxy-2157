import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date
import services
import storage
import json
import uuid


def _uid():
    return f"T{uuid.uuid4().hex[:6]}"


def test_reconciliation_basic():
    print("\n" + "=" * 60)
    print("测试1：基本对账单生成与一致性校验")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("对账单测试项目", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record1, _, _ = services.create_record(
        participant_name=f"测试员_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 6, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="良好"
    )
    services.submit_record(record1.record_id, "登记员")
    record1, _ = services.review_record(record1.record_id, "复核员", True, review_note="正常通过")

    record2, _, _ = services.create_record(
        participant_name=f"测试员_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 6, 15),
        start_time="14:00", end_time="17:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record2.record_id, "登记员")
    record2, _ = services.review_record(record2.record_id, "复核员", True)

    services.run_monthly_settlement("2024-06", "核算员")

    result = services.get_monthly_reconciliation(month="2024-06", participant_id=uid)
    stmt = result["statements"][0]

    print(f"参与人: {stmt['participant_name']} ({stmt['participant_id']})")
    print(f"记录数: {stmt['summary']['total_records']}")
    print(f"总时长: {stmt['summary']['total_hours']}")
    print(f"基础积分: {stmt['summary']['base_points']}")
    print(f"扣减积分: {stmt['summary']['deduction_points']}")
    print(f"最终积分: {stmt['summary']['final_points']}")
    print(f"一致性检查: {stmt['consistency_check']}")

    assert stmt["participant_id"] == uid
    assert stmt["summary"]["total_records"] == 2
    assert len(stmt["details"]) == 2
    assert stmt["consistency_check"]["is_consistent"] == True
    assert stmt["official_settlement_snapshot"] is not None
    assert stmt["official_settlement_snapshot"]["total_records"] == 2

    for d in stmt["details"]:
        assert "record_id" in d
        assert "service_date" in d
        assert "project_name" in d
        assert "duration_hours" in d
        assert "base_points" in d
        assert "deduction_points" in d
        assert "final_points" in d
        assert "review_result" in d
        assert "appeal_changes" in d

    print("    ✓ 基本对账单生成验证通过")


def test_reconciliation_with_appeal():
    print("\n" + "=" * 60)
    print("测试2：含申诉的对账单 - 积分变化说明")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("申诉对账测试项目", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, _, _ = services.create_record(
        participant_name=f"申诉员_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 7, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    record, _ = services.review_record(record.record_id, "复核员", True)

    appeal, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="质量评定有误，应为良好",
        submitted_by=f"申诉员_{uid}"
    )

    from models import AppealCorrection
    correction = AppealCorrection(quality="良好", note="经核实确为良好")
    approved_appeal, _ = services.approve_appeal(
        appeal_id=appeal.appeal_id,
        handler="管理员",
        correction=correction,
        handle_note="同意更正"
    )

    services.run_monthly_settlement("2024-07", "核算员")

    result = services.get_monthly_reconciliation(month="2024-07", participant_id=uid)
    stmt = result["statements"][0]

    print(f"参与人: {stmt['participant_name']}")
    print(f"最终积分: {stmt['summary']['final_points']}")
    detail = stmt["details"][0]
    print(f"质量: {detail['quality']}")
    print(f"基础积分: {detail['base_points']}")
    print(f"申诉变化: {detail['appeal_changes']}")

    assert len(detail["appeal_changes"]) == 1
    assert detail["appeal_changes"][0]["status"] == "已通过"
    assert len(detail["appeal_changes"][0]["changes"]) > 0
    assert stmt["consistency_check"]["is_consistent"] == True
    assert detail["quality"] == "良好"
    assert detail["base_points"] == 36.0
    print("    ✓ 含申诉对账单验证通过")


def test_reconciliation_with_rejected_appeal():
    print("\n" + "=" * 60)
    print("测试3：含驳回申诉的对账单")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("驳回申诉对账测试", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, _, _ = services.create_record(
        participant_name=f"驳回测试_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 8, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    record, _ = services.review_record(record.record_id, "复核员", True)

    appeal, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="认为评定不公",
        submitted_by=f"驳回测试_{uid}"
    )
    services.reject_appeal(appeal.appeal_id, "管理员", "评定无误，维持原判定")

    services.run_monthly_settlement("2024-08", "核算员")

    result = services.get_monthly_reconciliation(month="2024-08", participant_id=uid)
    stmt = result["statements"][0]
    detail = stmt["details"][0]

    print(f"申诉变化: {detail['appeal_changes']}")
    assert len(detail["appeal_changes"]) == 1
    assert detail["appeal_changes"][0]["status"] == "已驳回"
    assert detail["appeal_changes"][0]["rejection_reason"] is not None
    print("    ✓ 含驳回申诉对账单验证通过")


def test_reconciliation_multiple_participants():
    print("\n" + "=" * 60)
    print("测试4：多参与人对账单查询与筛选")
    print("=" * 60)

    uid1 = _uid()
    uid2 = _uid()
    project = services.create_project("多人对账测试项目", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 9, 1),
        created_by="admin"
    )

    for name, pid in [(f"多人A_{uid1}", uid1), (f"多人B_{uid2}", uid2)]:
        record, _, _ = services.create_record(
            participant_name=name, participant_id=pid,
            project_id=project.project_id, service_date=date(2024, 9, 10),
            start_time="09:00", end_time="12:00", duration_hours=3.0,
            registered_by="登记员", quality="合格"
        )
        services.submit_record(record.record_id, "登记员")
        services.review_record(record.record_id, "复核员", True)

    services.run_monthly_settlement("2024-09", "核算员")

    result_single = services.get_monthly_reconciliation(month="2024-09", participant_id=uid1)
    print(f"单人查询参与人数: {result_single['total_participants']}")
    assert result_single["total_participants"] == 1
    assert result_single["statements"][0]["participant_id"] == uid1

    result_name = services.get_monthly_reconciliation(month="2024-09", participant_name=f"多人A_{uid1}"[:4])
    print(f"姓名模糊查询: {result_name['total_participants']}")
    assert result_name["total_participants"] >= 1

    print("    ✓ 多参与人对账单查询与筛选验证通过")


def test_reconciliation_no_settlement():
    print("\n" + "=" * 60)
    print("测试5：未显式月度核算的对账单（自动核算一致性）")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("未核算对账测试", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 10, 1),
        created_by="admin"
    )

    record, _, _ = services.create_record(
        participant_name=f"未核算_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 10, 10),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    services.review_record(record.record_id, "复核员", True)

    result = services.get_monthly_reconciliation(month="2024-10", participant_id=uid)
    stmt = result["statements"][0]

    print(f"汇总记录数: {stmt['summary']['total_records']}")
    print(f"核算快照: {stmt['official_settlement_snapshot']}")
    print(f"一致性检查: {stmt['consistency_check']}")

    assert stmt["summary"]["total_records"] == 1
    assert stmt["summary"]["final_points"] == 30.0
    if stmt["official_settlement_snapshot"]:
        assert stmt["consistency_check"]["is_consistent"] == True
        print("    ✓ 自动核算一致性验证通过")
    else:
        assert stmt["consistency_check"] is None
        print("    ✓ 无核算快照时一致性检查为None验证通过")


def test_reconciliation_empty_month():
    print("\n" + "=" * 60)
    print("测试6：无记录月份的对账单")
    print("=" * 60)

    result = services.get_monthly_reconciliation(month="2099-12")
    print(f"无记录月份参与人数: {result['total_participants']}")
    assert result["total_participants"] == 0
    assert len(result["statements"]) == 0
    print("    ✓ 无记录月份的对账单验证通过")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# 开始验证 个人月度积分对账单 功能")
    print("#" * 60)

    try:
        test_reconciliation_basic()
        test_reconciliation_with_appeal()
        test_reconciliation_with_rejected_appeal()
        test_reconciliation_multiple_participants()
        test_reconciliation_no_settlement()
        test_reconciliation_empty_month()

        print("\n" + "=" * 60)
        print("所有个人月度积分对账单测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n验证失败: {e}")
        sys.exit(1)
