// Sample "shop" dataset for MongoDB (runs once on first container start).
const shop = db.getSiblingDB("shop");

shop.customers.insertMany([
  { _id: 1, name: "Ann Lee", email: "ann@example.com", country: "US" },
  { _id: 2, name: "Bob Rao", email: "bob@example.com", country: "IN" },
  { _id: 3, name: "Cy Wong", email: "cy@example.com", country: "SG" },
]);

shop.orders.insertMany([
  { customerId: 1, status: "paid", total: 120.5, createdAt: new Date("2024-03-01T10:00:00Z"),
    items: [{ sku: "A-100", qty: 2, price: 30 }, { sku: "B-200", qty: 1, price: 60.5 }] },
  { customerId: 1, status: "shipped", total: 80.0, createdAt: new Date("2024-03-05T12:30:00Z"),
    items: [{ sku: "C-300", qty: 4, price: 20 }] },
  { customerId: 2, status: "paid", total: 200.0, createdAt: new Date("2024-03-07T09:15:00Z"),
    items: [{ sku: "A-100", qty: 5, price: 40 }] },
  { customerId: 2, status: "refunded", total: 40.0, createdAt: new Date("2024-03-09T16:45:00Z"),
    items: [{ sku: "B-200", qty: 1, price: 40 }] },
  { customerId: 3, status: "pending", total: 75.25, createdAt: new Date("2024-03-10T11:20:00Z"),
    items: [{ sku: "C-300", qty: 3, price: 25.08 }] },
]);

// Least-privilege account for the SDK
shop.createUser({
  user: "kb_reader",
  pwd: "kb_reader_pass",
  roles: [{ role: "read", db: "shop" }],
});
