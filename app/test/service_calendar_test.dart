import 'package:flutter_test/flutter_test.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/services/journey_engine.dart';

void main() {
  test(
    'calendar filtering distinguishes market days and expires temporary service',
    () {
      final network = Network({
        'source': 'official_timetable',
        'hasServiceCalendars': true,
        'stops': [
          {'id': 'outside'},
          {'id': 'o'},
          {'id': 'd'},
        ],
        'footpaths': [],
        'routes': [
          {
            'id': 'market',
            'stops': ['o', 'd'],
            'offsets': [0, 10],
            'departures': [420],
            'departuresByDay': {
              'weekday': [420],
            },
            'serviceCalendar': {
              'onlyMonthDays': [3, 8, 13, 18, 23, 28],
            },
            'delaySamples': [0],
          },
          {
            'id': 'joint',
            'stops': ['outside', 'o', 'd'],
            'offsets': [0, 10, 20],
            'departures': [500],
            'departuresByDay': {
              'weekday': [500],
            },
            'passengerStops': ['o', 'd'],
            'serviceCalendar': {
              'startDate': '2026-10-06',
              'endDate': '2026-11-22',
            },
            'delaySamples': [0],
          },
        ],
      });
      List<Json> search(String origin, String date) =>
          JourneyEngine(network).search(
            SearchQuery(
              origin: origin,
              destination: 'd',
              departure: 400,
              serviceDate: date,
              maxTransfers: 0,
              samples: 20,
            ),
          );
      expect(search('o', '2026-11-13').first['arrival'], 430);
      expect(search('o', '2026-11-11').first['arrival'], 520);
      expect(search('o', '2026-11-24'), isEmpty);
      expect(search('outside', '2026-11-11'), isEmpty);
      expect(search('o', '2026-11-11').first['arrival'], 520);
      final request = const SearchQuery(
        origin: 'o',
        destination: 'd',
        serviceDate: '2026-11-13',
      ).withDelay(3).toJson();
      expect(request['service_date'], '2026-11-13');
    },
  );
}
