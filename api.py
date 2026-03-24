"""
API helpers for managing database operations across SQLite and PostgreSQL
"""
import os
import logging
from database_config import get_db_connection, is_postgres

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Handle database operations for both SQLite and PostgreSQL"""
    
    @staticmethod
    def execute_query(query, params=None, fetch=False, fetch_all=False):
        """Execute a query and return results"""
        try:
            conn, db_type = get_db_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if fetch:
                result = cursor.fetchone()
                conn.close()
                return result
            elif fetch_all:
                result = cursor.fetchall()
                conn.close()
                return result
            else:
                conn.commit()
                conn.close()
                return cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
        except Exception as e:
            logger.error(f'Database error: {e}')
            raise

    @staticmethod
    def get_connection():
        """Get raw database connection"""
        return get_db_connection()