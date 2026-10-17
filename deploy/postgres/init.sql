-- ==============================================================================
-- Production Enterprise Database Initialization Script
-- Configures schemas, pgvector extension, sample enterprise datasets,
-- and dedicated restricted read-only database user (Least Privilege principle).
-- ==============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create enterprise schemas
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS customers;

-- 3. Customers table
CREATE TABLE IF NOT EXISTS customers.customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL,
    region VARCHAR(50) NOT NULL,
    segment VARCHAR(50) DEFAULT 'STANDARD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Products table
CREATE TABLE IF NOT EXISTS sales.products (
    product_id SERIAL PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(80) NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    in_stock_quantity INTEGER DEFAULT 0
);

-- 5. Orders table
CREATE TABLE IF NOT EXISTS sales.orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers.customers(customer_id),
    order_date DATE NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    status VARCHAR(30) DEFAULT 'COMPLETED',
    region VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Insert sample enterprise records
INSERT INTO customers.customers (name, email, region, segment) VALUES
    ('Acme Industrial', 'procurement@acme.example.com', 'North America', 'ENTERPRISE'),
    ('Nova Global Tech', 'contact@novaglobal.example.com', 'EMEA', 'ENTERPRISE'),
    ('Solaria Energy', 'accounts@solaria.example.com', 'APAC', 'MID_MARKET'),
    ('Horizon Logistics', 'billing@horizon.example.com', 'North America', 'MID_MARKET'),
    ('Pinnacle Health', 'finance@pinnacle.example.com', 'North America', 'ENTERPRISE')
ON CONFLICT DO NOTHING;

INSERT INTO sales.products (sku, product_name, category, unit_price, in_stock_quantity) VALUES
    ('HW-SRV-01', 'Cloud Rack Server X8', 'Hardware', 4500.00, 120),
    ('SW-ENT-02', 'Enterprise Analytics Suite', 'Software', 12500.00, 9999),
    ('SVC-CON-03', 'Architecture Advisory 40h', 'Services', 8000.00, 50),
    ('HW-SWT-04', 'Managed 100G Switch', 'Hardware', 2800.00, 75),
    ('SW-AI-05', 'Agentic KB AI Platform', 'Software', 15000.00, 9999)
ON CONFLICT DO NOTHING;

INSERT INTO sales.orders (customer_id, order_date, total_amount, status, region) VALUES
    (1, '2026-08-15', 25000.00, 'COMPLETED', 'North America'),
    (2, '2026-08-20', 37500.00, 'COMPLETED', 'EMEA'),
    (3, '2026-09-02', 12500.00, 'COMPLETED', 'APAC'),
    (4, '2026-09-10', 8000.00, 'COMPLETED', 'North America'),
    (5, '2026-09-28', 45000.00, 'COMPLETED', 'North America'),
    (1, '2026-10-05', 18200.00, 'COMPLETED', 'North America'),
    (2, '2026-10-12', 31000.00, 'COMPLETED', 'EMEA')
ON CONFLICT DO NOTHING;

-- ==============================================================================
-- Least Privilege Security: Create Dedicated Read-Only Database User
-- Never run the AI agent as a superuser, owner, or administrator.
-- ==============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ai_agent_readonly') THEN
        CREATE ROLE ai_agent_readonly WITH LOGIN PASSWORD 'readonly_secret_pass';
    END IF;
END
$$;

-- Grant schema access
GRANT USAGE ON SCHEMA sales TO ai_agent_readonly;
GRANT USAGE ON SCHEMA customers TO ai_agent_readonly;

-- Grant read-only SELECT permissions
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO ai_agent_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA customers TO ai_agent_readonly;

-- Ensure future tables also inherit read-only SELECT
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO ai_agent_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA customers GRANT SELECT ON TABLES TO ai_agent_readonly;

-- Revoke dangerous permissions explicitly
REVOKE CREATE ON SCHEMA sales FROM ai_agent_readonly;
REVOKE CREATE ON SCHEMA customers FROM ai_agent_readonly;
