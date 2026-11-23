from __future__ import annotations

import json
import re
import struct
import time
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import covers
from .ranking import rank
from .store import GENRE_THEMES as BASE_GENRE_THEMES
from .store import MOODS

GENRE_THEMES = (*BASE_GENRE_THEMES, 'techno')

PARIS = ZoneInfo('Europe/Paris')

# Weekly mixes include genre themes; daily mixes keep the six mood prompts.
GENRES = {
    'pop': r'\b(pop|k[ -]?pop|j[ -]?pop|synth[ -]?pop|britpop)\b',
    'rap': r'\b(rap|hip[ -]?hop|trap)\b',
    'rock': r'\b(rock|metal|punk|grunge)\b',
    'electro': r'\b(electro\w*|house|techno|trance|dance|edm|dubstep)\b',
    'techno': r'\btechno\b',
    'jazz': r'\b(jazz|bebop|be[ -]?bop|swing|bossa[ -]?nova|smooth jazz)\b',
}
WEEKLY_SIZE = 25
DAILY_SIZE = 40

# A genre theme can be split by the account's language: the "national" variant
# keeps tracks whose native genre tag names the account's own music (French
# chanson, Latin music, ...), the "international" one keeps the rest. Languages
# without a known marker keep a single, unsplit genre mix. The tags come from
# the library's own genre frames, so no external lookup is needed.
NATIONAL_MARKERS = {
    'fr': r'\b(chanson[s]? fran[çc]aise[s]?|rap fran[çc]ais|'
    r'vari[ée]t[ée] fran[çc]aise|french pop|french hip hop|'
    r'fran[çc]ais[e]?|francophone)\b',
    'es': r'\b(latin[oa]?|urbano latino|espa[ñn]ol|spanish)\b',
    'pt': r'\b(portugu[eê]s|brasileir[oa]|mpb|samba|bossa[ -]?nova)\b',
    'it': r'\b(italian[oa]?|italo)\b',
    'de': r'\b(deutsch|german|schlager)\b',
}


# Client-facing metadata for every theme. The app renders whatever this list
# advertises, so a new mix only needs a server-side entry: no APK update.
MOOD_LABELS = {
    'calme': 'Calme',
    'concentration': 'Concentration',
    'energie': 'Motivation',
    'fete': 'Fête',
    'melancolie': 'Mélancolie',
    'detente': 'Détente',
    'rap': 'Rap & Hip-Hop',
    'rock': 'Rock',
    'electro': 'Électro',
    'pop': 'Pop',
    'jazz': 'Jazz',
    'techno': 'Techno',
}
MOOD_COLORS = {
    'calme': '#4F46E5',
    'concentration': '#334155',
    'energie': '#C2410C',
    'fete': '#A21CAF',
    'melancolie': '#1D4ED8',
    'detente': '#0F766E',
    'rap': '#854D0E',
    'rock': '#B91C1C',
    'electro': '#0369A1',
    'pop': '#BE185D',
    'jazz': '#7C3AED',
    'techno': '#0F766E',
}
DEFAULT_MOOD_COLOR = '#0F766E'


def _language(lang):
    return str(lang or 'en').split('-')[0].strip().lower() or 'en'


def _split_genre_theme(theme):
    """``(genre, variant)`` for a genre theme, or ``(None, None)``.

    ``variant`` is ``all`` (unsplit), ``national`` or ``international``.
    """
    if theme in GENRE_THEMES:
        return theme, 'all'
    for suffix, variant in (('-nat', 'national'), ('-intl', 'international')):
        if theme.endswith(suffix):
            base = theme[: -len(suffix)]
            if base in GENRE_THEMES:
                return base, variant
    return None, None


def is_genre_theme(theme):
    return _split_genre_theme(theme)[0] is not None


def is_theme(theme):
    return theme in MOODS or is_genre_theme(theme)


def genre_variants(lang='en'):
    """The weekly genre themes for an account, split by language when known."""
    language = _language(lang)
    if language in NATIONAL_MARKERS:
        variants = []
        for genre in GENRE_THEMES:
            variants.append(f'{genre}-nat')
            variants.append(f'{genre}-intl')
        return variants
    return list(GENRE_THEMES)


