"""Check every imported label against the reviewed client encounter-name inventory."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / 'dungeonmaps/data/dungeons.json').read_text(encoding='utf-8'))
audit = json.loads((ROOT / 'validation/boss-names.json').read_text(encoding='utf-8'))
assert set(audit['dungeons']) == set(data['bosses'])
total = 0
for key, bosses in data['bosses'].items():
    reviewed = audit['dungeons'][key]
    assert len(bosses) == len(reviewed), key
    labels = {b['name'] for b in bosses}
    for i, (boss, row) in enumerate(zip(bosses, reviewed), 1):
        assert row['index'] == i and row['label'] == boss['name'], (key, i)
        assert [e['id'] for e in row['encounters']] == boss['encounters'], (key, i)
        differences = [e for e in row['encounters'] if e['name'] != boss['name']]
        if differences:
            assert row['status'] == 'retained_creature_label' and row.get('reason'), (key, i)
            for encounter in differences:
                assert encounter['name'] in boss['aliases'] or encounter['name'] in labels, (key, i)
        else:
            assert row['status'] == 'matches_client_encounter', (key, i)
        total += 1
assert total == audit['boss_pins'] == 212
assert [b['name'] for b in data['bosses']['wailingcaverns']] == [
    'Lady Anacondra', 'Lord Cobrahn', 'Kresh', 'Lord Pythas', 'Skum',
    'Lord Serpentis', 'Verdan the Everliving', 'Mutanus the Devourer']
print('PASS 212 reviewed boss labels/encounter IDs, explicit creature-title exceptions, and WC names')
