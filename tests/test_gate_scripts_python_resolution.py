import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

QUICK_GATE = SCRIPTS_DIR / "quick_gate.ps1"
RC_GATE = SCRIPTS_DIR / "rc_gate.ps1"
VERIFY_ALL = SCRIPTS_DIR / "verify_all.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_function(content: str, func_name: str):
    m = re.search(
        rf"function {re.escape(func_name)} \{{.*?\n\}}", content, re.DOTALL
    )
    return m


class TestQuickGatePythonResolution:
    def test_contains_resolve_python_command(self):
        content = _read(QUICK_GATE)
        assert "function Resolve-PythonCommand" in content

    def test_contains_test_python_candidate(self):
        content = _read(QUICK_GATE)
        assert "function Test-PythonCandidate" in content

    def test_resolve_returns_structured_object(self):
        content = _read(QUICK_GATE)
        assert 'Exe = "python"' in content
        assert 'Exe = "py"' in content
        assert 'Args = @("-3")' in content

    def test_no_bare_py_minus_3_invocation(self):
        content = _read(QUICK_GATE)
        assert not re.search(r'&\s*"py -3"', content)
        assert not re.search(r'&\s*"py\-3"', content)

    def test_no_direct_python_invocation_outside_helpers(self):
        content = _read(QUICK_GATE)
        resolve_block = _extract_function(content, "Resolve-PythonCommand")
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        removed = ""
        if resolve_block:
            removed += resolve_block.group(0)
        if candidate_block:
            removed += candidate_block.group(0)
        content_without_helpers = content
        for block in [resolve_block, candidate_block]:
            if block:
                content_without_helpers = content_without_helpers.replace(
                    block.group(0), ""
                )
        bare_python_calls = re.findall(r'&\s+python\s+', content_without_helpers)
        assert len(bare_python_calls) == 0, (
            f"Found bare '& python' calls outside helpers in quick_gate.ps1: {bare_python_calls}"
        )

    def test_python_calls_use_exe_args_pattern(self):
        content = _read(QUICK_GATE)
        assert "$Python.Exe" in content
        assert "$Python.Args" in content
        assert "Invoke-PythonSafeCommand" in content

    def test_python_not_found_error_message(self):
        content = _read(QUICK_GATE)
        assert "Python was not found. Install Python or add it to PATH." in content

    def test_has_sensitive_patterns(self):
        content = _read(QUICK_GATE)
        assert "$SENSITIVE_PATTERNS" in content
        assert "API_KEY" in content
        assert "DATABASE_URL" in content

    def test_invoke_python_safe_command_exists(self):
        content = _read(QUICK_GATE)
        assert "function Invoke-PythonSafeCommand" in content

    def test_candidate_uses_get_command(self):
        content = _read(QUICK_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in quick_gate.ps1"
        block_text = candidate_block.group(0)
        assert "Get-Command" in block_text

    def test_candidate_uses_dynamic_exe_args(self):
        content = _read(QUICK_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in quick_gate.ps1"
        block_text = candidate_block.group(0)
        assert "& $Exe" in block_text
        assert "@($Args + @(" in block_text

    def test_candidate_checks_exit_code(self):
        content = _read(QUICK_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in quick_gate.ps1"
        block_text = candidate_block.group(0)
        assert "$LASTEXITCODE" in block_text
        assert "-eq 0" in block_text

    def test_candidate_catches_exceptions(self):
        content = _read(QUICK_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in quick_gate.ps1"
        block_text = candidate_block.group(0)
        assert "catch" in block_text
        assert "return $false" in block_text

    def test_candidate_returns_false_on_missing_command(self):
        content = _read(QUICK_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in quick_gate.ps1"
        block_text = candidate_block.group(0)
        assert "if (-not $cmd) { return $false }" in block_text

    def test_resolve_calls_candidate_for_python_then_py(self):
        content = _read(QUICK_GATE)
        resolve_block = _extract_function(content, "Resolve-PythonCommand")
        assert resolve_block, "Resolve-PythonCommand not found in quick_gate.ps1"
        block_text = resolve_block.group(0)
        assert 'Test-PythonCandidate -Exe "python" -Args @()' in block_text
        assert 'Test-PythonCandidate -Exe "py" -Args @("-3")' in block_text
        python_pos = block_text.index("python")
        py_pos = block_text.index('"py"')
        assert python_pos < py_pos


class TestRCGatePythonResolution:
    def test_contains_resolve_python_command(self):
        content = _read(RC_GATE)
        assert "function Resolve-PythonCommand" in content

    def test_contains_test_python_candidate(self):
        content = _read(RC_GATE)
        assert "function Test-PythonCandidate" in content

    def test_resolve_returns_structured_object(self):
        content = _read(RC_GATE)
        assert 'Exe = "python"' in content
        assert 'Exe = "py"' in content
        assert 'Args = @("-3")' in content

    def test_no_bare_py_minus_3_invocation(self):
        content = _read(RC_GATE)
        assert not re.search(r'&\s*"py -3"', content)
        assert not re.search(r'&\s*"py\-3"', content)

    def test_no_direct_python_invocation_outside_helpers(self):
        content = _read(RC_GATE)
        resolve_block = _extract_function(content, "Resolve-PythonCommand")
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        content_without_helpers = content
        for block in [resolve_block, candidate_block]:
            if block:
                content_without_helpers = content_without_helpers.replace(
                    block.group(0), ""
                )
        bare_python_calls = re.findall(r'&\s+python\s+', content_without_helpers)
        assert len(bare_python_calls) == 0, (
            f"Found bare '& python' calls outside helpers in rc_gate.ps1: {bare_python_calls}"
        )

    def test_python_calls_use_exe_args_pattern(self):
        content = _read(RC_GATE)
        assert "$Python.Exe" in content
        assert "$Python.Args" in content
        assert "Invoke-PythonSafeCommand" in content

    def test_python_not_found_error_message(self):
        content = _read(RC_GATE)
        assert "Python was not found. Install Python or add it to PATH." in content

    def test_has_sensitive_patterns(self):
        content = _read(RC_GATE)
        assert "$SENSITIVE_PATTERNS" in content

    def test_invoke_python_safe_command_exists(self):
        content = _read(RC_GATE)
        assert "function Invoke-PythonSafeCommand" in content

    def test_rejects_absolute_manifest_path(self):
        content = _read(RC_GATE)
        assert "ManifestPath must be project-relative" in content
        assert "IsPathRooted" in content

    def test_no_confirm_restore(self):
        content = _read(RC_GATE)
        assert "-ConfirmRestore" not in content

    def test_has_dry_run_restore(self):
        content = _read(RC_GATE)
        assert "-DryRun" in content

    def test_candidate_uses_get_command(self):
        content = _read(RC_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in rc_gate.ps1"
        block_text = candidate_block.group(0)
        assert "Get-Command" in block_text

    def test_candidate_uses_dynamic_exe_args(self):
        content = _read(RC_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in rc_gate.ps1"
        block_text = candidate_block.group(0)
        assert "& $Exe" in block_text
        assert "@($Args + @(" in block_text

    def test_candidate_checks_exit_code(self):
        content = _read(RC_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in rc_gate.ps1"
        block_text = candidate_block.group(0)
        assert "$LASTEXITCODE" in block_text
        assert "-eq 0" in block_text

    def test_candidate_catches_exceptions(self):
        content = _read(RC_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in rc_gate.ps1"
        block_text = candidate_block.group(0)
        assert "catch" in block_text
        assert "return $false" in block_text

    def test_candidate_returns_false_on_missing_command(self):
        content = _read(RC_GATE)
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        assert candidate_block, "Test-PythonCandidate not found in rc_gate.ps1"
        block_text = candidate_block.group(0)
        assert "if (-not $cmd) { return $false }" in block_text

    def test_resolve_calls_candidate_for_python_then_py(self):
        content = _read(RC_GATE)
        resolve_block = _extract_function(content, "Resolve-PythonCommand")
        assert resolve_block, "Resolve-PythonCommand not found in rc_gate.ps1"
        block_text = resolve_block.group(0)
        assert 'Test-PythonCandidate -Exe "python" -Args @()' in block_text
        assert 'Test-PythonCandidate -Exe "py" -Args @("-3")' in block_text
        python_pos = block_text.index("python")
        py_pos = block_text.index('"py"')
        assert python_pos < py_pos


class TestConsistencyWithVerifyAll:
    def test_resolve_python_command_matches_verify_all(self):
        va = _read(VERIFY_ALL)
        qg = _read(QUICK_GATE)
        rc = _read(RC_GATE)

        va_resolve = _extract_function(va, "Resolve-PythonCommand")
        qg_resolve = _extract_function(qg, "Resolve-PythonCommand")
        rc_resolve = _extract_function(rc, "Resolve-PythonCommand")

        assert va_resolve, "Resolve-PythonCommand not found in verify_all.ps1"
        assert qg_resolve, "Resolve-PythonCommand not found in quick_gate.ps1"
        assert rc_resolve, "Resolve-PythonCommand not found in rc_gate.ps1"

        assert qg_resolve.group(0) == va_resolve.group(0), (
            "quick_gate.ps1 Resolve-PythonCommand differs from verify_all.ps1"
        )
        assert rc_resolve.group(0) == va_resolve.group(0), (
            "rc_gate.ps1 Resolve-PythonCommand differs from verify_all.ps1"
        )

    def test_test_python_candidate_matches_verify_all(self):
        va = _read(VERIFY_ALL)
        qg = _read(QUICK_GATE)
        rc = _read(RC_GATE)

        va_candidate = _extract_function(va, "Test-PythonCandidate")
        qg_candidate = _extract_function(qg, "Test-PythonCandidate")
        rc_candidate = _extract_function(rc, "Test-PythonCandidate")

        assert va_candidate, "Test-PythonCandidate not found in verify_all.ps1"
        assert qg_candidate, "Test-PythonCandidate not found in quick_gate.ps1"
        assert rc_candidate, "Test-PythonCandidate not found in rc_gate.ps1"

        assert qg_candidate.group(0) == va_candidate.group(0), (
            "quick_gate.ps1 Test-PythonCandidate differs from verify_all.ps1"
        )
        assert rc_candidate.group(0) == va_candidate.group(0), (
            "rc_gate.ps1 Test-PythonCandidate differs from verify_all.ps1"
        )

    def test_invoke_python_safe_command_matches_verify_all(self):
        va = _read(VERIFY_ALL)
        qg = _read(QUICK_GATE)
        rc = _read(RC_GATE)

        va_cmd = _extract_function(va, "Invoke-PythonSafeCommand")
        qg_cmd = _extract_function(qg, "Invoke-PythonSafeCommand")
        rc_cmd = _extract_function(rc, "Invoke-PythonSafeCommand")

        assert va_cmd, "Invoke-PythonSafeCommand not found in verify_all.ps1"
        assert qg_cmd, "Invoke-PythonSafeCommand not found in quick_gate.ps1"
        assert rc_cmd, "Invoke-PythonSafeCommand not found in rc_gate.ps1"

        assert qg_cmd.group(0) == va_cmd.group(0), (
            "quick_gate.ps1 Invoke-PythonSafeCommand differs from verify_all.ps1"
        )
        assert rc_cmd.group(0) == va_cmd.group(0), (
            "rc_gate.ps1 Invoke-PythonSafeCommand differs from verify_all.ps1"
        )

    def test_sensitive_patterns_match_verify_all(self):
        va = _read(VERIFY_ALL)
        qg = _read(QUICK_GATE)
        rc = _read(RC_GATE)

        va_patterns = re.search(
            r"\$SENSITIVE_PATTERNS = @\([^)]+\)", va, re.DOTALL
        )
        qg_patterns = re.search(
            r"\$SENSITIVE_PATTERNS = @\([^)]+\)", qg, re.DOTALL
        )
        rc_patterns = re.search(
            r"\$SENSITIVE_PATTERNS = @\([^)]+\)", rc, re.DOTALL
        )

        assert va_patterns, "$SENSITIVE_PATTERNS not found in verify_all.ps1"
        assert qg_patterns, "$SENSITIVE_PATTERNS not found in quick_gate.ps1"
        assert rc_patterns, "$SENSITIVE_PATTERNS not found in rc_gate.ps1"

        assert qg_patterns.group(0) == va_patterns.group(0), (
            "quick_gate.ps1 $SENSITIVE_PATTERNS differs from verify_all.ps1"
        )
        assert rc_patterns.group(0) == va_patterns.group(0), (
            "rc_gate.ps1 $SENSITIVE_PATTERNS differs from verify_all.ps1"
        )


class TestNoUnsafePythonPatterns:
    @staticmethod
    def _check_no_unsafe_python_call(content: str, filename: str):
        resolve_block = _extract_function(content, "Resolve-PythonCommand")
        candidate_block = _extract_function(content, "Test-PythonCandidate")
        content_without_helpers = content
        for block in [resolve_block, candidate_block]:
            if block:
                content_without_helpers = content_without_helpers.replace(
                    block.group(0), ""
                )
        for line_num, line in enumerate(content_without_helpers.splitlines(), 1):
            stripped = line.strip()
            if "docker compose exec" in stripped:
                continue
            if "docker" in stripped and "python" in stripped:
                continue
            if re.search(r'&\s+python\s+scripts[\\/]', stripped):
                raise AssertionError(
                    f"Found unsafe '& python scripts/...' in {filename} line {line_num}: {stripped}"
                )
            if re.search(r'&\s+python\s+-m\s', stripped):
                raise AssertionError(
                    f"Found unsafe '& python -m ...' in {filename} line {line_num}: {stripped}"
                )

    def test_quick_gate_no_unsafe_python(self):
        self._check_no_unsafe_python_call(_read(QUICK_GATE), "quick_gate.ps1")

    def test_rc_gate_no_unsafe_python(self):
        self._check_no_unsafe_python_call(_read(RC_GATE), "rc_gate.ps1")

    def test_quick_gate_python_args_splat(self):
        content = _read(QUICK_GATE)
        assert "@allArgs" in content
        assert "$Python.Args + $PythonArgs" in content

    def test_rc_gate_python_args_splat(self):
        content = _read(RC_GATE)
        assert "@allArgs" in content
        assert "$Python.Args + $PythonArgs" in content
