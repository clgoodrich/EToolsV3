import math
import numpy as np
import wellpathpy as wp
import ModuleAgnostic

"""
This module is a mathematical module meant for the generation of well depth data through the minimum curvature calculation methodology
Require data includes:
    - a list of measured depths (the measured depths list, the inclinations list, and the azimuth list must all be the same length)
    - a list of inclinations
    - a list of azimuths
    - a grid convergence angle (the angle between a grid north reference or a true north reference)
    - an actual north reference on the survey itself, given as T for true north, M for magnetic north, or G for grid north
    - a platform north reference, referencing the survey data for the platform itself. This only matters if it is different from the actual north reference, in which case the grid convergence angle is used
    - a magnetic declination (given in degrees)
    - the target azimuth for the well path (given in degrees)

If no magnetic declination or convergence angle is found, input a 0 into that spot. It will assume that both the actual north reference and the platform north reference are the same.
If the platform reference is unknown, simply match the actual north reference.

A sample dataset might be as follows:
md_lst = [0.00, 100.00, 200.00, 300.00, 400.00, 500.00, 600.00, 700.00, 800.00, 900.00, 1000.00, 1100.00, 1200.00, 1300.00, 1400.00, 1500.00, 1600.00, 1700.00, 1800.00, 1900.00, 2000.00, 2100.00, 2200.00, 2300.00, 2400.00, 2500.00, 2600.00, 2700.00, 2800.00, 2900.00, 3000.00, 3100.00, 3200.00,
          3300.00, 3400.00, 3500.00, 3600.00, 3700.00, 3800.00, 3900.00, 4000.00, 4100.00, 4200.00, 4300.00, 4400.00, 4500.00, 4600.00, 4700.00, 4800.00, 4900.00, 5000.00, 5100.00, 5200.00, 5300.00, 5400.00, 5500.00, 5600.00, 5700.00, 5800.00, 5900.00, 6000.00, 6100.00, 6200.00, 6300.00, 6400.00,
          6500.00, 6600.00, 6700.00, 6800.00, 6900.00, 7000.00, 7100.00, 7200.00, 7300.00, 7400.00, 7500.00, 7600.00, 7700.00, 7800.00, 7900.00, 8000.00, 8100.00, 8200.00, 8300.00, 8400.00, 8500.00, 8600.00, 8700.00, 8800.00, 8900.00, 9000.00, 9100.00, 9200.00, 9300.00, 9400.00, 9500.00, 9600.00,
          9700.00, 9800.00, 9900.00, 10000.00, 10100.00, 10200.00, 10300.00, 10400.00, 10500.00, 10600.00, 10700.00, 10800.00, 10900.00, 11000.00, 11100.00, 11200.00, 11300.00, 11400.00, 11500.00, 11600.00, 11700.00, 11800.00, 11900.00, 12000.00, 12100.00, 12200.00, 12300.00, 12400.00, 12500.00,
          12600.00, 12700.00, 12800.00, 12900.00, 13000.00, 13100.00, 13200.00, 13300.00, 13400.00, 13500.00, 13600.00, 13700.00, 13800.00, 13900.00, 14000.00, 14100.00, 14200.00, 14300.00, 14400.00, 14500.00, 14600.00, 14700.00, 14800.00, 14900.00, 15000.00, 15100.00, 15200.00, 15300.00, 15400.00,
          15500.00, 15600.00, 15700.00, 15800.00, 15900.00, 16000.00, 16100.00, 16200.00, 16300.00, 16400.00, 16500.00, 16600.00, 16700.00, 16800.00, 16900.00, 17000.00, 17100.00, 17200.00, 17300.00, 17400.00, 17500.00, 17600.00, 17700.00, 17800.00, 17833.28]

inc_lst = [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 2.00, 4.00, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56,
           5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 5.56, 4.63, 6.15, 14.70, 23.58, 32.53, 41.50, 50.47, 59.46, 68.44, 77.43, 86.42, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70,
           87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70,
           87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70, 87.70,
           87.70, 87.70, 87.70, 87.70, 87.70]

azi_lst = [0.00, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64,
           211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64, 211.64,
           219.14, 331.63, 348.72, 353.24, 355.37, 356.65, 357.55, 358.24, 358.81, 359.31, 359.78, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85,
           359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85,
           359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85, 359.85]

convergence_angle = 0.9564
north_reference = 'T'
platform_reference = 'T'
magnetic_declination = 10.754
target_azimuth = 357.862

Sample method calls:
minimum_curvature_list = mainCalculation(md_lst, inc_lst, azi_lst, convergence_angle, north_reference, platform_reference, magnetic_declination, target_azimuth)

Example of each method:
md_1, md_2 = 1000, 1100
inclination_1, inclination_2 = 89, 90
azi_1, azi_2 = 170, 199
prev_tvd, prevNS_offset, prevEW_offset = 800, 100, 100

bearing
170 = bearing(170, 0.9564, 'T', 'T', 10.754)

doglegAngle
29.01 = dogLegAngle(89, 90, 170, 199)

f_factor
1.0219 = fFactor(29.01)

tvd
800.89 = tvd(1000, 1100, 89, 90, 1.0219, 800)

offsetNS
1.3743 = offsetNS(f, 1000, 1100, 170, 199, 89, 90, 100)

offsetEW
92.23 = offsetEW(f, 1000, 1100, 170, 199, 89, 90, 100)

bhlDeparture
92.24 = bhlDeparture(92.23, 1.3743)

bhlDirection
0.85 = bhlDirection(92.23, 1.3743)

deltaNS
-98.62235997073056 = deltaNS(1000, 1100, 1.0219, 170, 199, 89, 90)

deltaEW
-7.76370254699085 = deltaEW(1000, 1100, 1.0219, 170, 199, 89, 90)

courseLength
598.9274732490146 = courseLength(-98.62235997073056, -7.76370254699085, 500)

verticalSection
2.07 = verticalSection(357.862, 1.3743, 92.23)
"""


