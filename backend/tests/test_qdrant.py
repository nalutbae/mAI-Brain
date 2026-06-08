"""QdrantManager 단위 테스트

컬렉션 생성, 포인트 삽입, 삭제, 검색 기능을 테스트합니다.
"""

import pytest

from app.core.qdrant import QdrantManager, get_qdrant
from qdrant_client import models


class TestQdrantManager:
    """QdrantManager 테스트 스위트"""

    @pytest.fixture
    def qdrant(self):
        """QdrantManager 인스턴스 fixture"""
        manager = QdrantManager()
        # 기존 컬렉션이 있으면 삭제하여 테스트 격리
        if manager.collection_exists():
            manager.client.delete_collection(manager.collection_name)
        yield manager
        # 테스트 후 정리
        if manager.collection_exists():
            manager.client.delete_collection(manager.collection_name)

    def test_collection_creation(self, qdrant: QdrantManager):
        """컬렉션 생성 테스트"""
        # 컬렉션이 없는 상태 확인
        assert not qdrant.collection_exists()

        # 컬렉션 생성
        qdrant.init_collection()

        # 컬렉션이 생성되었는지 확인
        assert qdrant.collection_exists()

        # 중복 생성 시도 - 에러 없이 통과
        qdrant.init_collection()
        assert qdrant.collection_exists()

    def test_upsert_points(self, qdrant: QdrantManager):
        """포인트 삽입 (upsert) 테스트"""
        qdrant.init_collection()

        # 테스트 포인트 생성
        test_points = [
            models.PointStruct(
                id=1,
                vector={
                    "dense": [0.1] * 1024,  # 1024차원 dense 벡터
                    "sparse": models.SparseVector(
                        indices=[1, 2, 3],
                        values=[0.5, 0.3, 0.2],
                    ),
                },
                payload={
                    "source": "test_doc1.txt",
                    "text": "테스트 문장 1입니다.",
                    "chunk_index": 0,
                },
            ),
            models.PointStruct(
                id=2,
                vector={
                    "dense": [0.2] * 1024,
                    "sparse": models.SparseVector(
                        indices=[2, 3, 4],
                        values=[0.4, 0.3, 0.3],
                    ),
                },
                payload={
                    "source": "test_doc1.txt",
                    "text": "테스트 문장 2입니다.",
                    "chunk_index": 1,
                },
            ),
        ]

        # 포인트 삽입
        qdrant.upsert_points(test_points)

        # 컬렉션 정보 확인
        info = qdrant.get_collection_info()
        assert info["points_count"] >= 2

    def test_delete_by_source(self, qdrant: QdrantManager):
        """소스별 삭제 테스트"""
        qdrant.init_collection()

        # 테스트 포인트 삽입
        test_points = [
            models.PointStruct(
                id=1,
                vector={
                    "dense": [0.1] * 1024,
                    "sparse": models.SparseVector(
                        indices=[1, 2, 3],
                        values=[0.5, 0.3, 0.2],
                    ),
                },
                payload={
                    "source": "doc1.txt",
                    "text": "문서 1 청크 1",
                },
            ),
            models.PointStruct(
                id=2,
                vector={
                    "dense": [0.2] * 1024,
                    "sparse": models.SparseVector(
                        indices=[2, 3, 4],
                        values=[0.4, 0.3, 0.3],
                    ),
                },
                payload={
                    "source": "doc1.txt",
                    "text": "문서 1 청크 2",
                },
            ),
            models.PointStruct(
                id=3,
                vector={
                    "dense": [0.3] * 1024,
                    "sparse": models.SparseVector(
                        indices=[3, 4, 5],
                        values=[0.3, 0.4, 0.3],
                    ),
                },
                payload={
                    "source": "doc2.txt",
                    "text": "문서 2 청크 1",
                },
            ),
        ]

        qdrant.upsert_points(test_points)
        initial_count = qdrant.get_collection_info()["points_count"]
        assert initial_count == 3

        # doc1.txt 소스 삭제 (2개 포인트)
        qdrant.delete_by_source("doc1.txt")

        # 1개 포인트만 남아야 함 (doc2.txt의 1개)
        final_count = qdrant.get_collection_info()["points_count"]
        assert final_count == 1

    def test_search_hybrid(self, qdrant: QdrantManager):
        """하이브리드 검색 (dense + sparse RRF) 테스트"""
        qdrant.init_collection()

        # 유사한 내용의 포인트 삽입
        test_points = [
            models.PointStruct(
                id=1,
                vector={
                    "dense": [0.9] * 1024,  # 높은 유사도
                    "sparse": models.SparseVector(
                        indices=[10, 20, 30],  # 키워드 일치
                        values=[0.8, 0.7, 0.6],
                    ),
                },
                payload={
                    "source": "test.txt",
                    "text": "test혁명은 혁명의 길입니다.",
                },
            ),
            models.PointStruct(
                id=2,
                vector={
                    "dense": [0.1] * 1024,  # 낮은 유사도
                    "sparse": models.SparseVector(
                        indices=[99, 100, 101],  # 키워드 불일치
                        values=[0.8, 0.7, 0.6],
                    ),
                },
                payload={
                    "source": "test.txt",
                    "text": "무관한 내용입니다.",
                },
            ),
        ]

        qdrant.upsert_points(test_points)

        # 하이브리드 검색
        query_dense = [0.95] * 1024  # 첫 번째 포인트와 유사
        query_sparse = {10: 0.8, 20: 0.7}  # 첫 번째 포인트와 키워드 일치

        results = qdrant.search(query_dense, query_sparse, limit=2)

        # 결과 검증
        assert len(results) > 0
        # 첫 번째 포인트(text="test혁명은...")가 더 높은 점수를 받아야 함
        assert results[0]["payload"]["text"] == "test혁명은 혁명의 길입니다."

    def test_get_collection_info(self, qdrant: QdrantManager):
        """컬렉션 정보 조회 테스트"""
        qdrant.init_collection()

        info = qdrant.get_collection_info()

        # 필드 확인
        assert "points_count" in info
        assert "status" in info
        assert "config" in info
        assert info["points_count"] == 0  # 아직 포인트 없음

    def test_health_check(self, qdrant: QdrantManager):
        """헬스 체크 테스트"""
        # Qdrant가 실행 중이지 않으면 False 반환
        # 실행 중이면 True 반환
        is_healthy = qdrant.health_check()
        # 테스트 환경에 따라 결과가 다를 수 있음
        assert isinstance(is_healthy, bool)

    def test_singleton_get_qdrant(self):
        """싱글톤 get_qdrant() 테스트"""
        qdrant1 = get_qdrant()
        qdrant2 = get_qdrant()

        # 같은 인스턴스인지 확인
        assert qdrant1 is qdrant2


