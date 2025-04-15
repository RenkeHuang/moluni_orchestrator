import json

import requests
from pathlib import Path
import duckdb
import logging

from .constants import (NVIDIA_API_KEY, NVIDIA_NIM_API_URL, DEFAULT_RESULTS_DIR,
                        DB_PATH)

logger = logging.getLogger(__name__)


class AlchemiResultsProcessor:

    def __init__(self, results_dir: str | Path = DEFAULT_RESULTS_DIR):
        """Initialize the results processor"""
        _results_dir = results_dir or DEFAULT_RESULTS_DIR
        self.results_dir = Path(_results_dir)
        self.results_dir.mkdir(exist_ok=True, parents=True)

    def _get_pending_jobs(self) -> list:
        """Get list of pending job IDs"""
        pending_file = self.results_dir / "pending_jobs.json"
        if not pending_file.exists():
            return []

        with open(pending_file, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logger.error("Error parsing pending jobs file")
                return []

    def _update_pending_jobs(self, pending_jobs: list):
        """Update the list of pending job IDs"""
        with open(self.results_dir / "pending_jobs.json", 'w') as f:
            json.dump(pending_jobs, f)

    def check_job_status(self, job_id: str) -> dict:
        """
        Check the status of a job
        
        Args:
            job_id: Job ID to check
            
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
            logger.error(f"Error checking status for job {job_id}: {str(e)}")
            return {"status": "ERROR", "error": str(e)}

    def save_results_to_file(self, job_id: str, result_data: dict) -> Path:
        """
        Save job results to file
        
        Args:
            job_id: Job ID
            result_data: Job result data
            
        Returns:
            Path to result file
        """
        output_file = self.results_dir / f"{job_id}.json"
        with open(output_file, 'w') as f:
            json.dump(result_data, f, indent=2)
        logger.info(f"Saved results for job {job_id} to {output_file}")
        return output_file

    def save_to_database(self, result_file: Path) -> bool:
        """
        Save job results to database
        
        Args:
            result_file: Path to result file
            
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

            # Connect to database
            conn = duckdb.connect(DB_PATH)

            # Check if job already exists
            existing = conn.execute(
                f"SELECT id FROM calculations WHERE id = '{job_id}'").fetchone(
                )

            if existing:
                # Update existing record
                conn.execute(
                    """
                    UPDATE calculations
                    SET status = ?, completion_time = ?
                    WHERE id = ?
                """, (result.get("status"), result.get("completion_time"),
                      job_id))
            else:
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

            # Clear existing properties and insert new ones
            if existing:
                conn.execute(
                    f"DELETE FROM properties WHERE calculation_id = '{job_id}'"
                )

            # Insert properties
            for prop_name, prop_data in properties.items():
                if isinstance(prop_data, dict) and "value" in prop_data:
                    conn.execute(
                        """
                        INSERT INTO properties (calculation_id, property_name, property_value, units)
                        VALUES (?, ?, ?, ?)
                    """, (job_id, prop_name, prop_data.get("value"),
                          prop_data.get("units")))
                elif isinstance(prop_data, (int, float)):
                    conn.execute(
                        """
                        INSERT INTO properties (calculation_id, property_name, property_value, units)
                        VALUES (?, ?, ?, ?)
                    """, (job_id, prop_name, prop_data, None))

            conn.close()
            logger.info(f"Saved results for job {job_id} to database")
            return True
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            return False

    def process_results(self):
        """Process results for all pending jobs"""
        pending_jobs = self._get_pending_jobs()
        if not pending_jobs:
            logger.info("No pending jobs to process")
            return

        logger.info(f"Processing {len(pending_jobs)} pending jobs")
        still_pending = []

        for job_id in pending_jobs:
            # Check job status
            job_status = self.check_job_status(job_id)
            status = job_status.get("status", "UNKNOWN")

            if status in ["COMPLETED", "FAILED", "ERROR"]:
                # Job is done (successfully or not)
                logger.info(f"Job {job_id} finished with status: {status}")

                # Save results to file
                result_file = self.save_results_to_file(job_id, job_status)

                # Save to database
                self.save_to_database(result_file)
            else:
                # Job is still pending
                logger.info(
                    f"Job {job_id} is still running with status: {status}")
                still_pending.append(job_id)

        # Update pending jobs
        self._update_pending_jobs(still_pending)
        logger.info(f"Remaining pending jobs: {len(still_pending)}")