def mainCalculation(md_lst, inc_lst, azi_lst, convergence_angle, north_reference, platform_reference, magnetic_declination, target_azimuth):
    # bearing_lst = [bearing(float(azi_lst[i]), float(convergence_angle), north_reference, platform_reference, float(magnetic_declination)) for i in range(len(md_lst))]
    if north_reference.upper() == 'G':
        bearing_lst = [bearing(float(azi_lst[i]), float(convergence_angle), north_reference, platform_reference, float(magnetic_declination)) for i in range(len(md_lst))]
    else:
        bearing_lst = azi_lst
    dogLeg_lst, fFactor_lst, bhl_dep_lst, bhl_dir_lst, delta_ns_lst, delta_ew_lst, course_length_lst, vert_sec_lst = [0], [0], [0], [0], [0], [0], [0], [0]
    offsetNS_lst, offsetEW_lst, tvd_lst = [0], [0], [0]
    true_md, true_inc, true_azi = [], [], []
    used_md = []
    all_outputs = list(zip(md_lst,inc_lst,azi_lst))
    all_outputs = sorted(all_outputs, key=lambda x: x[0])
    all_outputs = ModuleAgnostic.removeDupesListOfLists(all_outputs)
    md_lst, inc_lst, azi_lst = [i[0] for i in all_outputs], [i[1] for i in all_outputs], [i[2] for i in all_outputs]

    for i in range(len(md_lst)):
        if md_lst[i] not in used_md:
            true_md.append(md_lst[i] * 0.3048)
            true_inc.append(inc_lst[i])
            true_azi.append(bearing_lst[i])
            # true_azi.append(azi_lst[i])
            used_md.append(md_lst[i] * 0.3048)
        else:
            pass

    md_lst, inc_lst, bearing_lst = true_md, true_inc, true_azi
    md_lst = [i / 0.3048 for i in md_lst]
    dev = wp.deviation(
        md=md_lst,
        inc=inc_lst,
        azi=bearing_lst)
    pos = dev.minimum_curvature(course_length=30)
    # md_lst = [i/0.3048 for i in md_lst]
    tvd_lst = pos.depth
    offsetNS_lst = pos.northing
    offsetEW_lst = pos.easting
    # for i in range(len(md_lst)):
    #     print(md_lst[i], inc_lst[i], azi_lst[i], tvd_lst[i], offsetNS_lst[i]/0.3048, offsetEW_lst[i]/0.3048)
    # ModuleAgnostic.printLine(offsetNS_lst)
    # for i in range(1, len(bearing_lst)):
    # ModuleAgnostic.printLine(offsetNS_lst)
    for i in range(1, len(bearing_lst)):
        dogLeg_lst.append(dogLegAngle(inc_lst[i - 1], inc_lst[i], bearing_lst[i - 1], bearing_lst[i]))
        fFactor_lst.append(fFactor(dogLeg_lst[i]))
        # tvd_lst.append(tvd(md_lst[i - 1], md_lst[i], inc_lst[i - 1], inc_lst[i], fFactor_lst[i], tvd_lst[i - 1]))
        # offsetNS_lst.append(offsetNS(fFactor_lst[i], md_lst[i - 1], md_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i], offsetNS_lst[i - 1]))
        # offsetEW_lst.append(offsetEW(fFactor_lst[i], md_lst[i - 1], md_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i], offsetEW_lst[i - 1]))
        bhl_dep_lst.append(bhlDeparture(offsetNS_lst[i], offsetEW_lst[i]))
        bhl_dir_lst.append(bhl_Direction(float(offsetNS_lst[i]), float(offsetEW_lst[i])))
        delta_ns_lst.append(deltaNS(md_lst[i - 1], md_lst[i], fFactor_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i]))
        delta_ew_lst.append(deltaEW(md_lst[i - 1], md_lst[i], fFactor_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i]))
        course_length_lst.append(courseLength(delta_ns_lst[i], delta_ew_lst[i], course_length_lst[i - 1]))

    for i in range(1, len(bearing_lst)):
        vert_sec_lst.append(verticalSection(target_azimuth, offsetNS_lst[i], offsetEW_lst[i]))
    tvd_lst = [round(i, 3) for i in tvd_lst]
    dogLeg_lst = [round(i, 3) for i in dogLeg_lst]
    fFactor_lst = [round(i, 3) for i in fFactor_lst]
    offsetNS_lst = [round(i, 3) for i in offsetNS_lst]
    offsetEW_lst = [round(i, 3) for i in offsetEW_lst]
    bhl_dep_lst = [round(i, 3) for i in bhl_dep_lst]
    bhl_dir_lst = [round(i, 3) for i in bhl_dir_lst]
    vert_sec_lst = [round(i, 3) for i in vert_sec_lst]
    delta_ns_lst = [round(i, 3) for i in delta_ns_lst]
    delta_ew_lst = [round(i, 3) for i in delta_ew_lst]

    min_curv_lst = list(zip(md_lst, inc_lst, azi_lst, bearing_lst, dogLeg_lst, fFactor_lst, tvd_lst, offsetNS_lst, offsetEW_lst, bhl_dep_lst, bhl_dir_lst, vert_sec_lst, delta_ns_lst, delta_ew_lst))

    return [list(i) for i in min_curv_lst]

