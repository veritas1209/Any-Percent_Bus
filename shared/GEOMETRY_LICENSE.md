# Road geometry data

Road shapes contain data derived from **© OpenStreetMap contributors**, obtained
from the [OSM Korea regional extract](https://tiles.osm.kr/download/).
OpenStreetMap data is available under the [Open Database License 1.0](https://www.openstreetmap.org/copyright).

The derived coordinates are included in `network.json` and `observed_network.json`.
The input bus GPS recording was supplied by the project owner; its rights remain
with its owner. The raw recording is not included in release archives.

GPS processing and matching run locally against the downloaded road graph.
No GPS coordinates or timestamps are transmitted to a public matching service.
The all-route dataset stores shared per-family road shapes by reference and
simplifies the displayed line within two metres. Shape lengths retain the road
graph length before simplification. A catalog-only connection has no timetable.

`gps_road_matched` denotes a historical GPS-constrained local road match.
`road_estimate` denotes a road-network estimate without verified GPS coverage.
`unavailable` denotes an unconnected/missing shape; it is not drawn as a straight
line between its endpoints. Turn-restriction relations and lane-level bus access
are outside this prototype's model.
