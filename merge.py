import pandas as pd
import re
import operator
from datetime import datetime
from math import isnan
import numpy as np

def get_original():
	epa_original = pd.read_csv(r'X:\EPA_MPG\epa_data.csv', encoding='utf8', dtype=unicode)
	vin_original = pd.read_csv(r'X:\EPA_MPG\vin_data_original.csv', encoding='utf8', dtype=unicode)

	# Get rid of the 'Results_0_' string in the column titles
	pattern = re.compile(u'Results_0_(.+)')
	vin_original.columns = [pattern.search(x).groups()[0] 
		if pattern.search(x) else x for x in vin_original.columns]

	# Define integer id based on error code from VIN database. 
	vin_original['error_id'] = vin_original.ErrorCode.apply(
		lambda x: re.match('([0-9]+).*', x).groups()[0])

	# Define columns on which the merge will be performed.
	epa_cols = [
		'make',
		'model',
		'year',
		'fuelType1',
		'drive',
		'transmission_type',
		'transmission_speeds',
		'cylinders',
		'displ',
		]
	vin_cols = [
		'Make',
		'Model',
		'ModelYear',
		'FuelTypePrimary',
		'DriveType',
		'TransmissionStyle', 
		'TransmissionSpeeds',
		'EngineCylinders',
		'DisplacementL',
		]

	# Get rid of undesirable columns.
	""" Previously vin_keep_cols included:
		'ModelYear', 'Series', 'FuelTypePrimary', 'Trim2', 'Doors', 'Make', 'Series2', 
		'BodyClass', 'DisplacementL', 'EngineCylinders', 'Trim', 'Model', 'FuelTypeSecondary', 
		'ErrorCode', 'VehicleType', 'Manufacturer', 'DriveType', 'TransmissionStyle', 'TransmissionSpeeds'
	"""
	vin_keep_cols = ['VIN', 'VehicleType', 'BodyClass', 'error_id', 'Series'] + vin_cols 
	vin_original.drop([x for x in vin_original.columns if x not in vin_keep_cols], axis=1, inplace=True)
	epa_keep_cols = ['trany', 'city08', 'city08U', 'comb08', 'comb08U', 'highway08', 'highway08U'] + epa_cols
	epa_original.drop([x for x in epa_original.columns if x not in epa_keep_cols], axis=1, inplace=True)

	# Rename the VIN dataframe columns to be the same as the EPA dataframe columns.
	vin_original = vin_original.rename(columns=dict(zip(vin_cols, epa_cols)))

	# Get rid of rows where certain info is missing.
	essential_cols = 'make, model, year'.split(', ')
	for col in essential_cols:
		vin_original = vin_original.loc[~vin_original[col].isnull()]

	# Replace missing values (nan) with u'-1'.
	vin_original, epa_original = [
		df.apply(lambda x: pd.Series.fillna(x, u'-1')) for df in (vin_original, epa_original)]

	# Make everything lower case and trim white spaces.
	vin_original, epa_original = [
		df.applymap(lambda s: s.lower().strip()) for df in (vin_original, epa_original)]

	# Get rid of undesirable vehicles.
	filter_out_strs = ['incomplete vehicle', 'trailer', 'motorcycle', 'bus', 'low speed vehicle (lsv)']
	vin_original = vin_original.loc[~vin_original['VehicleType'].isin(filter_out_strs)]
	vin_original = vin_original.loc[~vin_original['BodyClass'].str.contains('incomplete')]
	# Equivalent to: vin_original.loc[[not(x in filter_out_strs) for x in vin_original['VehicleType']]]
	vin_original, epa_original = [df.loc[~df.fuelType1.str.contains('(electric|flexible)')] 
		for df in (vin_original, epa_original)]
	vin_original, epa_original = [df.loc[~df.model.str.contains('(plug|hev|hybrid|bev|electric)')]
		for df in (vin_original, epa_original)]

	# Get rid of tranmission type in model for epa_original data. 
	epa_original['model'] = epa_original['model'].apply(
		lambda x: re.search('(.+) (.+)wd$', x).groups()[0] if re.search('(.+) (.+)wd$', x) else x)

	# Get rid of duplicates in fields (e.g. 'gasoline, gasoline', or 'audi, audi').
	def del_duplicate_in_str(s):
		def _del_duplicate_in_str(s):
			found = pattern.search(s)
			if found:
				s0, s1 = found.groups()
				if pattern.search(s0):
					return _del_duplicate_in_str(s0)
				elif s0 == s1:
					return s0
			return s

		if not isinstance(s, unicode):
			return s
		pattern = re.compile('(.*), (.*)')
		return _del_duplicate_in_str(s)	
	vin_original = vin_original.applymap(del_duplicate_in_str)

	# Split rows that contain '/' into several rows. 
	epa_original['model_mod'] = epa_original['model']
	vin_original['model_mod'] = vin_original['model']
	def split_row(s, separator):
		pattern = re.compile('(.*?)(?=\S*{}\S*?)(\S*)(.*)'.format(separator))
		if pattern.match(s):
			groups = pattern.match(s).groups()
			return map(''.join, [[groups[0], x, groups[2]] for x in re.split(separator, groups[1])])
		else:
			return [s]
	vin_expanded, epa_expanded = [
		pd.concat(
			[pd.Series(np.append(row[[col for col in df.columns if col != 'model_mod']].values, [x]))
				for _, row in df.iterrows() 
				for x in split_row(row['model_mod'], '\/|,')],
			axis=1).transpose() for df in vin_original, epa_original]
	vin_expanded.columns, epa_expanded.columns = vin_original.columns, epa_original.columns
	vin_original, epa_original = vin_expanded, epa_expanded

	## Add IDs
	vin_original['VIN_ID'] = range(1, len(vin_original) + 1)
	epa_original['EPA_ID'] = range(1, len(epa_original) + 1)

	# Reset index.
	vin_original = vin_original.reset_index(drop=True)
	epa_original = epa_original.reset_index(drop=True)

	return epa_original, vin_original

