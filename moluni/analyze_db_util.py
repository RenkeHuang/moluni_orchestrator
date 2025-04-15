"""
Utility for analyzing the results in the materials database.
"""

import os
import sys
import duckdb
import matplotlib.pyplot as plt
import json

from .constants import DB_PATH


def connect_db():
    """Connect to the DuckDB database"""
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file {DB_PATH} not found")
        sys.exit(1)

    return duckdb.connect(DB_PATH)


def list_properties(conn):
    """List all available properties in the database"""
    properties = conn.execute("""
        SELECT DISTINCT property_name, COUNT(*) as count 
        FROM properties 
        GROUP BY property_name 
        ORDER BY count DESC
    """).fetchall()

    print(f"Found {len(properties)} different properties:")
    for prop, count in properties:
        print(f"  - {prop} ({count} values)")

    return [p[0] for p in properties]


def get_calculation_types(conn):
    """Get all calculation types in the database"""
    types = conn.execute("""
        SELECT DISTINCT calculation_type, COUNT(*) as count 
        FROM calculations 
        GROUP BY calculation_type 
        ORDER BY count DESC
    """).fetchall()

    print(f"Found {len(types)} different calculation types:")
    for calc_type, count in types:
        print(f"  - {calc_type} ({count} calculations)")

    return [t[0] for t in types]


def get_calculation_status(conn):
    """Get calculation status summary"""
    statuses = conn.execute("""
        SELECT status, COUNT(*) as count 
        FROM calculations 
        GROUP BY status 
        ORDER BY count DESC
    """).fetchall()

    total = sum(s[1] for s in statuses)
    print(f"Status of {total} calculations:")
    for status, count in statuses:
        print(f"  - {status}: {count} ({count/total*100:.1f}%)")


def analyze_property(conn, property_name):
    """Analyze a specific property"""
    # Get basic statistics
    stats = conn.execute(f"""
        SELECT 
            COUNT(*) as count,
            MIN(property_value) as min_val,
            MAX(property_value) as max_val,
            AVG(property_value) as avg_val,
            STDDEV(property_value) as std_val
        FROM properties
        WHERE property_name = '{property_name}'
    """).fetchone()

    count, min_val, max_val, avg_val, std_val = stats

    print(f"\nAnalysis of property: {property_name}")
    print(f"  Available values: {count}")
    print(f"  Range: {min_val:.4f} to {max_val:.4f}")
    print(f"  Average: {avg_val:.4f}")
    print(f"  Standard deviation: {std_val:.4f}")

    # Get data for histogram
    data = conn.execute(f"""
        SELECT property_value
        FROM properties
        WHERE property_name = '{property_name}'
    """).fetchnumpy()

    values = data['property_value']

    # Create histogram
    plt.figure(figsize=(10, 6))
    plt.hist(values, bins=30, alpha=0.7, color='blue')
    plt.title(f'Distribution of {property_name}')
    plt.xlabel('Value')
    plt.ylabel('Frequency')
    plt.grid(alpha=0.3)

    # Save plot
    output_file = f"{property_name.replace('/', '_')}_distribution.png"
    plt.savefig(output_file)
    print(f"  Plot saved as: {output_file}")

    # Find molecules with extreme values
    extremes = conn.execute(f"""
        SELECT 
            c.formula, 
            c.smiles, 
            p.property_value,
            c.id
        FROM properties p
        JOIN calculations c ON p.calculation_id = c.id
        WHERE p.property_name = '{property_name}'
        ORDER BY p.property_value
        LIMIT 5
    """).fetchall()

    print("\n  Molecules with lowest values:")
    for formula, smiles, value, job_id in extremes:
        print(f"    {formula} ({smiles}): {value:.4f} [Job: {job_id}]")

    extremes = conn.execute(f"""
        SELECT 
            c.formula, 
            c.smiles, 
            p.property_value,
            c.id
        FROM properties p
        JOIN calculations c ON p.calculation_id = c.id
        WHERE p.property_name = '{property_name}'
        ORDER BY p.property_value DESC
        LIMIT 5
    """).fetchall()

    print("\n  Molecules with highest values:")
    for formula, smiles, value, job_id in extremes:
        print(f"    {formula} ({smiles}): {value:.4f} [Job: {job_id}]")


