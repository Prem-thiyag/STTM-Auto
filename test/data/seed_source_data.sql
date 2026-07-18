-- Synthetic test/dev seed data for source_db (raw.*).
-- Entirely fictional -- no real patients, doctors, or facilities.
-- Deliberately messy in the ways source_schema.md documents (mixed-case emails,
-- inconsistent phone formats, Y/N flags, string dates) so the UDF-driven
-- transformations (udf_clean_email, udf_clean_phone, udf_flag_to_boolean,
-- udf_parse_date, udf_parse_time, udf_full_name, hashdiff generation) have
-- something real to do when /execute runs.
--
-- Load with: psql -d source_db -f test/data/seed_source_data.sql
-- Run AFTER /seed and /execute's bootstrap step (raw.* tables must already exist).

BEGIN;

-- ---------------------------------------------------------------- facilities
INSERT INTO raw.facilities (facility_id, facility_name, facility_type, address_line1, city, state, pincode, phone, email, bed_count, accreditation, is_active, created_at, updated_at) VALUES
    ('FAC-0001', 'Apollo General Hospital', 'Hospital', '21 Anna Salai', 'Chennai', 'TN', '600002', '044-28291234', 'INFO@apollogeneral.in', 320, 'NABH', 'Y', '2019-03-11 09:00:00', '2026-06-01 10:15:00'),
    ('FAC-0002', 'Fortis City Clinic', 'Clinic', '88 Linking Road', 'Mumbai', 'MH', '400050', '+91 22 6612 9090', 'contact@FortisCityClinic.in', 40, 'JCI', 'Y', '2020-07-22 11:30:00', '2026-05-14 08:40:00'),
    ('FAC-0003', 'Max Diagnostic Center', 'Diagnostic Center', '5 Connaught Place', 'New Delhi', 'DL', '110001', '(011) 4155-7788', 'diagnostics@maxcenter.in', 0, 'None', 'Y', '2018-01-05 08:00:00', '2026-04-30 17:05:00'),
    ('FAC-0004', 'Manipal Hospital', 'Hospital', '98 Old Airport Road', 'Bangalore', 'KA', '560017', '080-25023344', 'Reception@ManipalHospital.in', 250, 'NABH', 'Y', '2017-09-18 09:00:00', '2026-06-10 12:00:00'),
    ('FAC-0005', 'City Care Clinic', 'Clinic', '14 Banjara Hills', 'Hyderabad', 'TG', '500034', '040 2354 6677', 'hello@citycareclinic.in', 15, 'None', 'N', '2021-02-14 10:00:00', '2025-11-20 09:30:00');

