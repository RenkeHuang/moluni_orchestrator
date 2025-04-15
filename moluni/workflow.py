import json
import time
import requests
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from ase import Atoms
import warp as wp
import duckdb

from .constants import (NVIDIA_API_KEY, NVIDIA_NIM_API_URL, DB_PATH)

logger = logging.getLogger(__name__)


class AlchemiWorkflow:

    def __init__(self, smiles_file: str, batch_size: int = 10):
        """
        Initialize the workflow with a file containing SMILES strings
        
        Args:
            smiles_file: Path to file with SMILES strings (one per line)
            batch_size: Number of molecules to process in parallel
        """
        self.smiles_file = smiles_file
        self.batch_size = batch_size
        self.smiles_list = self._load_smiles()

        self._timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        self._output_dir = Path(self._timestamp)
        self._output_dir.mkdir(exist_ok=True, parents=True)

        # Initialize WARP
        wp.init()

    def _load_smiles(self) -> List[str]:
        """Load SMILES strings from file"""
        with open(self.smiles_file, 'r') as f:
            return [line.strip() for line in f if line.strip()]

    def _init_database(self):
        """Initialize DuckDB database with necessary schema"""
        conn = duckdb.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY,
                smiles VARCHAR,
                inchi VARCHAR,
                formula VARCHAR,
                calculation_type VARCHAR,
                status VARCHAR,
                submission_time TIMESTAMP,
                completion_time TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                calculation_id INTEGER,
                property_name VARCHAR,
                property_value FLOAT,
                units VARCHAR,
                FOREIGN KEY (calculation_id) REFERENCES calculations(id)
            )
        """)
        conn.close()

    @staticmethod
    @wp.kernel
    def _optimize_geometry(pos: wp.array,
                           atomic_numbers: wp.array,
                           forces: wp.array) -> None:
        """
        WARP kernel to perform basic geometry optimization
        This is a simplified example - in practice would be more complex
        """
        tid = wp.tid()
        if tid < pos.shape[0]:
            # Simple force calculation (in practice would be more complex)
            force = wp.vec3f(0.0, 0.0, 0.0)
            for j in range(pos.shape[0]):
                if j != tid:
                    r = pos[tid] - pos[j]
                    dist = wp.length(r)
                    if dist < 0.1:  # Avoid division by zero
                        dist = 0.1
                    # Simple repulsive force based on atomic numbers
                    factor = atomic_numbers[tid] * atomic_numbers[j] / (dist *
                                                                        dist)
                    force = force + wp.normalize(r) * factor

            forces[tid] = force

    def preprocess_molecule(self, smiles: str) -> Dict[str, Any]:
        """
        Convert SMILES to 3D structure using RDKit and prepare for calculation
        
        Args:
            smiles: SMILES string of the molecule
            
        Returns:
            Dictionary with molecule information
        """
        try:
            # Convert SMILES to RDKit molecule
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.error(f"Failed to parse SMILES: {smiles}")
                return None

            # Add hydrogens and generate 3D coordinates
            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)

            # Get atomic positions and numbers
            conformer = mol.GetConformer()
            positions = np.array([
                conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms())
            ])
            atomic_numbers = np.array(
                [atom.GetAtomicNum() for atom in mol.GetAtoms()])

            # Use WARP to further optimize geometry
            pos_array = wp.array(positions.astype(np.float32), dtype=wp.vec3f)
            atomic_nums_array = wp.array(atomic_numbers.astype(np.int32),
                                         dtype=wp.int32)
            forces_array = wp.zeros_like(pos_array)

            # Run optimization kernel
            wp.launch(self._optimize_geometry,
                      dim=pos_array.shape[0],
                      inputs=[pos_array, atomic_nums_array, forces_array])

            # Get optimized positions
            optimized_positions = np.array(pos_array.numpy())

            # Create ASE Atoms object
            atoms = Atoms(numbers=atomic_numbers,
                          positions=optimized_positions)

            # Create input for NIM API
            inchi = Chem.MolToInchi(mol)
            formula = Chem.rdMolDescriptors.CalcMolFormula(mol)

            return {
                "smiles": smiles,
                "inchi": inchi,
                "formula": formula,
                "atoms": atoms,
                "atomic_positions": optimized_positions,
                "atomic_numbers": atomic_numbers
            }
        except Exception as e:
            logger.error(f"Error processing molecule {smiles}: {str(e)}")
            return None

    def prepare_nim_input(self, molecule_data: Dict[str, Any],
                          calc_type: str) -> Dict[str, Any]:
        """
        Prepare input for NVIDIA NIM API
        
        Args:
            molecule_data: Preprocessed molecule data
            calc_type: Type of calculation ('dft', 'md', etc.)
            
        Returns:
            Dictionary formatted for NIM API
        """
        atoms = molecule_data["atoms"]

        # Common parameters
        nim_input = {
            "molecule": {
                "elements": atoms.get_chemical_symbols(),
                "positions": atoms.positions.tolist(),
                "lattice": atoms.cell.tolist() if any(atoms.pbc) else None
            },
            "calculation": {
                "type": calc_type,
                "parameters": {}
            },
            "metadata": {
                "smiles": molecule_data["smiles"],
                "inchi": molecule_data["inchi"],
                "formula": molecule_data["formula"]
            }
        }

        # Add calculation-specific parameters
        if calc_type == "dft":
            nim_input["calculation"]["parameters"] = {
                "functional": "PBE",
                "basis_set": "def2-SVP",
                "task": "single_point"
            }
        elif calc_type == "md":
            nim_input["calculation"]["parameters"] = {
                "ensemble": "NVT",
                "temperature": 300,
                "steps": 1000,
                "timestep": 1.0
            }

        return nim_input

    def submit_calculation(self, nim_input: Dict[str, Any]) -> str:
        """
        Submit calculation to NVIDIA NIM API
        
        Args:
            nim_input: Formatted input for NIM API
            
        Returns:
            Job ID from NIM API
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {NVIDIA_API_KEY}"
        }

        try:
            response = requests.post(NVIDIA_NIM_API_URL,
                                     headers=headers,
                                     json=nim_input)
            response.raise_for_status()
            job_data = response.json()
            return job_data["job_id"]
        except Exception as e:
            logger.error(f"Error submitting calculation: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None

    def check_calculation_status(self, job_id: str) -> Dict[str, Any]:
        """
        Check status of a calculation
        
        Args:
            job_id: Job ID from NIM API
            
        Returns:
            Dictionary with job status information
        """
        headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}"}

        try:
            response = requests.get(f"{NVIDIA_NIM_API_URL}/{job_id}",
                                    headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error checking job status: {str(e)}")
            return {"status": "ERROR", "error": str(e)}

    def save_results_to_file(self, job_id: str,
                             result_data: Dict[str, Any]) -> Path:
        """
        Save calculation results to file
        
        Args:
            job_id: Job ID from NIM API
            result_data: Results from calculation
            
        Returns:
            Path to saved file
        """
        output_file = self._output_dir / f"{job_id}.json"
        with open(output_file, 'w') as f:
            json.dump(result_data, f, indent=2)
        return output_file

    def save_to_database(self, result_file: Path) -> bool:
        """
        Save calculation results to DuckDB
        
        Args:
            result_file: Path to JSON result file
            
        Returns:
            True if successful
        """
        try:
            # Load results from file
            with open(result_file, 'r') as f:
                result = json.load(f)

            # Extract data
            job_id = result.get("job_id")
            metadata = result.get("metadata", {})
            calculation = result.get("calculation", {})
            properties = result.get("properties", {})

            # Insert into database
            conn = duckdb.connect(DB_PATH)

            # Insert calculation info
            conn.execute(
                """
                INSERT INTO calculations (id, smiles, inchi, formula, calculation_type, status, 
                                         submission_time, completion_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, metadata.get("smiles"), metadata.get("inchi"),
                  metadata.get("formula"), calculation.get("type"),
                  result.get("status"), result.get("submission_time"),
                  result.get("completion_time")))

            # Insert properties
            for prop_name, prop_data in properties.items():
                if isinstance(prop_data, dict) and "value" in prop_data:
                    conn.execute(
                        """
                        INSERT INTO properties (calculation_id, property_name, property_value, units)
                        VALUES (?, ?, ?, ?)
                    """, (job_id, prop_name, prop_data.get("value"),
                          prop_data.get("units")))

            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            return False

    def process_batch(self,
                      batch: List[str],
                      calc_type: str = "dft") -> List[str]:
        """
        Process a batch of SMILES strings
        
        Args:
            batch: List of SMILES strings
            calc_type: Type of calculation
            
        Returns:
            List of job IDs
        """
        job_ids = []

        for smiles in batch:
            # Preprocess molecule
            logger.info(f"Processing molecule: {smiles}")
            molecule_data = self.preprocess_molecule(smiles)
            if molecule_data is None:
                continue

            # Prepare NIM input
            nim_input = self.prepare_nim_input(molecule_data, calc_type)

            # Submit calculation
            job_id = self.submit_calculation(nim_input)
            if job_id:
                logger.info(f"Submitted job {job_id} for molecule {smiles}")
                job_ids.append(job_id)

                # Save initial metadata
                output_file = self._output_dir / f"{job_id}_submit.json"
                with open(output_file, 'w') as f:
                    submission_data = {
                        "job_id": job_id,
                        "status": "SUBMITTED",
                        "metadata": molecule_data,
                        "submission_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    json.dump(submission_data, f, indent=2)

        return job_ids

    def run(self, calc_type: str = "dft"):
        """
        Run the entire workflow
        
        Args:
            calc_type: Type of calculation
        """
        # Initialize database
        self._init_database()

        # Process molecules in batches
        total_molecules = len(self.smiles_list)
        job_ids = []

        for i in range(0, total_molecules, self.batch_size):
            batch = self.smiles_list[i:i + self.batch_size]
            logger.info(
                f"Processing batch {i//self.batch_size + 1}/{(total_molecules-1)//self.batch_size + 1}"
            )
            batch_job_ids = self.process_batch(batch, calc_type)
            job_ids.extend(batch_job_ids)

            # Save job IDs for monitoring
            with open(self._output_dir / "pending_jobs.json", 'w') as f:
                json.dump(job_ids, f)

        logger.info(f"Submitted {len(job_ids)} jobs for processing")
        return job_ids