def calculateTargetAzimuth(ew_depart, ns_depart):
    angle = math.atan2(ew_depart, ns_depart)
    azimuth = math.degrees(angle) % 360
    return azimuth
    # if ew_depart < 0 and ns_depart < 0:
    #     return 180 + math.degrees(math.atan(ew_depart[1] / ns_depart[0]))
    # elif ew_depart > 0 and ns_depart < 0:
    #     pass
    # elif ew_depart > 0 and ns_depart > 0:
    #     pass
    # elif ew_depart < 0 and ns_depart < 0:
    #     pass

def bearing(azi_value, convergence_angle, north_reference, platform_reference, magnetic_declination):
    if north_reference.lower() == "m":
        return azi_value + magnetic_declination - convergence_angle
    elif north_reference.lower() == "t" and platform_reference.lower() == "g":
        return azi_value - convergence_angle
    elif north_reference.lower() == "g" and platform_reference.lower() == "t":
        return azi_value + convergence_angle
    else:
        return azi_value

# def bearing(azi_value, convergence_angle, north_reference, platform_reference, magnetic_declination):
#     if magnetic_declination == 0 and convergence_angle == 0:
#         return azi_value
#     if north_reference.lower() == "m":
#         return azi_value + magnetic_declination - convergence_angle
#     elif north_reference.lower() == "t" and platform_reference.lower() == "t":
#         return azi_value
#     elif north_reference.lower() == "g" and platform_reference.lower() == "t":
#         return azi_value + convergence_angle
#     elif north_reference.lower() == "g" and platform_reference.lower() == "g":
#         return azi_value
#     elif north_reference.lower() == "t" and platform_reference.lower() == "g":
#         return azi_value - convergence_angle
#     else:
#         return azi_value



