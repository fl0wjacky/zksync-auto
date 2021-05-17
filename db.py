import sqlite3

class DB:
    def __init__(self, logging):
        self.logging = logging
        self.con = sqlite3.connect("zksync.db")
        self.cur = self.con.cursor()
        # create table
        with open("tables.sql", "r") as f:
            create_table_sql = f.read()
            try:
                self.cur.executescript(create_table_sql)
                self.con.commit()
            except Exception as e:
                self.close()
                self.logging.error(e)
                raise

    def get_addresses(self, status):
        sql = "select address,prikey from wallets where status=%s" % status
        self.cur.execute(sql)
        return self.cur.fetchall()

    def get_prikeys(self, status):
        sql = "select prikey from wallets where status=%s" % status
        self.cur.execute(sql)
        return self.cur.fetchall()

    def update_address(self, address, key, value):
        sql = "UPDATE wallets SET %s=%s WHERE address='%s'" % (key, value, address)
        try:
            self.cur.execute(sql)
            self.con.commit()
        except Exception as e:
            self.close()
            self.logging.error(e)
            raise

    def update_prikey(self, prikey, key, value):
        sql = "UPDATE wallets SET %s=%s WHERE prikey='%s'" % (key, value, prikey)
        try:
            self.cur.execute(sql)
            self.con.commit()
        except Exception as e:
            self.close()
            self.logging.error(e)
            raise
    
    def count_status(self, status):
        sql = "SELECT COUNT(id) FROM wallets WHERE status=%s" % status
        try:
            self.cur.execute(sql)
            return self.cur.fetchone()[0]
        except Exception as e:
            self.close()
            self.logging.error(e)
            raise

    def insert_new_wallet(self, seed, prikey, address):
        sql = "INSERT INTO wallets (seed,prikey,address) VALUES ('%s','%s','%s')" % (seed, prikey, address)
        try:
            self.cur.execute(sql)
            self.con.commit()
        except Exception as e:
            self.close()
            self.logging.error(e)
            raise

    def close(self):
        self.cur.close()
        self.con.close()
