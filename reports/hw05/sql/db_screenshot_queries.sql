-- DATA-260 Homework 5, Part 1.II - "Submit a screenshot of your DB".
-- Paste this whole file into MySQL Workbench (or the mysql CLI) and run it.
-- It is read-only: no INSERT, UPDATE, DELETE or DDL.
--
-- The five result grids together show everything the requirement asks for:
-- both tables exist, the related entity has its unique field and timestamps,
-- the primary entity has its unique code / defaulted numeric field / foreign
-- key, the relationship actually joins, and no password is stored in clear.

USE s9871_rel;

-- 1. The tables in the database.
SHOW TABLES;

-- 2. The related entity's structure (id, primary text, secondary text,
--    unique field, timestamps).
DESCRIBE teams;

-- 3. The primary entity's structure (id, primary field, unique code,
--    defaulted numeric field, foreign key, timestamps).
DESCRIBE fixtures;

-- 4. The foreign key and its ON DELETE rule, read from the catalogue.
SELECT rc.constraint_name,
       rc.table_name,
       kcu.column_name,
       CONCAT(kcu.referenced_table_name, '.', kcu.referenced_column_name) AS refs,
       rc.delete_rule
FROM information_schema.referential_constraints rc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = rc.constraint_name
 AND kcu.constraint_schema = rc.constraint_schema
WHERE rc.constraint_schema = 's9871_rel'
ORDER BY rc.constraint_name;

-- 5. The relationship joined, plus row counts per team.
SELECT t.id            AS team_id,
       t.team_code,
       t.team_name,
       t.home_ground,
       COUNT(f.id)     AS fixtures_hosted,
       MIN(f.fixture_code) AS first_fixture_code,
       MIN(f.spots_available) AS min_spots,
       MAX(f.spots_available) AS max_spots
FROM teams t
LEFT JOIN fixtures f ON f.home_team_id = t.id
GROUP BY t.id, t.team_code, t.team_name, t.home_ground
ORDER BY t.id;

-- 6. A sample of joined rows, showing the fixture -> team relationship.
SELECT f.id, f.fixture_code, f.fixture_name, f.spots_available,
       f.home_team_id, t.team_code, t.team_name, f.created_at
FROM fixtures f
JOIN teams t ON t.id = f.home_team_id
ORDER BY f.id
LIMIT 10;

-- 7. Total rows, and proof that credentials are stored hashed, never in clear.
SELECT (SELECT COUNT(*) FROM teams)    AS teams,
       (SELECT COUNT(*) FROM fixtures) AS fixtures;

SELECT id, name, email,
       LEFT(password_hash, 7)   AS hash_prefix,
       LENGTH(password_hash)    AS hash_length
FROM users;
