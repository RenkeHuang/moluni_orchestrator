import argparse

from moluni import AlchemiResultsProcessor


def main():
    parser = argparse.ArgumentParser(
        description='Process results from Alchemi NIM API')
    parser.add_argument('--results-dir',
                        type=str,
                        help='Path of result directory to process')

    args = parser.parse_args()

    processor = AlchemiResultsProcessor(args.results_dir)
    processor.process_results()


if __name__ == "__main__":
    main()
