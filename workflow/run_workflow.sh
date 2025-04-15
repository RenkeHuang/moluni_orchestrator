#!/bin/bash

# Run Alchemi Workflow
# Usage: ./run_workflow.sh <smiles_file> [batch_size] [calc_type]

set -e

# Check parameters
if [ $# -lt 1 ]; then
    echo "Usage: $0 <smiles_file> [batch_size] [calc_type]"
    exit 1
fi

SMILES_FILE=$1
BATCH_SIZE=${2:-10}
CALC_TYPE=${3:-dft}

# Check if NVIDIA API key is set
if [ -z "$NVIDIA_API_KEY" ]; then
    echo "Error: NVIDIA_API_KEY environment variable not set"
    echo "Set it with: export NVIDIA_API_KEY=your_api_key"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if ! pip show rdkit >/dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install rdkit ase numpy duckdb requests
    
    # Install NVIDIA WARP
    pip install warp-lang
fi

# Run the workflow
echo "Starting workflow with SMILES from $SMILES_FILE"
python run_alchemi_workflow.py --smiles "$SMILES_FILE" --batch-size "$BATCH_SIZE" --calc-type "$CALC_TYPE"

echo "Workflow submission complete. Job IDs saved to results/pending_jobs.json"
echo "Use check_results.sh to monitor job status and retrieve results"
