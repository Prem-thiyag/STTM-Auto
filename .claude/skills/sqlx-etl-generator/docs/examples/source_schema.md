# Source Schema

Database: source_db

## Table: CUSTOMER

| Column | Type | Nullable | Key | Description |
|---|---|---|---|---|
| customer_id | integer | NOT NULL | PRIMARY KEY | Unique customer identifier |
| first_name | varchar(100) | NOT NULL | | Customer's given name |
| last_name | varchar(100) | NOT NULL | | Customer's family name |
| status | varchar(20) | NOT NULL | | Account status, e.g. ACTIVE / INACTIVE |
| created_at | timestamp | NOT NULL | | Row creation timestamp |

## Table: CUSTOMER_ORDER

| Column | Type | Nullable | Key | Description |
|---|---|---|---|---|
| order_id | integer | NOT NULL | PRIMARY KEY | Unique order identifier |
| customer_id | integer | NOT NULL | FOREIGN KEY -> CUSTOMER.customer_id | Ordering customer |
| order_date | date | NOT NULL | | Date the order was placed |
| amount | numeric(12,2) | NOT NULL | | Order total |
| status | varchar(20) | NOT NULL | | Order status, e.g. COMPLETE / CANCELLED |
