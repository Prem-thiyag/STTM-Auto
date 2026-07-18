# User Defined Functions

## udf_calculate_age
Input: dob DATE
Output: INT

```sql
CREATE OR REPLACE FUNCTION udf_calculate_age(dob DATE)
RETURNS INT AS $$
    SELECT CASE
        WHEN dob IS NULL THEN NULL
        ELSE EXTRACT(YEAR FROM AGE(CURRENT_DATE, dob))::INT
    END;
$$ LANGUAGE SQL IMMUTABLE;
```

## udf_full_name
Input: first_name,last_name
Output: VARCHAR

```sql
CREATE OR REPLACE FUNCTION udf_full_name(first_name VARCHAR, last_name VARCHAR)
RETURNS VARCHAR AS $$
    SELECT TRIM(BOTH ' ' FROM COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''));
$$ LANGUAGE SQL IMMUTABLE;
```