-- ------------------------------------------------------------------- doctors
INSERT INTO raw.doctors (doctor_id, first_name, last_name, specialization, qualification, license_number, email, phone, years_of_experience, facility_id, consultation_fee, is_active, created_at, updated_at) VALUES
    ('DOC-0001', 'Ramesh', 'Kumar', 'Cardiology', 'MBBS, MD (Cardiology)', 'TNMC-CARD-1001', 'Ramesh.Kumar@apollogeneral.in', '9840012345', 18, 'FAC-0001', 1200.00, 'Y', '2019-04-01 09:00:00', '2026-05-01 09:00:00'),
    ('DOC-0002', 'Anita', 'Sharma', 'Neurology', 'MBBS, DM (Neurology)', 'TNMC-NEURO-1002', 'anita.sharma@APOLLOGENERAL.in', '+91-98400-22345', 12, 'FAC-0001', 1500.00, 'Y', '2020-01-15 09:00:00', '2026-05-01 09:00:00'),
    ('DOC-0003', 'Suresh', 'Reddy', 'Oncology', 'MBBS, MD (Oncology)', 'KMC-ONCO-2003', 'suresh.reddy@manipalhospital.in', '080-2502-9911', 22, 'FAC-0004', 1800.00, 'Y', '2016-08-20 09:00:00', '2026-05-01 09:00:00'),
    ('DOC-0004', 'Priya', 'Nair', 'Pediatrics', 'MBBS, MD (Pediatrics)', 'MMC-PED-3004', 'Priya.Nair@fortiscityclinic.in', '9820098765', 9, 'FAC-0002', 900.00, 'Y', '2021-06-10 09:00:00', '2026-05-01 09:00:00'),
    ('DOC-0005', 'Vikram', 'Singh', 'Orthopedics', 'MBBS, MS (Ortho)', 'KMC-ORTHO-2005', 'vikram.singh@ManipalHospital.in', '(080) 2502-4477', 15, 'FAC-0004', 1300.00, 'Y', '2018-11-02 09:00:00', '2026-05-01 09:00:00'),
    ('DOC-0006', 'Meera', 'Iyer', 'Dermatology', 'MBBS, MD (Derm)', 'MMC-DERM-3006', 'meera.iyer@fortiscityclinic.in', '9833011223', 7, 'FAC-0002', 800.00, 'Y', '2022-03-05 09:00:00', '2026-05-01 09:00:00'),
    ('DOC-0007', 'Arjun', 'Menon', 'General Medicine', 'MBBS', 'TGMC-GEN-4007', 'ARJUN.MENON@citycareclinic.in', '040-23540099', 5, 'FAC-0005', 500.00, 'N', '2023-01-20 09:00:00', '2025-10-01 09:00:00'),
    ('DOC-0008', 'Kavita', 'Rao', 'Gynecology', 'MBBS, MD (OBG)', 'DMC-GYN-5008', 'kavita.rao@maxcenter.in', '+91 98111 22334', 14, 'FAC-0003', 1100.00, 'Y', '2019-09-09 09:00:00', '2026-05-01 09:00:00');

-- ------------------------------------------------------------------ patients
INSERT INTO raw.patients (patient_id, first_name, last_name, date_of_birth, gender, email, phone, address_line1, city, state, pincode, blood_group, is_active, created_at, updated_at) VALUES
    ('PAT-0001', 'Lakshmi', 'Venkatesan', '1985-04-12', 'F', 'Lakshmi.V@gmail.com', '9884411223', '12 Kamaraj Nagar', 'Chennai', 'TN', '600020', 'O+', 'Y', '2023-01-10 10:00:00', '2026-06-01 10:00:00'),
    ('PAT-0002', 'Rahul', 'Deshmukh', '1990-11-03', 'M', 'RAHUL.DESHMUKH@yahoo.com', '+91-98200-33445', '45 Andheri West', 'Mumbai', 'MH', '400058', 'A+', 'Y', '2023-02-14 11:00:00', '2026-06-02 11:00:00'),
    ('PAT-0003', 'Sneha', 'Kapoor', '1978-07-25', 'F', 'sneha.kapoor@hotmail.com', '011-41556677', '9 Karol Bagh', 'New Delhi', 'DL', '110005', 'B+', 'Y', '2023-03-01 09:30:00', '2026-06-03 09:30:00'),
    ('PAT-0004', 'Arvind', 'Bhat', '1965-01-30', 'M', 'Arvind.Bhat@gmail.com', '9900112233', '77 Indiranagar', 'Bangalore', 'KA', '560038', 'AB-', 'Y', '2023-03-15 14:00:00', '2026-06-04 14:00:00'),
    ('PAT-0005', 'Divya', 'Pillai', '2001-09-18', 'F', 'divya.pillai@gmail.com', '(040) 2356-8899', '3 Jubilee Hills', 'Hyderabad', 'TG', '500033', 'O-', 'Y', '2023-04-02 10:15:00', '2026-06-05 10:15:00'),
    ('PAT-0006', 'Manoj', 'Tiwari', '1955-05-05', 'M', 'MANOJ.TIWARI@rediffmail.com', '9871122334', '18 Rohini Sector 5', 'New Delhi', 'DL', '110085', 'B-', 'N', '2023-04-20 08:45:00', '2025-09-10 08:45:00'),
    ('PAT-0007', 'Kavya', 'Reddy', '1998-12-22', 'F', 'kavya.reddy@gmail.com', '9848899001', '22 Banjara Hills', 'Hyderabad', 'TG', '500034', 'A-', 'Y', '2023-05-05 16:20:00', '2026-06-06 16:20:00'),
    ('PAT-0008', 'Sanjay', 'Joshi', '1982-03-08', 'M', 'sanjay.joshi@outlook.com', '+91 98220 55667', '61 FC Road', 'Pune', 'MH', '411004', 'O+', 'Y', '2023-05-19 12:00:00', '2026-06-07 12:00:00'),
    ('PAT-0009', 'Nisha', 'Agarwal', '1993-06-14', 'F', 'Nisha.Agarwal@gmail.com', '9811223344', '5 Connaught Place', 'New Delhi', 'DL', '110001', 'AB+', 'Y', '2023-06-01 09:00:00', '2026-06-08 09:00:00'),
    ('PAT-0010', 'Ganesh', 'Iyer', '1970-10-10', 'M', 'ganesh.iyer@yahoo.com', '9884433221', '30 T Nagar', 'Chennai', 'TN', '600017', 'B+', 'Y', '2023-06-15 15:30:00', '2026-06-09 15:30:00'),
    ('PAT-0011', 'Pooja', 'Malhotra', '1988-02-27', 'F', 'POOJA.MALHOTRA@gmail.com', '9911002233', '14 Model Town', 'New Delhi', 'DL', '110009', 'O+', 'Y', '2023-07-01 13:00:00', '2026-06-10 13:00:00'),
    ('PAT-0012', 'Kiran', 'Kumar', '1960-08-19', 'M', 'kiran.kumar@gmail.com', '080-41223344', '55 Malleshwaram', 'Bangalore', 'KA', '560003', 'A+', 'N', '2023-07-10 10:00:00', '2025-08-15 10:00:00');

