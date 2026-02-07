PRAGMA foreign_keys = ON;
BEGIN;

-- Disciplines
INSERT OR IGNORE INTO disciplines(discipline_code, name_e, name_p)
SELECT DISTINCT
  TRIM(Discipline_Code),
  TRIM(Discipline_Name_E),
  TRIM(Discipline_Name_P)
FROM pkg_raw
WHERE Discipline_Code IS NOT NULL AND TRIM(Discipline_Code) <> '';

-- Packages
INSERT OR IGNORE INTO packages(discipline_code, package_code, package_name_e, package_name_p)
SELECT
  TRIM(Discipline_Code),
  TRIM(Package_Code),
  TRIM(Package_Name_E),
  TRIM(Package_Name_P)
FROM pkg_raw
WHERE TRIM(Discipline_Code) <> ''
  AND TRIM(Package_Code) <> ''
  AND TRIM(Package_Name_E) <> '';

COMMIT;