def dogLegAngle(inclination_1, inclination_2, bearing_1, bearing_2):
    rad_1 = math.radians(inclination_1)
    rad_2 = math.radians(inclination_2)
    rad_b = math.radians(bearing_2 - bearing_1)
    cos_d = math.cos(rad_1) * math.cos(rad_2) + math.sin(rad_1) * math.sin(rad_2) * math.cos(rad_b)
    dogLeg = math.acos(cos_d)
    return math.degrees(dogLeg) if inclination_1 != inclination_2 else 0

# def dogLegAngle(inclination_1, inclination_2, bearing_1, bearing_2):
#     if inclination_2 == inclination_1:
#         return 0
#     else:
#         dogLeg = math.acos(math.cos(inclination_1 * (math.pi / 180)) * math.cos(inclination_2 * (math.pi / 180)) + (
#                 math.sin(inclination_1 * (math.pi / 180)) * math.sin(inclination_2 * (math.pi / 180))) * math.cos(
#             (bearing_2 - bearing_1) * (math.pi / 180)))
#         return dogLeg * (180 / math.pi)


def fFactor(dogLeg_angle):
    if dogLeg_angle == 0:
        return 1
    else:
        return (2 / dogLeg_angle) * (180 / math.pi) * math.tan(dogLeg_angle * math.pi / 180 / 2)


def tvd(depth_1, depth_2, inclination_1, inclination_2, f_factor, prev_tvd):
    return prev_tvd + (f_factor * ((depth_2 - depth_1) / 2 * (math.cos(math.radians(inclination_1)) + math.cos(math.radians(inclination_2)))))


def offsetNS(f_factor, depth_1, depth_2, bearing_1, bearing_2, inclination_1, inclination_2, prev_offset):
    inclination_1_radians, inclination_2_radians = math.sin(math.radians(inclination_1)), math.sin(math.radians(inclination_2))
    bearing_1_radians, bearing_2_radians = math.cos(math.radians(bearing_1)), math.cos(math.radians(bearing_2))
    md_difference = (depth_2 - depth_1) / 2
    return prev_offset + f_factor * md_difference * (inclination_1_radians * bearing_1_radians + inclination_2_radians * bearing_2_radians)


def offsetEW(f_factor, depth_1, depth_2, bearing_1, bearing_2, inclination_1, inclination_2, prev_offset):
    inclination_1_radians, inclination_2_radians = math.sin(math.radians(inclination_1)), math.sin(math.radians(inclination_2))
    bearing_1_radians, bearing_2_radians = math.sin(math.radians(bearing_1)), math.sin(math.radians(bearing_2))
    md_difference = (depth_2 - depth_1) / 2
    return prev_offset + f_factor * md_difference * (inclination_1_radians * bearing_1_radians + inclination_2_radians * bearing_2_radians)


def bhlDeparture(ns_offset, ew_offset):
    return math.sqrt(ns_offset ** 2 + ew_offset ** 2)


