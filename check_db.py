import sqlite3, os
p = os.path.abspath(r'.\database\mdr_project.db')
print("DB:", p)
con = sqlite3.connect(p)
rows = con.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type,name").fetchall()
print(rows)
con.close()
