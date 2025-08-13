from file_helper import get_plss_sections_path
import sqlite3
import pandas as pd
import regex as re
pd.set_option('display.max_columns', None)
pd.options.mode.chained_assignment = None


def decimal_converter(side, deg, minutes, sec, dir_val):
    """
    Simplified version with clearer logic (mathematically equivalent to above).
    """
    deg, minutes, sec = float(deg), float(minutes), float(sec)
    dec_val_base = deg + minutes / 60 + sec / 3600
    side_lower = side.lower()

    # Base orientations for each side
    if 'west' in side_lower:
        base_azimuth = 90
    elif 'east' in side_lower:
        base_azimuth = 270
    elif 'north' in side_lower:
        if dir_val in [3, 2, 'SW', 'NE']:  # SW, NE
            base_azimuth = 90
        else:  # SE, NW
            base_azimuth = 270
    elif 'south' in side_lower:
        if dir_val in [4, 1, 'NW', 'SE']:  # NW, SE
            base_azimuth = 90
        else:  # NE, SW
            base_azimuth = 270
    else:
        return dec_val_base

    # Determine if we add or subtract the bearing
    if ((side_lower.startswith('west') and dir_val in [4, 1]) or
            (side_lower.startswith('east') and dir_val in [4, 1]) or
            (side_lower.startswith('north') and dir_val not in [3, 2]) or
            (side_lower.startswith('south') and dir_val in [4, 1])):
        return base_azimuth + dec_val_base
    else:
        return base_azimuth - dec_val_base


def convert_conc(sec, ts, ts_dir, rng, rng_dir, baseline):
    translations = {
        'rng': {'2': 'W', '1': 'E'},
        'township': {'2': 'S', '1': 'N'},
        'baseline': {'2': 'U', '1': 'S'},
        'alignment': {'1': 'SE', '2': 'NE', '3': 'SW', '4': 'NW'}
    }
    section = str(int(float(sec))).zfill(2)
    township = str(int(float(ts))).zfill(2)
    rng = str(int(float(rng))).zfill(2)

    # Handle direction codes (which might also be floats)
    ts_dir = str(ts_dir)
    rng_dir = str(rng_dir)
    baseline = str(baseline)

    # Translate direction codes
    ts_dir = translations.get('township', {}).get(ts_dir, ts_dir).upper()
    rng_dir = translations.get('rng', {}).get(rng_dir, rng_dir).upper()
    baseline = translations.get('baseline', {}).get(baseline, baseline).upper()

    return "".join([section, township, ts_dir, rng, rng_dir, baseline])


def transform_bearings(val, label):
    if label == 'township':
        return val[4]
    if label == 'range':
        return val[7]
    if label == 'baseline':
        return val[8]
    if label == 'bearing':
        val = str(val)
        if val == '1':
            return 'SE'
        elif val == '2':
            return 'NE'
        elif val == '3':
            return 'SW'
        else:
            return 'NW'


def transform_and_correct_side(side):
    side = side.lower()
    side = side.replace("-", "_")
    # side_val =  side[-1]
    side = side.replace(side[-1], f"_{side[-1]}")
    return side


def transform_string(s, v, all):
    part1 = s[:2]
    part2 = s[2:4] + s[4]
    part3 = s[5:7] + s[7]
    part4 = s[-1]

    return f"{part1} {part2} {part3} {part4} - {v}"


def setup_db():
    return sqlite3.connect(get_plss_sections_path())

def correct_north_ref(north_ref, vers):
    if 'AGRC' not in vers:
        return north_ref
    else:
        return 'G'
conn = setup_db()
query = "select * from SectionPlatDataAGRC"
output = pd.read_sql(query, conn).drop_duplicates(keep="first")
# output.sort_values(['Baseline', 'Township Direction', 'Range Direction', 'Township', 'Range', 'Section',
#                     'Version']).reset_index(drop=True)
# output['conc'] = output.apply(
#     lambda row: convert_conc(row['Section'], row['Township'], row['Township Direction'],
#                              row['Range'],
#                              row['Range Direction'], row['Baseline']), axis=1)
# output['label'] = output.apply(lambda x: transform_string(x['conc'], x['Version'], x[
#     ['Baseline', 'Township Direction', 'Range Direction', 'Township', 'Range', 'Section']]), axis=1)
# output = output.rename(
#     columns={
#         'Section': 'section',
#         'Township': 'township',
#         'Township Direction': 'township_bearing',
#         'Range': 'rng',
#         'Range Direction': 'rng_bearing',
#         'Baseline': 'baseline',
#         'Side': 'side',
#         'Length': 'length',
#         'Degrees': 'degrees',
#         'Minutes': 'minutes',
#         'Seconds': 'seconds',
#         'Alignment': 'bearing',
#         'North Reference': 'north_ref',
#         'Version': 'version'
#     }
# )
#
# output['township_bearing_str'] = output.apply(lambda x: transform_bearings(val=x['conc'], label='township'),
#                                               axis=1)
# output['rng_bearing_str'] = output.apply(lambda x: transform_bearings(val=x['conc'], label='range'), axis=1)
# output['baseline_str'] = output.apply(lambda x: transform_bearings(val=x['conc'], label='baseline'), axis=1)
# output['bearing_str'] = output.apply(lambda x: transform_bearings(val=x['bearing'], label='bearing'), axis=1)
# output.drop(columns=['new_code', 'index'], inplace=True)
# output['decimal_azimuth'] = output.apply(
#     lambda row: decimal_converter(row['side'], row['degrees'], row['minutes'], row['seconds'],
#                                   row['baseline_str']), axis=1)
output['north_ref'] = output.apply(lambda x: correct_north_ref(x['north_ref'], x['version']), axis=1)
new_order = ['section', 'township', 'township_bearing', 'township_bearing_str',
             'rng', 'rng_bearing', 'rng_bearing_str', 'baseline', 'baseline_str', 'side',
             'length', 'degrees', 'minutes', 'seconds', 'bearing', 'bearing_str', 'decimal_azimuth',
             'north_ref', 'version', 'conc',
             'label']

output = output[new_order]
output['side'] = output.apply(lambda x: transform_and_correct_side(x['side']), axis=1)
output = output.astype({"section": float, "township": float, "township_bearing": float, "rng": float,
                        "rng_bearing": float, "baseline": float, "length": float, "degrees": float,
                        "minutes": float, "seconds": float, "bearing": float, "decimal_azimuth": float})
output = output.astype({"section": int, "township": int, "township_bearing": int, "rng": int,
                        "rng_bearing": int, "baseline": int, "degrees": int,
                        "minutes": int, "bearing": int})
# output['side'] = output.apply(lambda x: re.sub(r'_+', '_', x), axis=1)
# # cleaned_string =
output['side'] = output['side'].str.replace(r'_+', '_', regex=True)

# output.to_sql('SectionPlatDataAGRC', conn, index=False, if_exists='replace')
