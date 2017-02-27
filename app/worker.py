import math
from log import logger
from math import ceil
import requests
import json
import time
import pytz
import hashlib
import string
import os
from requests.exceptions import Timeout
from dateutil.parser import parse as dateparse
from red import Red, streamer_key, game_key
from db import sql_db, Stream
from collections import Counter
from consts import GAMES, META_DATA, CHANNEL_COUNT, LANGUAGES, \
    MAX_VIEWERS, TOTAL_LIVE, ZERO_VIEWERS, API_MAX_ITEMS, \
    SIG_ADDED, SIG_SKIPPED, SIG_INVALID, SIG_OK, API_DECR, \
    WORKER_INTERVAL, MIN_LIVE_MINUTES, MAX_LIVE_MINUTES


cache = Red()
game_index = {
    "hashes": {},
    "counters": {}
}

languages = set()
timers = {
    "twitch": [],
    "sql": [],
}

stream_dicts = []

try:
    requests.packages.urllib3.disable_warnings()
except:
    logger.warning("Could not disable requests warnings. oh, well.")


def twitch_api(url, payload=None, is_retry=False):
    timer = timers.get("twitch")
    prep = requests.PreparedRequest()
    prep.prepare_url(url, payload)
    common_headers = {
        'accept': 'application/vnd.twitchtv.v3+json',
        'Client-ID': os.environ.get('TWITCH_CLIENT_ID', None)
    }
    try:
        t1 = time.time()
        res = requests.get(url, params=payload,
                           headers=common_headers, verify=False,
                           timeout=5.0)
        logger.debug(res.status_code)
        j = res.json()
        timer.append(time.time() - t1)
    except KeyboardInterrupt:
        exit(1)
    except (Timeout, ValueError) as e:
        logger.exception(e)
        if is_retry:
            logger.error("API retry failed. giving up")
            return {}
        else:
            logger.warning("timeout; retrying!")
            return twitch_api(url, payload, is_retry=True)
    return j


def get_streams(offset=0):
    payload = {
        'stream_type': 'live',
        'offset': offset,
        'limit': API_MAX_ITEMS,
    }

    url = 'https://api.twitch.tv/kraken/streams'
    logger.info("requesting offset: %d", offset)
    return twitch_api(url, payload)


def get_num_streams():
    """Force an offset so high that the payload is small and quick.
    In it, there will be a total number to base our reverse search from"""
    result = get_streams()
    logger.debug(result)
    if "error" in result:
        raise Exception("error in request: " + str(result))

    total = int(result.get('_total', 0))
    logger.info("Total live streams: %d", total)
    return total


def start_runback():
    start_time = time.time()
    sql_db.connect()
    red_db = cache.reset_db()
    meta_db = cache.meta_db()

    max_add = os.environ.get("WORKER_MAX", None)

    streams = get_num_streams()
    red_db.set(TOTAL_LIVE, streams)

    requests_made = 1
    pages = int(ceil(float(streams) / API_DECR))

    def offgen(pages):
        for p in xrange(pages, 0, -1):
            yield p * API_DECR

    total_added = 0
    offset = 0
    for offset in offgen(pages):
        try:
            result = get_streams(offset)
        except Exception as e:
            logger.exception(e)
            continue

        requests_made += 1
        if "error" in result:
            raise Exception("error in request: " + str(result))

        streams = result.get("streams", [])
        if not streams:
            continue

        added, num_added = add_streams(
            streams,
            red_db,
            meta_db,
            game_index
        )
        total_added += num_added
        logger.info("adding %d streams, total now %d", num_added, total_added)
        if not added:
            break

        if max_add and total_added > int(max_add):
            logger.warning("maximum reached; stopping loop")
            break

    red_db.set(GAMES, json.dumps(game_index))
    game_hashes = game_index.get("hashes")
    for k, v in game_hashes.iteritems():
        red_db.set(game_key(k), v)

    if len(languages):
        meta_db.sadd(LANGUAGES, *languages)
    red_db.set(CHANNEL_COUNT, total_added)

    meta_db.set(META_DATA, json.dumps({
        "cached": int(time.time())
    }))

    logger.info("committing sql..")
    sql_times = timers.get("sql")
    sql_db.set_autocommit(False)
    sql_start_time = time.time()
    sql_db.begin()

    for obj in stream_dicts:
        Stream(**obj).save()

    sql_times.append(time.time() - sql_start_time)
    sql_db.commit()
    sql_db.close()

    run_time = time.time() - start_time
    report_time("Twitch Times", timers.get("twitch"))
    report_time("SQL Times", timers.get("sql"))
    logger.info("Run Time: %s", run_time)

    red_db = cache.rotate_meta()
    print json.dumps(
        dict(
            last_offset=offset,
            requests=requests_made,
            channels=total_added,
            db=red_db,
            run_time=run_time,
        )
    )


