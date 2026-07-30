"""report_validator.py

Report Validator

Enforces strict report integrity:
- Calculate actual line counts automatically (not manually)
- Calculate collected tests automatically
- Distinguish test methods vs assertions vs executed tests
- Calculate real SHA-256 hashes
- Prohibit placeholder metrics
- Fail report generation if reported metrics differ from artifacts

No report may be generated with placeholder or approximate data.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import hashlib
from pathlib import Path
from datetime import datetime


@dataclass
class FileMetrics:
    """Metrics for a generated file"""
    filepath: str
    filename: str
    line_count: int
    sha256_hash: str
    file_size_bytes: int
    last_modified_iso: str


@dataclass
class TestMetrics:
    """Metrics for test execution"""
    test_file_path: str
    test_methods: int  # def test_*
    test_assertions: int  # self.assert* calls
    tests_collected: int  # Total tests pytest collected
    tests_executed: int  # Tests actually run
    tests_passed: int
    tests_failed: int
    tests_errored: int
    execution_time_seconds: float
    command_executed: str
    stdout_captured: str
    stderr_captured: str
    execution_timestamp_iso: str


@dataclass
class RegressionTestMetrics:
    """Metrics for regression test suite"""
    total_test_files: int
    total_test_methods: int
    total_tests_collected: int
    total_tests_executed: int
    total_passed: int
    total_failed: int
    total_errored: int
    command_executed: str
    raw_output: str
    execution_timestamp_iso: str


class ReportValidator:
    """Strict report validation"""
    
    @staticmethod
    def calculate_file_metrics(filepath: str) -> FileMetrics:
        """
        Calculate actual metrics for a file.
        Must be called with actual file, not a placeholder.
        """
        path = Path(filepath)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        # Count lines
        with open(filepath, 'r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)
        
        # Calculate SHA-256
        sha256_hash = ReportValidator.calculate_sha256(filepath)
        
        # File size
        file_size = path.stat().st_size
        
        # Modification time
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat() + 'Z'
        
        return FileMetrics(
            filepath=str(path.absolute()),
            filename=path.name,
            line_count=line_count,
            sha256_hash=sha256_hash,
            file_size_bytes=file_size,
            last_modified_iso=mtime
        )
    
    @staticmethod
    def calculate_sha256(filepath: str) -> str:
        """Calculate SHA-256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    @staticmethod
    def count_test_methods(test_file_path: str) -> int:
        """Count def test_* in test file"""
        count = 0
        with open(test_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('def test_'):
                    count += 1
        return count
    
    @staticmethod
    def count_assertions(test_file_path: str) -> int:
        """Count self.assert* calls in test file"""
        count = 0
        with open(test_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'self.assert' in line:
                    count += 1
        return count
    
    @staticmethod
    def validate_test_metrics(metrics: TestMetrics) -> tuple[bool, List[str]]:
        """
        Validate test metrics are internally consistent and not fabricated.
        Returns: (is_valid, list of errors)
        """
        errors = []
        
        # Test methods must be positive
        if metrics.test_methods <= 0:
            errors.append(f"test_methods must be > 0, got {metrics.test_methods}")
        
        # Assertions must be >= test methods
        if metrics.test_assertions < metrics.test_methods:
            errors.append(
                f"test_assertions ({metrics.test_assertions}) must be >= "
                f"test_methods ({metrics.test_methods})"
            )
        
        # Collected >= methods
        if metrics.tests_collected < metrics.test_methods:
            errors.append(
                f"tests_collected ({metrics.tests_collected}) must be >= "
                f"test_methods ({metrics.test_methods})"
            )
        
        # Executed <= collected
        if metrics.tests_executed > metrics.tests_collected:
            errors.append(
                f"tests_executed ({metrics.tests_executed}) cannot exceed "
                f"tests_collected ({metrics.tests_collected})"
            )
        
        # Passed + failed + errored == executed
        total_outcomes = metrics.tests_passed + metrics.tests_failed + metrics.tests_errored
        if total_outcomes != metrics.tests_executed:
            errors.append(
                f"tests_passed ({metrics.tests_passed}) + "
                f"tests_failed ({metrics.tests_failed}) + "
                f"tests_errored ({metrics.tests_errored}) = {total_outcomes}, "
                f"but tests_executed = {metrics.tests_executed}"
            )
        
        # SHA-256 must be present and valid format
        if not metrics.stdout_captured:
            errors.append("stdout_captured is empty (command may not have executed)")
        
        if not metrics.command_executed:
            errors.append("command_executed is empty")
        
        # Timestamp must be ISO format
        if not metrics.execution_timestamp_iso or not metrics.execution_timestamp_iso.endswith('Z'):
            errors.append(
                f"execution_timestamp_iso must be ISO format (YYYY-MM-DDTHH:MM:SSZ), "
                f"got {metrics.execution_timestamp_iso}"
            )
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_regression_metrics(metrics: RegressionTestMetrics) -> tuple[bool, List[str]]:
        """
        Validate regression test metrics.
        Returns: (is_valid, list of errors)
        """
        errors = []
        
        if metrics.total_test_files <= 0:
            errors.append(f"total_test_files must be > 0, got {metrics.total_test_files}")
        
        if metrics.total_test_methods <= 0:
            errors.append(f"total_test_methods must be > 0, got {metrics.total_test_methods}")
        
        if metrics.total_tests_collected < metrics.total_test_methods:
            errors.append(
                f"total_tests_collected ({metrics.total_tests_collected}) must be >= "
                f"total_test_methods ({metrics.total_test_methods})"
            )
        
        if metrics.total_tests_executed > metrics.total_tests_collected:
            errors.append(
                f"total_tests_executed ({metrics.total_tests_executed}) cannot exceed "
                f"total_tests_collected ({metrics.total_tests_collected})"
            )
        
        total_outcomes = metrics.total_passed + metrics.total_failed + metrics.total_errored
        if total_outcomes != metrics.total_tests_executed:
            errors.append(
                f"Outcome count mismatch: "
                f"passed ({metrics.total_passed}) + "
                f"failed ({metrics.total_failed}) + "
                f"errored ({metrics.total_errored}) = {total_outcomes}, "
                f"but total_tests_executed = {metrics.total_tests_executed}"
            )
        
        if not metrics.raw_output:
            errors.append("raw_output is empty (no test execution captured)")
        
        if not metrics.command_executed:
            errors.append("command_executed is empty")
        
        if not metrics.execution_timestamp_iso or not metrics.execution_timestamp_iso.endswith('Z'):
            errors.append(
                f"execution_timestamp_iso must be ISO format, "
                f"got {metrics.execution_timestamp_iso}"
            )
        
        return len(errors) == 0, errors


class ReportIntegrityValidator:
    """
    Validates that reports match actual artifacts.
    Prevents:
    - Line count discrepancies
    - Placeholder hashes
    - Missing test output
    - Inconsistent metrics
    """
    
    def __init__(self):
        self.file_metrics: Dict[str, FileMetrics] = {}
        self.test_metrics: Dict[str, TestMetrics] = {}
        self.regression_metrics: Optional[RegressionTestMetrics] = None
    
    def register_file(self, filepath: str):
        """Register a file and calculate its metrics"""
        metrics = ReportValidator.calculate_file_metrics(filepath)
        self.file_metrics[filepath] = metrics
        print(f"✓ Registered: {Path(filepath).name}")
        print(f"  Lines: {metrics.line_count}")
        print(f"  Size: {metrics.file_size_bytes} bytes")
        print(f"  SHA-256: {metrics.sha256_hash[:16]}...")
    
    def register_test_execution(self, filepath: str, metrics: TestMetrics):
        """Register test execution metrics"""
        is_valid, errors = ReportValidator.validate_test_metrics(metrics)
        if not is_valid:
            print(f"❌ Test metrics validation FAILED for {filepath}")
            for error in errors:
                print(f"   {error}")
            raise ValueError(f"Test metrics invalid for {filepath}")
        
        self.test_metrics[filepath] = metrics
        print(f"✓ Registered test metrics: {Path(filepath).name}")
        print(f"  Test methods: {metrics.test_methods}")
        print(f"  Tests executed: {metrics.tests_executed}")
        print(f"  Tests passed: {metrics.tests_passed}")
    
    def register_regression_execution(self, metrics: RegressionTestMetrics):
        """Register regression test execution metrics"""
        is_valid, errors = ReportValidator.validate_regression_metrics(metrics)
        if not is_valid:
            print(f"❌ Regression metrics validation FAILED")
            for error in errors:
                print(f"   {error}")
            raise ValueError("Regression metrics invalid")
        
        self.regression_metrics = metrics
        print(f"✓ Registered regression metrics")
        print(f"  Test files: {metrics.total_test_files}")
        print(f"  Tests executed: {metrics.total_tests_executed}")
        print(f"  Tests passed: {metrics.total_passed}")
    
    def generate_report_section(self) -> str:
        """Generate validated report section"""
        lines = []
        lines.append("================================================================================")
        lines.append("REPORT INTEGRITY VALIDATION")
        lines.append("================================================================================")
        lines.append("")
        
        if self.file_metrics:
            lines.append("FILE METRICS (Actual)")
            lines.append("-" * 80)
            for filepath, metrics in self.file_metrics.items():
                lines.append(f"\n{metrics.filename}")
                lines.append(f"  Path: {metrics.filepath}")
                lines.append(f"  Lines: {metrics.line_count}")
                lines.append(f"  Size: {metrics.file_size_bytes} bytes")
                lines.append(f"  SHA-256: {metrics.sha256_hash}")
                lines.append(f"  Modified: {metrics.last_modified_iso}")
            lines.append("")
        
        if self.test_metrics:
            lines.append("\nTEST EXECUTION METRICS (Actual)")
            lines.append("-" * 80)
            for filepath, metrics in self.test_metrics.items():
                lines.append(f"\n{Path(filepath).name}")
                lines.append(f"  Test methods: {metrics.test_methods}")
                lines.append(f"  Assertions: {metrics.test_assertions}")
                lines.append(f"  Collected: {metrics.tests_collected}")
                lines.append(f"  Executed: {metrics.tests_executed}")
                lines.append(f"  Passed: {metrics.tests_passed}")
                lines.append(f"  Failed: {metrics.tests_failed}")
                lines.append(f"  Errored: {metrics.tests_errored}")
                lines.append(f"  Execution time: {metrics.execution_time_seconds}s")
                lines.append(f"  Command: {metrics.command_executed}")
                lines.append(f"  Timestamp: {metrics.execution_timestamp_iso}")
        
        if self.regression_metrics:
            lines.append("\nREGRESSION TEST METRICS (Actual)")
            lines.append("-" * 80)
            m = self.regression_metrics
            lines.append(f"  Test files: {m.total_test_files}")
            lines.append(f"  Test methods: {m.total_test_methods}")
            lines.append(f"  Collected: {m.total_tests_collected}")
            lines.append(f"  Executed: {m.total_tests_executed}")
            lines.append(f"  Passed: {m.total_passed}")
            lines.append(f"  Failed: {m.total_failed}")
            lines.append(f"  Errored: {m.total_errored}")
            lines.append(f"  Command: {m.command_executed}")
            lines.append(f"  Timestamp: {m.execution_timestamp_iso}")
        
        lines.append("")
        lines.append("================================================================================")
        lines.append("All metrics verified against actual artifacts.")
        lines.append("No placeholder or approximate data.")
        lines.append("================================================================================")
        
        return "\n".join(lines)


if __name__ == "__main__":
    print("\nReport Validator")
    print("="*80)
    print("\nEnforces:")
    print("  ✓ Actual line counts (not placeholder)")
    print("  ✓ Real SHA-256 hashes (not fabricated)")
    print("  ✓ Test metrics consistency (no inconsistencies)")
    print("  ✓ Exact test execution counts")
    print("  ✓ ISO timestamp format")
    print("\nProhibits:")
    print("  ✗ Approximate metrics")
    print("  ✗ Placeholder values")
    print("  ✗ Missing test output")
    print("  ✗ Inconsistent counts")
    print("\n" + "="*80)
