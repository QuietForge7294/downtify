from types import SimpleNamespace

from downtify.library_sync import LibrarySync
from downtify.music_ai.catalog import candidates, snapshot, synchronize
from downtify.music_ai.store import Store


def test_native_cursor_only_reads_changed_rows_and_invalidates_replaced_sources(
    tmp_path,
):
    native = LibrarySync(tmp_path / 'native.db')
    database = Store(tmp_path / 'derived.db')
    rows = [
        {'file': f'{i}.mp3', 'title': str(i), 'duration': 180, 'size': 20}
        for i in range(120)
    ]
    native.refresh(rows)
    calls = []

    def changes(since):
        result = native.changes(since)
        calls.append((since, len(result['tracks']), len(result['deleted'])))
        return result

    feed = SimpleNamespace(cursor=native.cursor, changes=changes)
    assert synchronize(database, feed) == 120
    assert synchronize(database, feed) == 0
    assert len(calls) == 1
    first = snapshot(database)[0]
    database.put_analysis(
        first['id'], first['fingerprint'], 'm', [1] + [0] * 511
    )
    replaced = next(row for row in rows if row['file'] == first['file'])
    replaced['size'] = 999
    native.refresh(rows)
    assert synchronize(database, feed) == 1
    assert calls[-1][0] > 0
    assert calls[-1][1:] == (1, 0)
    assert database.vectors('m', {first['id']}) == {}
    rows.remove(replaced)
    native.refresh(rows)
    assert synchronize(database, feed) == 1
    assert calls[-1][1:] == (0, 1)
    assert first['id'] not in {row['id'] for row in snapshot(database)}
    assert len(candidates(database, 'm', limit=25)) == 25


def test_scopes_are_derived_once_per_changed_row_and_dropped_with_it(tmp_path):
    native = LibrarySync(tmp_path / 'native.db')
    database = Store(tmp_path / 'derived.db')
    rows = [
        {'file': 'a.mp3', 'title': 'A', 'genre': 'chanson française; pop', 'size': 20},
        {'file': 'b.mp3', 'title': 'B', 'genre': 'pop', 'size': 20},
        {'file': 'c.mp3', 'title': 'C', 'genre': 'rap français', 'size': 20},
    ]
    native.refresh(rows)
    feed = SimpleNamespace(cursor=native.cursor, changes=native.changes)
    assert synchronize(database, feed) == 3
    scopes = database.scopes()
    assert len(scopes) == 3
    values = {scope['genres'][0] for scope in scopes.values()}
    assert values == {'pop', 'rap'}
    first = next(
        key
        for key, scope in scopes.items()
        if scope['languages'] == ['fr'] and scope['genres'] == ['pop']
    )
    assert scopes[first]['languages'] == ['fr']
    # A second pass with an unchanged feed writes nothing.
    assert synchronize(database, feed) == 0
    assert database.scopes() == scopes
    # A changing tag updates only that row's scope.
    rows[0]['genre'] = 'rock'
    rows[0]['size'] = 21
    native.refresh(rows)
    assert synchronize(database, feed) == 1
    assert database.scopes()[first]['genres'] == ['rock']
    # A removed track forgets its scope.
    removed = next(
        key for key, scope in database.scopes().items() if scope['genres'] == ['rap']
    )
    rows[:] = [row for row in rows if row['file'] != 'c.mp3']
    native.refresh(rows)
    assert synchronize(database, feed) == 1
    assert removed not in database.scopes()


def test_backfill_classifies_legacy_rows_once_without_touching_files(tmp_path):
    from downtify.music_ai.catalog import backfill_scopes

    database = Store(tmp_path / 'derived.db')
    database.observe([
        {'id': 'x', 'fingerprint': 'fx', 'genre': 'latino', 'file': 'x.mp3'},
        {'id': 'y', 'fingerprint': 'fy', 'genre': 'jazz', 'file': 'y.mp3'},
    ])
    with database.connect() as db:
        db.executemany(
            'INSERT INTO catalog_live VALUES (?)', [('x',), ('y',)]
        )
    assert backfill_scopes(database) == 2
    scopes = database.scopes()
    assert scopes['x'] == {'genres': [], 'languages': ['es']}
    assert scopes['y'] == {'genres': ['jazz'], 'languages': []}
    # The marker makes the backfill a one-off.
    assert backfill_scopes(database) == 0


def test_native_bulk_lookup_resolves_requested_ids_without_full_feed(
    tmp_path, monkeypatch
):
    native = LibrarySync(tmp_path / 'native.db')
    native.refresh([{'file': f'{i}.mp3', 'size': 20} for i in range(8)])
    ids = list(native.ids_for_paths(['1.mp3', '2.mp3', '3.mp3']).values())
    monkeypatch.setattr(
        native,
        'changes',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('No full feed')),
    )
    resolved = native.rows_for(ids[::-1])
    assert [resolved[identity]['id'] for identity in ids[::-1]] == ids[::-1]
    assert native.rows_for([]) == {}


def test_visible_selection_checks_current_acl_and_hidden_files_using_only_points(
    tmp_path, monkeypatch
):
    from downtify import api, library_catalog, mobile_routes
    from downtify.music_ai import routes

    calls = []
    rows = [
        {'id': 'one', 'file': 'one.mp3'},
        {'id': 'hidden', 'file': 'hidden.mp3'},
        {'id': 'other', 'file': 'other.mp3'},
        {'id': 'forbidden', 'file': 'forbidden.mp3'},
    ]

    def points(ids):
        calls.append(ids)
        return {row['id']: row for row in rows if row['id'] in ids}

    monkeypatch.setattr(routes, 'owner', lambda _: 1)
    monkeypatch.setattr(
        mobile_routes, '_sync', lambda: SimpleNamespace(rows_for=points)
    )
    monkeypatch.setattr(
        api,
        'allowed_entry_keys',
        lambda _, entries=None: {'one.mp3', 'hidden.mp3', 'other.mp3'},
    )
    monkeypatch.setattr(
        api,
        'library_context',
        lambda: SimpleNamespace(hidden_files={'hidden.mp3'}),
    )
    monkeypatch.setattr(
        library_catalog, 'entry_content_key', lambda row: row['file']
    )
    assert [
        row['id']
        for row in routes.visible_rows(
            None, ['other', 'one', 'one', 'hidden', 'missing', 'forbidden']
        )
    ] == ['other', 'one']
    assert calls == [['other', 'one', 'hidden', 'missing', 'forbidden']]
