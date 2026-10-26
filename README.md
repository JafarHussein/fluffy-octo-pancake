# CareerForge

CareerForge is a data-driven resume tailoring project designed to help early-career developers align their resumes with job descriptions using structured career evidence.

Instead of asking an LLM to invent or rewrite a candidate's background, CareerForge starts with a structured PostgreSQL profile and uses a transparent strategy engine to evaluate evidence against a target role.

## Current capabilities

- PostgreSQL schema for structured career profiles, education, experience, projects, skills, certifications, and related records.
- Job-description input for resume strategy analysis.
- Heuristic matching of job requirements to available career evidence.
- A strategy report showing selected and omitted evidence, recognized requirements, and missing evidence.
- PowerShell scripts for local setup, database initialization, and running the strategy engine.
- Docker Compose configuration for a local PostgreSQL database.

**Current scope:** The public project currently generates a resume strategy report. Final DOCX/PDF resume generation and automated application submission are not claimed as implemented features.

## Requirements

- Windows with PowerShell
- Python and the dependencies listed in `requirements.txt`
- Docker Desktop with Docker Compose
- Git

## Getting started

1. Clone or download this repository.
2. Copy `.env.example` to `.env` and configure the local PostgreSQL connection settings.
3. Run the setup script:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\setup.ps1"
   ```

4. Start the PostgreSQL database:

   ```powershell
   docker compose up -d postgres
   ```

5. Initialize the database schema:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\resume\init-database.ps1"
   ```

6. Add your own career profile data to the local database. The example seed file is provided for demonstration:

   ```text
   database/seed_profile.example.sql
   ```

7. Create `input/job_description.txt` and add the target job description.
8. Run the strategy engine:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\generate-cv.ps1"
   ```

9. Review the generated report under `output/strategy/`.

Check `.env.example` and the database scripts before running commands. Use a disposable local database for testing.

## Configuration and privacy

- `.env` contains local configuration and must not be committed.
- Never commit real personal profiles, credentials, generated resumes, or database backups.
- `database/seed_profile.example.sql` should contain fictional demonstration data only.
- The contents of `input/` and `output/` are ignored by Git except for their `.gitkeep` placeholders.

## How the strategy works

The engine evaluates available career evidence against requirements detected in the target job description. The report contains selected evidence, omitted evidence, recognized requirements, and missing evidence.

Matching uses heuristics and requires human review. A detected keyword does not prove that a candidate has the corresponding skill, and missing evidence does not necessarily mean the candidate lacks that skill. Verify the profile and report before using the results in an application.

## Project structure

```text
config/                  Strategy, style, and ATS configuration
database/                PostgreSQL schema and example seed data
scripts/resume/          Strategy engine and database initialization
workflows/                Workflow definition
input/                    Local job-description input
output/                   Generated local reports
tests/                    Test suite
setup.ps1                 Local setup checks
generate-cv.ps1           Strategy execution entry point
docker-compose.yml        Local PostgreSQL service
requirements.txt          Python dependencies
```

## Development status

CareerForge is under active development. The strategy report is an intermediate artifact, not a guarantee of ATS compliance or interview success. Validate the output against representative test cases before relying on it.

## License

No license has been added yet. Until a license is selected and added, no additional permissions are granted by this project.
