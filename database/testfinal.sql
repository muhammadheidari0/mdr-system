SELECT 'projects' AS t, COUNT(*) AS n FROM projects
UNION ALL SELECT 'mdr_categories', COUNT(*) FROM mdr_categories
UNION ALL SELECT 'phases', COUNT(*) FROM phases
UNION ALL SELECT 'levels', COUNT(*) FROM levels
UNION ALL SELECT 'disciplines', COUNT(*) FROM disciplines
UNION ALL SELECT 'packages', COUNT(*) FROM packages
UNION ALL SELECT 'mdr_records', COUNT(*) FROM mdr_records;
