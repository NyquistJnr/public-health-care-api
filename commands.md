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
`relation "core_user" does not exist`, `relation "core_patientprofile" does not exist`,
`relation "core_auditlog" does not exist`, `relation "facilities_facility" does not exist`,
or another tenant app table.

Recommended one-command repair:

## python manage.py repair_tenant_schema plateau --domain primary-health-care-api.vercel.app

This runs tenant migrations for `plateau`, routes the Vercel hostname to `plateau`,
and validates every expected tenant app table.

If errors continue, confirm the running app and repair command are using the same database:

## python manage.py diagnose_tenant_routing --domain primary-health-care-api.vercel.app --schema plateau

If the CLI shows the tenant schema is healthy but HTTP requests still fail with
missing tenant tables, redeploy the app so `TenantHostFallbackMiddleware` can
correct the tenant from Vercel/proxy host headers before authentication runs.

Manual repair steps:

1. Apply tenant migrations to the schema that should serve the API hostname

## python manage.py migrate_schemas --tenant -s plateau

2. Route the deployed API hostname to the tenant schema that should serve it

## python manage.py route_domain primary-health-care-api.vercel.app plateau

3. Confirm the hostname and all required tenant app tables are correct

## python manage.py check_tenant_schema plateau --domain primary-health-care-api.vercel.app

4. Optional: check every non-public tenant schema for missing tenant app tables

## python manage.py check_tenant_schema --all-tenants
