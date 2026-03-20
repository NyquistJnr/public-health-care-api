1. Rebuild the empty database and user permissions

## python setup_db.py

2. Package up the new UUID models into migration instructions

## python manage.py makemigrations

3. Create the tables in the database

## python manage.py migrate_schemas

4. Rebuild the Public Router, State Offices, and Admins

## python manage.py seed_states

python manage.py setup_rbac
