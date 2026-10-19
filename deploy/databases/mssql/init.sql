-- Sample "shop" dataset for SQL Server, run once by the `mssql-init` service.
IF DB_ID('shop') IS NULL CREATE DATABASE shop;
GO
USE shop;
GO

IF OBJECT_ID('dbo.customers') IS NULL
BEGIN
    CREATE TABLE dbo.customers (
        id INT IDENTITY(1,1) PRIMARY KEY,
        name NVARCHAR(100) NOT NULL,
        email NVARCHAR(150) NOT NULL,
        country NVARCHAR(50) NOT NULL
    );
    CREATE TABLE dbo.orders (
        id INT IDENTITY(1,1) PRIMARY KEY,
        customerId INT NOT NULL REFERENCES dbo.customers (id),
        status NVARCHAR(20) NOT NULL,
        total DECIMAL(10, 2) NOT NULL,
        createdAt DATETIME2 NOT NULL
    );

    INSERT INTO dbo.customers (name, email, country) VALUES
        ('Ann Lee', 'ann@example.com', 'US'),
        ('Bob Rao', 'bob@example.com', 'IN'),
        ('Cy Wong', 'cy@example.com', 'SG');

    INSERT INTO dbo.orders (customerId, status, total, createdAt) VALUES
        (1, 'paid',     120.50, '2024-03-01T10:00:00'),
        (1, 'shipped',   80.00, '2024-03-05T12:30:00'),
        (2, 'paid',     200.00, '2024-03-07T09:15:00'),
        (2, 'refunded',  40.00, '2024-03-09T16:45:00'),
        (3, 'pending',   75.25, '2024-03-10T11:20:00');

    EXEC sp_addextendedproperty N'MS_Description', N'Customer orders', N'SCHEMA', N'dbo', N'TABLE', N'orders';
END
GO

-- Least-privilege login for the SDK (read-only)
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'kb_reader')
    CREATE LOGIN kb_reader WITH PASSWORD = 'Kb_reader_pass1', CHECK_POLICY = OFF;
GO
USE shop;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'kb_reader')
    CREATE USER kb_reader FOR LOGIN kb_reader;
ALTER ROLE db_datareader ADD MEMBER kb_reader;
GO
