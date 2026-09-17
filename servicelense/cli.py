from __future__ import annotations

import argparse
from pathlib import Path
import sys
import webbrowser

from . import __version__
from .report import existing_output, write_report
from .validation import ReportError, load_report

GUIDANCE = '''Install the service-lense skill in your personal ~/.agents/skills directory.
Open a separate output folder in Codex and ask:
"Use $service-lense to analyze /path/to/project and save the report here. Leave the project untouched."
Codex reads local source and writes a version-2 JSON report outside the project. Service Lense
validates the format and renders it offline; no additional LLM login is used.
See README.md for installation and the skill's references/report-format.md
for the contract. Validation does not establish that an inference is correct.'''
MIGRATION = 'The scan command was removed. Regenerate JSON using the service-lense Codex skill, then use validate or render. Saved profiles are no longer read; existing HTML reports remain usable.'


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog='servicelense', description='Validate and explore source dependency reports offline.')
    result.add_argument('--version', action='version', version=f'Service Lense {__version__}')
    subcommands = result.add_subparsers(dest='command')
    validate = subcommands.add_parser('validate', help='Validate a version-2 JSON report')
    validate.add_argument('report', type=Path)
    render = subcommands.add_parser('render', help='Generate a self-contained HTML report')
    render.add_argument('report', type=Path)
    render.add_argument('--out', type=Path, required=True)
    render.add_argument('--no-open', action='store_true')
    render.add_argument('--overwrite', action='store_true', help='Replace existing report output files')
    return result


def render(data: dict, out: Path, *, no_open: bool, overwrite: bool = False) -> int:
    write_report(data, out, overwrite=overwrite)
    print(f"{data['summary']['connections']} connections | {data['summary']['destinations']} destinations")
    print(f"Report: {(out / 'report.html').resolve()}")
    print(f"JSON:   {(out / 'dependencies.json').resolve()}")
    if not no_open:
        try:
            opened = webbrowser.open((out / 'report.html').resolve().as_uri(), new=2)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            print('Could not open the browser; open the report path above manually.', file=sys.stderr)
    return 0


def interactive() -> int:
    print('Service Lense\n1. Render a JSON report\n2. Validate a JSON report\n3. Skill usage guidance\n4. Exit')
    while True:
        choice = input('Choose [1]: ').strip() or '1'
        if choice in ('1', '2', '3', '4'):
            break
        print('Choose 1, 2, 3, or 4.')
    if choice == '4':
        return 0
    if choice == '3':
        print(GUIDANCE)
        return 0
    path = input('Report JSON path: ').strip()
    if not path:
        raise ReportError('A report JSON path is required')
    data = load_report(Path(path).expanduser())
    if choice == '2':
        print('Valid version-2 report. Source inferences have not been verified.')
        return 0
    out = Path(input('Output directory [reports]: ').strip() or 'reports').expanduser()
    overwrite = False
    if existing_output(out):
        overwrite = input('Replace report.html and dependencies.json in this directory? [y/N]: ').strip().lower() in ('y', 'yes')
        if not overwrite:
            print('Rendering cancelled; existing output preserved.')
            return 0
    no_open = input('Open report in browser? [Y/n]: ').strip().lower() in ('n', 'no')
    return render(data, out, no_open=no_open, overwrite=overwrite)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'scan':
        print('servicelense: ' + MIGRATION, file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    try:
        if args.command is None:
            if not sys.stdin.isatty():
                raise ReportError('Interactive mode needs a terminal. Use validate <report.json> or render <report.json> --out <directory> --no-open.\n' + GUIDANCE)
            return interactive()
        data = load_report(args.report)
        if args.command == 'validate':
            print('Valid version-2 report. Source inferences have not been verified.')
            return 0
        return render(data, args.out, no_open=args.no_open, overwrite=args.overwrite)
    except ReportError as error:
        print(f'servicelense: {error}', file=sys.stderr)
        return 2
    except OSError:
        print('servicelense: Could not read or write the requested file; check paths and permissions.', file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
