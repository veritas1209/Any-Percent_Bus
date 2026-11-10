"""Synthetic history generation. A sample day is never represented as a real observation."""
import random


def generate_history(network,days=21,seed=42):
    rng=random.Random(seed)
    records=[]
    for day in range(1,days+1):
        for route in network['routes']:
            for trip in route['departures']:
                delay=rng.choice(route['delaySamples'])
                for stop,offset in zip(route['stops'],route['offsets']):
                    records.append({'source':'simulated','sampleDay':day,'routeId':route['id'],
                                    'tripId':f"sim:{day}:{route['id']}:{trip}",'stopId':stop,
                                    'scheduledMinute':trip+offset,'arrivalMinute':trip+offset+delay,
                                    'delayMinutes':delay,'seed':seed})
    return records
