# Role-based access control

Enforced on every patient-specific clinical endpoint. Hiding a nav item is not security.

## Doctor

May attach to a patient who already has an account, edit clinical data, upload/assign files for **their** patients (assigned), interpret, view therapy/KG/provenance.

Must not mint a Patient ID. The ID is issued only when the patient creates an account.

Must not see another doctor's unassigned patients.

## Lab technician

May list **all** patients, uploads, and variants. May interpret, update laboratory report review notes, and view provenance.

Must not submit clinical workup / create patients.

## Patient

Identity comes from the authenticated session. Uploads attach automatically to the linked patient row. No manual assignment.

May view own clinical bundle, uploads, variants, reports, longitudinal observations, and provenance.

Must not interpret, change ACMG, or see other patients.

## Patient account linking

Patient signup creates the only Patient ID (`PAT-YYYY-NNNNNN`) and links
`patients.user_id` immediately. The same ID is required at patient login.

Doctor clinical workup must send that existing `patient_identifier`. It updates
the registered row and assigns the doctor. It does not create a second ID.

`GET /api/patient/me` resolves the linked record from the session. The browser
never supplies the patient ID for authorization.

## API messages

- `You do not have access to this patient.`
- `Patient identity could not be determined from the authenticated session.`
- `You do not have access to this upload.`
- `This action is limited to: doctor.`
