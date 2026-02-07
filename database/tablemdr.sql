PRAGMA foreign_keys = ON;

BEGIN;

-- 1) Projects
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_code TEXT NOT NULL UNIQUE,     -- مثل T202
  project_name TEXT,
  root_path    TEXT,                      -- مسیر روت فولدر پروژه روی سرور/کامپیوتر
  is_active    INTEGER NOT NULL DEFAULT 1,
  docnum_template TEXT NOT NULL DEFAULT '{PROJECT}-{MDR}{PKG}-{BLK}{LVL}'
);

-- 2) MDR Categories (Engineering/Procurement/Construction)
CREATE TABLE IF NOT EXISTS mdr_categories (
  name TEXT PRIMARY KEY,
  letter TEXT NOT NULL
);

-- 3) Phases
CREATE TABLE IF NOT EXISTS phases (
  ph_name_e TEXT PRIMARY KEY,
  ph_name_p TEXT NOT NULL,
  ph_code   TEXT NOT NULL
);

-- 4) Levels (طبقات)
CREATE TABLE IF NOT EXISTS levels (
  name_e TEXT PRIMARY KEY,     -- GEN, B01, L01, RF1...
  name_p TEXT,
  code INTEGER,
  sort_order INTEGER
);

-- 5) Disciplines
CREATE TABLE IF NOT EXISTS disciplines (
  discipline_code TEXT PRIMARY KEY,  -- AR, ME, EL, ST, ...
  name_e TEXT NOT NULL,
  name_p TEXT
);

-- 6) Packages (پکیج‌ها)
CREATE TABLE IF NOT EXISTS packages (
  discipline_code TEXT NOT NULL,
  package_code TEXT NOT NULL,        -- AR13 / ME01 / ...
  package_name_e TEXT NOT NULL,
  package_name_p TEXT,
  PRIMARY KEY (discipline_code, package_code),
  UNIQUE (discipline_code, package_name_e),
  FOREIGN KEY (discipline_code) REFERENCES disciplines(discipline_code)
);

-- 7) MDR Records (رکوردهای اصلی)
CREATE TABLE IF NOT EXISTS mdr_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  project_id INTEGER NOT NULL,

  row_no REAL,                       -- 1.0, 2.0...
  mdr_category TEXT NOT NULL,         -- Engineering/Procurement/Construction
  phase_name_e TEXT NOT NULL,         -- یکی از phases
  discipline_code TEXT NOT NULL,      -- AR/ME/...
  package_code TEXT NOT NULL,         -- AR13/ME01/...
  block TEXT NOT NULL,               -- T/A/B/...
  level_name_e TEXT NOT NULL,         -- GEN/B08/L01...

  document_title_e TEXT NOT NULL,
  document_title_p TEXT NOT NULL,
  subject_e TEXT,
  subject_p TEXT,

  serial_number REAL NOT NULL DEFAULT 1.0,
  document_number TEXT NOT NULL UNIQUE,

  folder_path TEXT,

  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (mdr_category) REFERENCES mdr_categories(name),
  FOREIGN KEY (phase_name_e) REFERENCES phases(ph_name_e),
  FOREIGN KEY (discipline_code) REFERENCES disciplines(discipline_code),
  FOREIGN KEY (level_name_e) REFERENCES levels(name_e),
  FOREIGN KEY (discipline_code, package_code) REFERENCES packages(discipline_code, package_code)
);

-- Indexes برای سرعت
CREATE INDEX IF NOT EXISTS idx_mdr_docnum ON mdr_records(document_number);
CREATE INDEX IF NOT EXISTS idx_mdr_filters ON mdr_records(project_id, mdr_category, phase_name_e, discipline_code, package_code, block, level_name_e);

COMMIT;
