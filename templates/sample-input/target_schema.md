# Target Schema

## DIM_PATIENT
| Column | Type | PK |
|---|---|---|
| patient_key | BIGINT | Y |
| patient_id | INT | |
| full_name | VARCHAR(200) | |
| gender | VARCHAR(10) | |
| age | INT | |
| phone | VARCHAR(20) | |

## FACT_PATIENT_VISIT
| Column | Type | PK |
|---|---|---|
| visit_key | BIGINT | Y |
| visit_id | INT | |
| patient_key | BIGINT | FK |
| hospital_id | INT | |
| doctor_id | INT | |
| visit_date | TIMESTAMP | |
| diagnosis_code | VARCHAR(20) | |
