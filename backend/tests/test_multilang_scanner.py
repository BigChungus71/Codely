import os

import pytest

from backend.app.analyzers.semgrep_adapter import ROOT, scan_repository


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1', reason='Requires native Semgrep')
def test_native_multilang_paths_lines_and_coverage():
    result = scan_repository(str(ROOT / 'fixtures/multilang'))
    assert result.status == 'complete', result.diagnostics
    assert result.coverage['scanned_files'] == 7
    assert result.coverage['analyzed_languages'] == ['java', 'javascript', 'typescript']
    assert {(item['rule_id'], item['file'], item['start_line'], tuple(item['cwe']))
            for item in result.findings} == {
        ('codely.java.sql-concatenation', 'unsafe/ReviewJava.java', 4, ('CWE-89',)),
        ('codely.java.weak-digest', 'unsafe/ReviewJava.java', 5, ('CWE-327',)),
        ('codely.web.raw-html', 'unsafe/review.ts', 3, ('CWE-79',)),
        ('codely.web.tls-disabled', 'unsafe/review.ts', 5, ('CWE-295',)),
    }


def test_unsupported_sources_do_not_report_success(tmp_path):
    (tmp_path / 'sample.go').write_text('package sample\n', encoding='utf-8')
    result = scan_repository(str(tmp_path))
    assert result.status == 'error'
    assert result.coverage['status'] == 'unsupported'
    assert result.coverage['unsupported_languages'] == ['go']
    assert result.coverage['scanned_files'] == 0
