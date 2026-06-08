"""mAI-Brain 에이전트 도구 — 파일 저장

에이전트가 생성한 텍스트, 데이터, 차트 등을 파일로 저장하는 도구.
저장된 파일은 다운로드 링크를 통해 사용자에게 제공.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.agent_tools.base import BaseTool, ToolParameter, ToolResult, ParameterType

logger = logging.getLogger(__name__)

# 저장 디렉토리 (환경변수로 오버라이드 가능)
SAVE_DIR = os.environ.get(
    "AGENT_SAVE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "agent_exports"),
)


class SaveFileTool(BaseTool):
    """파일 저장 도구

    에이전트가 생성한 데이터를 파일로 저장.
    텍스트, JSON, CSV 등 다양한 포맷을 지원하며,
    저장된 파일 경로를 프론트엔드에 반환.
    """

    VALID_FORMATS = {"text", "json", "csv", "markdown"}

    @property
    def name(self) -> str:
        return "save_file"

    @property
    def description(self) -> str:
        return (
            "데이터를 파일로 저장합니다. "
            "텍스트, JSON, CSV, 마크다운 포맷을 지원합니다. "
            "저장된 파일은 다운로드 링크가 제공됩니다."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="filename",
                type=ParameterType.STRING,
                description="저장할 파일명 (확장자 포함)",
                required=True,
            ),
            ToolParameter(
                name="content",
                type=ParameterType.STRING,
                description="저장할 내용 (문자열)",
                required=True,
            ),
            ToolParameter(
                name="format",
                type=ParameterType.STRING,
                description="파일 포맷: text, json, csv, markdown",
                required=False,
                default="text",
            ),
        ]

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        filename = params["filename"]
        content = params["content"]
        format_type = params.get("format", "text")

        # 포맷 검증
        if format_type not in self.VALID_FORMATS:
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"지원하지 않는 포맷: {format_type}. "
                      f"지원 포맷: {', '.join(self.VALID_FORMATS)}",
            )

        try:
            # 저장 디렉토리 생성
            save_path = Path(SAVE_DIR).resolve()
            save_path.mkdir(parents=True, exist_ok=True)

            # 파일명에 타임스탬프 추가 (충돌 방지)
            name, ext = os.path.splitext(filename)
            if not ext:
                ext_map = {
                    "json": ".json",
                    "csv": ".csv",
                    "markdown": ".md",
                    "text": ".txt",
                }
                ext = ext_map.get(format_type, ".txt")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{name}_{timestamp}{ext}"
            file_path = save_path / safe_filename

            # 포맷별 저장 처리
            if format_type == "json":
                # JSON은 구조화하여 저장
                try:
                    data = json.loads(content)
                    file_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except json.JSONDecodeError:
                    file_path.write_text(content, encoding="utf-8")
            else:
                file_path.write_text(content, encoding="utf-8")

            logger.info("파일 저장 완료: %s", file_path)

            # API 접근 경로 생성
            relative_path = str(file_path.relative_to(save_path))

            return ToolResult(
                success=True,
                tool_name=self.name,
                data={
                    "filename": safe_filename,
                    "path": str(file_path),
                    "size_bytes": file_path.stat().st_size,
                    "format": format_type,
                },
                display=ToolResult.ToolDisplay(
                    type="file",
                    title=f"💾 파일 저장: {safe_filename}",
                    file_path=f"/api/agent/files/{relative_path}",
                ),
            )

        except Exception as exc:
            logger.error("파일 저장 오류: %s", exc, exc_info=True)
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"파일 저장 중 오류: {exc}",
            )