def correlation_analysis(conn, property_names):
    """Analyze correlations between properties"""
    if len(property_names) < 2:
        print("Need at least 2 properties to analyze correlations")
        return

    # Create a temporary view joining properties
    property_pivots = []
    for i, prop in enumerate(property_names):
        property_pivots.append(f"""
            MAX(CASE WHEN p.property_name = '{prop}' THEN p.property_value END) AS {prop.replace('/', '_')}
        """)

    pivot_sql = ",\n            ".join(property_pivots)

    conn.execute(f"""
        CREATE OR REPLACE VIEW property_matrix AS
        SELECT 
            p.calculation_id,
            {pivot_sql}
        FROM properties p
        WHERE p.property_name IN ({', '.join(["'" + p + "'" for p in property_names])})
        GROUP BY p.calculation_id
    """)

    # Get data for correlation analysis
    df = conn.execute("SELECT * FROM property_matrix").df()
    df = df.dropna()  # Remove rows with missing values

    # Create correlation matrix
    corr_matrix = df.corr()

    # Print top correlations
    print("\nTop correlations:")
    corr_pairs = []
    for i in range(len(property_names)):
        for j in range(i + 1, len(property_names)):
            prop1 = property_names[i].replace('/', '_')
            prop2 = property_names[j].replace('/', '_')
            if prop1 in corr_matrix.columns and prop2 in corr_matrix.columns:
                corr = corr_matrix.loc[prop1, prop2]
                corr_pairs.append((prop1, prop2, abs(corr), corr))

    # Sort by absolute correlation
    corr_pairs.sort(key=lambda x: x[2], reverse=True)

    for prop1, prop2, _, corr in corr_pairs[:10]:
        print(f"  {prop1} vs {prop2}: {corr:.4f}")

    # Create scatter plot for top correlation
    if corr_pairs:
        prop1, prop2, _, corr = corr_pairs[0]
        plt.figure(figsize=(10, 6))
        plt.scatter(df[prop1], df[prop2], alpha=0.5)
        plt.title(f'Correlation between {prop1} and {prop2}: {corr:.4f}')
        plt.xlabel(prop1)
        plt.ylabel(prop2)
        plt.grid(alpha=0.3)

        output_file = f"correlation_{prop1}_{prop2}.png"
        plt.savefig(output_file)
        print(f"\nCorrelation plot saved as: {output_file}")


def export_json(conn, output_file):
    """Export database content to JSON"""
    # Get all calculations
    calculations = conn.execute("""
        SELECT id, smiles, inchi, formula, calculation_type, status
        FROM calculations
        WHERE status = 'COMPLETED'
    """).fetchall()

    result = []
    for calc_id, smiles, inchi, formula, calc_type, status in calculations:
        # Get properties for this calculation
        properties = conn.execute(f"""
            SELECT property_name, property_value, units
            FROM properties
            WHERE calculation_id = '{calc_id}'
        """).fetchall()

        prop_dict = {}
        for name, value, units in properties:
            prop_dict[name] = {"value": float(value), "units": units}

        result.append({
            "id": calc_id,
            "smiles": smiles,
            "inchi": inchi,
            "formula": formula,
            "calculation_type": calc_type,
            "properties": prop_dict
        })

    # Write to file
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"Exported {len(result)} calculations to {output_file}")


def analyze_db(list_properties: bool = False,
               status: bool = False,
               analyze: str = None,
               correlate: list = None,
               export: str = None):
    """Analyze the materials database"""
    conn = connect_db()

    if list_properties:
        list_properties(conn)

    if status:
        get_calculation_types(conn)
        get_calculation_status(conn)

    if analyze:
        analyze_property(conn, analyze)

    if correlate:
        correlation_analysis(conn, correlate)

    if export:
        export_json(conn, export)