class TestQdrantManagerEdgeCases:
    """엣지 케이스 테스트"""

    @pytest.fixture
    def qdrant(self, request):
        """테스트용 QdrantManager fixture"""
        manager = QdrantManager()
        if manager.collection_exists():
            manager.client.delete_collection(manager.collection_name)
        yield manager
        if manager.collection_exists():
            manager.client.delete_collection(manager.collection_name)

    def test_upsert_empty_points(self, qdrant: QdrantManager):
        """빈 포인트 리스트로 upsert 시 에러 없이 무시"""
        qdrant.init_collection()
        qdrant.upsert_points([])  # 에러 없이 통과

    def test_search_empty_collection(self, qdrant: QdrantManager):
        """빈 컬렉션에서 검색 시 빈 결과 반환"""
        qdrant.init_collection()

        query_dense = [0.5] * 1024
        query_sparse = {1: 0.5}

        results = qdrant.search(query_dense, query_sparse, limit=5)
        assert results == []

    def test_delete_nonexistent_source(self, qdrant: QdrantManager):
        """존재하지 않는 소스 삭제 시 에러 없이 처리"""
        qdrant.init_collection()
        qdrant.delete_by_source("nonexistent.txt")  # 에러 없이 통과


@pytest.mark.integration
class TestQdrantIntegration:
    """통합 테스트 (Qdrant 서버 필요) - 실제 포인트 수 많은 경우"""

    @pytest.fixture
    def qdrant(self):
        manager = QdrantManager()
        if not manager.health_check():
            pytest.skip("Qdrant 서버가 실행되지 않음")
        if manager.collection_exists():
            manager.client.delete_collection(manager.collection_name)
        yield manager
        if manager.collection_exists():
            manager.client.delete_collection(manager.collection_name)

    def test_large_batch_upsert(self, qdrant: QdrantManager):
        """대량 포인트 일괄 삽입 테스트"""
        qdrant.init_collection()

        # 100개 포인트 생성
        points = []
        for i in range(100):
            points.append(
                models.PointStruct(
                    id=i,
                    vector={
                        "dense": [i / 100] * 1024,
                        "sparse": models.SparseVector(
                            indices=[i],
                            values=[1.0],
                        ),
                    },
                    payload={
                        "source": f"doc_{i % 10}.txt",
                        "text": f"청크 {i}",
                    },
                )
            )

        qdrant.upsert_points(points)

        info = qdrant.get_collection_info()
        assert info["points_count"] == 100

    def test_hybrid_search_multiple_sources(self, qdrant: QdrantManager):
        """여러 소스에서 하이브리드 검색 테스트"""
        qdrant.init_collection()

        # 여러 소스의 포인트 삽입
        points = []
        for doc_id in range(3):
            for chunk_id in range(10):
                points.append(
                    models.PointStruct(
                        id=doc_id * 10 + chunk_id,
                        vector={
                            "dense": [doc_id / 3] * 1024,
                            "sparse": models.SparseVector(
                                indices=[doc_id * 100 + chunk_id],
                                values=[1.0],
                            ),
                        },
                        payload={
                            "source": f"doc{doc_id}.txt",
                            "text": f"문서 {doc_id} 청크 {chunk_id}",
                        },
                    )
                )

        qdrant.upsert_points(points)

        # doc0에서 검색
        query_dense = [0.3] * 1024  # doc0/1 중간
        query_sparse = {0 * 100 + 5: 1.0, 1 * 100 + 5: 0.5}  # doc0 청크 5 강조

        results = qdrant.search(query_dense, query_sparse, limit=5)

        # doc0의 청크가 상위에 와야 함
        top_results = [r["payload"]["source"] for r in results[:3]]
        assert "doc0.txt" in top_results