def merge_with_erg(vin):
	# Merge with the ERG database.
	erg = pd.read_csv('X:\EPA_MPG\ERG_output.csv', header=None, dtype=unicode)
	erg.columns = ['VIN', 'counts']
	erg = erg[erg['counts'] != '.']
	erg['counts'] = erg['counts'].astype(int)
	erg = erg.loc[erg['counts'] > 10]
	erg['VIN'] = erg['VIN'].apply(str.lower)
	return pd.merge(vin, erg, how='inner')

def modify_df(vin, epa):
	# Change the namings of certain fields. 
	## Define mapping.
	mapping = {
		'vin': {
			'fuelType1':	{
				'compressed natural gas (cng)':									'natural gas',
				'liquefied petroleum gas (propane or lpg)':						'natural gas',
				'liquefied natural gas (lng)':									'natural gas',
				},
			'drive':	{
				'4x2':																'two',
				'6x6':																'all',
				'6x2':																'two',
				'8x2':																'two',
				'rwd/ rear wheel drive':											'two',
				'fwd/front wheel drive':											'two',
				'4x2, rwd/ rear wheel drive':										'two',
				'4x2, fwd/front wheel drive':										'two',
				'rwd/ rear wheel drive, 4x2':										'two',
				'fwd/front wheel drive, 4x2':										'two',
				'4wd/4-wheel drive/4x4':											'all',
				'awd/all wheel drive':												'all',
				},
			'transmission_type':	{
				'manual/standard': 												'manu',
				'automated manual transmission (amt)': 							'manu',
				'manual/standard, manual/standard': 							'manu',
				'dual-clutch transmission (dct)': 								'manu',
				'continuously variable transmission (cvt)': 					'auto',
				'automatic': 													'auto',
				'automatic, continuously variable transmission (cvt)': 			'auto',
				}
			},
		'epa': {
			'fuelType1':	{
				'regular gasoline':			'gasoline',
				'premium gasoline':			'gasoline',
				'midgrade gasoline':		'gasoline',
				},
			'drive':	{
				'rear-wheel drive':				'two',
				'front-wheel drive':			'two',
				'2-wheel drive':				'two',
				'all-wheel drive':				'all',
				'4-wheel drive':				'all',
				'4-wheel or all-wheel drive':	'all',
				'part-time 4-wheel drive':		'all',
				},
			}
		}
	## Modify fuel type, drive type for epa and vin, and transmission type for vin. 
	for (df, df_name) in ((epa, 'epa'), (vin, 'vin')):
		for item in mapping[df_name]:
			print(df_name, item)
			df[item + '_mod'] = df[item].replace(mapping[df_name][item])

	# Modify transmission information
	## In VIN DB: turn transmission speeds into integers then strings.
	def try_int_unicode(a):
		try:
			return unicode(int(a))
		except:
			return unicode(a)
	vin['transmission_speeds_mod'] = vin['transmission_speeds'].apply(try_int_unicode)
	## In EPA DB: transform info in EPA database to get trammission speeds and types.
	## Transmission speeds.
	def get_transmission_speeds(s):
		try:
			return re.search(r'\d+', s).group()
		except:
			return None
	## Transmission type.
	def get_transmission_type(s):
		if isinstance(s, unicode):
			if re.search(r'auto', s):
				return "auto"
			else:
				return "manu"
	## Apply to epa.
	epa['transmission_speeds_mod'] = epa['transmission_speeds'] = epa.trany.apply(get_transmission_speeds)
	epa['transmission_type_mod'] = epa['transmission_type'] = epa.trany.apply(get_transmission_type)

	# Round displacement in both databases.
	def convert_displacement(s):
		try:
			return round(float(s), 1)
		except:
			return None
	for df in (epa, vin):
		df['displ_mod'] = df['displ'].apply(convert_displacement)

	# Update -1 to default values.
	for df in (epa, vin):
		df['fuelType1_mod'] = df['fuelType1_mod'].replace({'-1': 'gasoline'}) 
		df['drive_mod'] = df['drive_mod'].replace({'-1': 'two'}) 
	epa['cylinders'] = epa['cylinders'].fillna(-1).astype(int).astype(unicode)
	vin['cylinders'] = vin['cylinders'].astype(unicode)

	# Change type of mpg values to be floats. 
	mpg_list = 'highway08, highway08U, comb08, comb08U, city08, city08U'.split(', ')
	epa[mpg_list] = epa[mpg_list].astype(float)

	# Modify model names. 
	## Mazda.
	def delete_mazda(s):
		match = re.match('mazda(.*)', s)
		if match:
			return match.groups()[0]
		else:
			return s
	vin.ix[vin['make'] == 'mazda', 'model_mod'] = \
		vin.ix[vin['make'] == 'mazda', 'model_mod'].apply(delete_mazda)
	## John Cooper Works. 
	pattern = re.compile('john cooper works(.*)')
	epa['model_mod'] = epa['model_mod'].apply(
		lambda x: 'jcw'+pattern.match(x).groups()[0] if(pattern.match(x)) else x)
	## Keep only first word of the model. 
	for df in (epa, vin):
		df['model_mod'] = df['model_mod'].apply(lambda x: x.split(' ')[0])
	## Apply pattern modifications. 
	pattern_list = [
		re.compile('(.*) [0-9]\.[0-9]$'), 	# Drop the second part if it's like 'model 3.2'
		re.compile('.*[0-9]\.[0-9](.+)')]	# Drop the first part if it's like '3.2cl'
	for pattern in pattern_list:
		epa['model_mod'] = epa['model_mod'].apply(
			lambda x: pattern.match(x).groups()[0] if(pattern.match(x)) else x)
	## Get rid of spaces and dashes. 
	def try_no_sep(s):
		try:
			return s.replace(' ', '').replace('-', '')
		except:
			return s
	for df in (epa, vin):
		df['model_mod'] = df['model_mod'].apply(try_no_sep)

	# For certain makes, only keep the string before the number. 
	# pattern = re.compile(r'(\D+)(\d+)')

	return vin, epa

