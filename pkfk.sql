SHOW TRIGGERS FROM pharmenia;
SHOW PROCEDURE STATUS WHERE Db='pharmenia';
SHOW FUNCTION STATUS WHERE Db='pharmenia';
SHOW FULL TABLES IN pharmenia WHERE Table_type='VIEW';

-- PK/FK list
SELECT table_name, constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema='pharmenia'
  AND constraint_type IN ('PRIMARY KEY','FOREIGN KEY')
ORDER BY table_name, constraint_type;