def bhlDirection(ns_offset, ew_offset):
    if ns_offset == 0 and ew_offset == 0:
        return 0
    elif ns_offset >= 0 and ew_offset >= 0:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi)
    elif ns_offset < 0 and ew_offset >= 0:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 180
    elif ns_offset < 0 and ew_offset < 0:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 180
    else:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 360
    # if int(ns_offset) == 0 and int(ew_offset) == 0:
    #     return 0
    # elif int(ns_offset) > 0 and int(ew_offset) > 0:
    #     return math.atan(ew_offset / ns_offset) * (180 / math.pi)
    # elif int(ns_offset) < 0 and int(ew_offset) > 0:
    #     return 180 + math.atan(ew_offset / ns_offset) * (180 / math.pi)
    # elif int(ns_offset) < 0 and int(ew_offset) < 0:
    #     return 180 - math.atan(ew_offset / ns_offset) * (180 / math.pi)
    # elif int(ns_offset) == 0 and int(ew_offset) < 0:
    #     return 270
    # elif int(ns_offset) == 0 and int(ew_offset) > 0:
    #     return 90
    # else:
    #     return 360 - math.atan(ew_offset / ns_offset) * (180 / math.pi)

def bhl_Direction(ns_offset, ew_offset):
    if ns_offset == 0 and ew_offset == 0:
        return 0
    elif ns_offset >= 0 and ew_offset >= 0:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi)
    elif ns_offset < 0 and ew_offset >= 0:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 180
    elif ns_offset < 0 and ew_offset < 0:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 180
    else:
        return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 360

    # if ns_offset == 0 and ew_offset == 0:
    #     return 0
    # elif ns_offset >= 0 and ew_offset >= 0:
    #     return math.atan(ew_offset / ns_offset) * (180 / math.pi)
    # elif ns_offset < 0 and ew_offset >= 0:
    #     return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 180
    # elif ew_offset < 0 and ns_offset < 0:
    #     return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 180
    # else:
    #     return math.atan(ew_offset / ns_offset) * (180 / math.pi) + 360
    # IF(AND(I23 < 0, J23 < 0), ATAN(J23 / I23) * (180 / PI()) + 180, ATAN(J23 / I23) * (180 / PI()) + 360)))))

def deltaNS(depth_1, depth_2, f_factor, bearing_1, bearing_2, inclination_1, inclination_2):
    inc1_sin = math.sin(inclination_1 * math.pi / 180)
    inc2_sin = math.sin(inclination_2 * math.pi / 180)
    bearing1_cos = math.cos(bearing_1 * math.pi / 180)
    bearing2_cos = math.cos(bearing_2 * math.pi / 180)
    depth_diff = abs(depth_2 - depth_1)
    return f_factor * (depth_diff / 2) * (inc1_sin * bearing1_cos + inc2_sin * bearing2_cos)


def deltaEW(depth_1, depth_2, f_factor, bearing_1, bearing_2, inclination_1, inclination_2):
    inc1_sin = math.sin(inclination_1 * math.pi / 180)
    inc2_sin = math.sin(inclination_2 * math.pi / 180)
    bearing1_sin = math.sin(bearing_1 * math.pi / 180)
    bearing2_sin = math.sin(bearing_2 * math.pi / 180)
    depth_diff = abs(depth_2 - depth_1)
    return f_factor * (depth_diff / 2) * (inc1_sin * bearing1_sin + inc2_sin * bearing2_sin)


def courseLength(delta_NS, delta_EW, prev_offset):
    return math.sqrt(delta_NS ** 2 + delta_EW ** 2) + prev_offset


def verticalSection(target_azimuth, ns_offset, ew_offset):
    closure_distance = (ns_offset ** 2 + ew_offset ** 2) ** .5
    if ns_offset == 0:
        closure_azimuth = 0
    else:
        closure_azimuth = math.degrees(np.arctan(ew_offset / ns_offset))
    vertical_section = (closure_distance * (np.cos(math.radians(closure_azimuth - target_azimuth))))
    return abs(vertical_section)

def doglegSeverity(prev_tvd, current_tvd, dogleg_angle):
    if current_tvd == prev_tvd:
        return 0
    else:
        return (dogleg_angle * 100) / (current_tvd-prev_tvd)

def courseLen(deltaN, deltaE):
    return math.sqrt(deltaE ** 2 + deltaN ** 2)

def chartVS(vert_section):
    return vert_section

def chartTVD(tvd):
    return tvd*-1
