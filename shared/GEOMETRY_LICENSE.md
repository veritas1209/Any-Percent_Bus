# Road geometry data

Road shapes contain data derived from **© OpenStreetMap contributors**, obtained
from the [OSM Korea regional extract](https://tiles.osm.kr/download/).
OpenStreetMap data is available under the [Open Database License 1.0](https://www.openstreetmap.org/copyright).

The derived coordinates are included in `network.json` and `observed_network.json`.
The derived pedestrian graph (`walk_graph.bin`) and place/address index
(`places.json`) also contain OpenStreetMap data under the same license.
The `service_network.json` bus routes, stop sequences, road coordinates and
terminal timetables were retrieved from the [Ulsan Traffic Management Center](https://its.ulsan.kr/route/timetable.do)
on 2026-11-11. Its walking links use the local OpenStreetMap pedestrian graph.
Sparse official road links are connected through the local directed OpenStreetMap
road graph when the endpoints match within 40 metres and the road length remains
consistent with the supplied link. These shapes use `ulsan_its_osm_connected`.
Source response hashes and retrieval times are recorded in `artifacts/official-data.json`.
The input bus GPS recording was supplied by the project owner; its rights remain
with its owner. The raw recording is not included in release archives.

GPS processing and matching run locally against the downloaded road graph.
No GPS coordinates or timestamps are transmitted to a public matching service.
The all-route dataset stores shared per-family road shapes by reference and
simplifies the displayed line within two metres. Shape lengths retain the road
graph length before simplification. A catalog-only connection has no timetable.

`gps_road_matched` denotes a historical GPS-constrained local road match.
`gps_trace_matched` denotes direction-aware trace matching with timestamped
progress samples. Stop coordinates are not forced into the vehicle trace.
`osm_pedestrian_access` denotes a query-time access/egress walk on the local
pedestrian graph, including short estimated links from the selected endpoints.
`road_estimate` denotes a road-network estimate without verified GPS coverage.
`unavailable` denotes an unconnected/missing shape; it is not drawn as a straight
line between its endpoints. Turn-restriction relations and lane-level bus access
are outside this prototype's model.