def mood_catalog(lang='en'):
    """Descriptors for every advertised theme: name, label, colour, group.

    Kept additive next to ``moods`` so older clients keep working. The whole
    mix shelf is data-driven: adding a genre here makes it appear in updated
    clients without shipping a new application build.
    """
    rows = []
    for mood in MOODS:
        if mood in GENRE_THEMES:
            continue
        rows.append(
            {
                'name': mood,
                'label': MOOD_LABELS.get(mood, mood.title()),
                'color': MOOD_COLORS.get(mood, DEFAULT_MOOD_COLOR),
                'group': 'daily',
            }
        )
    for theme in genre_variants(lang):
        genre, variant = _split_genre_theme(theme)
        label = MOOD_LABELS.get(genre, genre.title())
        if variant == 'national':
            label = f'{label} · national'
        elif variant == 'international':
            label = f'{label} · international'
        rows.append(
            {
                'name': theme,
                'label': label,
                'color': MOOD_COLORS.get(genre, DEFAULT_MOOD_COLOR),
                'group': 'weekly',
                'base': genre,
            }
        )
    return rows


def themes(cadence, lang='en'):
    if cadence == 'daily':
        return [mood for mood in MOODS if mood not in GENRE_THEMES]
    if cadence == 'weekly':
        return list(MOODS) + genre_variants(lang)
    raise ValueError('Invalid cadence')


GENRE_PATTERNS = {
    genre: re.compile(pattern, re.I) for genre, pattern in GENRES.items()
}
LANGUAGE_PATTERNS = {
    language: re.compile(pattern, re.I)
    for language, pattern in NATIONAL_MARKERS.items()
}


def classify_genre(genre):
    """Derived scope of one track's native genre tag.

    ``genres`` lists the weekly themes it belongs to, ``languages`` the
    account languages whose own music it names (``chanson française`` is
    French, ``latino`` Spanish, ...). Computed once when the library row is
    ingested, never by re-reading the file.
    """
    text = str(genre or '')
    if not text:
        return {'genres': [], 'languages': []}
    return {
        'genres': [
            genre
            for genre, matcher in GENRE_PATTERNS.items()
            if matcher.search(text)
        ],
        'languages': [
            language
            for language, matcher in LANGUAGE_PATTERNS.items()
            if matcher.search(text)
        ],
    }


def genre_rows(theme, rows, lang='en', scopes=None):
    """A genre theme never falls back to another style when its tag is missing.

    A ``-nat`` theme keeps only the account language's own tracks, a ``-intl``
    one keeps everything else in that genre. ``scopes`` is the mapping filled
    by the incremental library pass; rows without an entry are classified from
    their own tag, which keeps this function usable on plain rows.
    """
    genre, variant = _split_genre_theme(theme)
    if genre is None:
        return rows

    cache = scopes if scopes is not None else {}

    def scope_of(row):
        identity = row.get('id')
        scope = cache.get(identity) if identity is not None else None
        if scope is None:
            scope = classify_genre(row.get('genre'))
            if identity is not None:
                cache[identity] = scope
        return scope

    selected = [row for row in rows if genre in scope_of(row)['genres']]
    if variant == 'all':
        return selected
    language = _language(lang)
    if language not in NATIONAL_MARKERS:
        # No known national marker: the split is meaningless, keep the genre.
        return selected

    def is_national(row):
        return language in scope_of(row)['languages']

    if variant == 'national':
        return [row for row in selected if is_national(row)]
    return [row for row in selected if not is_national(row)]


def period(cadence, now=None):
    now = (now or datetime.now(PARIS)).astimezone(PARIS)
    if cadence == 'daily':
        return (now - timedelta(hours=4)).date().isoformat()
    if cadence != 'weekly':
        raise ValueError('Invalid cadence')
    shifted = now - timedelta(hours=4, minutes=15)
    return (shifted.date() - timedelta(days=shifted.weekday())).isoformat()


