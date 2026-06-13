import requests
import json
from datetime import date

BASE_URL = "http://localhost:8114"

def test_appeal_workflow():
    print("=" * 60)
    print("测试服务记录申诉与积分更正功能")
    print("=" * 60)

    # 1. 获取现有记录
    print("\n1. 获取已计入的服务记录...")
    resp = requests.get(f"{BASE_URL}/api/records", params={"status": "已计入"})
    records = resp.json()
    print(f"   已计入记录数: {len(records)}")
    if not records:
        print("   没有已计入的记录，跳过测试")
        return

    test_record = records[0]
    record_id = test_record["record_id"]
    print(f"   测试记录ID: {record_id}")
    print(f"   原积分: {test_record['final_points']}")
    print(f"   原质量等级: {test_record['quality']}")
    print(f"   原时长: {test_record['duration_hours']}h")

    # 2. 提交申诉
    print("\n2. 提交申诉...")
    appeal_data = {
        "record_id": record_id,
        "appeal_reason": "服务时长登记有误，实际服务时间更长",
        "submitted_by": "volunteer001",
        "supplementary_note": "当天活动实际从14:00持续到18:00，共4小时",
        "expected_result": "希望将服务时长更正为4小时，并重新计算积分"
    }
    resp = requests.post(f"{BASE_URL}/api/appeals", json=appeal_data)
    if resp.status_code != 200:
        print(f"   提交申诉失败: {resp.status_code} - {resp.text}")
        return
    appeal = resp.json()
    appeal_id = appeal["appeal_id"]
    print(f"   申诉提交成功，申诉ID: {appeal_id}")
    print(f"   申诉状态: {appeal['status']}")
    print(f"   原始积分保存: {appeal['original_final_points']}")

    # 3. 查询申诉列表
    print("\n3. 查询申诉列表...")
    resp = requests.get(f"{BASE_URL}/api/appeals")
    appeals = resp.json()
    print(f"   申诉总数: {len(appeals)}")

    # 4. 按状态筛选
    print("\n4. 按状态筛选（待处理）...")
    resp = requests.get(f"{BASE_URL}/api/appeals", params={"status": "待处理"})
    pending_appeals = resp.json()
    print(f"   待处理申诉数: {len(pending_appeals)}")

    # 5. 按项目筛选
    print("\n5. 按项目筛选...")
    resp = requests.get(f"{BASE_URL}/api/appeals", params={"project_id": test_record["project_id"]})
    proj_appeals = resp.json()
    print(f"   该项目申诉数: {len(proj_appeals)}")

    # 6. 获取申诉详情
    print("\n6. 获取申诉详情...")
    resp = requests.get(f"{BASE_URL}/api/appeals/{appeal_id}")
    detail = resp.json()
    print(f"   申诉信息存在: {detail['appeal'] is not None}")
    print(f"   原记录信息存在: {detail['original_record'] is not None}")
    print(f"   原记录状态: {detail['original_record']['status']}")
    print(f"   处理轨迹数: {len(detail['appeal']['timeline'])}")

    # 7. 通过申诉并更正积分
    print("\n7. 通过申诉并更正积分（调整质量等级为优秀）...")
    approve_data = {
        "handler": "admin001",
        "correction": {
            "quality": "优秀",
            "duration_hours": 4.0,
            "note": "经核实，服务时长和质量等级确实有误，予以更正"
        },
        "handle_note": "情况属实，同意更正"
    }
    resp = requests.post(f"{BASE_URL}/api/appeals/{appeal_id}/approve", json=approve_data)
    if resp.status_code != 200:
        print(f"   通过申诉失败: {resp.status_code} - {resp.text}")
        return
    approved_appeal = resp.json()
    print(f"   申诉状态: {approved_appeal['status']}")
    print(f"   处理人: {approved_appeal['handler']}")
    print(f"   处理时间: {approved_appeal['handled_at']}")
    print(f"   更正信息: {approved_appeal['correction']}")

    # 8. 验证记录已更新
    print("\n8. 验证服务记录已更新...")
    resp = requests.get(f"{BASE_URL}/api/records/{record_id}")
    updated_record = resp.json()
    print(f"   质量等级: {updated_record['quality']} (原: {test_record['quality']})")
    print(f"   服务时长: {updated_record['duration_hours']}h (原: {test_record['duration_hours']}h)")
    print(f"   最终积分: {updated_record['final_points']} (原: {test_record['final_points']})")

    # 9. 验证个人积分汇总已更新
    print("\n9. 验证个人积分汇总...")
    resp = requests.get(f"{BASE_URL}/api/statistics/personal-summary", 
                       params={"participant_id": test_record["participant_id"]})
    summary = resp.json()
    print(f"   个人汇总记录数: {len(summary)}")
    if summary:
        print(f"   总积分: {summary[0]['final_points']}")

    # 10. 验证项目贡献排行已更新
    print("\n10. 验证项目贡献排行...")
    resp = requests.get(f"{BASE_URL}/api/statistics/project-ranking")
    ranking = resp.json()
    print(f"   排行项目数: {len(ranking)}")
    for item in ranking:
        if item["project_id"] == test_record["project_id"]:
            print(f"   项目总积分: {item['total_points']}")

    # 11. 测试另一个申诉（用于测试驳回）
    print("\n11. 提交第二个申诉用于测试驳回...")
    appeal_data2 = {
        "record_id": record_id,
        "appeal_reason": "测试驳回流程",
        "submitted_by": "volunteer002",
        "expected_result": "测试"
    }
    resp = requests.post(f"{BASE_URL}/api/appeals", json=appeal_data2)
    if resp.status_code != 200:
        print(f"   提交失败（正常，因为已有待处理申诉）: {resp.status_code}")
    else:
        appeal2 = resp.json()
        appeal_id2 = appeal2["appeal_id"]
        print(f"   申诉2提交成功，ID: {appeal_id2}")

        # 驳回申诉
        print("\n12. 驳回申诉...")
        reject_data = {
            "handler": "admin001",
            "rejection_reason": "证据不足，无法证明服务时长有误",
            "handle_note": "请补充更多证明材料后重新申诉"
        }
        resp = requests.post(f"{BASE_URL}/api/appeals/{appeal_id2}/reject", json=reject_data)
        if resp.status_code != 200:
            print(f"   驳回失败: {resp.status_code} - {resp.text}")
        else:
            rejected = resp.json()
            print(f"   申诉状态: {rejected['status']}")
            print(f"   驳回原因: {rejected['rejection_reason']}")
            print(f"   处理轨迹数: {len(rejected['timeline'])}")

    # 12. 获取某记录的所有申诉
    print("\n13. 获取该记录的所有申诉...")
    resp = requests.get(f"{BASE_URL}/api/records/{record_id}/appeals")
    record_appeals = resp.json()
    print(f"   该记录申诉数: {len(record_appeals)}")
    for a in record_appeals:
        print(f"     - {a['appeal_id']}: {a['status']}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_appeal_workflow()
