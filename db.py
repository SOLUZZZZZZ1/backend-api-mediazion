import os
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta DATABASE_URL en el entorno")

# Intentar psycopg v3 primero
try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
    _PSYCOPG3 = True
except Exception:
    _PSYCOPG3 = False

# Fallback a psycopg2
if not _PSYCOPG3:
    try:
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Necesitas instalar 'psycopg' (v3) o 'psycopg2-binary' para conectarte a PostgreSQL"
        ) from e

@contextmanager
def pg_conn():
    """
    Context manager que devuelve una conexión PostgreSQL lista para usar.
    - Soporta psycopg v3 o psycopg2 automáticamente.
    - Hace commit en éxito y rollback en excepción.
    """
    if _PSYCOPG3:
        conn = psycopg.connect(DATABASE_URL, autocommit=False, row_factory=dict_row)  # type: ignore
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = psycopg2.connect(DATABASE_URL)  # type: ignore
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