def merge(vin, epa):
	# Perform the merge.
	## Merge. 
	mod_cols = [
		'model',
		'fuelType1',
		'drive',
		'transmission_speeds',
		'transmission_type',
		'displ',
		]
	append_to_list = lambda l, s: map(''.join, zip(l, [s] * len(l)))
	mod_cols_mod = append_to_list(mod_cols, '_mod')

	# # Clean up columns. 
	# vin.drop([x for x in vin.columns if x not in mod_cols_mod + epa_cols + ['VIN_ID', 'VIN', 'counts']], 
	# 	axis=1, inplace=True)

	# on_cols = [x for x in epa_cols + mod_cols_mod if x not in mod_cols]
	on_cols = [
		'make',
		'model_mod',
		'year',
		'fuelType1_mod',
		'drive_mod',
		'displ_mod',
		'cylinders',
		'transmission_speeds_mod',
		'transmission_type_mod',
		]

	matched_vins = pd.DataFrame()

	for _ in range(5):
		on_cols = on_cols[:-1]
		remaining_vins = vin.iloc[[x for x in vin.index if x not in matched_vins.index]].copy()
		inner_join = pd.merge(remaining_vins.reset_index(), epa, how='inner', on=on_cols).set_index('index')
		matched_vins = pd.concat([inner_join, matched_vins])

	return matched_vins

# Get original databases, and make modifications to them that are not subject to debate...
epa_original, vin_original = get_original()
# Export. 
# vin_original.to_csv('vin_data_processed.csv', encoding='utf8')

# Create a copy of the VIN and EPA databases.
epa = epa_original.copy()
vin = vin_original.copy()

# Merge the VIN db with the ERG db.
vin = merge_with_erg(vin)
# Export.
# vin.sort_values(['error_id', 'counts']).to_csv('errors.csv', encoding='utf8')

# Modify info in VIN and EPA db that might be less obvious...
vin, epa = modify_df(vin, epa)

# Merge VIN and EPA db. 
matched_vins = merge(vin, epa)

# Drop all columns which names match `pattern`.
def drop_pattern(df, pattern):
	return df.drop([x for x in df.columns if pattern.match(x)], axis=1)

