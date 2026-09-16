"""Versioned report validation. Diagnostics never include supplied field values."""
from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from jsonschema import Draft202012Validator, FormatChecker


class ReportError(ValueError):
    pass


SCHEMA = json.loads(files('servicelense').joinpath('assets/report.schema.json').read_text(encoding='utf-8'))
FORMATS = FormatChecker()


@FORMATS.checks('relative-source-path')
def relative_source_path(value):
    if not isinstance(value, str):
        return True  # Type validation handles this separately.
    return bool(value.strip()) and not (
        PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
        or '\\' in value or any(part in ('', '.', '..') for part in value.split('/'))
        or any(ord(char) < 32 for char in value)
    )


VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMATS)
# Only schema-owned property names may appear in error paths.
KNOWN_FIELDS = set(SCHEMA['properties'])
for definition in SCHEMA['$defs'].values():
    KNOWN_FIELDS.update(definition.get('properties', {}))
KNOWN_FIELDS.update(('status', 'inspected', 'excluded', 'gaps'))


def field_path(parts):
    return '$' + ''.join(f'[{p}]' if isinstance(p, int) else '.' + (p if p in KNOWN_FIELDS else '<field>') for p in parts)


def fail(path, message):
    raise ReportError(f'{path}: {message}')


def validate_report(data: object) -> dict:
    if not isinstance(data, dict):
        fail('$', 'expected a report object')
    version = data.get('schema_version')
    if type(version) is not int or version != 2:
        fail('$.schema_version', 'unsupported version; regenerate a version-2 report with the service-lense skill (version-1 reports cannot be imported)')
    errors = list(VALIDATOR.iter_errors(data))
    if errors:
        messages = {'required': 'required field missing', 'additionalProperties': 'unexpected field',
                    'type': 'incorrect field type', 'enum': 'value is not an allowed option',
                    'minLength': 'expected nonempty text', 'minimum': 'must be a positive line number',
                    'minItems': 'at least one evidence location is required', 'format': 'expected a relative source file path without traversal'}
        error = errors[0]
        path = list(error.absolute_path)
        if error.validator == 'required':
            path.append(next(key for key in error.validator_value if key not in error.instance))
        fail(field_path(path), messages.get(error.validator, 'invalid field'))
    indexes = {}
    for name, records in [('projects', data['projects']), ('destinations', data['destinations']),
                          ('connections', data['connections']), ('diagnostics', data['diagnostics']),
                          ('packages', data['analysis']['packages'])]:
        indexes[name] = {}
        for i, record in enumerate(records):
            path = '$.analysis.packages' if name == 'packages' else '$.' + name
            if record['id'] in indexes[name]:
                fail(f'{path}[{i}].id', 'duplicate ID')
            indexes[name][record['id']] = record

    def reference(value, collection, path):
        if value is not None and value not in indexes[collection]:
            fail(path, 'reference does not identify an existing record')

    def evidence(items, path):
        for i, item in enumerate(items):
            collection = 'projects' if item['source_type'] == 'project' else 'packages'
            reference(item['source_id'], collection, f'{path}[{i}].source_id')
            if collection == 'packages' and indexes[collection][item['source_id']]['availability'] != 'available':
                fail(f'{path}[{i}].source_id', 'cannot cite unavailable package source')

    for i, dest in enumerate(data['destinations']):
        reference(dest['project_id'], 'projects', f'$.destinations[{i}].project_id')
    for i, conn in enumerate(data['connections']):
        path = f'$.connections[{i}]'
        for key, collection in [('project_id', 'projects'), ('destination_id', 'destinations'), ('package_id', 'packages')]:
            reference(conn[key], collection, path + '.' + key)
        if conn['kind'] != indexes['destinations'][conn['destination_id']]['kind']:
            fail(path + '.kind', 'must match destination kind')
        if conn['strength'] != 'supported' and not conn['uncertainty_reasons']:
            fail(path + '.uncertainty_reasons', 'explain inferred or unknown evidence strength')
        evidence(conn['evidence'], path + '.evidence')
    for i, diagnostic in enumerate(data['diagnostics']):
        reference(diagnostic['project_id'], 'projects', f'$.diagnostics[{i}].project_id')
        evidence(diagnostic['evidence'], f'$.diagnostics[{i}].evidence')
    coverage = data['analysis']['coverage']
    for i, package in enumerate(data['analysis']['packages']):
        if package['availability'] == 'available' and package['root'] is None:
            fail(f'$.analysis.packages[{i}].root', 'available source needs a root')
    if any(p['availability'] == 'unavailable' for p in data['analysis']['packages']) and not coverage['gaps']:
        fail('$.analysis.coverage.gaps', 'record unavailable package source as a coverage gap')
    if coverage['gaps'] and coverage['status'] != 'partial':
        fail('$.analysis.coverage.status', 'coverage with gaps must be partial')
    result = deepcopy(data)
    result['summary'] = {key: len(data[key]) for key in ('projects', 'destinations', 'connections', 'diagnostics')}
    for field, values in [('strength', ('supported', 'inferred', 'unknown')), ('usage', ('used', 'configured'))]:
        result['summary'].update({v: sum(c[field] == v for c in data['connections']) for v in values})
    return result


def load_report(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail('$', 'duplicate JSON object field')
            result[key] = value
        return result

    def invalid_constant(_):
        fail('$', 'non-finite numbers are not valid JSON')

    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        fail('$', 'malformed JSON or invalid UTF-8')
    return validate_report(data)