-- ----------------------------------------------------------------- insurance
INSERT INTO raw.insurance (insurance_id, patient_id, provider_name, policy_number, plan_type, coverage_amount, premium_amount, start_date, end_date, is_active, created_at, updated_at) VALUES
    ('INS-0001', 'PAT-0001', 'Star Health Insurance', 'SH-2023-001122', 'Individual', 500000.00, 12000.00, '2023-01-15', '2027-01-14', 'Y', '2023-01-15 10:00:00', '2026-06-01 10:00:00'),
    ('INS-0002', 'PAT-0002', 'HDFC ERGO', 'HE-2023-004455', 'Family', 1000000.00, 22000.00, '2023-02-20', '2027-02-19', 'Y', '2023-02-20 11:00:00', '2026-06-02 11:00:00'),
    ('INS-0003', 'PAT-0003', 'ICICI Lombard', 'IL-2023-007788', 'Individual', 300000.00, 8000.00, '2023-03-05', '2026-03-04', 'Y', '2023-03-05 09:30:00', '2026-06-03 09:30:00'),
    ('INS-0004', 'PAT-0005', 'Star Health Insurance', 'SH-2023-009900', 'Individual', 400000.00, 9500.00, '2023-04-10', '2027-04-09', 'Y', '2023-04-10 10:15:00', '2026-06-05 10:15:00'),
    ('INS-0005', 'PAT-0008', 'Bajaj Allianz', 'BA-2023-002233', 'Group', 750000.00, 15000.00, '2023-05-25', '2027-05-24', 'Y', '2023-05-25 12:00:00', '2026-06-07 12:00:00'),
    ('INS-0006', 'PAT-0009', 'HDFC ERGO', 'HE-2023-006677', 'Individual', 350000.00, 8800.00, '2023-06-05', '2026-06-04', 'N', '2023-06-05 09:00:00', '2025-12-01 09:00:00');

