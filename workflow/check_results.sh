#!/bin/bash

# Check Alchemi Results
# Usage: ./check_results.sh

set -e

# Check if NVIDIA API key is set
if [ -z "$NVIDIA_API_KEY" ]; then
    echo "Error: NVIDIA_API_KEY environment variable not set"
    echo "Set it with: export NVIDIA_API_KEY=your_api_key"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Run the results processor
echo "Checking for job results..."
python process_results.py

# Show summary of results
echo "Results summary:"
if [ -f "data.duckdb" ]; then
    echo "Database statistics:"
    python -c "
import duckdb
conn = duckdb.connect('data.duckdb')
total_calcs = conn.execute('SELECT COUNT(*) FROM calculations').fetchone()[0]
completed = conn.execute('SELECT COUNT(*) FROM calculations WHERE status = \'COMPLETED\'').fetchone()[0]
failed = conn.execute('SELECT COUNT(*) FROM calculations WHERE status IN (\'FAILED\', \'ERROR\')').fetchone()[0]
pending = conn.execute('SELECT COUNT(*) FROM calculations WHERE status NOT IN (\'COMPLETED\', \'FAILED\', \'ERROR\')').fetchone()[0]
num_properties = conn.execute('SELECT COUNT(*) FROM properties').fetchone()[0]

print(f'Total calculations: {total_calcs}')
print(f'Completed: {completed}')
print(f'Failed: {failed}')
print(f'Pending: {pending}')
print(f'Total properties: {num_properties}')

if completed > 0:
    print('\\nMost recent completed calculations:')
    results = conn.execute('''
        SELECT id, formula, calculation_type, completion_time 
        FROM calculations 
        WHERE status = \'COMPLETED\' 
        ORDER BY completion_time DESC 
        LIMIT 5
    ''').fetchall()
    
    for row in results:
        print(f'  Job {row[0]}: {row[1]} ({row[2]}) - {row[3]}')
    
    print('\\nAvailable properties:')
    props = conn.execute('''
        SELECT DISTINCT property_name 
        FROM properties
        ORDER BY property_name
    ''').fetchall()
    
    print('  ' + ', '.join([row[0] for row in props]))
"
else
    echo "No database found yet."
fi
