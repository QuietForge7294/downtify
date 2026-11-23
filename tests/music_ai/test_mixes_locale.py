"""Genre mixes split by the account language: national vs international."""

from datetime import datetime

import pytest
from ai_test_support import opted_in_store

from downtify.music_ai.playlists import (
    GENRE_THEMES,
    PARIS,
    generate,
    genre_rows,
    genre_variants,
    is_genre_theme,
    themes,
)
from downtify.music_ai.store import MOODS, Store


def vector(axis=0):
    result = [0.0] * 512
    result[axis] = 1.0
    return result


def pop_rows():
    data = [
        {
            'id': f'fr-{i}',
            'artist': f'a{i}',
            'genre': 'chanson française; pop',
        }
        for i in range(30)
    ]
    data += [
        {'id': f'intl-{i}', 'artist': f'b{i}', 'genre': 'pop'}
        for i in range(30)
    ]
    return data


@pytest.fixture
def store(tmp_path):
    database = opted_in_store(tmp_path / 'derived.db')
    data = pop_rows()
    database.observe([
        {**row, 'fingerprint': 'f-' + row['id']} for row in data
    ])
    for row in data:
        database.put_analysis(row['id'], 'f-' + row['id'], 'm', vector())
    for mood in MOODS:
        with database.connect() as db:
            db.execute(
                'INSERT OR REPLACE INTO mood_vectors VALUES (?,?,?)',
                (mood, 'm', Store.pack(vector())),
            )
    return database


NOW = datetime(2026, 11, 12, 10, tzinfo=PARIS)


def test_genre_variants_split_for_known_languages():
    fr = genre_variants('fr')
    assert len(fr) == 2 * len(GENRE_THEMES)
    assert 'pop-nat' in fr and 'pop-intl' in fr
    assert 'jazz-nat' in fr and 'jazz-intl' in fr
    assert genre_variants('fr-FR') == fr
    assert genre_variants('es')
    # English (and unknown languages) keep a single, unsplit genre mix.
    assert genre_variants('en') == list(GENRE_THEMES)
    assert genre_variants('xx') == list(GENRE_THEMES)


def test_weekly_themes_include_locale_variants():
    assert len(themes('weekly', 'fr')) == len(MOODS) + 2 * len(GENRE_THEMES)
    assert 'pop-nat' in themes('weekly', 'fr')
    assert 'pop-nat' not in themes('weekly', 'en')


def test_is_genre_theme_accepts_variants_and_base_genres():
    assert is_genre_theme('pop')
    assert is_genre_theme('jazz-nat')
    assert is_genre_theme('rap-intl')
    assert not is_genre_theme('calme')
    assert not is_genre_theme('unknown')


def test_genre_rows_separate_national_and_international():
    data = [
        {'id': 'a', 'genre': 'chanson française; pop'},
        {'id': 'b', 'genre': 'pop'},
        {'id': 'c', 'genre': 'rap français'},
    ]
    national = [row['id'] for row in genre_rows('pop-nat', data, 'fr')]
    international = [row['id'] for row in genre_rows('pop-intl', data, 'fr')]
    assert national == ['a']
    assert international == ['b']


def test_generate_reads_scopes_written_by_the_library_scan(tmp_path):
    database = opted_in_store(tmp_path / 'derived.db')
    data = [
        {'id': f'n{i}', 'artist': f'n{i}', 'genre': ''} for i in range(10)
    ] + [
        {'id': f'x{i}', 'artist': f'x{i}', 'genre': ''} for i in range(10)
    ]
    database.observe([
        {**row, 'fingerprint': 'f-' + row['id']} for row in data
    ])
    for row in data:
        database.put_analysis(
            row['id'], 'f-' + row['id'], 'm', vector(ord(row['id'][0]) % 512)
        )
    for mood in MOODS:
        with database.connect() as db:
            db.execute(
                'INSERT OR REPLACE INTO mood_vectors VALUES (?,?,?)',
                (mood, 'm', Store.pack(vector())),
            )
    # The incremental scan already classified these rows: tags stay empty here
    # to prove generation never re-reads them.
    database.set_scopes(
        {
            **{
                f'n{i}': {'genres': ['jazz'], 'languages': ['fr']}
                for i in range(10)
            },
            **{
                f'x{i}': {'genres': ['jazz'], 'languages': []}
                for i in range(10)
            },
        }
    )
    national = generate(
        database, 1, 'weekly', 'jazz-nat', data, 'm', now=NOW, lang='fr'
    )
    international = generate(
        database, 1, 'weekly', 'jazz-intl', data, 'm', now=NOW, lang='fr'
    )
    assert {row['id'][0] for row in national} == {'n'}
    assert {row['id'][0] for row in international} == {'x'}


def test_generate_national_and_international(store):
    data = pop_rows()
    national = generate(
        store, 1, 'weekly', 'pop-nat', data, 'm', now=NOW, lang='fr'
    )
    international = generate(
        store, 1, 'weekly', 'pop-intl', data, 'm', now=NOW, lang='fr'
    )
    assert {row['id'].split('-')[0] for row in national} == {'fr'}
    assert {row['id'].split('-')[0] for row in international} == {'intl'}


def test_mood_catalog_labels_and_colours_every_theme():
    from downtify.music_ai.playlists import mood_catalog

    catalog = mood_catalog('fr')
    assert [row['name'] for row in catalog] == list(MOODS) + genre_variants('fr')
    weekly = [row for row in catalog if row['group'] == 'weekly']
    labels = {row['name']: row['label'] for row in weekly}
    assert labels['pop-nat'] == 'Pop · national'
    assert labels['jazz-intl'] == 'Jazz · international'
    assert {row['base'] for row in weekly} == set(GENRE_THEMES)
    assert all(row['color'].startswith('#') for row in catalog)
    assert [row['name'] for row in mood_catalog('en')] == (
        list(MOODS) + list(GENRE_THEMES)
    )


def test_techno_filters_vectors_and_cached_mix_does_not_read_scopes(store, monkeypatch):
    data = pop_rows()
    ids = {row['id'] for row in data[:25]}
    store.set_scopes({
        row['id']: {'genres': ['techno'] if row['id'] in ids else ['pop']}
        for row in data
    })
    original = store.vectors

    def only_techno(model, identities):
        assert identities == ids
        return original(model, identities)

    monkeypatch.setattr(store, 'vectors', only_techno)
    first = generate(store, 1, 'weekly', 'techno-intl', data, 'm', now=NOW, lang='fr')
    assert {row['id'] for row in first} == ids

    def no_scopes():
        raise AssertionError('Cache hits must not read the scope index')

    monkeypatch.setattr(store, 'scopes', no_scopes)
    cached = generate(store, 1, 'weekly', 'techno-intl', data, 'm', now=NOW, lang='fr')
    assert [row['id'] for row in cached] == [row['id'] for row in first]
