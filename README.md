# High-throughput computational materials workflow

This repository contains a end-to-end workflow for automating high-throughput materials discovery calculations 
using [NVIDIA ALCHEMI API](https://developer.nvidia.com/blog/revolutionizing-ai-driven-material-discovery-using-nvidia-alchemi/). 
The workflow takes SMILES strings as input, processes them using [RDKit](https://github.com/rdkit/rdkit) and [ASE](https://wiki.fysik.dtu.dk/ase/), 
runs GPU-accelerated geometry optimizations via ALCHEMI NIM API, 
and stores results to database.


## Components
1. Input Processing and Calculation Submission System
   - Takes SMILES strings as input and converts them to 3D structures using RDKit
   - Leverages [NVIDIA Warp](https://nvidia.github.io/warp/index.html) for GPU-accelerated geometry optimization
   - Submits batches of calculations to the NIM API

2. Job Monitoring and Results Processing Pipeline
   - Tracks job IDs and status in a persistently monitored queue
   - Periodically checks for completed calculations
   - Processes returned results and stores them in structured DuckDB database, enabling efficient querying and analysis of material properties

3. GitHub Actions Integration
   - Orchestrates the entire workflow from submission to results collection
   - Provides scheduled monitoring of pending calculations
   - Automatically detects when new results are available
   <!-- - Uses artifacts to persist data between workflow runs -->


<!-- ## Prerequisites

- Python 3.8+
- NVIDIA API Key for Alchemi services
- RDKit, ASE, NVIDIA Warp, DuckDB -->

## Project Structure

```
moluni_orchestrator/
├── .github/workflows/      # GitHub Actions workflow files
├── data/smiles             # directory to upload input SMILES files
├── moluni
│   ├── __init__.py
│   ├── analyze_db_util.py  # Database analysis utilities
│   ├── constants.py
│   ├── postprocess.py      # Utils to check job status, process results
│   └── workflow.py         # Preprocessing and prepare workflow
├── README.md
├── results              
└── workflow
    ├── analyze_db.py
    ├── check_results.sh         # Bash script to check for results locally
    ├── process_results.py
    ├── run_alchemi_workflow.py
    └── run_workflow.sh          # Bash script to run the workflow locally
```

## Usage

### Setting Up

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install rdkit ase numpy duckdb requests warp-lang
   ```
3. Set your NVIDIA API key as an environment variable:
   ```bash
   export NVIDIA_API_KEY=your_api_key_here
   ```

### Submitting Calculations

1. Create a file with SMILES strings (one per line) in `data/smiles/molecules.txt`
2. Run the workflow:
   ```bash
   workflow/run_workflow.sh data/smiles/molecules.txt
   ```
   
   Optional parameters:
   ```bash
   ./run_workflow.sh data/smiles/molecules.txt 20 dft  # Batch size 20, DFT calculations
   ```

### Checking Results

Run the results checker to update the database with completed calculations:
```bash
./check_results.sh
```

### Analyzing Results

Use the analysis script to explore the database:
```bash
# List available properties
python workflow/analyze_db.py --list-properties

# Check calculation status
python workflow/analyze_db.py --status

# Analyze a specific property
python workflow/analyze_db.py --analyze "total_energy"

# Analyze correlations between properties
python workflow/analyze_db.py --correlate "total_energy" "band_gap" "formation_energy"

# Export data to JSON
python workflow/analyze_db.py --export "results.json"
```

## Using GitHub Actions

The workflow is fully integrated with GitHub Actions:

1. Fork this repository
2. Add your NVIDIA API key as a repository secret named `NVIDIA_API_KEY`
3. Create or update a SMILES file in the `data/smiles/` directory
4. Push to the `main` branch to trigger the workflow
5. The workflow will automatically:
   - Process the SMILES strings
   - Submit calculations to ALCHEMI NIM API
   - Check for results periodically
   - Update the database with completed results

You can also manually trigger the workflow through the GitHub Actions UI.

## Understanding the Database

The DuckDB database contains two main tables:

1. **calculations**: Contains metadata about each calculation including SMILES, formula, status
2. **properties**: Contains the actual properties calculated for each molecule

Query example:
```python
import duckdb

conn = duckdb.connect("data.duckdb")
# Get all molecules with band gap > 2.0 eV
results = conn.execute("""
    SELECT c.formula, c.smiles, p.property_value 
    FROM properties p
    JOIN calculations c ON p.calculation_id = c.id
    WHERE p.property_name = 'band_gap' AND p.property_value > 2.0
    ORDER BY p.property_value DESC
""").fetchall()

for formula, smiles, band_gap in results:
    print(f"{formula} ({smiles}): {band_gap} eV")
```

<!-- ## Advanced Usage: Warp Optimization

The workflow uses NVIDIA Warp to accelerate geometry optimization. The Warp kernel in `main_workflow.py` can be customized for more advanced force field calculations:

```python
@wp.kernel
def _optimize_geometry(pos: wp.array(dtype=wp.vec3f),
                      atomic_numbers: wp.array(dtype=wp.int32),
                      forces: wp.array(dtype=wp.vec3f)):
    # Custom force field implementation goes here
    # ...
``` -->

<!-- ## Known Limitations

- Large molecules may take longer to process
- Some calculation types may not be available in NIM API
- Warp acceleration requires an NVIDIA GPU for best performance -->

## License

This project is licensed under the MIT License.
