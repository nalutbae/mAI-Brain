"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Document,
  getDocuments,
  uploadMultipleDocuments,
  deleteDocument,
  uploadUrl,
} from "../../lib/api";
import { AdminGuard } from "../../components/AuthGuard";

// ── 상태 뱃지 컴포넌트 ──────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Document["status"] }) {
  const colors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
    indexing: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 animate-pulse",
    completed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  };
  const labels: Record<string, string> = {
    pending: "대기",
    indexing: "인덱싱 중",
    completed: "완료",
    failed: "실패",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[status] || ""}`}
    >
      {labels[status] || status}
    </span>
  );
}

// ── 드래그 & 드롭 업로드 영역 ───────────────────────────────────────────────

function UploadZone({
  files,
  onFilesChange,
  uploading,
  onUpload,
  urlInput,
  onUrlInputChange,
  onUrlUpload,
  urlUploading,
}: {
  files: File[];
  onFilesChange: (files: File[]) => void;
  uploading: boolean;
  onUpload: () => void;
  urlInput: string;
  onUrlInputChange: (value: string) => void;
  onUrlUpload: () => void;
  urlUploading: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current === 0) {
      setDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      dragCounter.current = 0;
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const validFiles = Array.from(e.dataTransfer.files).filter((f) => {
          const ext = f.name.split(".").pop()?.toLowerCase();
          return ext && ["pdf", "epub", "txt", "md", "markdown", "docx", "doc", "hwp", "xlsx", "xls", "csv"].includes(ext);
        });
        onFilesChange(validFiles);
      }
    },
    [onFilesChange]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        onFilesChange(Array.from(e.target.files));
      }
    },
    [onFilesChange]
  );

  const removeFile = useCallback(
    (index: number) => {
      onFilesChange(files.filter((_, i) => i !== index));
    },
    [files, onFilesChange]
  );

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="mb-6">
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors
          ${dragging ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20" : "border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500"}
          ${files.length > 0 ? "pb-4" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.epub,.txt,.md,.markdown,.docx,.doc,.hwp,.xlsx,.xls,.csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <svg
          className="mx-auto h-12 w-12 text-gray-400"
          stroke="currentColor"
          fill="none"
          viewBox="0 0 48 48"
        >
          <path
            d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          <span className="font-medium text-blue-600 dark:text-blue-400">
            클릭하여 파일 선택
          </span>{" "}
          또는 여기로 파일을 드래그하세요
        </p>
        <p className="text-xs text-gray-500 mt-1">
          PDF, EPUB, TXT, DOCX, DOC, HWP, XLSX, XLS, CSV, MD 파일 지원
        </p>
      </div>

      {/* ── URL 웹페이지 인덱싱 ──────────────────────────────── */}
      <div className="mt-4 p-4 border border-blue-200 dark:border-blue-800 rounded-lg bg-blue-50 dark:bg-blue-900/20">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg">🌐</span>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">URL 웹페이지 인덱싱</h3>
        </div>
        <div className="flex gap-2">
          <input
            type="url"
            placeholder="https://example.com/article"
            value={urlInput}
            onChange={(e) => onUrlInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && urlInput.trim()) onUrlUpload();
            }}
            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            onClick={onUrlUpload}
            disabled={!urlInput.trim() || urlUploading}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {urlUploading ? "인덱싱 중..." : "인덱싱"}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          웹페이지 본문을 자동 추출하여 인덱싱합니다 (readability 기반)
        </p>
      </div>

      {/* 선택된 파일 목록 */}
      {files.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {files.length}개 파일 선택됨
            </p>
            <div className="flex gap-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onFilesChange([]);
                }}
                className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                모두 취소
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onUpload();
                }}
                disabled={uploading}
                className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {uploading ? "업로드 중..." : "업로드"}
              </button>
            </div>
          </div>
          {files.map((file, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2 min-w-0">
                <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="truncate dark:text-gray-200">{file.name}</span>
                <span className="text-gray-400 shrink-0">{formatFileSize(file.size)}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeFile(idx);
                }}
                className="text-gray-400 hover:text-red-500 ml-2 shrink-0"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 문서 목록 테이블 ────────────────────────────────────────────────────────

function DocumentTable({
  documents,
  onDelete,
}: {
  documents: Document[];
  onDelete: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              파일명
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              상태
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              청크
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              업로드 시간
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
              관리
            </th>
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
          {documents.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-12 text-center text-gray-500 dark:text-gray-400">
                업로드된 문서가 없습니다.
              </td>
            </tr>
          ) : (
            documents.map((doc) => (
              <tr key={doc.document_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-200 max-w-[300px] truncate">
                  {doc.filename}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.status} />
                </td>
                <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                  {doc.total_chunks ?? "-"}
                </td>
                <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                  {doc.created_at
                    ? new Date(doc.created_at).toLocaleString("ko-KR", {
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "-"}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => onDelete(doc.document_id)}
                    className="text-red-500 hover:text-red-700 dark:hover:text-red-400 text-sm font-medium transition-colors"
                  >
                    삭제
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── 관리자 페이지 메인 ────────────────────────────────────────────────────

export default function AdminPage() {
  return (
    <AdminGuard>
      <AdminContent />
    </AdminGuard>
  );
}

function AdminContent() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [urlUploading, setUrlUploading] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // 문서 목록 불러오기
  const loadDocuments = useCallback(async () => {
    try {
      const docs = await getDocuments();
      setDocuments(docs);
      setError(null);
    } catch {
      setError("문서 목록을 불러오는데 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 초기 로드 + 3초마다 폴링 (인덱싱 상태 갱신)
  useEffect(() => {
    loadDocuments();
    const interval = setInterval(loadDocuments, 3000);
    return () => clearInterval(interval);
  }, [loadDocuments]);

  // 업로드 실행
  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const results = await uploadMultipleDocuments(files);
      const failed = results.filter((r) => r.status === "failed");
      const succeeded = results.filter((r) => r.status !== "failed");
      if (succeeded.length > 0) {
        setSuccessMsg(`${succeeded.length}개 파일 업로드 완료`);
      }
      if (failed.length > 0) {
        setError(
          `${failed.length}개 파일 업로드 실패: ${failed.map((f) => f.filename).join(", ")}`
        );
      }
      setFiles([]);
      loadDocuments();
    } catch (e) {
      setError("파일 업로드 중 오류가 발생했습니다.");
    } finally {
      setUploading(false);
    }
  };

  // URL 웹페이지 업로드
  const handleUrlUpload = async () => {
    if (!urlInput.trim()) return;
    setUrlUploading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await uploadUrl(urlInput.trim());
      setSuccessMsg("URL 웹페이지 인덱싱이 시작되었습니다.");
      setUrlInput("");
      loadDocuments();
    } catch (e: any) {
      setError(e.message || "URL 인덱싱 중 오류가 발생했습니다.");
    } finally {
      setUrlUploading(false);
    }
  };

  // 문서 삭제
  const handleDelete = async (id: string) => {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      await deleteDocument(id);
      setSuccessMsg("문서가 삭제되었습니다.");
      loadDocuments();
    } catch {
      setError("문서 삭제에 실패했습니다.");
    }
  };

  // 통계
  const stats = {
    total: documents.length,
    completed: documents.filter((d) => d.status === "completed").length,
    indexing: documents.filter((d) => d.status === "indexing").length,
    failed: documents.filter((d) => d.status === "failed").length,
    totalChunks: documents.reduce((sum, d) => sum + (d.total_chunks || 0), 0),
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* 헤더 */}
      <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          📚 문서 관리
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          PDF, EPUB, TXT, DOCX, DOC, HWP, XLSX, XLS, CSV, MD 파일을 업로드하고 관리합니다
        </p>
      </header>

      {/* 메인 컨텐츠 */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* 알림 메시지 */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}
        {successMsg && (
          <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg text-sm text-green-700 dark:text-green-300">
            {successMsg}
          </div>
        )}

        {/* 업로드 영역 */}
        <section className="mb-8 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            파일 업로드
          </h2>
          <UploadZone
            files={files}
            onFilesChange={setFiles}
            uploading={uploading}
            onUpload={handleUpload}
            urlInput={urlInput}
            onUrlInputChange={setUrlInput}
            onUrlUpload={handleUrlUpload}
            urlUploading={urlUploading}
          />
        </section>

        {/* 통계 */}
        <section className="mb-8">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total}</p>
              <p className="text-xs text-gray-500 mt-1">전체 문서</p>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <p className="text-2xl font-bold text-green-600">{stats.completed}</p>
              <p className="text-xs text-gray-500 mt-1">인덱싱 완료</p>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <p className="text-2xl font-bold text-blue-600">{stats.indexing}</p>
              <p className="text-xs text-gray-500 mt-1">인덱싱 중</p>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <p className="text-2xl font-bold text-red-600">{stats.failed}</p>
              <p className="text-xs text-gray-500 mt-1">실패</p>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.totalChunks}</p>
              <p className="text-xs text-gray-500 mt-1">전체 청크</p>
            </div>
          </div>
        </section>

        {/* 문서 목록 */}
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              문서 목록
            </h2>
            <button
              onClick={loadDocuments}
              className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
            >
              ↻ 새로고침
            </button>
          </div>
          {isLoading ? (
            <div className="p-12 text-center text-gray-500">
              로딩 중...
            </div>
          ) : (
            <DocumentTable documents={documents} onDelete={handleDelete} />
          )}
        </section>
      </div>
    </div>
  );
}
