# Target Schema

Database: target_db

## Table: DIM_CUSTOMER

| Column | Type | Nullable | Key | Description |
|---|---|---|---|---|
| customer_key | integer | NOT NULL | PRIMARY KEY | Customer dimension key |
| full_name | varchar(200) | NOT NULL | | Customer's full display name |
| status | varchar(20) | NOT NULL | | Account status |

## Table: FACT_ORDER

| Column | Type | Nullable | Key | Description |
|---|---|---|---|---|
| order_key | integer | NOT NULL | PRIMARY KEY | Order fact key |
| customer_key | integer | NOT NULL | FOREIGN KEY -> DIM_CUSTOMER.customer_key | Ordering customer's dimension key |
| order_date | date | NOT NULL | | Date the order was placed |
| amount | numeric(12,2) | NOT NULL | | Order total |
