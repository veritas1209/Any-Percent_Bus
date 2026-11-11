"""Apply reviewed source supplements while preserving the original official snapshot."""


def apply_supplements(network, supplements):
    routes = {r['id']:r for r in network['routes']}
    stops = {s['id']:s for s in network['stops']}
    changed = supplements.get('stops',{})
    assert changed.keys() <= stops.keys()
    for identity,patch in changed.items():
        stops[identity].update(patch)
    if changed:
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
        from app.walking import default_graph,distance
        graph=default_graph()
        paths={(f['from'],f['to']):f for f in network['footpaths'] if f['from'] not in changed and f['to'] not in changed}
        for identity in changed:
            stop=stops[identity]
            point=stop['lat'],stop['lon']
            neighbors=[s for s in stops.values() if s['id']!=identity and distance(point,(s['lat'],s['lon']))<=250]
            for other,meters,line in graph.connections(point,neighbors,250):
                for a,b,points in ((identity,other,line),(other,identity,list(reversed(line)))):
                    key=f'itswalk:{a}:{b}'
                    network['shapes'][key]=dict(points=points,meters=meters,source='osm_pedestrian_access')
                    paths[(a,b)]=dict(**{'from':a,'to':b},meters=meters,shape=key)
        network['footpaths']=list(paths.values())
    known = {k for r in routes.values() for k in r['shapeSegments']}
    assert supplements['shapes'].keys() <= known
    network['shapes'].update(supplements['shapes'])
    touched = {key.rsplit(':',1)[0] for key in supplements['shapes']}
    for identity, patch in supplements.get('routes',{}).items():
        assert identity in routes
        routes[identity].update(patch)
    for identity in touched:
        route = routes[identity]
        distances, offsets = [0.0], [0.0]
        for key in route['shapeSegments']:
            meters = network['shapes'][key]['meters']
            distances.append(round(distances[-1]+meters,1))
            offsets.append(round(offsets[-1]+meters/(22_000/60)+20/60,4))
        route.update(distanceOffsets=distances,offsets=offsets)
    for extra in supplements.get('extraRoutes',[]):
        route=dict(routes[extra['baseRoute']],id=extra['id'],**extra['patch'])
        routes[extra['id']]=route
    for route in routes.values():
        if any(route['departuresByDay'].values()):
            route['scheduleSource'] = 'official_terminal_estimated_stops'
        route['departures'] = route['departuresByDay']['weekday']
    network['routes']=list(routes.values())
    network['routeFamilies']=len(routes)
    network['version'] = network['version'].split('+')[0]+'+sources3'
    network['geometryVersion'] = 'ulsan-multi-source-3'
    network['geometryAttribution'] = '울산교통관리센터 / NAVER 지도 / © OpenStreetMap contributors'
    network['supplementalSources'] = supplements['sources']
    network['hasServiceCalendars'] = any(route.get('serviceCalendar') for route in routes.values())
    return network
