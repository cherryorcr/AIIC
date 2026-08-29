from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.config import Settings


ALLOWED_IMPORTS = {
    "bisect", "collections", "decimal", "fractions", "functools", "heapq",
    "itertools", "math", "operator", "random", "re", "statistics", "string", "typing",
}
FORBIDDEN_CALLS = {"__import__", "breakpoint", "compile", "eval", "exec", "input", "open"}
FORBIDDEN_ATTRIBUTES = {
    "__bases__", "__builtins__", "__class__", "__code__", "__globals__",
    "__mro__", "__subclasses__", "__traceback__",
}


class _CodePolicy(ast.NodeVisitor):
    def __init__(self) -> None:
        self.error: str | None = None

    def fail(self, message: str) -> None:
        if self.error is None:
            self.error = message

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name.split(".", 1)[0] not in ALLOWED_IMPORTS:
                self.fail(f"禁止导入模块: {alias.name}")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        root = (node.module or "").split(".", 1)[0]
        if node.level or root not in ALLOWED_IMPORTS:
            self.fail(f"禁止导入模块: {node.module or 'relative'}")

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            self.fail(f"禁止调用: {node.func.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.fail(f"禁止访问属性: {node.attr}")
        self.generic_visit(node)


class SandboxService:
    """Isolated challenge runner with process and language-level controls."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, code: str, tests: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        job_id = f"alg-{uuid.uuid4().hex}"
        tests = tests or []
        security = self._security_summary()
        if not self.settings.sandbox_enabled:
            return {"job_id": job_id, "status": "disabled", "passed": 0, "total": 0, "details": [], "security": security}
        if not code.strip():
            return {"job_id": job_id, "status": "rejected", "passed": 0, "total": 0, "stderr": "代码不能为空", "security": security}
        policy_error = self._validate_code(code)
        if policy_error:
            return {"job_id": job_id, "status": "rejected", "passed": 0, "total": len(tests), "stderr": policy_error, "details": [], "security": security}

        harness = self._build_harness(code, tests, int(self.settings.sandbox_max_output_bytes))
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="interview-sandbox-") as directory:
            script = Path(directory) / "runner.py"
            script.write_text(harness, encoding="utf-8")
            env = {"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "PATH": os.getenv("PATH", "")}
            kwargs: dict[str, Any] = {}
            preexec = self._resource_limiter()
            if preexec is not None:
                kwargs["preexec_fn"] = preexec
            elif os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", "-B", str(script)], cwd=directory, env=env,
                    capture_output=True, text=True, errors="replace",
                    timeout=max(0.05, float(self.settings.sandbox_timeout_seconds)), **kwargs,
                )
                stdout = completed.stdout[: self.settings.sandbox_max_output_bytes]
                stderr = completed.stderr[: self.settings.sandbox_max_output_bytes]
                payload = self._parse_result(stdout)
                runtime_ms = round((time.perf_counter() - started) * 1000, 2)
                if payload is not None:
                    return {"job_id": job_id, "runtime_ms": runtime_ms, **payload, "stdout": stdout, "stderr": stderr, "security": security}
                limited = completed.returncode < 0 and os.name != "nt"
                return {"job_id": job_id, "status": "resource_limited" if limited else ("passed" if completed.returncode == 0 else "error"), "passed": 0, "total": len(tests), "runtime_ms": runtime_ms, "stdout": stdout, "stderr": stderr or ("进程超过资源限制" if limited else ""), "details": [], "security": security}
            except subprocess.TimeoutExpired as exc:
                return {"job_id": job_id, "status": "timeout", "passed": 0, "total": len(tests), "runtime_ms": round((time.perf_counter() - started) * 1000, 2), "stdout": self._decode_timeout_output(exc.stdout), "stderr": "代码运行超时", "details": [], "security": security}

    @staticmethod
    def _validate_code(code: str) -> str | None:
        try:
            tree = ast.parse(code, mode="exec")
        except (SyntaxError, ValueError, MemoryError) as exc:
            return f"代码语法错误: {getattr(exc, 'msg', type(exc).__name__)}"
        policy = _CodePolicy()
        policy.visit(tree)
        return f"代码包含被禁止的操作（{policy.error}）" if policy.error else None

    def _resource_limiter(self) -> Callable[[], None] | None:
        if os.name != "posix":
            return None
        import resource
        cpu = max(1, int(self.settings.sandbox_cpu_seconds))
        memory = max(32, int(self.settings.sandbox_memory_mb)) * 1024 * 1024
        processes = max(1, int(self.settings.sandbox_max_processes))
        file_bytes = max(4096, int(self.settings.sandbox_max_file_bytes))

        def limit() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
            if hasattr(resource, "RLIMIT_NPROC"):
                resource.setrlimit(resource.RLIMIT_NPROC, (processes, processes))
            if hasattr(resource, "RLIMIT_NOFILE"):
                resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        return limit

    def _security_summary(self) -> dict[str, Any]:
        return {"network": "denied_by_import_policy_and_audit_hook", "isolated_python": True, "wall_timeout_seconds": self.settings.sandbox_timeout_seconds, "output_limit_bytes": self.settings.sandbox_max_output_bytes, "os_resource_limits": os.name == "posix", "cpu_seconds": self.settings.sandbox_cpu_seconds if os.name == "posix" else None, "memory_mb": self.settings.sandbox_memory_mb if os.name == "posix" else None, "max_processes": self.settings.sandbox_max_processes if os.name == "posix" else None, "max_file_bytes": self.settings.sandbox_max_file_bytes if os.name == "posix" else None}

    @staticmethod
    def _build_harness(code: str, tests: list[dict[str, Any]], max_output_bytes: int = 20000) -> str:
        encoded_tests = json.dumps(tests, ensure_ascii=False)
        encoded_code = json.dumps(code, ensure_ascii=False)
        return f'''# generated sandbox harness
import builtins as _builtins
import io as _io
import json as _json
import sys as _sys
class _LimitWriter(_io.TextIOBase):
    def __init__(self, wrapped, limit): self.wrapped, self.remaining = wrapped, limit
    def write(self, value):
        value = str(value); chunk = value[:max(0, self.remaining)]; self.remaining -= len(chunk.encode("utf-8", errors="replace")); return self.wrapped.write(chunk) if chunk else len(value)
    def flush(self): return self.wrapped.flush()
_sys.stdout = _LimitWriter(_sys.stdout, {max(1024, max_output_bytes)})
_sys.stderr = _LimitWriter(_sys.stderr, {max(1024, max_output_bytes)})
def _audit(event, args):
    if event.startswith("socket.") or event in {{"subprocess.Popen", "os.system", "os.posix_spawn", "ctypes.dlopen"}}: raise PermissionError("sandbox operation denied: " + event)
_sys.addaudithook(_audit)
_safe_import = _builtins.__import__
_allowed = {sorted(ALLOWED_IMPORTS)!r}
def _limited_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".", 1)[0] not in _allowed: raise ImportError("sandbox import denied: " + name)
    return _safe_import(name, globals, locals, fromlist, level)
_user_builtins = dict(vars(_builtins))
for _name in {sorted(FORBIDDEN_CALLS)!r}: _user_builtins.pop(_name, None)
_user_builtins["__import__"] = _limited_import
_scope = {{"__builtins__": _user_builtins, "__name__": "__sandbox__"}}
exec(compile({encoded_code}, "<submission>", "exec"), _scope, _scope)
_solution = _scope.get("solution")
if not callable(_solution): raise TypeError("必须定义 solution 函数")
_tests = _json.loads({encoded_tests!r}); _results = []; _passed = 0
for _case in _tests:
    try:
        _value = _solution(*_case.get("args", []), **_case.get("kwargs", {{}})); _expected = _case.get("expected"); _ok = _value == _expected
        _results.append({{"ok": _ok, "expected": _expected, "actual": _value}}); _passed += int(_ok)
    except Exception as _exc: _results.append({{"ok": False, "error": type(_exc).__name__ + ": " + str(_exc)}})
print(_json.dumps({{"status": "passed" if _passed == len(_tests) else "failed", "passed": _passed, "total": len(_tests), "details": _results}}, ensure_ascii=False))
'''

    def _decode_timeout_output(self, value: str | bytes | None) -> str:
        if isinstance(value, bytes): value = value.decode("utf-8", errors="replace")
        return (value or "")[: self.settings.sandbox_max_output_bytes]

    @staticmethod
    def _parse_result(stdout: str) -> dict[str, Any] | None:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines: return None
        try:
            value = json.loads(lines[-1]); return value if isinstance(value, dict) and "status" in value else None
        except json.JSONDecodeError: return None
