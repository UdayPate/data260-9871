-- DATA-260 Homework 4, Part 3, requirement 8: the one index added.
-- Database: s9871_rel
--
-- Query used for the EXPLAIN comparison:
--   EXPLAIN SELECT * FROM fixtures WHERE fixture_name = 'Lions vs Tigers';
--
-- BEFORE the index:
--   type=ALL  possible_keys=NULL  key=NULL  key_len=NULL  ref=NULL
--   rows=4856  filtered=10.00  Extra=Using where          (full table scan)
--
-- AFTER the index:
--   type=ref  possible_keys=idx_fixture_name  key=idx_fixture_name
--   key_len=1022  ref=const  rows=1  filtered=100.00  Extra=NULL   (index lookup)
--
-- Applied with the mysql command-line client:
ALTER TABLE fixtures ADD INDEX idx_fixture_name (fixture_name);

-- To reproduce the "before" plan, drop the index and re-run the EXPLAIN:
-- ALTER TABLE fixtures DROP INDEX idx_fixture_name;