def add_streams(streams, red_db, meta_db, game_index):
    added = False
    num_added = 0
    for stream in streams:
        sig = add_stream(stream, red_db, meta_db, game_index)
        if sig != SIG_INVALID:
            added = True
        if sig == SIG_ADDED:
            num_added += 1

    return added, num_added


def add_stream(stream, red_db, meta_db, game_index):
    logger.debug(json.dumps(stream))

    sig = qualified_stream(stream, red_db)
    if sig != SIG_OK:
        return sig

    channel = stream.get("channel")
    viewers = int(stream.get("viewers"))
    if viewers == 0:
        red_db.incr(ZERO_VIEWERS)

    language = channel.get("broadcaster_language") or "en"
    languages.add(language)

    game_counters = game_index.get("counters")
    game_counter_all = game_counters.get('_', None)
    game_counter_lang = game_counters.get(language, None)
    if not game_counter_all:
        game_counter_all = Counter()
        game_counters['_'] = game_counter_all
    if not game_counter_lang:
        game_counter_lang = Counter()
        game_counters[language] = game_counter_lang

    game_hashes = game_index.get("hashes")

    game = channel.get("game", "None")
    game_hash = hashmd5(game or 'None')
    game_counter_all[game_hash] += 1
    game_counter_lang[game_hash] += 1
    game_hashes[game_hash] = game

    logger.debug("Game: %s, Hash: %s", game, game_hash)

    name = channel.get("name")
    meta_db.setnx(streamer_key(name), 1)
    uptime = timestamp(stream.get("created_at"))

    obj = {
        "preview": stream.get("preview").get("medium"),
        "viewers": viewers,
        "language": unicode(language),
        "average_fps": "%0.2f" % (float(stream.get("average_fps")),),

        "name": unicode(name),
        "status": channel.get("status"),
        "display_name": channel.get("display_name"),
        "views": int(channel.get("views")),
        "followers": int(channel.get("followers")),
        "game": unicode(game),
        "game_hash": unicode(game_hash),
        "url": channel.get("url"),

        "created": stream.get("created_at"),
        "uptime": uptime,
        "dbnum": cache.inactive_state
    }

    stream_dicts.append(obj)

    return SIG_ADDED


def qualified_stream(stream, db):
    if stream.get("is_playlist"):
        return SIG_INVALID

    if stream.get("viewers") > MAX_VIEWERS:
        return SIG_INVALID

    channel = stream.get("channel")

    if channel.get("partner"):
        return SIG_INVALID

    name = channel.get("name")
    if not db.setnx("c-" + name, 1):
        return SIG_SKIPPED

    uptime = timestamp(stream.get("created_at"))
    live_seconds = int(time.time()) - uptime
    live_min = 60 * MIN_LIVE_MINUTES
    live_max = 60 * MAX_LIVE_MINUTES

    logger.debug("live seconds: %d", live_seconds)
    if live_seconds < live_min:
        logger.debug(
            "%s skipped, live for only %d",
            channel.get("name"),
            live_seconds,
        )
        return SIG_SKIPPED

    if live_seconds > live_max:
        logger.debug(
            "%s skipped, live too long! %d",
            channel.get("name"),
            live_seconds,
        )
        return SIG_SKIPPED

    return SIG_OK


def timestamp(created):
    d = dateparse(created).replace(tzinfo=pytz.utc)
    return int(time.mktime(d.timetuple()))


def hashmd5(s):
    m = hashlib.md5()
    printable = set(string.printable)
    m.update(filter(lambda x: x in printable, s))
    return m.hexdigest()


def report_time(title, times):
    logger.info(title)
    _len = len(times)
    _min = min(times)
    _max = max(times)

    if _len == 1:
        _med = times[0]
    elif _len % 2:
        _med = times[int(math.ceil(float(_len)/2))]
    else:
        mid = _len / 2
        _med = float(times[mid] + times[mid + 1]) / 2

    _sum = 0
    for t in times:
        _sum += t
    _avg = _sum / _len

    logger.info({
        "length": _len,
        "minimum": _min,
        "maximum": _max,
        "median": _med,
        "average": _avg,
        "total": _sum,
    })


if __name__ == '__main__':
    os.environ['TZ'] = 'UTC'
    run_worker = bool(int(os.environ.get('WORKER_ENABLED', 1)))
    if run_worker:
        cache.setup()
        start_runback()

    logger.info("Sleeping until next run.")
    time.sleep(WORKER_INTERVAL)
    logger.info("Sleep done, brb.")
