#!/usr/bin/env python3
"""测试 Neo4j 连接和基础功能"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from graph.client import Neo4jClient
from memory.neo4j_service import Neo4jGraphService


def test_connection():
    """测试 Neo4j 连接"""
    print("=" * 60)
    print("测试 Neo4j 连接")
    print("=" * 60)

    print(f"\n配置:")
    print(f"  URI: {settings.neo4j_uri}")
    print(f"  User: {settings.neo4j_username}")
    print(f"  Database: {settings.neo4j_database}")

    try:
        client = Neo4jClient()
        print("\n✅ Neo4j 连接成功!")

        # 测试基础查询
        with client.driver.session(database=client.database) as session:
            result = session.run("RETURN 1 as num")
            record = result.single()
            print(f"✅ 基础查询成功: {record['num']}")

        client.close()
        return True

    except Exception as e:
        print(f"\n❌ Neo4j 连接失败: {e}")
        return False


def test_graph_operations():
    """测试图操作"""
    print("\n" + "=" * 60)
    print("测试图操作")
    print("=" * 60)

    TEST_GROUP_ID = "test_group_123"

    try:
        service = Neo4jGraphService()

        # 1. 确保 Graph 存在
        print(f"\n1. 创建测试 Graph: {TEST_GROUP_ID}")
        service.ensure_graph_exists(TEST_GROUP_ID)
        print("   ✅ Graph 创建成功")

        # 2. 创建实体
        print("\n2. 创建测试实体")
        entity1_uuid = service.get_or_create_entity(
            TEST_GROUP_ID, "测试人物A", "person", "一个测试人物"
        )
        entity2_uuid = service.get_or_create_entity(
            TEST_GROUP_ID, "测试组织B", "organization", "一个测试组织"
        )
        print(f"   ✅ 实体1 UUID: {entity1_uuid}")
        print(f"   ✅ 实体2 UUID: {entity2_uuid}")

        # 3. 查询实体
        print("\n3. 查询实体")
        entities = service.get_all_entities(TEST_GROUP_ID)
        print(f"   ✅ 共 {len(entities)} 个实体")
        for ent in entities[:3]:
            print(f"      - {ent['name']} ({ent['entity_type']})")

        # 4. 创建关系
        print("\n4. 创建测试关系")
        from memory.extractor import Triplet
        from datetime import datetime

        triplet = Triplet(
            subject="测试人物A",
            subject_type="person",
            predicate="领导",
            object="测试组织B",
            object_type="organization",
            fact="测试人物A领导测试组织B",
            subject_summary="一个测试人物",
            object_summary="一个测试组织"
        )

        edge_uuid = service.temporal_upsert(
            TEST_GROUP_ID,
            triplet,
            "test_episode_001",
            datetime.now()
        )
        print(f"   ✅ 关系 UUID: {edge_uuid}")

        # 5. 查询关系
        print("\n5. 查询关系")
        edges = service.get_all_edges(TEST_GROUP_ID, active_only=True)
        print(f"   ✅ 共 {len(edges)} 条活跃关系")
        for edge in edges[:3]:
            print(f"      - {edge['predicate']}: {edge['fact'][:50]}")

        # 清理测试数据
        print("\n6. 清理测试数据")
        service.client.delete_graph(TEST_GROUP_ID)
        print("   ✅ 测试数据已清理")

        service.close()
        return True

    except Exception as e:
        print(f"\n❌ 图操作测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n🚀 开始 Neo4j 测试\n")

    # Test 1: Connection
    if not test_connection():
        print("\n❌ 连接测试失败，请检查配置")
        return 1

    # Test 2: Graph operations
    if not test_graph_operations():
        print("\n❌ 图操作测试失败")
        return 1

    print("\n" + "=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