def generate(store, owner, cadence, mood, rows, model, *, now=None, lang='en'):
    if not is_theme(mood):
        raise ValueError('Unknown mood')
    genre, _variant = _split_genre_theme(mood)
    features = store.effective(owner)
    if not features.get(cadence, False):
        raise PermissionError('Feature disabled')
    profile_revision = store.metadata(f'profile_revision:{owner}', 0)
    analysis_generation = store.metadata('analysis_generation', 0)
    selection_revision = store.metadata(f'selection_revision:{owner}', 0)
    key = period(cadence, now)
    allowed = {row['id']: row for row in rows}
    with store.connect() as db:
        old = db.execute(
            'SELECT ids FROM playlists WHERE owner=? AND cadence=? AND mood=? AND period=?',
            (owner, cadence, mood, key),
        ).fetchone()
        if old:
            identities = json.loads(old[0])
            current = store.vectors(model, set(identities) & set(allowed))
            return [
                {**allowed[tid], 'reason': 'Correspond à cette humeur'}
                for tid in identities
                if tid in allowed and tid in current
            ]
        if genre is not None:
            target = None
        else:
            prompt = db.execute(
                'SELECT vector FROM mood_vectors WHERE mood=? AND model=?',
                (mood, model),
            ).fetchone()
            target = struct.unpack('<512f', prompt[0]) if prompt else None
        proposed = recent_proposals(db, owner)
    scopes = store.scopes() if genre is not None else None
    candidates = genre_rows(mood, rows, lang, scopes=scopes)
    target_size = DAILY_SIZE if cadence == 'daily' else WEEKLY_SIZE
    if genre is not None and len(candidates) < min(target_size, 8):
        raise RuntimeError(
            'Not enough local tracks tagged in this genre; fill their metadata '
            'or pick a mood'
        )
    vectors = store.vectors(model, {row['id'] for row in candidates})
    analyzed_rows = [row for row in candidates if row['id'] in vectors]
    if not analyzed_rows or len(analyzed_rows) < min(
        target_size, len(candidates)
    ):
        raise RuntimeError('The initial catalog analysis is still in progress')
    if genre is not None:
        # A genre theme ranks against the centroid of its analysed tracks,
        # never against a mood prompt (the bundled CLAP release pins only the
        # six mood vectors, so there is no genre mood_vector to look up).
        import numpy as np

        target = np.mean([vectors[row['id']] for row in analyzed_rows], axis=0)
    elif target is None:
        # Mood playlists must not silently masquerade as AI when the model is absent.
        raise RuntimeError('Mood analysis is not ready')
    result = rank(
        analyzed_rows,
        vectors,
        target=target,
        history=store.history(owner) if features['personalization'] else (),
        favorites=[row['id'] for row in rows if row.get('favorite')]
        if features['personalization']
        else (),
        proposed_artists=Counter(
            str(allowed[tid].get('artist') or '').casefold().strip()
            for tid, count in proposed.items()
            if tid in allowed
            for _ in range(count)
        ),
        limit=target_size,
        rotation=f'{owner}:{mood}:{key}:{selection_revision}',
        proposed=proposed,
    )
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        revisions = {
            row[0]: json.loads(row[1])
            for row in db.execute(
                'SELECT key,value FROM metadata WHERE key IN (?,?,?,?)',
                (
                    f'profile_revision:{owner}',
                    'analysis_generation',
                    'analysis_paused',
                    f'selection_revision:{owner}',
                ),
            )
        }
        if (
            revisions.get(f'profile_revision:{owner}', 0) != profile_revision
            or revisions.get('analysis_generation', 0) != analysis_generation
            or revisions.get('analysis_paused', False)
            or revisions.get(f'selection_revision:{owner}', 0)
            != selection_revision
        ):
            raise RuntimeError('Generation invalidated')
        from .store import DEFAULTS

        preferences = {
            row[0]: {**DEFAULTS, **json.loads(row[1])}
            for row in db.execute(
                'SELECT owner,value FROM preferences WHERE owner IN (-1,?)',
                (owner,),
            )
        }
        if not all(
            preferences.get(uid, DEFAULTS)[cadence] for uid in (-1, owner)
        ):
            raise PermissionError('Feature disabled')
        db.execute(
            'INSERT OR IGNORE INTO playlists VALUES (?,?,?,?,?,?)',
            (
                owner,
                cadence,
                mood,
                key,
                json.dumps([row['id'] for row in result]),
                time.time(),
            ),
        )
        chosen = db.execute(
            'SELECT ids FROM playlists WHERE owner=? AND cadence=? AND mood=? AND period=?',
            (owner, cadence, mood, key),
        ).fetchone()
    return [
        {**allowed[tid], 'reason': 'Correspond à cette humeur'}
        for tid in json.loads(chosen[0])
        if tid in allowed
    ]


def _previous_period(cadence, key):
    """The period just before `key`, the only fallback a card may show."""
    day = datetime.fromisoformat(key).date()
    return (day - timedelta(days=1 if cadence == 'daily' else 7)).isoformat()


def _latest(store, owner, cadence, key):
    """Current mix per mood, or yesterday's while this morning's is not ready.

    A fresh period starts at 04:00 Paris. Until today's mix exists the previous
    one stays playable, so an early morning open never lands on an empty
    "preparing" card. Older periods are never resurrected.
    """
    with store.connect() as db:
        found = db.execute(
            'SELECT mood,period,ids,created FROM playlists '
            'WHERE owner=? AND cadence=? AND period IN (?,?) '
            'ORDER BY period DESC, created DESC',
            (owner, cadence, key, _previous_period(cadence, key)),
        ).fetchall()
    latest = {}
    for mood, stored_period, ids, created in found:
        if is_theme(mood) and mood not in latest:
            latest[mood] = (stored_period, ids, created)
    return latest


