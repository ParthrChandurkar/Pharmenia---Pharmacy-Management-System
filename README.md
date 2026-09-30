# Pharmenia Pharmacy Management System

Pharmenia is a Python desktop application backed by MySQL for managing medicines, suppliers, customers, inventory, and invoices. The database scripts define the schema and supporting triggers, functions, procedures, views, and cursor-based FIFO stock allocation.

## Features

- Medicine, supplier, customer, and inventory management
- Invoice creation with FIFO batch allocation
- Trigger- and procedure-backed database operations
- PDF invoice generation with ReportLab
- Backup utility and Tkinter administrative interface

## Architecture

`pharmenia_admin_app.py` provides the desktop user interface and database operations. The SQL files initialize and extend the MySQL schema:

- `pharmenia.sql` creates the base database objects.
- `norm.sql` contains the normalized schema work.
- `trig_cursor.sql` defines triggers and cursor logic.
- `stored_proce.sql`, `functions.sql`, and `views.sql` define reusable database behavior.
- `pkfk.sql` helps inspect keys and database objects.

## Getting Started

Prerequisites: Python 3, MySQL, and Tk support.

```bash
python -m pip install mysql-connector-python reportlab
```

Load the database schema in MySQL, then apply the remaining SQL files according to their dependencies:

```sql
SOURCE pharmenia.sql;
```

Review the connection settings in `pharmenia_admin_app.py`, then run:

```bash
python pharmenia_admin_app.py
```

## Security Note

The application contains demonstration-oriented local login and database configuration. Replace hardcoded values and use environment-based secret management before deploying it outside a controlled academic environment.

## Limitations

- There is no dependency lock file or automated test suite.
- Setup is oriented toward a local MySQL installation.
- Authentication and secret handling require further work for shared or hosted use.

