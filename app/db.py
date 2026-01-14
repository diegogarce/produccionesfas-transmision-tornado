import pymysql
from datetime import datetime

from app.config import MYSQL_CONFIG


def create_db_connection():
    connection = pymysql.connect(**MYSQL_CONFIG)
    connection.autocommit(True)
    return connection


def _normalize_timestamps(row):
    normalized = row.copy()
    for key, value in row.items():
        if isinstance(value, datetime):
            normalized[key] = value.strftime("%Y-%m-%d %H:%M")
    return normalized