def summaries(store, owner, rows, *, now=None):
    """List current mixes, falling back to the previous one until it is ready."""
    flags = store.effective(owner)
    keys = {
        cadence: period(cadence, now)
        for cadence in ('daily', 'weekly')
        if flags[cadence]
    }
    if not keys:
        return []
    allowed = {row['id'] for row in rows}
    result = []
    for cadence, key in keys.items():
        for mood, (stored, ids, created) in sorted(
            _latest(store, owner, cadence, key).items()
        ):
            identities = json.loads(ids)
            count = len(set(identities) & allowed)
            if not count:
                continue
            result.append({
                'cadence': cadence,
                'mood': mood,
                'period': stored,
                'created': created,
                'count': count,
                'cover_track_ids': [
                    identity for identity in identities if identity in allowed
                ][:4],
                'cover_url': covers.url(cadence, mood, stored),
                'state': 'ready' if stored == key else 'previous',
            })
    return result


def stored_selections(store, owner, *, now=None):
    flags = store.effective(owner)
    selections = []
    for cadence in ('daily', 'weekly'):
        if not flags.get(cadence):
            continue
        key = period(cadence, now)
        for mood, (stored, ids, created) in sorted(
            _latest(store, owner, cadence, key).items()
        ):
            selections.append(
                dict(
                    cadence=cadence,
                    mood=mood,
                    period=stored,
                    ids=json.loads(ids),
                    created=created,
                )
            )
    return selections


def recent_proposals(db, owner):
    """Current and explicitly renewed selections share a bounded rotation window."""
    cutoff = time.time() - 7 * 86400
    identities = [
        identity
        for row in db.execute(
            'SELECT ids FROM playlists WHERE owner=? AND created>? '
            'ORDER BY created DESC LIMIT 84',
            (owner, cutoff),
        )
        for identity in json.loads(row[0])
    ]
    archived = db.execute(
        'SELECT value FROM metadata WHERE key=?',
        (f'playlist_rotation_history:{owner}',),
    ).fetchone()
    if archived:
        identities.extend(
            identity
            for cohort in json.loads(archived[0])[-84:]
            if cohort['created'] > cutoff
            for identity in cohort['ids']
        )
    return Counter(identities)


def refresh(store, owner, request_id, *, now=None):
    """Invalidate this owner's current automatic mixes, without audio work."""
    from .store import DEFAULTS

    keys = {cadence: period(cadence, now) for cadence in ('daily', 'weekly')}
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')

        def read(key, default):
            row = db.execute(
                'SELECT value FROM metadata WHERE key=?', (key,)
            ).fetchone()
            return json.loads(row[0]) if row else default

        def write(key, value):
            db.execute(
                'INSERT OR REPLACE INTO metadata VALUES (?,?)',
                (key, json.dumps(value)),
            )

        preferences = {
            row[0]: {**DEFAULTS, **json.loads(row[1])}
            for row in db.execute(
                'SELECT owner,value FROM preferences WHERE owner IN (-1,?)',
                (owner,),
            )
        }
        enabled = [
            cadence
            for cadence in keys
            if all(
                preferences.get(uid, DEFAULTS)[cadence] for uid in (-1, owner)
            )
        ]
        if not enabled:
            raise PermissionError('Feature disabled')
        receipts_key = f'playlist_refresh_receipts:{owner}'
        receipts = read(receipts_key, [])
        previous = next(
            (r for r in receipts if r['request_id'] == request_id), None
        )
        if previous:
            return previous['result']
        archived = read(f'playlist_rotation_history:{owner}', [])
        removed = 0
        for cadence in enabled:
            archived.extend(
                dict(ids=json.loads(row['ids']), created=row['created'])
                for row in db.execute(
                    'SELECT ids,created FROM playlists '
                    'WHERE owner=? AND cadence=? AND period=?',
                    (owner, cadence, keys[cadence]),
                )
            )
            removed += db.execute(
                'DELETE FROM playlists WHERE owner=? AND cadence=? AND period=?',
                (owner, cadence, keys[cadence]),
            ).rowcount
        archived = sorted(
            (
                item
                for item in archived
                if item['created'] > time.time() - 7 * 86400
            ),
            key=lambda item: item['created'],
        )[-84:]
        write(f'playlist_rotation_history:{owner}', archived)
        revision = read(f'selection_revision:{owner}', 0) + 1
        write(f'selection_revision:{owner}', revision)
        result = dict(accepted=True, revision=revision, removed=removed)
        receipts.append(dict(request_id=request_id, result=result))
        write(receipts_key, receipts[-32:])
        return result
