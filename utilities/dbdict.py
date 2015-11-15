import sqlite3
from msgpack import packb, unpackb
from base64 import b64encode, b64decode
from collections import namedtuple
from functools import partial

def to_db(data):
    return b64encode(packb(data, use_bin_type=True))

def from_db(data):
    return unpackb(b64decode(data), use_list=False, encoding='utf-8')

# tuple_type should be a namedtuple if present
def convert_tuple(data, properties, convert, tuple_type=None):
    assert isinstance(data, tuple)
    converted = []
    for i,field_name in enumerate(tuple_type._fields if tuple_type else data._fields):
        converted.append(convert(data[i]) if properties[field_name].blob else data[i])
    return tuple_type(*converted) if tuple_type else tuple(converted)

# if data has the same fields as tuple_type, then no specific type is required to be passed since a regular tuple is fine when going into the db
def tuple_to_db(data, properties, tuple_type):
    return convert_tuple(data, properties, to_db, None if tuple_type._fields == data._fields else tuple_type)

def tuple_from_db(data, properties, tuple_type):
    return convert_tuple(data, properties, from_db, tuple_type)

# tuple_type is expected to be the default namedtuple of all values (key not included) that would be used in the regular case
def named_tuple_factory(cursor, row, properties, tuple_type):
    field_names = tuple(f[0] for f in cursor.description)
    return convert_tuple(row, properties, from_db, tuple_type if tuple_type._fields == field_names else namedtuple('tuple_type', ','.join(field_names)))

ColumnProperties = namedtuple('ColumnProperties', 'blob')

class DatabaseDictionary(object):
    # value_types determines what columns are stored for each key
    def __init__(self, file_name, value_types):
        assert len(value_types) != 0

        column_types = [('key', 'BLOB UNIQUE NOT NULL')] + value_types
        self.column_props = {c[0]: ColumnProperties('blob' in c[1].lower()) for c in column_types}

        values_sql = 'VALUES(null' + ',?' * len(column_types) + ')'
        self.insert_sql = 'INSERT INTO dictionary ' + values_sql
        self.insert_replace_sql = 'INSERT OR REPLACE INTO dictionary ' + values_sql
        self.select_sql = 'SELECT ' + ','.join(v[0] for v in value_types) + ' FROM dictionary WHERE key = ?'
        self.row_tuple = namedtuple('RowTuple', ','.join(v[0] for v in value_types))

        self.connection = sqlite3.connect(file_name, isolation_level = None)
        self.cursor = self.connection.cursor()
        self.cursor.row_factory = partial(named_tuple_factory, properties = self.column_props, tuple_type = self.row_tuple)

        self.cursor.execute('PRAGMA journal_mode=WAL')
        self.cursor.execute('PRAGMA synchronous=OFF')

        self.cursor.execute('CREATE TABLE IF NOT EXISTS dictionary (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,' + ','.join(v[0] + ' ' + v[1] for v in column_types) + ')')

    def get_random_filtered_key(self, filter_conditions):
        self.cursor.execute('SELECT key FROM dictionary WHERE ' + ' AND '.join(filter_conditions) + ' ORDER BY RANDOM() LIMIT 1')
        return self.cursor.fetchone()

    def get_random_key(self):
        self.cursor.execute('SELECT key FROM dictionary ORDER BY RANDOM() LIMIT 1')
        return self.cursor.fetchone()

    def __setitem__(self, key, value):
        self.cursor.execute(self.insert_replace_sql, (to_db(key),) + tuple_to_db(value, self.column_props, self.row_tuple))

    def __getitem__(self, key):
        value = self.get(key)
        if value == None:
            raise KeyError
        return value

    def __delitem__(self, key):
        self.__getitem__(key) # Will ensure key exists
        self.cursor.execute('DELETE FROM dictionary WHERE key = ?', (to_db(key),))

    def __len__(self):
        cursor = self.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM dictionary')
        return cursor.fetchone()[0]

    def update(self, other):
        self.cursor.executemany(self.insert_replace_sql, ((to_db(k),) + tuple_to_db(v, self.column_props, self.row_tuple) for k,v in other.iteritems()))

    def replace(self, other):
        self.cursor.execute('DELETE FROM dictionary')
        self.cursor.executemany(self.insert_sql, ((to_db(k),) + tuple_to_db(v, self.column_props, self.row_tuple) for k,v in other.iteritems()))

    def get(self, key):
        self.cursor.execute(self.select_sql, (to_db(key),))
        return self.cursor.fetchone()

    def keys(self):
        self.cursor.execute('SELECT key FROM dictionary')
        values = self.cursor.fetchall()
        return [v.key for v in values]

    def begin(self):
        self.cursor.execute('BEGIN')

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.commit()
        self.connection.close()