import argparse

from moluni import analyze_db

def main():
    parser = argparse.ArgumentParser(description='Analyze materials database')
    parser.add_argument('--list-properties',
                        action='store_true',
                        help='List all available properties')
    parser.add_argument('--status',
                        action='store_true',
                        help='Show calculation status summary')
    parser.add_argument('--analyze',
                        type=str,
                        metavar='PROPERTY',
                        help='Analyze a specific property')
    parser.add_argument('--correlate',
                        type=str,
                        nargs='+',
                        metavar='PROPERTY',
                        help='Analyze correlations between properties')
    parser.add_argument('--export',
                        type=str,
                        metavar='FILE',
                        help='Export data to JSON file')

    args = parser.parse_args()

    # If no arguments, show help
    if not any(vars(args).values()):
        parser.print_help()

    analyze_db(
        list_properties=args.list_properties,
        status=args.status,
        analyze=args.analyze,
        correlate=args.correlate,
        export=args.export
    )


if __name__ == "__main__":
    main()
