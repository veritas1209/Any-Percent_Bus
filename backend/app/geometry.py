"""Interpolate a vehicle on an attached road shape, never across a missing span."""
import math


def distance(a,b):
    return math.hypot((a[0]-b[0])*111000,(a[1]-b[1])*91000)


def point_along(points,fraction):
    if len(points)<2:return None
    spans=[distance(a,b) for a,b in zip(points,points[1:])]
    remaining=sum(spans)*max(0,min(1,fraction))
    for i,span in enumerate(spans):
        if remaining<=span or i==len(spans)-1:
            f=0 if span==0 else max(0,min(1,remaining/span))
            return [points[i][0]+(points[i+1][0]-points[i][0])*f,points[i][1]+(points[i+1][1]-points[i][1])*f]
        remaining-=span
    return points[-1]