# Rename columns with the first group that matches `pattern`. 
def rename_pattern(df, pattern):
	return df.rename(columns=
		dict(zip(df.columns, [pattern.match(x).groups()[0] for x in df.columns])))

pattern = re.compile(r'.*_[x, y]')
matched_vins_simple = drop_pattern(matched_vins, pattern)
matched_vins_no_dupes = matched_vins_simple.drop_duplicates(subset='VIN')
print('Merge fraction weighted: {:.2%}'.format(float(matched_vins_no_dupes['counts'].sum())/vin['counts'].sum()))

# Duplicates characterization.
## Create the ranges of values for each VIN. 
matched_vins_ranges = matched_vins_simple.groupby('VIN')
matched_vins_ranges['highway08', 'comb08', 'city08'].describe(percentiles=[]).unstack().reset_index()
## Max number of duplicates:
max(map(len, matched_vins_ranges.groups.values()))

vins_matched = matched_vins_no_dupes.VIN_ID
epas_matched = matched_vins_no_dupes.EPA_ID

# not_matched_vins = vin.loc[[not(x in vins_matched) for x in vin.VIN_ID]]
# not_matched_epas = epa.loc[[not(x in epas_matched) for x in epa.EPA_ID]]

not_matched_vins = vin.loc[~vin.VIN_ID.isin(vins_matched)]
not_matched_epas = epa.loc[~epa.EPA_ID.isin(epas_matched)]

not_matched = pd.concat([not_matched_epas, not_matched_vins])
not_matched[['make',
	'model_mod',
	'model',
	'year',
	'fuelType1_mod',
	'drive_mod',
	'displ_mod',
	'cylinders',
	'transmission_speeds_mod',
	'transmission_type_mod',
	'EPA_ID',
	'VIN_ID',
	'VIN',
	'counts',
	'BodyClass',
	'VehicleType',
	'Series'
		]].to_csv('not_matched.csv', encoding='utf8')

matched_all_vins = drop_pattern(pd.merge(vin, matched_vins_no_dupes, how='left', on='VIN_ID'), re.compile(r'.*_y'))
matched_all_vins.to_csv('matched_vins.csv')

outer_join = pd.merge(matched_all_vins, epa, how='outer', on='EPA_ID')
outer_join = outer_join[sorted(outer_join.columns)]
outer_join.to_csv('outer_join.csv')

found = left_join_1['counts'][[not(x) for x in left_join_1['EPA_ID'].isnull()]].sum()
print('Merge fraction weighted: {:.2%}'.format(found/vin['counts'].sum()))

other_cols = list(set(inner_join_1.columns) - set(on_cols))
ord_dict = dict(zip(on_cols, range(len(on_cols))) + zip(other_cols, [len(on_cols)]*len(other_cols)))
inner_join_1 = inner_join_1[sorted(inner_join_1.columns, key= lambda x: ord_dict[x])]


matched_vins.loc[matched_vins['VIN_ID'] == 81191].to_csv('duplicate_example.csv')

# Export.
## Define columns to output.
mod_cols_sub = [x for x in mod_cols  if x not in ['transmission_speeds', 'transmission_type',]]
out_cols = on_cols + append_to_list(mod_cols_sub, '_x') \
	+ append_to_list(mod_cols_sub, '_y') + ['VIN_ID', 'EPA_ID', 'counts']
## Push to database. 
conn = sqlite3.connect('X:\EPA_MPG\VIN_EPA_DB2.db')
inner_join[out_cols].to_sql(
	name='model_no_mod', con=conn, flavor='sqlite', if_exists='replace', index=False)
## To .csv file.
inner_join.to_csv(
	'outer_join_{}_{}.csv'.format(
		datetime.now().date().isoformat(), datetime.now().strftime("%H-%M-%S")), 
	encoding='utf8')
outer_join[out_cols].to_csv(
	'outer_join_{}_{}.csv'.format(
		datetime.now().date().isoformat(), datetime.now().strftime("%H-%M-%S")), 
	encoding='utf8')




# Find what's not matching. 
vin_sub = pd.DataFrame(vin[on_cols].groupby(
						on_cols).groups.keys(), columns=on_cols)
epa_sub = pd.DataFrame(epa[on_cols].groupby(
						on_cols).groups.keys(), columns=on_cols)
## Add IDs
vin_sub['VIN_ID'] = range(1, len(vin_sub) + 1)
epa_sub['EPA_ID'] = range(1, len(epa_sub) + 1)
pd.merge(vin_sub, epa_sub, how='outer', on=on_cols).to_csv(
	'model_merge_sub_{}_{}.csv'.format(
		datetime.now().date().isoformat(), datetime.now().strftime("%H-%M-%S")), 
	encoding='utf8')


