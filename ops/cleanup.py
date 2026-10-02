import sqlite3; db=sqlite3.connect('data/crm.db'); db.execute("PRAGMA foreign_keys=ON")
n=db.execute("DELETE FROM leads WHERE name IN ('Живой тест','Ольга (вручную)')").rowcount
db.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM lead_tags)"); db.commit(); print("удалено", n)
