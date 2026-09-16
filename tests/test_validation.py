from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from servicelense.validation import SCHEMA, ReportError, load_report, validate_report
from servicelense.report import render_report, write_report


@pytest.fixture
def report():
    return json.loads(Path('examples/internal-clients/report.json').read_text())


def test_contract_and_examples(report):
    Draft202012Validator.check_schema(SCHEMA)
    data = validate_report(report)
    assert data['summary']['connections'] == 6
    assert data['summary']['configured'] == 1
    assert {c['kind'] for c in data['connections']} == {'service_api', 'database', 'messaging', 'cache', 'storage'}
    assert data['destinations'][0]['project_id'] == 'inventory'
    assert data['destinations'][1]['endpoint'] is None
    assert data['analysis']['packages'][1]['availability'] == 'unavailable'
    assert 'summary' not in report
    report['summary'] = {'connections': 9999}
    assert validate_report(report)['summary']['connections'] == 6
    load_report(Path('skills/service-lense/references/example-report.json'))


def test_evidence_matches_synthetic_source(report):
    """Fixture citations must point to the real source exercised by the skill workflow."""
    root = Path('examples/internal-clients')
    bases = {('project', p['id']): root / p['root'] for p in report['projects']}
    bases.update({('package', p['id']): root / p['root'] for p in report['analysis']['packages'] if p['root']})
    for c in report['connections']:
        for e in c['evidence']:
            lines = (bases[e['source_type'], e['source_id']] / e['file']).read_text().splitlines()
            assert lines[e['line'] - 1].strip()
    used = report['connections'][0]
    assert used['usage'] == 'used'
    assert 'inventory.reserve' in (root / 'app/main.py').read_text().splitlines()[used['evidence'][0]['line'] - 1]
    assert report['connections'][-1]['usage'] == 'configured'


@pytest.mark.parametrize('collection', ['projects', 'destinations', 'connections', 'diagnostics'])
def test_duplicate_ids(report, collection):
    report[collection].append(deepcopy(report[collection][0]))
    with pytest.raises(ReportError, match='duplicate ID'):
        validate_report(report)


@pytest.mark.parametrize('field', ['project_id', 'destination_id', 'package_id'])
def test_dangling_connection(report, field):
    report['connections'][0][field] = 'secret-value'
    with pytest.raises(ReportError) as error:
        validate_report(report)
    assert field in str(error.value)
    assert 'secret-value' not in str(error.value)


@pytest.mark.parametrize('file', ['/absolute.py', '../outside.py', 'a/../b.py', 'C:/file.py', '\\server\\share', 'a\\b.py', './file.py', 'a//b', 'x\n.py', ''])
def test_evidence_paths(report, file):
    report['connections'][0]['evidence'][0]['file'] = file
    with pytest.raises(ReportError, match=r'\$\.connections\[0\].evidence\[0\].file'):
        validate_report(report)


@pytest.mark.parametrize('line', [0, -1, True, 1.5, '1'])
def test_evidence_line(report, line):
    report['connections'][0]['evidence'][0]['line'] = line
    with pytest.raises(ReportError):
        validate_report(report)


@pytest.mark.parametrize('version', [1, 3, None, '2', True, 2.0])
def test_versions(report, version):
    report['schema_version'] = version
    with pytest.raises(ReportError, match='regenerate'):
        validate_report(report)


@pytest.mark.parametrize('field,value', [('kind','http'),('strength','resolved'),('usage','runtime'),('evidence',[]),('client',5)])
def test_allowed_values(report, field, value):
    report['connections'][0][field] = value
    with pytest.raises(ReportError):
        validate_report(report)


def test_inference_and_consistency(report):
    report['connections'][0]['strength'] = 'inferred'
    validate_report(report)
    report['connections'][0]['uncertainty_reasons'] = []
    with pytest.raises(ReportError, match='uncertainty_reasons'):
        validate_report(report)
    report['connections'][0]['strength'] = 'supported'
    report['connections'][0]['kind'] = 'database'
    with pytest.raises(ReportError, match='match destination'):
        validate_report(report)


def test_package_evidence_and_coverage(report):
    e = report['connections'][0]['evidence'][1]
    e['source_id'] = 'absent'
    with pytest.raises(ReportError, match='source_id'):
        validate_report(report)
    e['source_id'] = 'audit'
    with pytest.raises(ReportError, match='unavailable package'):
        validate_report(report)
    e['source_id'] = 'clients'
    report['analysis']['coverage']['gaps'] = []
    with pytest.raises(ReportError, match='coverage.gaps'):
        validate_report(report)
    report['analysis']['coverage']['gaps'] = ['missing source']
    report['analysis']['coverage']['status'] = 'complete'
    with pytest.raises(ReportError, match='coverage.status'):
        validate_report(report)


@pytest.mark.parametrize('content', ['{"secret":"oops', '{"x":NaN}', '{"schema_version":2,"schema_version":2}', '\ud800'])
def test_bad_json(tmp_path, content):
    path = tmp_path / 'input.json'
    path.write_bytes(content.encode('utf-8', errors='surrogatepass'))
    with pytest.raises(ReportError) as error:
        load_report(path)
    assert 'secret' not in str(error.value)


def test_errors_never_echo_extra_keys_or_values(report):
    report['secret-key-value'] = 'secret-content'
    with pytest.raises(ReportError) as error:
        validate_report(report)
    assert 'secret' not in str(error.value)
    del report['secret-key-value']
    report['summary'] = {'secret-key-value': 'secret-content'}
    with pytest.raises(ReportError) as error:
        validate_report(report)
    assert 'secret' not in str(error.value)


def test_empty_report(report):
    report.update(projects=[], destinations=[], connections=[], diagnostics=[])
    report['analysis']['packages'] = []
    assert validate_report(report)['summary']['connections'] == 0


def test_render_escapes_and_does_not_mutate(report):
    hostile = '</script><script>window.pwned=true</script>&\u2028'
    report['projects'][0]['name'] = hostile
    original = deepcopy(report)
    html = render_report(report)
    assert hostile not in html
    assert '\\u003c/script\\u003e' in html
    assert report == original


def test_output_validation_and_overwrite(report, tmp_path):
    out = tmp_path / 'report'
    invalid = deepcopy(report)
    invalid['connections'][0]['project_id'] = 'absent'
    with pytest.raises(ReportError):
        write_report(invalid, out)
    assert not out.exists()
    write_report(report, out)
    (out / 'keep.txt').write_text('keep')
    before = (out / 'report.html').read_bytes()
    with pytest.raises(ReportError, match='overwrite'):
        write_report(report, out)
    with pytest.raises(ReportError):
        write_report(invalid, out, overwrite=True)
    assert (out / 'report.html').read_bytes() == before
    write_report(report, out, overwrite=True)
    assert (out / 'keep.txt').read_text() == 'keep'
    assert load_report(out / 'dependencies.json')['summary']['connections'] == 6


def test_output_symlink_refused(report, tmp_path):
    victim = tmp_path / 'victim'
    victim.write_text('keep')
    out = tmp_path / 'report'
    out.mkdir()
    try:
        (out / 'report.html').symlink_to(victim)
    except OSError:
        pytest.skip('symlinks unavailable')
    with pytest.raises(ReportError, match='regular files'):
        write_report(report, out, overwrite=True)
    assert victim.read_text() == 'keep'
    assert not (out / 'dependencies.json').exists()