-- -------------------------------------------------------------- appointments
INSERT INTO raw.appointments (appointment_id, patient_id, doctor_id, facility_id, appointment_date, appointment_time, appointment_type, status, diagnosis_code, diagnosis_description, notes, billing_amount, created_at, updated_at) VALUES
    ('APT-0001', 'PAT-0001', 'DOC-0001', 'FAC-0001', '2026-06-01', '09:30', 'In-Person', 'Completed', 'I10', 'Essential hypertension', 'Patient advised to reduce salt intake, follow up in 3 months.', 1200.00, '2026-05-25 10:00:00', '2026-06-01 10:00:00'),
    ('APT-0002', 'PAT-0002', 'DOC-0004', 'FAC-0002', '2026-06-02', '11:00', 'In-Person', 'Completed', 'J06.9', 'Acute upper respiratory infection', 'Prescribed antibiotics for 5 days.', 900.00, '2026-05-26 11:00:00', '2026-06-02 11:00:00'),
    ('APT-0003', 'PAT-0003', 'DOC-0002', 'FAC-0001', '2026-06-03', '15:00', 'Teleconsult', 'Completed', 'G43.9', 'Migraine, unspecified', 'Recommended MRI if symptoms persist.', 1500.00, '2026-05-27 09:30:00', '2026-06-03 15:00:00'),
    ('APT-0004', 'PAT-0004', 'DOC-0003', 'FAC-0004', '2026-06-04', '10:00', 'In-Person', 'Completed', 'C50.9', 'Malignant neoplasm of breast, unspecified', 'Referred to oncology for further tests.', 1800.00, '2026-05-28 14:00:00', '2026-06-04 10:00:00'),
    ('APT-0005', 'PAT-0005', 'DOC-0006', 'FAC-0002', '2026-06-05', '16:30', 'In-Person', 'Completed', 'L70.0', 'Acne vulgaris', 'Prescribed topical treatment.', 800.00, '2026-05-29 10:15:00', '2026-06-05 16:30:00'),
    ('APT-0006', 'PAT-0006', 'DOC-0007', 'FAC-0005', '2026-06-06', '08:45', 'In-Person', 'No-Show', NULL, NULL, NULL, 0.00, '2026-05-30 08:45:00', '2026-06-06 09:00:00'),
    ('APT-0007', 'PAT-0007', 'DOC-0008', 'FAC-0003', '2026-06-07', '17:15', 'In-Person', 'Completed', 'Z34.9', 'Encounter for supervision of normal pregnancy, unspecified', 'Routine prenatal checkup, all normal.', 1100.00, '2026-05-31 16:20:00', '2026-06-07 17:15:00'),
    ('APT-0008', 'PAT-0008', 'DOC-0005', 'FAC-0004', '2026-06-08', '12:00', 'In-Person', 'Scheduled', NULL, NULL, NULL, 0.00, '2026-06-01 12:00:00', '2026-06-01 12:00:00'),
    ('APT-0009', 'PAT-0009', 'DOC-0001', 'FAC-0001', '2026-06-09', '09:00', 'In-Person', 'Cancelled', NULL, NULL, 'Patient cancelled due to travel.', 0.00, '2026-06-02 09:00:00', '2026-06-08 18:00:00'),
    ('APT-0010', 'PAT-0010', 'DOC-0003', 'FAC-0004', '2026-06-10', '15:30', 'In-Person', 'Completed', 'E11.9', 'Type 2 diabetes mellitus without complications', 'Adjusted insulin dosage.', 1800.00, '2026-06-03 15:30:00', '2026-06-10 15:30:00'),
    ('APT-0011', 'PAT-0011', 'DOC-0002', 'FAC-0001', '2026-06-11', '13:00', 'Teleconsult', 'Completed', 'G47.00', 'Insomnia, unspecified', 'Recommended sleep hygiene and follow-up in 4 weeks.', 1500.00, '2026-06-04 13:00:00', '2026-06-11 13:00:00'),
    ('APT-0012', 'PAT-0001', 'DOC-0006', 'FAC-0002', '2026-06-12', '10:00', 'In-Person', 'Completed', 'L30.9', 'Dermatitis, unspecified', 'Prescribed antihistamine cream.', 800.00, '2026-06-05 10:00:00', '2026-06-12 10:00:00'),
    ('APT-0013', 'PAT-0004', 'DOC-0005', 'FAC-0004', '2026-06-13', '11:30', 'In-Person', 'Completed', 'M17.9', 'Osteoarthritis of knee, unspecified', 'Recommended physiotherapy sessions.', 1300.00, '2026-06-06 11:30:00', '2026-06-13 11:30:00'),
    ('APT-0014', 'PAT-0007', 'DOC-0004', 'FAC-0002', '2026-06-14', '14:45', 'In-Person', 'Scheduled', NULL, NULL, NULL, 0.00, '2026-06-07 14:45:00', '2026-06-07 14:45:00'),
    ('APT-0015', 'PAT-0010', 'DOC-0001', 'FAC-0001', '2026-06-15', '09:15', 'In-Person', 'Completed', 'I25.10', 'Atherosclerotic heart disease', 'Prescribed statins, follow up in 6 weeks.', 1200.00, '2026-06-08 09:15:00', '2026-06-15 09:15:00');

