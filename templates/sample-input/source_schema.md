# Source Schema

## PATIENT_MASTER
| Column | Type | PK |
|---|---|---|
| patient_id | INT | Y |
| first_name | VARCHAR(100) | |
| last_name | VARCHAR(100) | |
| gender | VARCHAR(10) | |
| dob | DATE | |
| phone | VARCHAR(20) | |

## VISIT_MASTER
| Column | Type | PK |
|---|---|---|
| visit_id | INT | Y |
| patient_id | INT | FK |
| hospital_id | INT | |
| doctor_id | INT | |
| visit_date | TIMESTAMP | |
| diagnosis_code | VARCHAR(20) | |
