import sqlite3
# import json
# from shapely.geometry import LineString

# # Connect to SQLite
conn = sqlite3.connect("roads.db")
cur = conn.cursor()

# # Create table
# cur.execute("""
# CREATE TABLE IF NOT EXISTS roads (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     name TEXT,
#     ref TEXT,
#     geometry TEXT
# )
# """)
# conn.commit()


import geojson

with open("nevada.geojson") as f:
    data = geojson.load(f)

for feature in data['features']:
    props = feature['properties']
    geom = feature['geometry']
    print(f"Processing feature: {props.get('name')}", geom['type'])
    if geom['type'] == 'LineString':
        coords = geom['coordinates']
        cur.execute(
            "INSERT INTO roads (name, ref, geometry) VALUES (?, ?, ?)",
            (props.get('name'), props.get('ref'), json.dumps(coords))
        )
conn.commit()

