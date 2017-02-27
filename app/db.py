from peewee import *
from consts import PAGE_MAX_ITEMS
from log import logger
import datetime
import os

db_file = os.environ.get('DATABASE', 'zeroview.db')
mktables = not os.path.isfile(db_file)
sql_db = SqliteDatabase(db_file)


class BaseModel(Model):
    class Meta:
        database = sql_db


class Stream(BaseModel):
    preview = CharField(null=True)
    viewers = IntegerField(index=True)
    language = CharField(index=True)
    average_fps = FloatField()

    name = CharField()
    status = CharField(null=True)
    display_name = CharField()
    views = IntegerField(index=True)
    followers = IntegerField(index=True)
    game = CharField(null=True)
    game_hash = CharField(index=True)
    url = CharField()

    created = CharField()
    uptime = IntegerField()
    dbnum = IntegerField(index=True)

    class Meta():
        indexes = (
            (('name', 'dbnum'), True),
        )


class User(BaseModel):
    name = CharField(unique=True)
    created = DateTimeField(default=datetime.datetime.now)


class Upvote(BaseModel):
    viewer = ForeignKeyField(
        User,
        related_name='upvotes',
        to_field='name'
    )
    streamer = ForeignKeyField(
        Stream,
        related_name='votes',
        to_field='name'
    )
    upvote = BooleanField()
    updated_date = DateTimeField(default=datetime.datetime.now)

    class Meta:
        indexes = (
            (('viewer', 'streamer'), True),
        )


def upvote(viewer, streamer, up=True):
    try:
        if up:
            logger.debug("Inserting record")
            Upvote.create(
                viewer=viewer,
                streamer=streamer,
                upvote=up
            )
        else:
            logger.debug("Deleting record")
            Upvote.delete().where(
                Upvote.viewer == viewer,
                Upvote.streamer == streamer
            ).execute()
    except IntegrityError:
        pass


def count_stars(streamer):
    stars = Upvote.select().where(
        Upvote.streamer == streamer,
    )

    return stars.count()


def did_user_star(viewer, streamer):
    stars = Upvote.select().where(
        Upvote.viewer == viewer,
        Upvote.streamer == streamer,
    )
    return stars.count() == 1


def query_streams(filters, sort=None, page=1):
    filters = filters or {}
    _filters = []
    for k, v in filters.iteritems():
        _filters.append(
            getattr(Stream, k) == v
        )

    if sort:
        if sort in sorts:
            sort = sorts.get(sort, None)

    if not sort:
        sort = sorts.get("stars")

    query = (Stream.select()
        .where(*_filters)
        .join(Upvote, JOIN.LEFT_OUTER)
        .paginate(page, PAGE_MAX_ITEMS)
        .order_by(*sort)
        .annotate(Upvote)
    )

    c = []
    for r in query:
        d = r._data
        d.update({"stars": r.count})
        c.append(d)

    return c


def count_streams(filters):
    filters = filters or {}
    _filters = []
    for k, v in filters.iteritems():
        _filters.append(
            getattr(Stream, k) == v
        )

    return (Stream.select()
        .where(*_filters)
        .count()
    )


def add_user(name):
    User.create_or_get(name=name)


def purge_streams(dbnum):
    Stream.delete().where(Stream.dbnum == dbnum).execute()


def get_upvotes(user):
    res = (Upvote.select(Upvote.streamer)
        .where(Upvote.viewer == user)
    )

    ret = []
    for stream in res:
        try:
            name = stream.streamer.name
            ret.append(name)
        except:
            pass
    return ret

sorts = {
    "stars": (
        fn.COUNT(Upvote.id).desc(),
        Stream.views.desc(),
    ),
    "viewers": (
        Stream.viewers.desc(),
        fn.COUNT(Upvote.id).desc(),
        Stream.views.desc(),
    ),
    "views": (
        Stream.views.desc(),
        fn.COUNT(Upvote.id).desc(),
    ),
    "followers": (
        Stream.followers.desc(),
        fn.COUNT(Upvote.id).desc(),
        Stream.views.desc(),
    ),
    "uptime": (
        Stream.uptime.desc(),
    ),
    "fps": (
        Stream.average_fps.desc(),
        fn.COUNT(Upvote.id).desc(),
    )
}

if mktables:
    sql_db.connect()
    sql_db.create_tables([User, Stream, Upvote], safe=True)
    sql_db.close()
