from __future__ import annotations

import threading
from collections import Counter


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_total: Counter[tuple[str, str, int]] = Counter()
        self._request_duration_ms_total: Counter[tuple[str, str]] = Counter()
        self._request_duration_count: Counter[tuple[str, str]] = Counter()
        self._job_total: Counter[tuple[str, str]] = Counter()
        self._exception_total: Counter[str] = Counter()
        self._dispatch_total: Counter[tuple[str, str]] = Counter()
        self._auth_total: Counter[tuple[str, str]] = Counter()

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path or "/unknown"

    @staticmethod
    def _status_bucket(status_code: int) -> int:
        return (status_code // 100) * 100

    def record_request(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        path = self._normalize_path(path)
        method = method.upper()
        status_bucket = self._status_bucket(status_code)
        with self._lock:
            self._request_total[(method, path, status_bucket)] += 1
            self._request_duration_ms_total[(method, path)] += duration_ms
            self._request_duration_count[(method, path)] += 1

    def record_job(self, *, name: str, status: str) -> None:
        with self._lock:
            self._job_total[(name, status)] += 1

    def record_exception(self, *, code: str) -> None:
        with self._lock:
            self._exception_total[code] += 1

    def record_dispatch(self, *, event: str, outcome: str = "success", count: int = 1) -> None:
        with self._lock:
            self._dispatch_total[(event, outcome)] += count

    def record_auth(self, *, event: str, outcome: str = "success", count: int = 1) -> None:
        with self._lock:
            self._auth_total[(event, outcome)] += count

    def reset(self) -> None:
        with self._lock:
            self._request_total.clear()
            self._request_duration_ms_total.clear()
            self._request_duration_count.clear()
            self._job_total.clear()
            self._exception_total.clear()
            self._dispatch_total.clear()
            self._auth_total.clear()

    def render_prometheus(self) -> str:
        lines: list[str] = [
            "# HELP moovesaathi_requests_total Total HTTP requests handled by the API.",
            "# TYPE moovesaathi_requests_total counter",
        ]
        with self._lock:
            for (method, path, status_bucket), value in sorted(self._request_total.items()):
                lines.append(
                    f'moovesaathi_requests_total{{method="{method}",path="{path}",status="{status_bucket}"}} {value}'
                )

            lines.extend(
                [
                    "# HELP moovesaathi_request_duration_ms_sum Total request duration in milliseconds.",
                    "# TYPE moovesaathi_request_duration_ms_sum counter",
                ]
            )
            for (method, path), value in sorted(self._request_duration_ms_total.items()):
                lines.append(
                    f'moovesaathi_request_duration_ms_sum{{method="{method}",path="{path}"}} {round(value, 2)}'
                )

            lines.extend(
                [
                    "# HELP moovesaathi_request_duration_ms_count Total request samples observed.",
                    "# TYPE moovesaathi_request_duration_ms_count counter",
                ]
            )
            for (method, path), value in sorted(self._request_duration_count.items()):
                lines.append(
                    f'moovesaathi_request_duration_ms_count{{method="{method}",path="{path}"}} {value}'
                )

            lines.extend(
                [
                    "# HELP moovesaathi_jobs_total Total background jobs processed by status.",
                    "# TYPE moovesaathi_jobs_total counter",
                ]
            )
            for (name, status), value in sorted(self._job_total.items()):
                lines.append(f'moovesaathi_jobs_total{{job="{name}",status="{status}"}} {value}')

            lines.extend(
                [
                    "# HELP moovesaathi_exceptions_total Total exceptions seen by code.",
                    "# TYPE moovesaathi_exceptions_total counter",
                ]
            )
            for code, value in sorted(self._exception_total.items()):
                lines.append(f'moovesaathi_exceptions_total{{code="{code}"}} {value}')

            lines.extend(
                [
                    "# HELP moovesaathi_dispatch_total Total dispatch lifecycle and cleanup events.",
                    "# TYPE moovesaathi_dispatch_total counter",
                ]
            )
            for (event, outcome), value in sorted(self._dispatch_total.items()):
                lines.append(f'moovesaathi_dispatch_total{{event="{event}",outcome="{outcome}"}} {value}')

            lines.extend(
                [
                    "# HELP moovesaathi_auth_total Total auth security and recovery events.",
                    "# TYPE moovesaathi_auth_total counter",
                ]
            )
            for (event, outcome), value in sorted(self._auth_total.items()):
                lines.append(f'moovesaathi_auth_total{{event="{event}",outcome="{outcome}"}} {value}')

        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
