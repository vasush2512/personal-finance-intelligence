"""Steps 11-15 - the database side.

Each module here is the bridge between one pure pipeline module and
SQLAlchemy. Route handlers call these; they never reach past them into
the pipeline.
"""