-- ------------------------------------------------------------------ medications
INSERT INTO raw.medications (medication_id, appointment_id, patient_id, doctor_id, drug_name, dosage, duration_days, prescribed_date, is_chronic, created_at, updated_at) VALUES
    ('MED-0001', 'APT-0001', 'PAT-0001', 'DOC-0001', 'Amlodipine', '5mg once daily', 90, '2026-06-01', 'Y', '2026-06-01 10:05:00', '2026-06-01 10:05:00'),
    ('MED-0002', 'APT-0002', 'PAT-0002', 'DOC-0004', 'Amoxicillin', '500mg three times daily', 5, '2026-06-02', 'N', '2026-06-02 11:05:00', '2026-06-02 11:05:00'),
    ('MED-0003', 'APT-0003', 'PAT-0003', 'DOC-0002', 'Sumatriptan', '50mg as needed', 30, '2026-06-03', 'N', '2026-06-03 15:05:00', '2026-06-03 15:05:00'),
    ('MED-0004', 'APT-0004', 'PAT-0004', 'DOC-0003', 'Tamoxifen', '20mg once daily', 180, '2026-06-04', 'Y', '2026-06-04 10:05:00', '2026-06-04 10:05:00'),
    ('MED-0005', 'APT-0005', 'PAT-0005', 'DOC-0006', 'Clindamycin gel', 'apply twice daily', 60, '2026-06-05', 'N', '2026-06-05 16:35:00', '2026-06-05 16:35:00'),
    ('MED-0006', 'APT-0007', 'PAT-0007', 'DOC-0008', 'Folic Acid', '5mg once daily', 90, '2026-06-07', 'Y', '2026-06-07 17:20:00', '2026-06-07 17:20:00'),
    ('MED-0007', 'APT-0010', 'PAT-0010', 'DOC-0003', 'Metformin', '1000mg twice daily', 90, '2026-06-10', 'Y', '2026-06-10 15:35:00', '2026-06-10 15:35:00'),
    ('MED-0008', 'APT-0011', 'PAT-0011', 'DOC-0002', 'Melatonin', '3mg at bedtime', 30, '2026-06-11', 'N', '2026-06-11 13:05:00', '2026-06-11 13:05:00'),
    ('MED-0009', 'APT-0012', 'PAT-0001', 'DOC-0006', 'Cetirizine', '10mg once daily', 14, '2026-06-12', 'N', '2026-06-12 10:05:00', '2026-06-12 10:05:00'),
    ('MED-0010', 'APT-0015', 'PAT-0010', 'DOC-0001', 'Atorvastatin', '20mg once daily', 180, '2026-06-15', 'Y', '2026-06-15 09:20:00', '2026-06-15 09:20:00');

COMMIT;
