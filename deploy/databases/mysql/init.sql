-- Sample "shop" dataset for MySQL (runs once on first container start; database `shop` already exists).
USE shop;

CREATE TABLE customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    country VARCHAR(50) NOT NULL
) COMMENT = 'Registered customers';

CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customerId INT NOT NULL,
    status VARCHAR(20) NOT NULL COMMENT 'pending | paid | shipped | refunded',
    total DECIMAL(10, 2) NOT NULL,
    createdAt DATETIME NOT NULL,
    CONSTRAINT fk_orders_customer FOREIGN KEY (customerId) REFERENCES customers (id)
) COMMENT = 'Customer orders';

INSERT INTO customers (name, email, country) VALUES
    ('Ann Lee', 'ann@example.com', 'US'),
    ('Bob Rao', 'bob@example.com', 'IN'),
    ('Cy Wong', 'cy@example.com', 'SG');

INSERT INTO orders (customerId, status, total, createdAt) VALUES
    (1, 'paid',     120.50, '2024-03-01 10:00:00'),
    (1, 'shipped',   80.00, '2024-03-05 12:30:00'),
    (2, 'paid',     200.00, '2024-03-07 09:15:00'),
    (2, 'refunded',  40.00, '2024-03-09 16:45:00'),
    (3, 'pending',   75.25, '2024-03-10 11:20:00');

-- Least-privilege account for the SDK
GRANT SELECT ON shop.* TO 'kb_reader'@'%';
FLUSH PRIVILEGES;
