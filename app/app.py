from flask import Flask, render_template, request, session, redirect, \
    jsonify, url_for
from flask_oauthlib.client import OAuth
from log import logger
import requests
import json
import os
import math
from xml.sax.saxutils import escape
import iso639
from red import Red, streamer_key, game_key
from db import upvote, query_streams, count_streams, \
    count_stars, add_user, get_upvotes
from consts import PAGE_MAX_ITEMS, GAMES, CHANNELS, META_DATA, \
    MIN_LIVE_MINUTES, MAX_LIVE_MINUTES, LOGIN_ENABLED, \
    MAX_VIEWERS, TOTAL_LIVE, APP_VERSION, ZERO_VIEWERS, \
    LANGUAGES, CHANNEL_COUNT, APP_PHASE, CONTACT_EMAIL, \
    DONATE_URL, DONATE_SERVICE

app = Flask(__name__)
app.secret_key = "__this_key_can_be_changed.__Its_for_session_data."
TWITCH_CLIENT_ID = os.environ.get('TWITCH_CLIENT_ID', None)
TWITCH_SECRET = os.environ.get('TWITCH_SECRET', None)

if not TWITCH_CLIENT_ID or not TWITCH_SECRET:
    raise Exception('TWITCH_CLIENT_ID and TWITCH_SECRET must be set.')

oauth = OAuth()

twitch = oauth.remote_app(
    'twitch',
    base_url='https://api.twitch.tv/kraken/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://api.twitch.tv/kraken/oauth2/token',
    authorize_url='https://api.twitch.tv/kraken/oauth2/authorize',
    consumer_key=os.environ.get('TWITCH_OAUTH_CLIENT_ID', TWITCH_CLIENT_ID),
    consumer_secret=os.environ.get('TWITCH_OAUTH_SECRET', TWITCH_SECRET),
    request_token_params={'scope': ["user_read"]}
)

cache = Red()

try:
    requests.packages.urllib3.disable_warnings()
except:
    logger.warning("Could not disable requests warnings. oh, well.")


@app.before_request
def before_request():
    active = cache.setup()
    logger.debug("Setup Active DB: %s", active)


@app.route('/')
def index():
    return render_template(
        'index.j2',
        meta=get_meta(),
        site_title="ZeroViewers",
    )


@app.route('/login')
def login():
    callback = os.environ.get("TWITCH_CALLBACK",
                              "http://localhost:3000/authorize")
    return twitch.authorize(callback=callback)


@app.route('/logout')
def logout():
    session.pop('twitch_token', None)
    return redirect(url_for('index'))


@twitch.tokengetter
def get_twitch_token(token=None):
    return session.get('twitch_token')


@app.route('/authorize')
def authorize():
    resp = twitch.authorized_response()
    if resp is None:
        return 'Access denied: reason=%s error=%s' % (
            request.args['error'],
            request.args['error_description']
        )

    session['twitch_token'] = (resp['access_token'], '')
    headers = {'Authorization': ("OAuth " + session['twitch_token'][0])}
    r = requests.get(twitch.base_url, headers=headers)
    name = json.loads(r.text).get("token").get("user_name", None)
    if name:
        session['user_name'] = name
        add_user(name)

    return redir_home()


def redir_home():
    return redirect(url_for('index'))


@app.route('/about')
def about():
    return render_template(
        'about.j2',
        meta=get_meta(),
        site_title="ZeroViewers - About",
    )


@app.route('/donate')
def donate():
    return render_template(
        'donate.j2',
        meta=get_meta(),
        site_title="ZeroViewers - Donate",
    )


@app.route('/settings/language', methods=['POST'])
def set_language():
    lang = request.form.get("lang")
    if lang:
        languages = cache.meta_db().smembers(LANGUAGES)
        if lang in languages:
            session["lang"] = lang
        elif lang == u'_':
            session.pop("lang")
    return lang


@app.route('/games')
def games_index():
    sort = request.args.get('sort', None)
    db = cache.active_db()
    games_index = json.loads(db.get(GAMES))
    index_lang = '_'
    if "lang" in session:
        index_lang = session['lang']

    counts = games_index.get("counters").get(index_lang, {})
    hashes = games_index.get("hashes")
    game_list = [(k, v, hashes.get(k)) for k, v in counts.iteritems()]

    def by_stream(games):
        return sorted(
            games,
            key=lambda i: (-1 * int(i[1]), unicode(i[2]).lower()),
        )

    def by_name(games):
        return sorted(
            games,
            key=lambda i: unicode(i[2]).lower(),
        )

    sorts = {
        "game": by_name,
        "streams": by_stream,
    }

    if not sort or sort not in sorts:
        sort = "game"
    sort_fn = sorts.get(sort)

    return render_template(
        'games.j2',
        games=sort_fn(game_list),
        meta=get_meta(db),
        site_title="ZeroViewers - Games",
    )


@app.route('/games/<game_hash>')
def game_page(game_hash):
    return page(game=game_hash)


@app.route('/games/<game_hash>/<int:page_num>')
def game_page_n(game_hash, page_num):
    return page(page_num=page_num, game=game_hash)


@app.route('/channels')
def channel_page():
    return page()


@app.route('/channels/<int:page_num>')
def channel_page_n(page_num):
    return page(page_num=page_num)


