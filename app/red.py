import os
from redis import StrictRedis
from db import purge_streams
from log import logger

ACTIVE_DB = "active_db"


class Red:
    BLUE = 0
    GREEN = 1
    ORANGE = 2

    def __init__(self):
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        self.dbs = {
            Red.BLUE: StrictRedis(db=Red.BLUE, host=redis_host),
            Red.GREEN: StrictRedis(db=Red.GREEN, host=redis_host),
            Red.ORANGE: StrictRedis(db=Red.ORANGE, host=redis_host),
        }

        self.active_state = None
        self.inactive_state = None
        self.setup()

    def rotate(self):
        logger.info("Rotating DBs")
        rotation = {
            Red.BLUE: Red.GREEN,
            Red.GREEN: Red.BLUE
        }

        self.active_state = rotation.get(self.active_state)
        self.inactive_state = rotation.get(self.inactive_state)
        logger.info("Active DB is: %s", self.active_state)
        return self.active_state

    def active_db(self):
        return self.dbs.get(self.active_state)

    def inactive_db(self):
        return self.dbs.get(self.inactive_state)

    def meta_db(self):
        return self.dbs.get(Red.ORANGE)

    def reset_db(self):
        logger.info("Resetting inactive DB: %s", self.inactive_state)
        db = self.inactive_db()
        db.flushdb()
        purge_streams(self.inactive_state)
        return db

    def setup(self):
        color = int(self.meta_db().get(ACTIVE_DB) or Red.BLUE)
        if color == Red.BLUE:
            self.active_state = Red.BLUE
            self.inactive_state = Red.GREEN
        else:
            self.active_state = Red.GREEN
            self.inactive_state = Red.BLUE

        return self.active_state

    def rotate_meta(self):
        rotated = self.rotate()
        self.meta_db().set(ACTIVE_DB, rotated)
        self.reset_db()
        return rotated


def streamer_key(s):
    return 'st-' + s


def game_key(g):
    return 'g-' + g
