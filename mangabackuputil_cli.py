import argparse
import os
import sys

# Ensure current dir and proto dir are in path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
proto_dir = os.path.join(current_dir, 'proto')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

from manga_converter_engine import convert_any, TARGET_FORMATS

def run_cli():
    if sys.platform == 'win32':
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
                sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog='mangabackuputil', description='Manga Backup Converter')
    subparsers = parser.add_subparsers(dest='command', help='Sub-commands')

    available_fmts = list(TARGET_FORMATS.keys())
    convert_parser = subparsers.add_parser('convert', help='Convert a backup to another format')
    convert_parser.add_argument('-b', '--backup', required=True, help='Path to input backup file')
    convert_parser.add_argument(
        '-f', '--output-format',
        required=True,
        choices=available_fmts + ['tachibk', 'tmb'],
        help=f"Target format ({', '.join(available_fmts)})"
    )
    convert_parser.add_argument('-i', '--input-format', help='Input format override')
    convert_parser.add_argument('-o', '--output', help='Output file path')
    convert_parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    gui_parser = subparsers.add_parser('gui', help='Launch Graphical Interface')
    gui_parser.add_argument('file', nargs='?', help='Optional file to load')

    args = parser.parse_args()

    if args.command == 'convert':
        fmt = args.output_format.lower()
        if fmt == 'tachibk':
            fmt = 'mihon'
        elif fmt == 'tmb':
            fmt = 'tachimanga'

        input_file = args.backup
        if not os.path.exists(input_file):
            print(f"Error: Input file '{input_file}' not found.")
            sys.exit(1)

        ext = TARGET_FORMATS[fmt][1]
        output_file = args.output or f"{os.path.splitext(input_file)[0]}_converted{ext}"
        convert_any(input_file, output_file, fmt, log_cb=print)
    elif args.command == 'gui':
        from manga_backup_converter_gui import launch_gui
        launch_gui(args.file)
    else:
        parser.print_help()

def main():
    # If launched with no arguments, or launched by dragging a file onto the EXE icon
    if len(sys.argv) == 1:
        from manga_backup_converter_gui import launch_gui
        launch_gui()
    elif len(sys.argv) == 2 and not sys.argv[1].startswith('-') and sys.argv[1] not in ('convert', 'merge', 'gui', 'help'):
        # Dragged and dropped a file onto the executable icon
        from manga_backup_converter_gui import launch_gui
        launch_gui(sys.argv[1])
    else:
        run_cli()

if __name__ == '__main__':
    main()