@app.route('/vote/<streamer>/up')
def vote_up(streamer):
    return vote(streamer, True)


@app.route('/vote/<streamer>/down')
def vote_down(streamer):
    return vote(streamer, False)


def vote(streamer, updown):
    if not logged_in():
        return redirect(url_for('login'))
    if not is_channel(streamer):
        return jsonify(error="Streamer not found.")

    if streamer == session["user_name"]:
        uh_nope = "Nice try, voting for youself. We won't tell anyone."
        return jsonify(error=uh_nope)

    try:
        upvote(session['user_name'], streamer, updown)
        return jsonify(
            streamer=streamer,
            voted_for=updown,
            stars=count_stars(streamer)
        )
    except Exception as e:
        return jsonify(error=e.message)


def is_channel(streamer):
    return cache.meta_db().get(streamer_key(streamer))


def page(page_num=1, game=None):
    sort = request.args.get('sort', None)
    additional = {
        "site_title": "ZeroViewers - page %d" % (page_num,),
    }

    channels, meta = get_channels(page_num, game, sort)

    top = meta.get('filtered_count')
    pages = int(math.ceil(float(top) / PAGE_MAX_ITEMS))
    prev_page = min(page_num - 1, pages)
    if prev_page <= 0:
        prev_page = None

    next_page = min(page_num + 1, pages + 1)
    if next_page > pages:
        next_page = None

    paging = {
        "pages": pages,
        "prev_page": prev_page,
        "page_num": page_num,
        "next_page": next_page,
    }

    additional.update(paging)

    logger.debug("Page: %d, Channels: %d", page_num, len(channels))
    return render_template("channels.j2",
                           channels=channels,
                           meta=meta,
                           **additional)


def get_channels(page_num, game=None, sort=None):
    db = cache.active_db()
    meta = get_meta(db, game)
    db = cache.active_db()

    filters = {
        "dbnum": cache.active_state
    }

    if game:
        filters["game_hash"] = game
    if "lang" in session:
        filters["language"] = unicode(session["lang"])

    channels = query_streams(
        filters=filters,
        page=page_num,
        sort=sort,
    )
    llen = count_streams(filters)

    game_name = "Channels"
    if game:
        game_name = db.get(game_key(game))
        game_name = escape(game_name.decode('utf-8'))

    range_min = ((page_num - 1) * PAGE_MAX_ITEMS) + 1
    range_max = min(llen, range_min + PAGE_MAX_ITEMS - 1)
    if range_min > range_max:
        range_max = range_min = ''

    meta.update({
        "range_min": range_min,
        "range_max": range_max,
        "game_name": game_name,
        "filtered_count": llen,
    })

    return channels, meta


def gen_meta(db=None, index=None):
    db = cache.active_db()
    index = index or CHANNELS
    page_slug = '/channels'
    if index != CHANNELS:
        page_slug = '/games/' + index

    meta_db = cache.meta_db()
    try:
        cache_meta = json.loads(meta_db.get(META_DATA))
        logger.debug("post loads: %s", cache_meta)
    except Exception as e:
        logger.exception(e)
        cache_meta = {}

    cached_time = cache_meta.get("cached")
    languages = []
    for l in meta_db.smembers(LANGUAGES):
        fmt = "%s / %s"
        try:
            native = escape(iso639.to_native(l).split(';')[0])
            languages.append({
                "code": l,
                "name": fmt % (iso639.to_name(l), native),
            })
        except iso639.NonExistentLanguageError:
            languages.append({
                "code": l,
                "name": l,
            })

    meta = {
        "channel_count": db.get(CHANNEL_COUNT),
        "cached": cached_time,
        "zero_viewers": db.get(ZERO_VIEWERS),
        "page_slug": page_slug,
        "app_version": APP_VERSION,
        "languages": sorted(languages, key=lambda l: l.get("name")),
    }

    return meta


def meta_name(index):
    index = index or CHANNELS
    return 'meta-' + index


def get_meta(db=None, game=None):
    db = db or cache.active_db()
    meta = gen_meta(index=game)
    lang = None

    if "lang" in session:
        lang = session["lang"]

    meta.update({
        "total": db.get(TOTAL_LIVE),
        "max_viewers": MAX_VIEWERS,
        "min_live_minutes": MIN_LIVE_MINUTES,
        "max_live_minutes": MAX_LIVE_MINUTES,
        "lang": lang,
    })

    meta.update(common_vars())

    if logged_in():
        upvotes = get_upvotes(session['user_name'])
        meta.update({
            "logged_in": True,
            "user_name": session['user_name'],
            "upvotes": upvotes
        })
    else:
        meta.update({
            "logged_in": False
        })

    return meta


def common_vars():
    return {
        "login_enabled": LOGIN_ENABLED,
        "app_phase": APP_PHASE,
        "contact_email": CONTACT_EMAIL,
        "donate_url": DONATE_URL,
        "donate_service": DONATE_SERVICE,
    }


def logged_in():
    return "twitch_token" in session


def html_escape_dict(obj):
    for k, v in obj.iteritems():
        try:
            if isinstance(v, (str, unicode)):
                obj[k] = v
        except UnicodeEncodeError as e:
            logger.exception(e)
            return ''
    return obj


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
