-- DATA-260 Homework 5, Part 1.I - the DDL that migrate_hw05.py actually
-- executed against s9871_rel on 2026-09-28 at 21:00:31 PDT.
-- Copied from the script's real console output (reports/hw05/RUN_LOG.txt,
-- section 1a), not hand-written.
--
-- WHY A SCRIPT AND NOT create_all(): the table already held 5,001 HW4
-- rows, and SQLAlchemy's Base.metadata.create_all() never ALTERs an
-- existing table. MySQL also will not accept a NOT NULL column on a
-- non-empty table without a value for the existing rows, so the columns
-- go on NULL-able, get backfilled, and are only then tightened.

-- Step 1: the related entity. Issued by create_all() for the new table.
CREATE TABLE teams (
    id INTEGER NOT NULL AUTO_INCREMENT,
    team_name VARCHAR(255) NOT NULL,          -- primary text field
    home_ground VARCHAR(255) NOT NULL,        -- secondary text field
    team_code VARCHAR(20) NOT NULL,           -- unique field, format TM-####
    created_at DATETIME NOT NULL DEFAULT (now()),
    updated_at DATETIME NOT NULL DEFAULT (now()),
    PRIMARY KEY (id),
    UNIQUE (team_code)
);
-- 12 teams then inserted (TM-0001 .. TM-0012).

-- Step 2: add the new columns to the primary entity, NULL-able for now.
ALTER TABLE fixtures ADD COLUMN fixture_code VARCHAR(24) NULL;
ALTER TABLE fixtures ADD COLUMN spots_available INT NOT NULL DEFAULT 22;
ALTER TABLE fixtures ADD COLUMN home_team_id INT NULL;
ALTER TABLE fixtures ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE fixtures ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Step 3: backfill all 5,001 existing rows. Both values are derived from
-- the row's own primary key, so the result is identical on every re-run
-- and no random number generator is involved.
UPDATE fixtures SET fixture_code = CONCAT('FX-9871-', LPAD(id, 5, '0'))
  WHERE fixture_code IS NULL;
UPDATE fixtures SET home_team_id = 1 + MOD(id - 1, 12)
  WHERE home_team_id IS NULL;

-- Step 4: tighten the constraints now that no NULLs remain.
ALTER TABLE fixtures MODIFY fixture_code VARCHAR(24) NOT NULL;
ALTER TABLE fixtures MODIFY home_team_id INT NOT NULL;
ALTER TABLE fixtures ADD CONSTRAINT uq_fixtures_fixture_code UNIQUE (fixture_code);
ALTER TABLE fixtures ADD CONSTRAINT fk_fixtures_home_team
  FOREIGN KEY (home_team_id) REFERENCES teams (id) ON DELETE RESTRICT;

-- ON DELETE RESTRICT is the documented anti-cascade choice: deleting a
-- team that is still the home team of any fixture is refused by MySQL
-- with error 1451, independently of the API's own 409 check.
