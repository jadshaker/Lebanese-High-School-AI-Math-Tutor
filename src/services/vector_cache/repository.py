import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Condition,
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    VectorParams,
)

from src.config import Config
from src.models.schemas import SearchFilters, SourceType


class QdrantRepository:
    """Repository for Qdrant vector database operations"""

    def __init__(self, client: AsyncQdrantClient):
        self.client = client
        self.questions_collection = Config.COLLECTIONS.QUESTIONS
        self.nodes_collection = Config.COLLECTIONS.TUTORING_NODES

    async def ensure_collections(self) -> None:
        """Create collections if they don't exist"""
        collections = await self.client.get_collections()
        existing = {c.name for c in collections.collections}

        if self.questions_collection not in existing:
            await self.client.create_collection(
                collection_name=self.questions_collection,
                vectors_config=VectorParams(
                    size=Config.VECTOR.DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
            await self.client.create_payload_index(
                collection_name=self.questions_collection,
                field_name="lesson",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=self.questions_collection,
                field_name="source",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=self.questions_collection,
                field_name="confidence",
                field_schema=PayloadSchemaType.FLOAT,
            )

        if self.nodes_collection not in existing:
            await self.client.create_collection(
                collection_name=self.nodes_collection,
                vectors_config=VectorParams(
                    size=Config.VECTOR.DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
            await self.client.create_payload_index(
                collection_name=self.nodes_collection,
                field_name="question_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=self.nodes_collection,
                field_name="parent_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )

    async def get_collection_counts(self) -> dict[str, int]:
        """Get point counts for all collections"""
        counts = {}
        for name in [self.questions_collection, self.nodes_collection]:
            try:
                info = await self.client.get_collection(name)
                counts[name] = info.points_count or 0
            except Exception:
                counts[name] = 0
        return counts

    # === Question Operations ===

    async def search_questions(
        self,
        embedding: list[float],
        top_k: int,
        threshold: float,
        filters: Optional[SearchFilters] = None,
    ) -> list[dict]:
        """Search for similar questions"""
        query_filter = None
        if filters:
            conditions: list[Condition] = []
            if filters.lesson:
                conditions.append(
                    FieldCondition(key="lesson", match=MatchValue(value=filters.lesson))
                )
            if filters.min_confidence is not None:
                conditions.append(
                    FieldCondition(
                        key="confidence", range=Range(gte=filters.min_confidence)
                    )
                )
            if filters.source:
                conditions.append(
                    FieldCondition(
                        key="source", match=MatchValue(value=filters.source.value)
                    )
                )
            if conditions:
                query_filter = Filter(must=conditions)

        results = await self.client.query_points(
            collection_name=self.questions_collection,
            query=embedding,
            limit=top_k,
            score_threshold=threshold,
            query_filter=query_filter,
            with_payload=True,
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                **(r.payload or {}),
            }
            for r in results.points
        ]

    async def add_question(
        self,
        question_text: str,
        reformulated_text: str,
        answer_text: str,
        embedding: list[float],
        lesson: Optional[str],
        source: SourceType,
        confidence: float,
    ) -> str:
        """Add a new question to the cache"""
        question_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "question_text": question_text,
            "reformulated_text": reformulated_text,
            "answer_text": answer_text,
            "lesson": lesson,
            "source": source.value,
            "confidence": confidence,
            "usage_count": 0,
            "positive_feedback": 0,
            "negative_feedback": 0,
            "created_at": now,
            "updated_at": now,
        }

        await self.client.upsert(
            collection_name=self.questions_collection,
            points=[PointStruct(id=question_id, vector=embedding, payload=payload)],
        )

        return question_id

    async def get_question(self, question_id: str) -> Optional[dict]:
        """Get a question by ID"""
        results = await self.client.retrieve(
            collection_name=self.questions_collection,
            ids=[question_id],
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        return {"id": str(results[0].id), **(results[0].payload or {})}

    async def update_question(
        self,
        question_id: str,
        answer_text: Optional[str] = None,
        confidence: Optional[float] = None,
        lesson: Optional[str] = None,
    ) -> bool:
        """Update question fields"""
        updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if answer_text is not None:
            updates["answer_text"] = answer_text
        if confidence is not None:
            updates["confidence"] = confidence
        if lesson is not None:
            updates["lesson"] = lesson

        await self.client.set_payload(
            collection_name=self.questions_collection,
            payload=updates,
            points=[question_id],
        )
        return True

    async def increment_usage(self, question_id: str) -> None:
        """Increment usage count for a question"""
        question = await self.get_question(question_id)
        if question:
            new_count = question.get("usage_count", 0) + 1
            await self.client.set_payload(
                collection_name=self.questions_collection,
                payload={"usage_count": new_count},
                points=[question_id],
            )

    async def add_feedback(self, question_id: str, positive: bool) -> dict:
        """Add feedback to a question"""
        question = await self.get_question(question_id)
        if not question:
            raise ValueError(f"Question {question_id} not found")

        pos = question.get("positive_feedback", 0)
        neg = question.get("negative_feedback", 0)

        if positive:
            pos += 1
        else:
            neg += 1

        total = pos + neg
        score = pos / total if total > 0 else 0.5

        await self.client.set_payload(
            collection_name=self.questions_collection,
            payload={"positive_feedback": pos, "negative_feedback": neg},
            points=[question_id],
        )

        return {
            "id": question_id,
            "positive_feedback": pos,
            "negative_feedback": neg,
            "feedback_score": score,
        }

    async def delete_question(self, question_id: str) -> bool:
        """Delete a question"""
        await self.client.delete(
            collection_name=self.questions_collection,
            points_selector=[question_id],
        )
        return True

    # === Interaction Node Operations ===

    async def add_interaction(
        self,
        question_id: str,
        parent_id: Optional[str],
        user_input: str,
        user_input_embedding: list[float],
        system_response: str,
    ) -> str:
        """Add an interaction node"""
        node_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        depth = 1
        if parent_id:
            parent = await self.get_interaction(parent_id)
            if parent:
                depth = parent.get("depth", 0) + 1

        payload: dict[str, Any] = {
            "question_id": question_id,
            "parent_id": parent_id,
            "user_input": user_input,
            "system_response": system_response,
            "depth": depth,
            "source": SourceType.API_LLM.value,
            "created_at": now,
        }

        await self.client.upsert(
            collection_name=self.nodes_collection,
            points=[
                PointStruct(id=node_id, vector=user_input_embedding, payload=payload)
            ],
        )

        return node_id

    async def get_interaction(self, node_id: str) -> Optional[dict]:
        """Get an interaction node by ID"""
        results = await self.client.retrieve(
            collection_name=self.nodes_collection,
            ids=[node_id],
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        return {"id": str(results[0].id), **(results[0].payload or {})}

    async def search_children(
        self,
        question_id: str,
        parent_id: Optional[str],
        user_input_embedding: list[float],
        threshold: float = 0.7,
    ) -> dict:
        """Search for similar user inputs among children of a parent node."""
        conditions: list[Condition] = [
            FieldCondition(key="question_id", match=MatchValue(value=question_id))
        ]

        if parent_id:
            conditions.append(
                FieldCondition(key="parent_id", match=MatchValue(value=parent_id))
            )
        else:
            conditions.append(FieldCondition(key="depth", match=MatchValue(value=1)))

        results = await self.client.query_points(
            collection_name=self.nodes_collection,
            query=user_input_embedding,
            limit=1,
            score_threshold=threshold,
            query_filter=Filter(must=conditions),
            with_payload=True,
        )

        if results.points:
            best = results.points[0]
            return {
                "is_cache_hit": True,
                "match_score": best.score,
                "matched_node": {
                    "id": str(best.id),
                    **(best.payload or {}),
                },
                "parent_id": parent_id,
            }

        return {
            "is_cache_hit": False,
            "match_score": None,
            "matched_node": None,
            "parent_id": parent_id,
        }

    async def get_conversation_path(
        self, question_id: str, node_id: Optional[str]
    ) -> dict:
        """Get full conversation path from question to current node"""
        question = await self.get_question(question_id)
        if not question:
            return {"question_id": question_id, "path": [], "total_depth": 0}

        path: list[dict[str, Any]] = []

        if node_id:
            current_id: Optional[str] = node_id
            while current_id:
                node = await self.get_interaction(current_id)
                if not node:
                    break
                path.append(
                    {
                        "id": node["id"],
                        "user_input": node["user_input"],
                        "system_response": node["system_response"],
                        "depth": node["depth"],
                    }
                )
                current_id = node.get("parent_id")
            path.reverse()

        return {
            "question_id": question_id,
            "question_text": question.get("question_text", ""),
            "answer_text": question.get("answer_text", ""),
            "path": path,
            "total_depth": len(path),
        }
