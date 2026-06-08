"""mAI-Brain 에이전트 도구 — 차트 생성

데이터를 차트(막대, 선, 파이, 산점도)로 시각화하는 도구.
프론트엔드에서 Chart.js 등으로 렌더링할 수 있는 구조화된 데이터를 반환.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.agent_tools.base import BaseTool, ToolParameter, ToolResult, ParameterType

logger = logging.getLogger(__name__)


class GenerateChartTool(BaseTool):
    """차트 생성 도구

    데이터와 차트 타입을 받아 프론트엔드에서 렌더링 가능한
    구조화된 차트 데이터를 반환. Chart.js 호환 형식.
    """

    VALID_CHART_TYPES = {"bar", "line", "pie", "scatter"}

    @property
    def name(self) -> str:
        return "generate_chart"

    @property
    def description(self) -> str:
        return (
            "데이터를 차트로 시각화합니다. "
            "막대 그래프, 선 그래프, 원형 차트, 산점도를 지원합니다. "
            "데이터를 시각적으로 비교/분석할 때 사용합니다."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="chart_type",
                type=ParameterType.STRING,
                description="차트 타입: bar, line, pie, scatter",
                required=True,
            ),
            ToolParameter(
                name="title",
                type=ParameterType.STRING,
                description="차트 제목",
                required=True,
            ),
            ToolParameter(
                name="labels",
                type=ParameterType.ARRAY,
                description="X축 레이블 목록 (pie: 항목 이름)",
                required=True,
            ),
            ToolParameter(
                name="datasets",
                type=ParameterType.ARRAY,
                description="데이터셋 목록 [{label, data, color?}]",
                required=True,
            ),
        ]

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        chart_type = params.get("chart_type", "bar")
        title = params.get("title", "")
        labels = params.get("labels", [])
        datasets = params.get("datasets", [])

        # 입력 검증
        if chart_type not in self.VALID_CHART_TYPES:
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"지원하지 않는 차트 타입: {chart_type}. "
                      f"지원 타입: {', '.join(self.VALID_CHART_TYPES)}",
            )

        if not labels or not datasets:
            return ToolResult(
                success=False,
                tool_name=self.name,
                error="labels와 datasets는 필수입니다.",
            )

        # Chart.js 호환 데이터 구조 생성
        chart_data = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": self._normalize_datasets(datasets, chart_type),
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {"display": True, "text": title},
                    "legend": {"display": len(datasets) > 1 or chart_type == "pie"},
                },
            },
        }

        return ToolResult(
            success=True,
            tool_name=self.name,
            data=chart_data,
            display=ToolResult.ToolDisplay(
                type="chart",
                title=title,
                chart_type=chart_type,
                chart_data=chart_data,
            ),
        )

    def _normalize_datasets(
        self, datasets: list[dict], chart_type: str
    ) -> list[dict]:
        """데이터셋을 Chart.js 호환 형식으로 정규화"""
        # 기본 색상 팔레트
        default_colors = [
            "rgba(59, 130, 246, 0.7)",   # blue
            "rgba(239, 68, 68, 0.7)",     # red
            "rgba(34, 197, 94, 0.7)",     # green
            "rgba(234, 179, 8, 0.7)",     # yellow
            "rgba(168, 85, 247, 0.7)",    # purple
            "rgba(249, 115, 22, 0.7)",    # orange
            "rgba(20, 184, 166, 0.7)",    # teal
            "rgba(236, 72, 153, 0.7)",    # pink
        ]

        normalized = []
        for i, ds in enumerate(datasets):
            label = ds.get("label", f"데이터셋 {i + 1}")
            data = ds.get("data", [])
            color = ds.get("color", default_colors[i % len(default_colors)])

            entry: dict[str, Any] = {"label": label, "data": data}

            if chart_type == "pie":
                # 파이 차트는 backgroundColor 배열 필요
                entry["backgroundColor"] = [
                    default_colors[j % len(default_colors)] for j in range(len(data))
                ]
                entry["borderColor"] = "#fff"
                entry["borderWidth"] = 2
            else:
                entry["backgroundColor"] = color
                entry["borderColor"] = color.replace("0.7", "1")
                entry["borderWidth"] = 2

            if chart_type == "line":
                entry["fill"] = False
                entry["tension"] = 0.1

            if chart_type == "scatter":
                # scatter는 {x, y} 형식 데이터
                entry["data"] = data

            normalized.append(entry)

        return normalized