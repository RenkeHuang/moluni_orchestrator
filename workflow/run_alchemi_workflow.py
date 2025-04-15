import argparse

from moluni import AlchemiWorkflow

def main():
    parser = argparse.ArgumentParser(
        description='Alchemi Materials Discovery Workflow')
    parser.add_argument('--smiles',
                        required=True,
                        help='Path to file with SMILES strings')
    parser.add_argument('--batch-size',
                        type=int,
                        default=10,
                        help='Batch size for processing')
    parser.add_argument('--calc-type',
                        default='dft',
                        choices=['dft', 'md'],
                        help='Calculation type')

    args = parser.parse_args()

    workflow = AlchemiWorkflow(args.smiles, args.batch_size)
    workflow.run(args.calc_type)


if __name__ == "__main__":
    main()