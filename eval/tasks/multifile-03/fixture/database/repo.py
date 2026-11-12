from database.connection import Connection


class Repo:
    def __init__(self): self.conn = Connection()
    def find_all(self): return self.conn.execute('SELECT *')
