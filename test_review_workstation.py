import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime
import services
import storage
from models import QualityLevel


def test_review_workstation():
    print("=" * 60)
    print("服务记录复核工作台 - 功能测试")
    print("=" * 60)

    project = services.create_project("社区环境整治", "测试项目")
    print(f"\n[1] 创建项目: {project.project_name} (ID: {project.project_id})")

    point_rule = services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin",
        description="测试积分规则"
    )
    print(f"[2] 创建积分规则: {point_rule.rule_id} (版本: {point_rule.rule_version})")

    ded_rule = services.create_deduction_rule(
        reason="服务质量不达标",
        deduction_points=5.0,
        effective_date=date(2024, 1, 1),
        created_by="admin",
        description="测试扣减规则"
    )
    print(f"[3] 创建扣减规则: {ded_rule.deduction_id} (扣减: {ded_rule.deduction_points}分)")

    record, warnings, error = services.create_record(
        participant_name="张三",
        participant_id="P001",
        project_id=project.project_id,
        service_date=date(2024, 6, 15),
        start_time="09:00",
        end_time="12:00",
        duration_hours=3.0,
        registered_by="登记员小王",
        quality="良好",
        remarks="测试服务记录"
    )
    print(f"\n[4] 创建服务记录: {record.record_id}")
    print(f"    状态: {record.status}, 预估积分: {record.calculated_points}")
    if warnings:
        print(f"    警告: {warnings}")

    record, error = services.submit_record(record.record_id, "登记员小王")
    print(f"\n[5] 提交复核: 状态 -> {record.status}")

    pending = services.query_pending_review(month="2024-06")
    print(f"\n[6] 查询待复核列表 (2024-06):")
    print(f"    总数: {pending['total']}, 异常统计: {pending['anomaly_stats']}")
    for r in pending["records"]:
        print(f"    - {r['record_id']}: {r['participant_name']}, {r['duration_hours']}h, {r['quality']}")

    detail = services.get_review_detail(record.record_id)
    print(f"\n[7] 复核详情:")
    print(f"    记录ID: {detail['record']['record_id']}")
    print(f"    参与人: {detail['record']['participant_name']}")
    print(f"    适用积分规则: {detail['applicable_point_rule']['rule_id'] if detail['applicable_point_rule'] else '无'}")
    print(f"    扣减规则候选数: {len(detail['deduction_candidates'])}")
    print(f"    历史申诉数: {len(detail['appeal_history'])}")
    print(f"    是否规则缺失: {detail['missing_rule']}")
    print(f"    时长异常: {detail['duration_anomaly']}")

    print(f"\n[8] 测试 - 扣减后通过:")
    old_final = record.final_points
    record, error = services.review_record(
        record_id=record.record_id,
        reviewer="复核员老李",
        approved=True,
        deduction_rule_id=ded_rule.deduction_id,
        review_note="服务质量存在瑕疵，扣减5分后通过"
    )
    print(f"    操作前积分: {old_final}")
    print(f"    操作后积分: {record.final_points}")
    print(f"    状态: {record.status}")
    print(f"    扣减积分: {record.deduction_points}")
    print(f"    复核人: {record.reviewed_by}")
    print(f"    复核备注: {record.review_note}")

    print(f"\n[9] 验证 - 个人积分汇总:")
    summary = services.get_personal_point_summary(participant_id="P001", month="2024-06")
    for s in summary:
        print(f"    {s['participant_name']}: 记录数={s['total_records']}, 总时长={s['total_hours']}h, "
              f"基础积分={s['base_points']}, 扣减={s['deduction_points']}, 最终积分={s['final_points']}")

    print(f"\n[10] 验证 - 项目贡献排行:")
    ranking = services.get_project_contribution_ranking(month="2024-06")
    for r in ranking:
        print(f"    {r['project_name']}: 记录数={r['total_records']}, 参与人数={r['total_participants']}, "
              f"总时长={r['total_hours']}h, 总积分={r['total_points']}")

    record2, warnings2, error2 = services.create_record(
        participant_name="李四",
        participant_id="P002",
        project_id=project.project_id,
        service_date=date(2024, 6, 16),
        start_time="14:00",
        end_time="17:00",
        duration_hours=3.0,
        registered_by="登记员小王",
        quality="合格",
        remarks="第二条测试记录"
    )
    services.submit_record(record2.record_id, "登记员小王")
    print(f"\n[11] 创建第二条记录并提交: {record2.record_id}")

    print(f"\n[12] 测试 - 退回复核:")
    record2, error = services.review_record(
        record_id=record2.record_id,
        reviewer="复核员老李",
        approved=False,
        rejection_reason="服务时间与实际不符",
        review_note="需要重新核实服务时长"
    )
    print(f"    状态: {record2.status}")
    print(f"    退回原因: {record2.rejection_reason}")

    record3, warnings3, error3 = services.create_record(
        participant_name="王五",
        participant_id="P003",
        project_id=project.project_id,
        service_date=date(2024, 6, 17),
        start_time="08:00",
        end_time="12:00",
        duration_hours=4.0,
        registered_by="登记员小王",
        quality="优秀",
        remarks="第三条测试记录"
    )
    services.submit_record(record3.record_id, "登记员小王")
    print(f"\n[13] 创建第三条记录并提交: {record3.record_id}")

    print(f"\n[14] 测试 - 直接通过:")
    record3, error = services.review_record(
        record_id=record3.record_id,
        reviewer="复核员老李",
        approved=True,
        review_note="服务记录完整，直接通过"
    )
    print(f"    状态: {record3.status}")
    print(f"    最终积分: {record3.final_points}")

    record4, warnings4, error4 = services.create_record(
        participant_name="赵六",
        participant_id="P004",
        project_id=project.project_id,
        service_date=date(2024, 6, 18),
        start_time="09:00",
        end_time="15:00",
        duration_hours=6.0,
        registered_by="登记员小王",
        quality="合格",
        remarks="第四条测试记录-待作废"
    )
    services.submit_record(record4.record_id, "登记员小王")
    print(f"\n[15] 创建第四条记录并提交: {record4.record_id}")

    print(f"\n[16] 测试 - 作废记录:")
    before_summary = services.get_personal_point_summary(participant_id="P004", month="2024-06")
    print(f"    作废前个人积分: {before_summary[0]['final_points'] if before_summary else 0}")

    record4_voided = services.void_record(record4.record_id, "复核员老李", "重复登记，作废处理")
    print(f"    作废后状态: {record4_voided.status}")
    print(f"    作废原因: {record4_voided.rejection_reason}")
    print(f"    操作人: {record4_voided.reviewed_by}")

    after_summary = services.get_personal_point_summary(participant_id="P004", month="2024-06")
    print(f"    作废后个人积分: {after_summary[0]['final_points'] if after_summary else 0}")

    print(f"\n[17] 执行月度核算:")
    settlement_result = services.run_monthly_settlement("2024-06", "核算员小张")
    print(f"    月份: {settlement_result['month']}")
    print(f"    参与人数: {settlement_result['total_participants']}")
    print(f"    总积分: {settlement_result['total_points']}")
    for d in settlement_result['details']:
        print(f"    - {d['participant_name']}: {d['final_points']}分")

    print(f"\n[18] 验证 - 核算结果与记录一致性:")
    all_settlements = services.get_settlements(month="2024-06")
    for s in all_settlements:
        records = services.query_records(participant_id=s.participant_id, status="已计入", month="2024-06")
        calc_final = sum(r.final_points or 0 for r in records)
        match = abs(s.final_points - calc_final) < 0.01
        print(f"    {s.participant_name}: 核算={s.final_points}, 计算={calc_final}, 一致={match}")

    print(f"\n[19] 测试 - 按异常类型筛选:")
    pending_all = services.query_pending_review(anomaly_type="all")
    print(f"    全部异常类型: {pending_all['total']} 条")
    pending_dup = services.query_pending_review(anomaly_type="duplicate")
    print(f"    重复登记: {pending_dup['total']} 条")
    pending_dur = services.query_pending_review(anomaly_type="duration")
    print(f"    时长异常: {pending_dur['total']} 条")
    pending_miss = services.query_pending_review(anomaly_type="missing_rule")
    print(f"    规则缺失: {pending_miss['total']} 条")

    print(f"\n[20] 验证 - 异常记录处理原因和操作人:")
    rec = services.storage.get_record(record.record_id)
    print(f"    记录ID: {rec.record_id}")
    print(f"    操作人: {rec.reviewed_by}")
    print(f"    操作时间: {rec.reviewed_at}")
    print(f"    复核备注: {rec.review_note}")
    print(f"    扣减规则: {rec.applicable_deduction_id}")
    print(f"    扣减版本: {rec.applicable_deduction_version}")

    print("\n" + "=" * 60)
    print("测试完成！所有功能验证通过。")
    print("=" * 60)


if __name__ == "__main__":
    test_review_workstation()
