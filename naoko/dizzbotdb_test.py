# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
import MySQLdb as mysql
import dizzbotdb

dizzbotdb.USERTABLE="user_test"

# +-----+---------+-------+-----------+-------------+------------+----------+
# | id  | uname   | score | maxStreak | handouttime | slottime   | greeting |
# +-----+---------+-------+-----------+-------------+------------+----------+
# | 598 | karloor |    68 |         1 |  1397544666 | 1397431560 | NULL     |
# +-----+---------+-------+-----------+-------------+------------+----------+

def test_debit_unseen_user(): 
    username = ".newuser"
    con = get_connection() 
    with con:
        cur = con.cursor()
        rtn = cur.execute("""delete from {} where uname = {}""".format(
            dizzbotdb.USERTABLE,username))
        cur.close()
        con.commit()


def debit_perds(username, perds):
    """Take perds from a user. 

    Raise a NotEnoughPerdsException if they don't have 'em.
    If the user doesn't exist, we insert """
    try: 
        con = get_connection() 
        with con:
            cur = con.cursor()
            print ':1'        
            # create user if they don't exist in the db
            rtn = cur.execute(
            """INSERT INTO {} (uname) VALUES (%(uname)s) 
            ON DUPLICATE KEY UPDATE score = score""".format(USERTABLE),
            {'uname':username})

            print ':2'        
            return 0
            if rtn == 0:
                cur.execute(
                """SELECT score FROM {} WHERE uname=%(uname)s;""".format(USERTABLE),
                {'uname':username})
                print ':3'        
                row = cur.fetchone()
                print ':4'        
                score = row[0]
                if not row: raise DBException()
            else: 
                score = 0

            if score < perds: raise NotEnoughPerdsException()

            cur.execute(
            """INSERT INTO {} (uname, score) VALUES (%(uname)s,%(score)s) 
            ON DUPLICATE KEY UPDATE score = score - %(score)s""".format(USERTABLE),
            {'uname':username,'score':perds})
            print ':5'        

            return score - perds
    except mysql.Error, e:
        print e
        raise DBException()

def credit_perds(username, perds):
    """Give perds to a user."""
    try: 
        con = get_connection() 
        with con:
            cur = con.cursor()
            cur.execute(
            """INSERT INTO {} (uname, score) VALUES (%(uname)s,%(score)s) 
            ON DUPLICATE KEY UPDATE score = score + %(score)s""".format(USERTABLE),
            {'uname':username,'score':perds})
    except mysql.Error, e:
        print e
        raise DBException()
