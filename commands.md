1. Rebuild the empty database and user permissions

## python setup_db.py

2. Package up the new UUID models into migration instructions

## python manage.py makemigrations

3. Create the tables in the database

## python manage.py migrate_schemas

4. Rebuild the Public Router, State Offices, and Admins

## python manage.py seed_states

python manage.py setup_rbac

## Production tenant routing repair

Use this when a tenant endpoint fails with a missing tenant table such as
`relation "core_auditlog" does not exist` or `relation "facilities_facility" does not exist`.

1. Apply tenant migrations to the schema that should serve the API hostname

## python manage.py migrate_schemas --tenant -s plateau

2. Route the deployed API hostname to the tenant schema that should serve it

## python manage.py route_domain primary-health-care-api.vercel.app plateau

3. Confirm the hostname and required tenant tables are correct

## python manage.py check_tenant_schema plateau --domain primary-health-care-api.vercel.app
