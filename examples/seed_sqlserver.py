"""
Seed Sample Tables into Sagar Database on SQL Server
Run from project root:
    python examples/seed_sqlserver.py
"""
import pyodbc

SERVER = r"DESKTOP-EF69CVF\SQLEXPRESS"
DATABASE = "Sagar"

DDL_STATEMENTS = [
    # 1. departments
    """
    IF OBJECT_ID('dbo.departments', 'U') IS NOT NULL DROP TABLE dbo.departments;
    CREATE TABLE dbo.departments (
        dept_id INT PRIMARY KEY,
        dept_name VARCHAR(50) NOT NULL UNIQUE,
        manager_name VARCHAR(50) NOT NULL,
        budget DECIMAL(12, 2) NOT NULL,
        location VARCHAR(50) NOT NULL,
        headcount INT NOT NULL
    );
    """,
    """
    INSERT INTO dbo.departments (dept_id, dept_name, manager_name, budget, location, headcount) VALUES
    (1, 'HR', 'Amit Sharma', 250000.00, 'Mumbai', 12),
    (2, 'PRODUCTION', 'Rajesh Patel', 750000.00, 'Pune', 45),
    (3, 'IT & Engineering', 'Priya Deshmukh', 1200000.00, 'Bangalore', 35),
    (4, 'SALES', 'Vikram Joshi', 500000.00, 'Delhi', 20),
    (5, 'FINANCE', 'Sunita Rao', 300000.00, 'Mumbai', 8);
    """,
    # 2. projects
    """
    IF OBJECT_ID('dbo.projects', 'U') IS NOT NULL DROP TABLE dbo.projects;
    CREATE TABLE dbo.projects (
        project_id INT PRIMARY KEY,
        project_name VARCHAR(100) NOT NULL,
        dept_name VARCHAR(50) NOT NULL,
        budget DECIMAL(12, 2) NOT NULL,
        status VARCHAR(20) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NULL
    );
    """,
    """
    INSERT INTO dbo.projects (project_id, project_name, dept_name, budget, status, start_date, end_date) VALUES
    (101, 'Cloud Data Migration', 'IT & Engineering', 350000.00, 'Completed', '2024-01-15', '2024-06-30'),
    (102, 'ERP NextGen Upgrade', 'IT & Engineering', 500000.00, 'In Progress', '2024-04-01', '2025-03-31'),
    (103, 'Factory Automation Phase 2', 'PRODUCTION', 400000.00, 'In Progress', '2024-07-01', '2025-06-30'),
    (104, 'Employee Self-Service Portal', 'HR', 120000.00, 'Completed', '2024-02-01', '2024-05-31'),
    (105, 'Q4 Sales Expansion Drive', 'SALES', 200000.00, 'Planning', '2024-10-01', '2024-12-31');
    """,
    # 3. orders
    """
    IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
    CREATE TABLE dbo.orders (
        order_id INT PRIMARY KEY,
        customer_name VARCHAR(100) NOT NULL,
        order_date DATE NOT NULL,
        total_amount DECIMAL(10, 2) NOT NULL,
        status VARCHAR(20) NOT NULL,
        shipping_city VARCHAR(50) NOT NULL,
        sales_rep VARCHAR(50) NOT NULL
    );
    """,
    """
    INSERT INTO dbo.orders (order_id, customer_name, order_date, total_amount, status, shipping_city, sales_rep) VALUES
    (5001, 'Reliance Industries', '2024-09-01', 45000.00, 'Delivered', 'Mumbai', 'Vikram Joshi'),
    (5002, 'Tata Consultancy Services', '2024-09-12', 120000.00, 'Delivered', 'Pune', 'Vikram Joshi'),
    (5003, 'Infosys Technologies', '2024-09-20', 85000.00, 'Shipped', 'Bangalore', 'Rahul Nair'),
    (5004, 'Wipro Enterprises', '2024-10-02', 32000.00, 'Processing', 'Hyderabad', 'Rahul Nair'),
    (5005, 'HDFC Bank', '2024-10-05', 95000.00, 'Processing', 'Mumbai', 'Sneha Kulkarni'),
    (5006, 'Mahindra & Mahindra', '2024-10-10', 150000.00, 'Delivered', 'Nashik', 'Vikram Joshi'),
    (5007, 'Larsen & Toubro', '2024-10-15', 210000.00, 'Shipped', 'Chennai', 'Sneha Kulkarni');
    """,
]

def main():
    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE};Trusted_Connection=yes;"
    print(f"Connecting to {SERVER} / {DATABASE}...")
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()

    for idx, stmt in enumerate(DDL_STATEMENTS, 1):
        print(f"Executing step {idx}/{len(DDL_STATEMENTS)}...")
        cursor.execute(stmt)

    print("\nVerifying tables created:")
    for tbl in ["dbo.employee", "dbo.departments", "dbo.projects", "dbo.orders"]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
            cnt = cursor.fetchone()[0]
            print(f"  [OK] {tbl:18}: {cnt} rows")
        except Exception as e:
            print(f"  [--] {tbl:18}: {e}")

    cursor.close()
    conn.close()
    print("\nDatabase seeded successfully!")

if __name__ == "__main__":
    main()
